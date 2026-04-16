import os
import json
import random
import sqlite3
import hashlib
import urllib.parse
import traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import requests
import anthropic
from google import genai
from google.genai import types
from flask import Flask, render_template, request, jsonify, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "zombie-history-project-secret-key-change-in-production")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
google_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

DATABASE = os.path.join(os.path.dirname(__file__), "conversations.db")

# Directory for generated images (Imagen returns bytes, not URLs)
GENERATED_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "static", "generated")
os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)

# In-memory cache for active conversations (fast access during chat)
conversations = {}

# Image cache to avoid regenerating the same images
image_cache = {}

# Pending image generation futures
pending_images = {}

# Pending opening message futures (pre-generated while user sees confirmation)
pending_openings = {}

# Thread pool for parallel API calls
executor = ThreadPoolExecutor(max_workers=4)


# ===== DATABASE =====
def get_db():
    """Get database connection for current request."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they don't exist."""
    db = sqlite3.connect(DATABASE)
    db.execute(
        """CREATE TABLE IF NOT EXISTS conversations (
        session_id TEXT PRIMARY KEY,
        figure_name TEXT NOT NULL,
        figure_era TEXT,
        figure_location TEXT,
        figure_description TEXT,
        figure_data TEXT,
        system_prompt TEXT NOT NULL,
        image_url TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES conversations(session_id)
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        username TEXT NOT NULL,
        password_hash TEXT,
        google_id TEXT UNIQUE,
        created_at TEXT NOT NULL
    )"""
    )
    # Add user_id column to conversations if it doesn't exist
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN user_id INTEGER REFERENCES users(id)")
    except sqlite3.OperationalError:
        pass  # Column already exists
    db.commit()
    db.close()


def save_conversation(session_id, figure, system_prompt, image_url, user_id=None):
    """Save a new conversation to the database."""
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute(
        """INSERT OR REPLACE INTO conversations
        (session_id, figure_name, figure_era, figure_location, figure_description,
         figure_data, system_prompt, image_url, created_at, updated_at, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            figure.get("name", "Unknown"),
            figure.get("era", ""),
            figure.get("location", ""),
            figure.get("description", ""),
            json.dumps(figure),
            system_prompt,
            image_url,
            now,
            now,
            user_id,
        ),
    )
    db.commit()


def save_message(session_id, role, content):
    """Save a single message to the database."""
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now),
    )
    db.execute(
        "UPDATE conversations SET updated_at = ? WHERE session_id = ?",
        (now, session_id),
    )
    db.commit()


def load_conversation(session_id):
    """Load a conversation and its messages from the database."""
    db = get_db()
    conv = db.execute(
        "SELECT * FROM conversations WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not conv:
        return None

    messages = db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()

    return {
        "system_prompt": conv["system_prompt"],
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "figure": json.loads(conv["figure_data"]),
        "image_url": conv["image_url"],
    }


def get_all_conversations(user_id=None):
    """Get past conversations for a specific user, most recent first."""
    db = get_db()
    if user_id:
        rows = db.execute(
            """SELECT session_id, figure_name, figure_era, figure_location,
            figure_description, image_url, created_at, updated_at,
            (SELECT COUNT(*) FROM messages WHERE messages.session_id = conversations.session_id) as message_count
            FROM conversations WHERE user_id = ? ORDER BY updated_at DESC""",
            (user_id,),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT session_id, figure_name, figure_era, figure_location,
            figure_description, image_url, created_at, updated_at,
            (SELECT COUNT(*) FROM messages WHERE messages.session_id = conversations.session_id) as message_count
            FROM conversations WHERE user_id IS NULL ORDER BY updated_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


# ===== PROMPTS =====
DISAMBIGUATE_PROMPT = """You are a historical research assistant. The user wants to speak with a historical figure or type of person.

Given their input, determine:
1. The full name (or description if not a specific person)
2. The era/time period (specific years or century)
3. The location/civilization they are associated with
4. A brief one-sentence description of who they are

If the person is ambiguous (e.g., "Caesar" could be multiple people), pick the MOST FAMOUS one but mention it.
If they describe a type of person (e.g., "a peasant in 14th century France"), flesh out a believable character with a name.

IMPORTANT: Generate an image description for a ZOMBIE portrait. Your prompt must follow this EXACT structure — the ORDER matters:

STEP 1 — THE LIVING PERSON (write this first, it's the foundation):
Describe what this person looked like ALIVE. This is the most important part. Be specific about:
  a) ETHNICITY AND FACE: Describe their actual ancestral features — face shape, nose shape, skin tone, hair type. Be precise and heritage-based:
     * Ptolemaic dynasty (Cleopatra etc.): Macedonian Greek — broad olive-skinned face, strong Greek nose, dark curly hair. NOT thin Western European features.
     * Native Egyptians: Brown to dark brown skin, broad nose, North African bone structure.
     * Sub-Saharan Africans: Deep dark brown skin, broad nose, full lips, Black African features.
     * South Asians: Brown skin, South Asian facial structure.
     * East Asians: East Asian features, warm-toned skin.
     * Aboriginal Australians: Very dark skin, broad nose, deep-set eyes, Aboriginal features.
     * Mesoamericans: Brown skin, indigenous American features.
     * Central Asian steppe peoples: East/Central Asian features, weathered.
     * Mediterranean/Southern European: Olive skin, dark hair, strong features.
     * Northern European: Fair skin, lighter hair.
     Do NOT default to Western European features for non-European people.
  b) BODY TYPE: Based on their class and lifestyle. Royalty was well-fed — soft, full-figured. Peasants were lean and wiry from hard labor and poor nutrition. Warriors were strong but scarred. Nobody looked like a modern gym body.
  c) CLOTHING: Accurate to their era and station, but now centuries old — faded, frayed, moth-eaten, dirt-stained.
  d) TEETH: Pre-sugar cultures (before 1600s): worn and chipped but not rotten. Post-sugar Europe (1600s+): missing and blackened teeth, especially the wealthy who could afford sugar.

STEP 2 — ADD ZOMBIE DECAY (write this second, layered on top):
Now add moderate undead decay ON TOP of the person you just described. Keep it simple — just say something like:
"Now undead — grayish-green tinge to the skin, gaunt and hollow, some patches of decay showing bone at the cheek and jaw, sunken dark eyes, withered hands. Enough face remaining to show expression and personality — a wry smirk or knowing look. Think Pirates of the Caribbean undead, not horror movie gore."
Do NOT micro-manage specific bones or anatomy. Let the image model handle the details naturally.

STEP 3 — MOOD AND FRAMING:
Dark atmospheric background, fog, dramatic side lighting. Portrait framing — head and upper torso. Cinematic and photorealistic.

Respond in this exact JSON format:
{
    "name": "Full Name or Character Name",
    "era": "Time period (e.g., '44 BC', '14th Century', '1520s')",
    "location": "Place/Civilization",
    "description": "One sentence about who they are",
    "birth_year": "Approximate birth year or 'Unknown'",
    "death_year": "Approximate death year or 'Unknown'",
    "confirmation_message": "A message to confirm with the user, e.g., 'So you wish to awaken Julius Caesar, the great dictator of Rome who fell to assassins' blades in 44 BC?'",
    "voice_gender": "male or female",
    "voice_region": "The person's ACTUAL cultural/linguistic origin. Be specific. Use one of: japanese, chinese, korean, mongolian, arabic, egyptian, greek, indian, persian, turkish, french, italian, spanish, german, scandinavian, british, irish, scottish, russian, african, mesoamerican, aboriginal-australian, caribbean, american. Pick the one that matches their native language and culture — NOT where they ruled, but where they or their ancestors were FROM. Cleopatra would be 'greek' (Macedonian descent). Genghis Khan would be 'mongolian'. Oda Nobunaga would be 'japanese'. A Mayan priest would be 'mesoamerican'. Ashoka would be 'indian'.",
    "image_prompt": "A cinematic zombie portrait description. Example: 'An undead middle-aged Roman man with decayed olive-tan Mediterranean skin showing grayish-green decomposition. Sunken dark eye sockets, visible cracks in his gaunt face revealing bone beneath. He wears a tattered, dirt-stained white toga. Dark atmospheric background with faint fog. Dramatic side lighting. Photorealistic cinematic horror portrait.'"
}"""

ZOMBIE_SYSTEM_PROMPT = """You are {name}, a zombie who has risen from the dead. You lived in {location} during {era}.

CRITICAL RULES:
- You are a ZOMBIE. You are physically decayed, rotting, and undead. You are aware of your grotesque physical state.
- You ONLY know about events, people, places, and things from YOUR lifetime and before. You know NOTHING about anything that happened after {death_year}.
- If asked about something after your death, you are confused. You have been DEAD. You have no knowledge of the modern world, modern technology, modern countries, or modern events.
- Speak in a style appropriate to your era and culture, but in English. Use grammar patterns, vocabulary, and speech mannerisms that would have been common in {location} during {era}.
- You are {description}

ZOMBIE PERSONALITY:
- Occasionally reference your physical state of decay in humorous ways. Maybe a finger falls off mid-sentence, or you apologize for the smell.
- You can be witty. Death has given you a dark sense of humor.
- Despite being a zombie, you have genuine memories and emotions about your life.

HISTORICAL ACCURACY:
- Stay true to the historical knowledge, culture, beliefs, and worldview of your time.
- Reference real places, customs, foods, religions, and events from your era.
- If you were a real historical figure, stay true to known facts about your life.
- If you are a fictional character from a real era, be consistent with what life was like for someone of your station.

RESPONSE LENGTH:
- Keep ALL responses SHORT — 2 to 4 sentences maximum. Be punchy and conversational.
- Your OPENING introduction should be especially brief: just your name, one zombie quip, and a question to the user. 3 sentences max. Example: "I am Cleopatra, last pharaoh of Egypt... though I smell considerably worse than I used to. *jaw creaks* Why have you disturbed my rest?"
- Do NOT dump your life story upfront. Let the user ask questions. Build the conversation naturally.
- Only go longer if the user asks a detailed question that genuinely requires a longer answer."""


SUGGESTION_FIGURES = [
    {"name": "Cleopatra", "era": "69-30 BC", "location": "Egypt", "tagline": "Last Pharaoh of Egypt"},
    {"name": "Genghis Khan", "era": "1162-1227", "location": "Mongolia", "tagline": "Founder of the Mongol Empire"},
    {"name": "Leonardo da Vinci", "era": "1452-1519", "location": "Italy", "tagline": "Renaissance Polymath"},
    {"name": "A Viking Warrior", "era": "9th Century", "location": "Scandinavia", "tagline": "Norse Raider and Explorer"},
    {"name": "Nefertiti", "era": "1370-1330 BC", "location": "Egypt", "tagline": "Queen of the Nile"},
    {"name": "Socrates", "era": "470-399 BC", "location": "Athens", "tagline": "Father of Western Philosophy"},
    {"name": "A Samurai", "era": "16th Century", "location": "Japan", "tagline": "Warrior of Feudal Japan"},
    {"name": "Marie Antoinette", "era": "1755-1793", "location": "France", "tagline": "Queen of France"},
    {"name": "A Mayan Priest", "era": "8th Century", "location": "Mesoamerica", "tagline": "Keeper of the Calendar"},
    {"name": "Spartacus", "era": "111-71 BC", "location": "Rome", "tagline": "Gladiator and Rebel"},
    {"name": "An Aboriginal Elder", "era": "Ancient Times", "location": "Australia", "tagline": "Keeper of the Dreamtime"},
    {"name": "Blackbeard", "era": "1680-1718", "location": "Caribbean", "tagline": "Terror of the Seas"},
    {"name": "A Medieval Peasant", "era": "14th Century", "location": "England", "tagline": "Survivor of the Black Death"},
    {"name": "Hatshepsut", "era": "1507-1458 BC", "location": "Egypt", "tagline": "Female Pharaoh"},
    {"name": "Attila the Hun", "era": "406-453", "location": "Central Asia", "tagline": "Scourge of God"},
    {"name": "A Roman Gladiator", "era": "1st Century", "location": "Rome", "tagline": "Fighter of the Colosseum"},
    {"name": "Ashoka the Great", "era": "304-232 BC", "location": "India", "tagline": "Emperor Who Chose Peace"},
    {"name": "Oda Nobunaga", "era": "1534-1582", "location": "Japan", "tagline": "The Great Unifier"},
    {"name": "Qin Shi Huang", "era": "259-210 BC", "location": "China", "tagline": "First Emperor of China"},
    {"name": "A Mughal Court Musician", "era": "16th Century", "location": "India", "tagline": "Artist of the Golden Age"},
]


# ===== IMAGE GENERATION =====
def get_image_url(prompt):
    """Generate image using Google Imagen 4 Fast."""
    try:
        # Check cache first
        cache_key = prompt.strip()[:100]
        if cache_key in image_cache:
            print(f"Image cache hit!")
            return image_cache[cache_key]

        styled_prompt = (
            f"{prompt}\n\n"
            f"Render this person as an undead zombie in the style of Pirates of the Caribbean — "
            f"moderate decay, creepy but with personality and dark humor. Not pure horror. "
            f"The ethnicity, body type, and clothing described above are the MOST important things to get right. "
            f"Zombie decay should be uniform across face, hands, and body. "
            f"Gaunt, withered, mottled grayish-green skin, some exposed bone. "
            f"Worn and tattered clothing. Dark foggy background, dramatic lighting. "
            f"Cinematic photorealistic portrait. No text in the image."
        )

        # Imagen has a prompt length limit — truncate if needed
        if len(styled_prompt) > 3000:
            styled_prompt = styled_prompt[:3000]
            print(f"Warning: prompt truncated to 3000 chars")

        print(f"Generating image, prompt length: {len(styled_prompt)}")

        response = google_client.models.generate_images(
            model="imagen-4.0-fast-generate-001",
            prompt=styled_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="3:4",
            ),
        )

        if response.generated_images:
            image_bytes = response.generated_images[0].image.image_bytes
            # Save to static/generated/ with a hash-based filename
            filename = hashlib.md5(prompt.encode()).hexdigest() + ".png"
            filepath = os.path.join(GENERATED_IMAGES_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(image_bytes)

            url = f"/static/generated/{filename}"
            image_cache[cache_key] = url
            print(f"Imagen 4 image saved: {filename}")
            return url
        else:
            print("Imagen 4 returned no images")
            return f"https://placehold.co/768x512/1a2618/4a7a3a?text=No+Image"

    except Exception as e:
        print(f"Image generation failed: {e}")
        traceback.print_exc()
        return f"https://placehold.co/768x512/1a2618/4a7a3a?text={urllib.parse.quote(prompt[:30])}"


# ===== AUTH ROUTES =====
@app.route("/api/auth/status", methods=["GET"])
def auth_status():
    """Check if user is logged in."""
    if "user_id" in session:
        db = get_db()
        user = db.execute("SELECT id, email, username FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if user:
            return jsonify({"logged_in": True, "user": {"id": user["id"], "email": user["email"], "username": user["username"]}})
    return jsonify({"logged_in": False})


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    """Register with email and password."""
    data = request.json
    email = (data.get("email") or "").strip().lower()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not email or not username or not password:
        return jsonify({"error": "Email, username, and password are required."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if len(username) < 2:
        return jsonify({"error": "Username must be at least 2 characters."}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return jsonify({"error": "An account with this email already exists. Try logging in."}), 400

    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO users (email, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (email, username, generate_password_hash(password), now),
    )
    db.commit()

    user = db.execute("SELECT id, email, username FROM users WHERE email = ?", (email,)).fetchone()
    session["user_id"] = user["id"]
    session.permanent = True

    return jsonify({"user": {"id": user["id"], "email": user["email"], "username": user["username"]}})


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """Login with email and password."""
    data = request.json
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not user["password_hash"] or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password."}), 401

    session["user_id"] = user["id"]
    session.permanent = True

    return jsonify({"user": {"id": user["id"], "email": user["email"], "username": user["username"]}})


@app.route("/api/auth/google", methods=["POST"])
def auth_google():
    """Authenticate with Google ID token."""
    data = request.json
    token = data.get("credential") or ""

    if not token:
        return jsonify({"error": "No credential provided."}), 400

    # Verify the Google ID token
    try:
        resp = requests.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={token}")
        if resp.status_code != 200:
            return jsonify({"error": "Invalid Google token."}), 401

        token_info = resp.json()
        google_id = token_info.get("sub")
        email = token_info.get("email", "").lower()
        name = token_info.get("name") or email.split("@")[0]

        if not google_id:
            return jsonify({"error": "Could not verify Google account."}), 401

        db = get_db()
        # Check if user exists by google_id or email
        user = db.execute("SELECT * FROM users WHERE google_id = ? OR email = ?", (google_id, email)).fetchone()

        if user:
            # Update google_id if they previously registered with email
            if not user["google_id"]:
                db.execute("UPDATE users SET google_id = ? WHERE id = ?", (google_id, user["id"]))
                db.commit()
            session["user_id"] = user["id"]
            return jsonify({"user": {"id": user["id"], "email": user["email"], "username": user["username"]}})
        else:
            # Create new user
            now = datetime.utcnow().isoformat()
            db.execute(
                "INSERT INTO users (email, username, google_id, created_at) VALUES (?, ?, ?, ?)",
                (email, name, google_id, now),
            )
            db.commit()
            user = db.execute("SELECT id, email, username FROM users WHERE google_id = ?", (google_id,)).fetchone()
            session["user_id"] = user["id"]
            session.permanent = True
            return jsonify({"user": {"id": user["id"], "email": user["email"], "username": user["username"]}})

    except Exception as e:
        print(f"Google auth error: {e}")
        traceback.print_exc()
        return jsonify({"error": "Google authentication failed."}), 500


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    """Log out."""
    session.pop("user_id", None)
    return jsonify({"status": "ok"})


# ===== ROUTES =====
@app.route("/sw.js")
def service_worker():
    """Serve service worker from root scope for PWA support."""
    return app.send_static_file("sw.js"), 200, {"Content-Type": "application/javascript", "Service-Worker-Allowed": "/"}


@app.route("/")
def index():
    user_id = session.get("user_id")
    has_history = False
    if user_id:
        has_history = len(get_all_conversations(user_id)) > 0
    shuffled = random.sample(SUGGESTION_FIGURES, len(SUGGESTION_FIGURES))
    google_client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    return render_template("index.html", suggestions=shuffled, has_history=has_history, google_client_id=google_client_id)


@app.route("/history")
def history_page():
    """Dedicated page for past conversations."""
    user_id = session.get("user_id")
    if not user_id:
        return render_template("history.html", conversations=[], not_logged_in=True)
    convs = get_all_conversations(user_id)
    return render_template("history.html", conversations=convs)


# Figures that must not be summoned as zombies
BLOCKED_FIGURES = [
    "jesus", "jesus christ", "jesus of nazareth", "christ", "yeshua",
    "muhammad", "mohammed", "mohammad", "prophet muhammad", "prophet mohammed",
]


@app.route("/api/identify", methods=["POST"])
def identify_figure():
    """Identify and disambiguate the historical figure."""
    data = request.json
    user_input = data.get("query", "")

    if not user_input:
        return jsonify({"error": "Please enter a name or description"}), 400

    # Check for blocked religious figures
    query_lower = user_input.lower().strip()
    for blocked in BLOCKED_FIGURES:
        if blocked in query_lower:
            return jsonify({"error": "Out of respect, some religious figures cannot be summoned as zombies. Please choose someone else."}), 400

    # Use Haiku for fast identification — it's great at structured JSON extraction
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        system=DISAMBIGUATE_PROMPT,
        messages=[{"role": "user", "content": user_input}],
    )

    try:
        result_text = response.content[0].text
        start = result_text.find("{")
        end = result_text.rfind("}") + 1
        if start != -1 and end > start:
            figure_data = json.loads(result_text[start:end])
        else:
            figure_data = json.loads(result_text)

        # Second check: block if the AI identified a blocked figure from an indirect query
        identified_name = figure_data.get("name", "").lower()
        for blocked in BLOCKED_FIGURES:
            if blocked in identified_name:
                return jsonify({"error": "Out of respect, some religious figures cannot be summoned as zombies. Please choose someone else."}), 400

        # Return identification immediately — image will be generated in parallel
        # Store the image prompt for later use
        figure_data["image_url"] = ""  # Placeholder — frontend will show loading state

        # Start image generation in background
        image_prompt = figure_data.get("image_prompt", "")
        future = executor.submit(get_image_url, image_prompt)

        # Store the future so we can retrieve the result
        figure_key = figure_data.get("name", "") + "_" + figure_data.get("era", "")
        pending_images[figure_key] = future

        figure_data["figure_key"] = figure_key

        # Pre-generate the opening message in background while user views confirmation
        def generate_opening(fig_data):
            system_prompt = ZOMBIE_SYSTEM_PROMPT.format(
                name=fig_data.get("name", "Unknown"),
                location=fig_data.get("location", "Unknown"),
                era=fig_data.get("era", "Unknown"),
                death_year=fig_data.get("death_year", "Unknown"),
                description=fig_data.get("description", "a person from history"),
            )
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": "You have just risen from your grave. Introduce yourself."}],
            )
            return {"system_prompt": system_prompt, "opening": resp.content[0].text}

        opening_future = executor.submit(generate_opening, figure_data)
        pending_openings[figure_key] = opening_future

        return jsonify(figure_data)
    except (json.JSONDecodeError, IndexError) as e:
        return jsonify({"error": f"Failed to identify figure: {str(e)}"}), 500


@app.route("/api/get_image", methods=["POST"])
def get_image():
    """Poll for a pending image generation result."""
    data = request.json
    figure_key = data.get("figure_key", "")

    if figure_key in pending_images:
        future = pending_images[figure_key]
        if future.done():
            url = future.result()
            del pending_images[figure_key]
            return jsonify({"status": "ready", "image_url": url})
        else:
            return jsonify({"status": "pending"})

    return jsonify({"status": "ready", "image_url": ""})


@app.route("/api/start_conversation", methods=["POST"])
def start_conversation():
    """Start a conversation with the identified zombie."""
    data = request.json
    figure = data.get("figure", {})
    figure_key = data.get("figure_key", "")

    session_id = os.urandom(16).hex()

    # Check if we pre-generated the opening message during identification
    if figure_key and figure_key in pending_openings:
        future = pending_openings[figure_key]
        result = future.result(timeout=30)  # Wait for it if still running
        system_prompt = result["system_prompt"]
        opening_message = result["opening"]
        del pending_openings[figure_key]
        print(f"Used pre-generated opening for {figure_key}")
    else:
        # Fallback: generate now
        system_prompt = ZOMBIE_SYSTEM_PROMPT.format(
            name=figure.get("name", "Unknown"),
            location=figure.get("location", "Unknown"),
            era=figure.get("era", "Unknown"),
            death_year=figure.get("death_year", "Unknown"),
            description=figure.get("description", "a person from history"),
        )

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": "You have just risen from your grave. Introduce yourself.",
                }
            ],
        )

        opening_message = response.content[0].text

    # Save to database
    image_url = figure.get("image_url", "")
    user_id = session.get("user_id")
    save_conversation(session_id, figure, system_prompt, image_url, user_id=user_id)
    save_message(session_id, "user", "You have just risen from your grave. Introduce yourself.")
    save_message(session_id, "assistant", opening_message)

    # Cache in memory for fast access
    conversations[session_id] = {
        "system_prompt": system_prompt,
        "messages": [
            {"role": "user", "content": "You have just risen from your grave. Introduce yourself."},
            {"role": "assistant", "content": opening_message},
        ],
        "figure": figure,
    }

    return jsonify(
        {"session_id": session_id, "message": opening_message, "figure": figure}
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    """Continue the conversation with the zombie."""
    data = request.json
    session_id = data.get("session_id", "")
    user_message = data.get("message", "")

    # Try memory cache first, then fall back to database
    if session_id not in conversations:
        conv_data = load_conversation(session_id)
        if conv_data:
            conversations[session_id] = conv_data
        else:
            return jsonify({"error": "Conversation not found. Please start over."}), 404

    conv = conversations[session_id]
    conv["messages"].append({"role": "user", "content": user_message})

    # Save user message to database
    save_message(session_id, "user", user_message)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=conv["system_prompt"],
        messages=conv["messages"],
    )

    assistant_message = response.content[0].text
    conv["messages"].append({"role": "assistant", "content": assistant_message})

    # Save assistant message to database
    save_message(session_id, "assistant", assistant_message)

    return jsonify({"message": assistant_message})


@app.route("/api/history", methods=["GET"])
def get_history():
    """Get all past conversations for the logged-in user."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify([])
    convs = get_all_conversations(user_id)
    return jsonify(convs)


@app.route("/api/resume/<session_id>", methods=["GET"])
def resume_conversation(session_id):
    """Resume a past conversation by loading it from the database."""
    conv_data = load_conversation(session_id)
    if not conv_data:
        return jsonify({"error": "Conversation not found."}), 404

    # Load into memory cache
    conversations[session_id] = conv_data

    # Build the chat messages (skip the initial "rise from grave" prompt)
    chat_messages = []
    for msg in conv_data["messages"]:
        if msg["role"] == "user" and msg["content"] == "You have just risen from your grave. Introduce yourself.":
            continue
        chat_messages.append(msg)

    figure = conv_data["figure"]
    figure["image_url"] = conv_data.get("image_url", "")

    return jsonify({
        "session_id": session_id,
        "figure": figure,
        "messages": chat_messages,
    })


@app.route("/api/end_conversation", methods=["POST"])
def end_conversation():
    """End the current conversation (just remove from memory cache, keep in DB)."""
    data = request.json
    session_id = data.get("session_id", "")

    if session_id in conversations:
        del conversations[session_id]

    return jsonify({"status": "ok"})


@app.route("/api/delete_conversation/<session_id>", methods=["DELETE"])
def delete_conversation(session_id):
    """Permanently delete a conversation from the database."""
    db = get_db()
    db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    db.commit()

    if session_id in conversations:
        del conversations[session_id]

    return jsonify({"status": "ok"})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=True, port=port)
