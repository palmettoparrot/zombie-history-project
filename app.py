import os
import re
import json
import random
import sqlite3
import hashlib
import urllib.parse
import traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import requests
import anthropic
from google import genai
from google.genai import types
from flask import Flask, render_template, request, jsonify, session, g, Response, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "zombie-history-project-secret-key-change-in-production")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RENDER", "") != ""  # HTTPS only on Render
app.config["SESSION_COOKIE_HTTPONLY"] = True   # No JS access to session cookie
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # Basic CSRF protection

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
google_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# ElevenLabs voice library — pre-made + custom community voices
ELEVENLABS_VOICES = {
    # --- Pre-made male voices ---
    "daniel":    "onwK4e9ZLuTAKqWW03F9",   # Authoritative British
    "adam":      "pNInz6obpgDQGcFmaJgB",   # Deep, resonant
    "arnold":    "VR6AewLTigWG4xSOukaG",   # Gruff, intense
    "callum":    "N2lVS1w4EtoT3dr4eOWO",   # Hoarse, weathered
    "brian":     "nPczCjzI2devNBz1zQrb",   # Narrator, commanding
    "antoni":    "ErXwobaYiN019PkySvjV",   # Warm, European
    "bill":      "pqHfZKP75CvOlQylNhV4",   # Deep American
    "chris":     "iP95p4xoKVk53GoZ742B",   # Casual, modern
    "charlie":   "IKne3meq5aSn9XLyUdCD",   # Natural, youthful
    "josh":      "TxGEqnHWrfWFTfGW9XjX",   # Deep, dramatic
    "sam":       "yoZ06aMxZJJ28mfd3POQ",   # Warm narrator
    "harry":     "SOYHLrjzK2X1ezoPC6cr",   # Expressive
    "james":     "ZQe5CZNOzWyzPSCn5a3c",   # Authoritative, deep
    "jeremy":    "bVMeCyTHy58xNoL34h3p",   # Scholarly, thoughtful
    "michael":   "flq6f7yk4E4fJM5XTYuZ",   # Warm, natural
    "george":    "JBFqnCBsd6RMkjVDRZzb",   # Precise, measured
    "eric":      "cjVigY5qzO86Huf0OWal",   # Mid-range, versatile
    "roger":     "CwhRBWXzGAHq8TQ4Fs17",   # Older, gravelly
    "liam":      "TX3LPaxmHKxFdv7VOQHJ",   # Strong, clear
    "will":      "bIHbv24MWmeRgasZH58o",   # Warm, approachable
    "river":     "SAz9YHcvj6GT2YYXdXww",   # Smooth, calm
    # --- Pre-made female voices ---
    "sarah":     "EXAVITQu4vr4xnSDxMaL",   # Soft, expressive
    "alice":     "Xb7hH8MSUJpSbSDYk0k2",   # Confident, clear
    "lily":      "pFZP5JQG7iQjIQuC4Bku",   # Warm British
    "rachel":    "21m00Tcm4TlvDq8ikWAM",   # Calm, measured
    "domi":      "AZnzlk1XvdvUeBnXmlld",   # Strong, assertive
    "elli":      "MF3mGyEYCl7XYWbV9V6O",   # Clear, younger
    "dorothy":   "ThT5KcBeYPX3keUQqHPh",   # Deeper, mature
    "gigi":      "jBpfuIE2acCO8z3wKNLl",   # Light, youthful
    "matilda":   "XrExE9yKIg1WjnnlVkGX",   # Warm, expressive
    "freya":     "jsCqWAovK2LkecY7zXl4",   # Clear, Nordic feel
    "grace":     "oWAxZDx7w5VEj9dCyTzz",   # Warm, elegant
    "charlotte": "XB0fDUnXU5powFXDhCwa",   # Refined, clear
    "jessica":   "cgSgspJ2msm6clMCkdW9",   # Warm, natural
    "glinda":    "z9fAnlkpzviPz146aGWa",   # Unique, expressive
    "laura":     "FGY2WhTYpPnrIDTdsKH5",   # Warm, natural
    "aria":      "g5CIjZEefAph4nQFvHAz",   # Musical, clear

    # --- Custom community voices (curated for zombie essence) ---
    # DARK / ANCIENT / HORROR (for role-based overrides)
    "dante":        "wXvR48IpOq9HACltTmt7",   # Growly, raspy, menacing — WARRIOR
    "victor":       "cPoqAvGWCPfCfyPMwe4z",   # Deep, slow, malevolent, ancient — MONARCH
    "caleb":        "DQCYGgKbvha45IXs96FO",   # The Dark Wizard — PRIEST (special settings)
    "agatha":       "HH3kybY6uEJ2ebSa9Vy3",   # Villainous, echoing, ancient witch — PRIESTESS
    "raven":        "Df0A8fHl2LOO7kDNIlpg",   # Deep, dark, mysterious female — QUEEN/EMPRESS
    "larauque":     "LifjXiNLcYfyYJD8PCDT",   # Hoarse, deep, dramatic, cinematic
    "ethereal_husk": "jpUA5miJyO2ygonZPVsO",  # Gravely, atmospheric female storyteller
    "victor_hale":  "CVP7d0EDsPO8YR2fweYp",   # Deep, dark, raspy, European/German accent
    "nephilia":     "r3pMaobgFa3QoTEBmnk4",   # Velvet-toned fallen angel, Polish accent
    "monika":       "6aO1exAR9bDruq155LzQ",   # Sinister, slow, creepy female
    # RESERVED — for future "cursed/insane" voice variant
    "gollum":       "1zvnni6XluAvqQJWPf1M",   # Raspy, fractured, small voice
    "xukas":        "xYWUvKNK6zWCgsdAK7Wi",   # Reptilian, hissing, monstrous
    "jet_du":       "mEHuKdn0uRQSMynXjRNO",   # Eerie whispered male
    "mira":         "thNHFcPYszCz6ZPG6mUp",   # Gentle whispered female
    # REGIONAL ACCENTS
    "vlad":         "XjdmlV0OFXfXE6Mg2Sb7",   # Eastern European male, mysterious
    "artemis":      "4Eq5uDjZLBd4UhQpKwuP",   # Slight Russian accent female
    "petra":        "ztyYYqlYMny7nllhThgo",   # Hard German accent female
    "lison":        "CKfuQaJKfvUG2Wtrda3Y",   # Soft French accent female
    "cristiano":    "IpCcRCVYm2nsZJjBFn4H",   # Portuguese accent male
    "charles":      "IT5cb4lfodSX8eyXUzyO",   # Afrikaans-colored male
    # NICHE (held for future use)
    "taro":         "UznIBkKIQe3ZG2tGydre",   # Young Japanese (too upbeat for zombies)
    "bachlava":     "ZXx7nI6BzemJq3Qy0ZUL",   # Young expressive English
    "darryl":       "O8ykjWKd0RjX6e5EyDuE",   # Malaysian male
    "jawid":        "wIwafQRMRzBqGgHCoUm0",   # Malaysian English
    "anna":         "brM9iIbwDREZaWL8luun",   # Thai female
}

# Role-based voice overrides — applied BEFORE region lookup.
# These archetypes are distinctive enough that the voice defines the character
# more than the culture does.
ROLE_VOICE_OVERRIDES = {
    # Priests, oracles, shamans, prophets — ritualistic delivery
    "priest": {
        "male":   "caleb",      # Dark wizard — formal ritualistic delivery
        "female": "agatha",     # Ancient witch — commanding, echoing
    },
    # Ancient monarchs — pharaohs, emperors, ancient kings/queens
    "monarch": {
        "male":   "victor",     # Deep, slow, malevolent, ancient
        "female": "raven",      # Deep, dark, mysterious, commanding
    },
    # Warriors — generals, soldiers, gladiators
    "warrior": {
        "male":   "dante",      # Growly, raspy, menacing
        "female": "raven",      # Authoritative female warrior
    },
}

# Per-voice settings overrides — some voices have creator-specified settings
# that sound better than our universal zombie defaults.
VOICE_SETTINGS_OVERRIDES = {
    "caleb": {
        # Caleb's creator: "Slow down the speed, increase stability, 95% similarity"
        "stability": 0.85,
        "similarity_boost": 0.95,
        "style": 0.30,
    },
}

# Region-to-voice mapping + per-region voice settings
# Each region maps to: voice IDs AND voice_settings overrides
# Stability: 0.15-0.20 = dramatic/guttural, 0.20-0.30 = expressive, 0.30-0.40 = measured
# Similarity_boost: lower = voice drifts from its base accent (critical for ancient non-European)
# Style: higher = more expressive/theatrical
REGION_ELEVENLABS = {
    # --- Ancient Middle Eastern / North African ---
    # Use custom dark voices with European accents — closer to Semitic/Afro-Asiatic feel
    "egyptian":  {"male": "victor_hale", "female": "nephilia",
                  "settings": {"stability": 0.20, "similarity_boost": 0.70, "style": 0.45}},
    "arabic":    {"male": "victor_hale", "female": "nephilia",
                  "settings": {"stability": 0.20, "similarity_boost": 0.70, "style": 0.45}},
    "persian":   {"male": "victor_hale", "female": "nephilia",
                  "settings": {"stability": 0.22, "similarity_boost": 0.70, "style": 0.42}},
    "turkish":   {"male": "victor_hale", "female": "nephilia",
                  "settings": {"stability": 0.22, "similarity_boost": 0.70, "style": 0.42}},

    # --- African ---
    # Afrikaans-colored male + deep mysterious female
    "african":   {"male": "charles",  "female": "raven",
                  "settings": {"stability": 0.20, "similarity_boost": 0.75, "style": 0.42}},

    # --- South Asian ---
    "indian":    {"male": "sam",      "female": "aria",
                  "settings": {"stability": 0.22, "similarity_boost": 0.55, "style": 0.42}},

    # --- East Asian ---
    "japanese":  {"male": "george",   "female": "elli",
                  "settings": {"stability": 0.30, "similarity_boost": 0.60, "style": 0.28}},
    "chinese":   {"male": "eric",     "female": "aria",
                  "settings": {"stability": 0.28, "similarity_boost": 0.60, "style": 0.30}},
    "korean":    {"male": "george",   "female": "elli",
                  "settings": {"stability": 0.28, "similarity_boost": 0.60, "style": 0.30}},

    # --- Central Asian / Steppe ---
    # Hoarse male, gravelly female — evokes ancient steppe
    "mongolian": {"male": "larauque", "female": "ethereal_husk",
                  "settings": {"stability": 0.18, "similarity_boost": 0.70, "style": 0.48}},

    # --- Mediterranean / Southern European ---
    "greek":     {"male": "antoni",   "female": "rachel",
                  "settings": {"stability": 0.22, "similarity_boost": 0.60, "style": 0.42}},
    "italian":   {"male": "antoni",   "female": "charlotte",
                  "settings": {"stability": 0.22, "similarity_boost": 0.65, "style": 0.42}},
    "spanish":   {"male": "cristiano", "female": "jessica",
                  "settings": {"stability": 0.22, "similarity_boost": 0.70, "style": 0.42}},
    "french":    {"male": "antoni",   "female": "lison",
                  "settings": {"stability": 0.22, "similarity_boost": 0.68, "style": 0.40}},

    # --- Northern European ---
    "british":   {"male": "daniel",   "female": "lily",
                  "settings": {"stability": 0.22, "similarity_boost": 0.70, "style": 0.35}},
    "irish":     {"male": "charlie",  "female": "grace",
                  "settings": {"stability": 0.22, "similarity_boost": 0.65, "style": 0.38}},
    "scottish":  {"male": "callum",   "female": "freya",
                  "settings": {"stability": 0.20, "similarity_boost": 0.62, "style": 0.40}},
    "german":    {"male": "victor_hale", "female": "petra",
                  "settings": {"stability": 0.22, "similarity_boost": 0.70, "style": 0.35}},
    "scandinavian": {"male": "brian", "female": "freya",
                  "settings": {"stability": 0.22, "similarity_boost": 0.65, "style": 0.32}},
    "russian":   {"male": "vlad",     "female": "artemis",
                  "settings": {"stability": 0.22, "similarity_boost": 0.75, "style": 0.38}},

    # --- Americas ---
    "american":  {"male": "bill",     "female": "laura",
                  "settings": {"stability": 0.22, "similarity_boost": 0.70, "style": 0.38}},
    "mesoamerican": {"male": "larauque", "female": "ethereal_husk",
                  "settings": {"stability": 0.18, "similarity_boost": 0.70, "style": 0.48}},
    "caribbean": {"male": "chris",    "female": "jessica",
                  "settings": {"stability": 0.20, "similarity_boost": 0.60, "style": 0.42}},

    # --- Pacific ---
    "aboriginal-australian": {"male": "larauque", "female": "ethereal_husk",
                  "settings": {"stability": 0.18, "similarity_boost": 0.70, "style": 0.48}},
}

# Data directory — persistent disk on Render, local folder for dev.
# /var/data is where the Render persistent disk is mounted.
# Everything here survives deploys: SQLite DB + generated portraits.
if os.path.isdir("/var/data"):
    DATA_DIR = "/var/data"
else:
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE = os.path.join(DATA_DIR, "conversations.db")

# Directory for generated images (Imagen returns bytes, not URLs)
GENERATED_IMAGES_DIR = os.path.join(DATA_DIR, "generated")
os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)

# Fallback image shown when Imagen fails or is blocked by safety filter.
# This URL must NEVER be saved to the prefab cache as a real image.
FALLBACK_IMAGE_URL = "/static/images/loading-zombie.jpg"

# In-memory cache for active conversations (fast access during chat)
conversations = {}

# Image cache to avoid regenerating the same images
image_cache = {}

# Pending image generation futures
pending_images = {}

# Last image generation error — exposed via /api/health for debugging
last_image_error = None
last_image_error_time = None

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
    db.execute(
        """CREATE TABLE IF NOT EXISTS prefab_figures (
        slug TEXT PRIMARY KEY,
        figure_data TEXT NOT NULL,
        image_url TEXT,
        system_prompt TEXT NOT NULL,
        opening_messages TEXT NOT NULL,
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


# ===== PREFAB FIGURE CACHE =====
def get_prefab(slug):
    """Look up a pre-built figure by slug (lowercase name).

    Auto-heals corrupted entries: if the cached image_url is the fallback
    (meaning image generation failed previously), delete the row and return
    None so the next request will regenerate it properly.
    """
    db = get_db()
    row = db.execute("SELECT * FROM prefab_figures WHERE slug = ?", (slug,)).fetchone()
    if row:
        # Auto-heal: discard cache entries that have the fallback image
        if row["image_url"] == FALLBACK_IMAGE_URL or not row["image_url"]:
            db.execute("DELETE FROM prefab_figures WHERE slug = ?", (slug,))
            db.commit()
            print(f"Auto-healed corrupted prefab: {slug} (had fallback image)")
            return None
        return {
            "figure_data": json.loads(row["figure_data"]),
            "image_url": row["image_url"],
            "system_prompt": row["system_prompt"],
            "opening_messages": json.loads(row["opening_messages"]),
        }
    return None


def save_prefab(slug, figure_data, image_url, system_prompt, opening_messages):
    """Save a pre-built figure to the cache."""
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute(
        """INSERT OR REPLACE INTO prefab_figures
        (slug, figure_data, image_url, system_prompt, opening_messages, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (slug, json.dumps(figure_data), image_url, system_prompt, json.dumps(opening_messages), now),
    )
    db.commit()


def figure_slug(name):
    """Create a lookup slug from a figure name."""
    return name.lower().strip()


ROLE_CADENCE_GUIDANCE = {
    "priest": (
        "\n\nSPEECH CADENCE: You are a religious figure. Speak with ritualistic gravity. "
        "Use shorter, more formal phrases. Use occasional pauses (represented as '...') between thoughts. "
        "Sometimes repeat key phrases for emphasis, like an incantation. Avoid casual modern English."
    ),
    "monarch": (
        "\n\nSPEECH CADENCE: You are a ruler. Speak with formal authority and measured pacing. "
        "Use commanding, dignified phrasing. Avoid casual language. "
        "Your words should feel weighty and deliberate."
    ),
    "nomad": (
        "\n\nSPEECH CADENCE: You come from the open plains. Speak plainly and directly. "
        "Short, punchy sentences. No flowery language. Hardened by wind and sky."
    ),
    "warrior": (
        "\n\nSPEECH CADENCE: You are a warrior. Speak directly and bluntly. "
        "Short sentences. No wasted words. Your voice carries the weight of battle."
    ),
}


def build_system_prompt(figure_data):
    """Build the zombie system prompt from figure data dict."""
    base = ZOMBIE_SYSTEM_PROMPT.format(
        name=figure_data.get("name", "Unknown"),
        location=figure_data.get("location", "Unknown"),
        era=figure_data.get("era", "Unknown"),
        death_year=figure_data.get("death_year", "Unknown"),
        description=figure_data.get("description", "a person from history"),
    )
    # Add role-specific cadence guidance if relevant
    role = figure_data.get("voice_role", "").lower()
    cadence = ROLE_CADENCE_GUIDANCE.get(role, "")
    return base + cadence


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
  b) SIGNATURE FEATURES — THE MOST IMPORTANT PART: What makes this person INSTANTLY RECOGNIZABLE? Describe the features they are FAMOUS for prominently and early in the prompt. Examples:
     * Blackbeard: massive long black beard, wild long dark hair, fearsome scowl
     * Einstein: wild white frizzy hair, bushy mustache
     * Genghis Khan: long braided hair, thin wispy beard, weathered Mongolian face
     * Cleopatra: elaborate Egyptian headdress, kohl-lined eyes
     * Viking warrior: long braided hair and beard, battle scars
     If someone is named for a feature (Blackbeard, Longshanks, etc.), that feature MUST be prominent. If they are known for specific hair, facial hair, scars, accessories, or body features, describe those IN DETAIL.
  c) BODY TYPE: What they looked like ALIVE, based on their class — royalty was well-fed, peasants were lean, warriors were muscular. But remember: Step 2 will override this with centuries of grave decay, so don't over-describe the living body. Focus on face and clothing instead.
  d) CLOTHING: Accurate to their era and station, but now centuries old — faded, frayed, moth-eaten, dirt-stained.
  e) TEETH: Pre-sugar cultures (before 1600s): worn and chipped but not rotten. Post-sugar Europe (1600s+): missing and blackened teeth, especially the wealthy who could afford sugar.

STEP 2 — ADD UNDEAD TRANSFORMATION (write this second, layered on top):
This person has been dead for centuries and has risen from the grave. They must look unmistakably UNDEAD — not a living person with dirt on them.

IMPORTANT: Use image-generation-safe language. Describe them as "undead", "ancient", "skeletal", "withered" — avoid graphic medical/gore terms.

REQUIRED undead features — include ALL of these:
  a) SKIN: Mottled grayish-green or ashen grey, weathered and ancient-looking. Stretched tight over the skull and bones. NOT healthy skin with a tint — this should look like parchment or ancient leather.
  b) FACE: Deeply gaunt and hollow-cheeked. Dark sunken eye sockets with eerie pale or glowing eyes. Skeletal features showing through — prominent cheekbones, jawline, brow ridge. Thin cracked lips.
  c) BODY: Gaunt and skeletal — no healthy muscle tone. Thin wiry frame, bony hands and fingers, visible collarbones and skeletal structure through the skin. Think ancient mummy, not athlete.
  d) AGING: Wisps of remaining hair (grey, thin, patchy). Weathered ancient texture to all skin. Cobwebs, grave dust, dried earth clinging to them.

The overall look: Captain Barbossa's cursed crew in Pirates of the Caribbean — clearly supernatural undead beings, skeletal and eerie, but with enough character to be expressive. NOT a living person with makeup.

STEP 3 — MOOD AND FRAMING:
Dark atmospheric background, fog, dramatic side lighting. Portrait framing — head and upper torso. Cinematic photorealistic fantasy portrait. Harsh shadows emphasizing the gaunt skeletal features.

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
    "voice_role": "The person's primary social role — determines the acoustic space their voice is placed in. Use one of: priest (religious figures, oracles, shamans, prophets, high priestesses), monarch (kings, queens, emperors, pharaohs, czars), warrior (soldiers, gladiators, knights, generals, military leaders), scholar (philosophers, scientists, inventors, writers, physicians), artist (musicians, poets, painters, court artists), explorer (navigators, adventurers, non-military conquerors), nomad (steppe horsemen, nomadic peoples, tribal wanderers), commoner (peasants, servants, common laborers, slaves), merchant (traders, artisans, bankers, shopkeepers). If someone fits multiple roles, pick the one most associated with where they'd have been HEARD. A pharaoh is 'monarch' even if also religious. A Mongol warrior is 'nomad' (they lived in open plains/tents, not stone halls). Leonardo is 'scholar'. Beethoven is 'artist'.",
    "image_prompt": "A cinematic undead portrait. Use SAFE language — describe as undead/skeletal/ancient/withered, avoid graphic gore terms. Example: 'An ancient undead Roman man risen from the grave. Gaunt skeletal face with mottled grey-green parchment-like skin stretched tight over prominent cheekbones and jaw. Dark hollow eye sockets with eerie pale glowing eyes. Thin cracked lips, patchy grey hair. Emaciated bony frame, skeletal hands with long thin fingers. Tattered moth-eaten dirt-stained white toga, cobwebs and grave dust clinging to him. Dark atmospheric background with fog, dramatic side lighting. Cinematic photorealistic fantasy portrait.'"
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
    global last_image_error, last_image_error_time
    try:
        # Check cache first
        cache_key = hashlib.md5(prompt.strip().encode()).hexdigest()
        if cache_key in image_cache:
            print(f"Image cache hit!")
            return image_cache[cache_key]

        styled_prompt = (
            f"{prompt}\n\n"
            f"Style: Ancient undead fantasy character in the style of Pirates of the Caribbean cursed pirates. "
            f"Gaunt skeletal frame, mottled grey-green parchment skin, dark hollow eye sockets, "
            f"prominent bones visible through weathered skin. NO healthy muscle tone — thin and emaciated. "
            f"The ethnicity, facial features, and clothing described above are the MOST important things to get right. "
            f"Tattered ancient clothing, cobwebs, grave dust. Dark foggy background, dramatic lighting. "
            f"Cinematic photorealistic fantasy portrait. No text in the image."
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

            url = f"/generated/{filename}"
            image_cache[cache_key] = url
            print(f"Imagen 4 image saved: {filename}")
            return url
        else:
            last_image_error = f"No images returned (likely safety filter) — prompt: {prompt[:80]}..."
            last_image_error_time = datetime.utcnow().isoformat()
            print(f"Imagen 4 {last_image_error}")
            return None

    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "resource_exhausted" in err.lower():
            last_image_error = f"Imagen daily quota exhausted (70/day on paid tier 1). Resets at midnight Pacific."
        else:
            last_image_error = f"Imagen error: {err[:200]}"
        last_image_error_time = datetime.utcnow().isoformat()
        print(f"Image generation failed: {e}")
        traceback.print_exc()
        return None


# ===== SHARED FIGURE BUILDER =====
def build_figure(name, location, era, num_openings=3, use_app_context=False):
    """Build a complete prefab figure: identify, generate image, create openings, save to cache.

    Used by: admin prebuild endpoint, auto-prebuild on startup, and auto-cache of new searches.
    If use_app_context=True, uses get_db() (inside a request). Otherwise uses direct sqlite3 connection.
    """
    query = f"{name} from {location}, {era}"
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=DISAMBIGUATE_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    result_text = resp.content[0].text
    start = result_text.find("{")
    end = result_text.rfind("}") + 1
    figure_data = json.loads(result_text[start:end])

    # Generate image
    image_prompt = figure_data.get("image_prompt", "")
    image_url = get_image_url(image_prompt)

    # If image generation failed, don't save this to the prefab cache —
    # we want it to retry on the next request instead of being stuck with
    # the fallback image forever.
    if not image_url:
        raise Exception(f"Image generation failed for {figure_data.get('name', 'Unknown')} — not caching")

    # Build system prompt
    system_prompt = build_system_prompt(figure_data)

    # Generate opening messages
    openings = []
    for i in range(num_openings):
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": "You have just risen from your grave. Introduce yourself."}],
        )
        openings.append(resp.content[0].text)

    # Save to prefab cache
    slug = figure_slug(figure_data.get("name", ""))
    if use_app_context:
        save_prefab(slug, figure_data, image_url, system_prompt, openings)
    else:
        # Direct DB connection (for background threads outside Flask request context)
        db = sqlite3.connect(DATABASE)
        now = datetime.utcnow().isoformat()
        db.execute(
            """INSERT OR REPLACE INTO prefab_figures
            (slug, figure_data, image_url, system_prompt, opening_messages, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (slug, json.dumps(figure_data), image_url, system_prompt, json.dumps(openings), now),
        )
        db.commit()
        db.close()

    return {
        "figure_data": figure_data,
        "image_url": image_url,
        "system_prompt": system_prompt,
        "openings": openings,
        "slug": slug,
    }


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


@app.route("/generated/<path:filename>")
def serve_generated_image(filename):
    """Serve generated zombie portraits from the persistent data directory."""
    return send_from_directory(GENERATED_IMAGES_DIR, filename, max_age=604800)


@app.route("/api/health")
def health_check():
    """Health check — verify API keys and database."""
    status = {"app": "running"}
    status["anthropic_key"] = "set" if os.getenv("ANTHROPIC_API_KEY") else "MISSING"
    status["google_key"] = "set" if os.getenv("GOOGLE_API_KEY") else "MISSING"
    status["elevenlabs_key"] = "set" if ELEVENLABS_API_KEY else "MISSING"
    status["secret_key"] = "set" if app.secret_key else "MISSING"
    try:
        db = get_db()
        count = db.execute("SELECT COUNT(*) FROM prefab_figures").fetchone()[0]
        status["prefab_count"] = count
    except Exception as e:
        status["db_error"] = str(e)
    # Surface the last image generation failure for debugging
    if last_image_error:
        status["last_image_error"] = last_image_error
        status["last_image_error_time"] = last_image_error_time
    return jsonify(status)


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

    # Check prefab cache first — zero API calls for known figures
    # Try exact match, then try extracting the core name from queries like "Cleopatra from Egypt, 69-30 BC"
    slug = figure_slug(user_input)
    prefab = get_prefab(slug)
    if not prefab:
        # Try just the first part before "from" (suggestion cards send "Name from Location, Era")
        core_name = user_input.split(" from ")[0].strip() if " from " in user_input else ""
        if core_name:
            prefab = get_prefab(figure_slug(core_name))

    if prefab:
        figure_data = prefab["figure_data"]
        figure_data["image_url"] = prefab["image_url"]
        figure_data["figure_key"] = figure_slug(figure_data.get("name", "")) + "_prefab"
        figure_data["_prefab"] = True
        print(f"Prefab cache hit: {figure_data.get('name')}")
        return jsonify(figure_data)

    # No cache hit — use Haiku for identification
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=DISAMBIGUATE_PROMPT,
            messages=[{"role": "user", "content": user_input}],
        )
    except Exception as e:
        print(f"Anthropic API error: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Failed to reach the spirits. API error: {str(e)[:100]}"}), 500

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
            system_prompt = build_system_prompt(fig_data)
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": "You have just risen from your grave. Introduce yourself."}],
            )
            return {"system_prompt": system_prompt, "opening": resp.content[0].text}

        opening_future = executor.submit(generate_opening, figure_data)
        pending_openings[figure_key] = opening_future

        # Cache this figure for future users (image will be added when ready)
        def cache_new_figure(fig_data, fig_key):
            """After image and opening are ready, save as prefab for future users."""
            try:
                time.sleep(2)  # Give image time to generate
                img_url = pending_images[fig_key].result(timeout=60) if fig_key in pending_images else None

                # Don't cache if image generation failed — we want it to retry next time
                if not img_url:
                    print(f"Not caching {fig_data.get('name', 'Unknown')} — image failed")
                    return

                sys_prompt = ""
                opening = ""
                if fig_key in pending_openings:
                    result = pending_openings[fig_key].result(timeout=30)
                    opening = result.get("opening", "")
                    sys_prompt = result.get("system_prompt", "")

                if not sys_prompt:
                    sys_prompt = build_system_prompt(fig_data)

                # Save to database directly (not using get_db since we're in a thread)
                db = sqlite3.connect(DATABASE)
                slug = figure_slug(fig_data.get("name", ""))
                now = datetime.utcnow().isoformat()
                db.execute(
                    """INSERT OR REPLACE INTO prefab_figures
                    (slug, figure_data, image_url, system_prompt, opening_messages, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (slug, json.dumps(fig_data), img_url, sys_prompt, json.dumps([opening]), now),
                )
                db.commit()
                db.close()
                print(f"Cached new prefab: {slug}")
            except Exception as e:
                print(f"Failed to cache prefab: {e}")

        executor.submit(cache_new_figure, figure_data, figure_key)

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
            # If generation failed (None), serve the fallback for display only.
            # The prefab cache won't have saved this, so next request retries.
            return jsonify({"status": "ready", "image_url": url or FALLBACK_IMAGE_URL})
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

    # Check if this is a prefab figure — use cached opening + system prompt
    if figure.get("_prefab"):
        slug = figure_slug(figure.get("name", ""))
        prefab = get_prefab(slug)
        if prefab:
            system_prompt = prefab["system_prompt"]
            openings = prefab["opening_messages"]
            opening_message = random.choice(openings) if openings else None
            if opening_message:
                print(f"Using prefab opening for {slug}")
            else:
                opening_message = None  # Fall through to generate

            if not opening_message:
                # Generate fresh opening with Haiku
                resp = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=512,
                    system=system_prompt,
                    messages=[{"role": "user", "content": "You have just risen from your grave. Introduce yourself."}],
                )
                opening_message = resp.content[0].text

            image_url = figure.get("image_url", prefab["image_url"])
            user_id = session.get("user_id")
            save_conversation(session_id, figure, system_prompt, image_url, user_id=user_id)
            save_message(session_id, "user", "You have just risen from your grave. Introduce yourself.")
            save_message(session_id, "assistant", opening_message)

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

    # Non-prefab: check if we pre-generated the opening message during identification
    if figure_key and figure_key in pending_openings:
        future = pending_openings[figure_key]
        result = future.result(timeout=30)
        system_prompt = result["system_prompt"]
        opening_message = result["opening"]
        del pending_openings[figure_key]
        print(f"Used pre-generated opening for {figure_key}")
    else:
        system_prompt = build_system_prompt(figure)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": "You have just risen from your grave. Introduce yourself.",
                }
            ],
        )
        opening_message = response.content[0].text

    image_url = figure.get("image_url", "")
    user_id = session.get("user_id")
    save_conversation(session_id, figure, system_prompt, image_url, user_id=user_id)
    save_message(session_id, "user", "You have just risen from your grave. Introduce yourself.")
    save_message(session_id, "assistant", opening_message)

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

    # Cap conversation history sent to API — keep first 2 (intro) + last 8 messages
    # This prevents token costs from growing unbounded in long conversations
    all_msgs = conv["messages"]
    if len(all_msgs) > 10:
        capped_msgs = all_msgs[:2] + all_msgs[-8:]
    else:
        capped_msgs = all_msgs

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=conv["system_prompt"],
        messages=capped_msgs,
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


@app.route("/api/speak", methods=["POST"])
def speak():
    """Convert text to speech using ElevenLabs API. Returns MP3 audio."""
    if not ELEVENLABS_API_KEY:
        return jsonify({"error": "Voice service not configured"}), 503

    data = request.json or {}
    text = data.get("text", "").strip()
    gender = data.get("gender", "male").lower()
    region = data.get("region", "british").lower()
    role = data.get("role", "").lower()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    # Strip action text (*between asterisks*) — only speak dialogue
    clean_text = re.sub(r'\*[^*]+\*', '...', text).strip()
    if not clean_text or clean_text == '...':
        return jsonify({"error": "No dialogue to speak"}), 400

    # --- Voice selection ---
    # Priority 1: role override (priest/monarch/warrior use archetypal voices)
    # Priority 2: region-based mapping
    voice_key = None
    source = "region"
    if role in ROLE_VOICE_OVERRIDES:
        voice_key = ROLE_VOICE_OVERRIDES[role].get(gender)
        if voice_key:
            source = f"role:{role}"

    # Fall back to region lookup
    region_map = REGION_ELEVENLABS.get(region, REGION_ELEVENLABS.get("british"))
    if not voice_key:
        voice_key = region_map.get(gender, region_map.get("male", "daniel"))

    voice_id = ELEVENLABS_VOICES.get(voice_key, ELEVENLABS_VOICES["daniel"])

    # --- Voice settings ---
    # Priority 1: per-voice override (e.g. Caleb's creator-specified settings)
    # Priority 2: region-based settings
    if voice_key in VOICE_SETTINGS_OVERRIDES:
        settings_source = VOICE_SETTINGS_OVERRIDES[voice_key]
    else:
        settings_source = region_map.get("settings", {})

    voice_settings = {
        "stability": settings_source.get("stability", 0.22),
        "similarity_boost": settings_source.get("similarity_boost", 0.70),
        "style": settings_source.get("style", 0.40),
        "use_speaker_boost": True,
    }

    print(f"TTS: {region}/{gender}/{role or '-'} → {voice_key} via {source} "
          f"(stability={voice_settings['stability']}, style={voice_settings['style']})")

    try:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": clean_text,
                # Turbo model — ~2-4s faster per response than multilingual_v2,
                # slight quality tradeoff. Works with all our custom voices.
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": voice_settings,
            },
            timeout=15,
        )

        if response.status_code != 200:
            print(f"ElevenLabs error {response.status_code}: {response.text[:200]}")
            return jsonify({"error": "Voice generation failed"}), 502

        # Return the MP3 audio directly
        return Response(
            response.content,
            mimetype="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    except requests.Timeout:
        return jsonify({"error": "Voice service timeout"}), 504
    except Exception as e:
        print(f"ElevenLabs exception: {e}")
        return jsonify({"error": "Voice service error"}), 500


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


@app.route("/api/admin/prebuild", methods=["POST"])
def prebuild_figures():
    """Admin endpoint: pre-generate all suggestion figures. Run once to populate cache."""
    # Simple protection — require a secret key
    data = request.json or {}
    if data.get("secret") != app.secret_key:
        return jsonify({"error": "Unauthorized"}), 401

    results = []
    for fig in SUGGESTION_FIGURES:
        slug = figure_slug(fig["name"])

        # Skip if already cached
        existing = get_prefab(slug)
        if existing and existing.get("image_url"):
            results.append({"name": fig["name"], "status": "already cached"})
            continue

        try:
            result = build_figure(fig["name"], fig["location"], fig["era"], use_app_context=True)
            results.append({"name": fig["name"], "status": "built", "image": result["image_url"]})
            print(f"Pre-built: {fig['name']}")
        except Exception as e:
            results.append({"name": fig["name"], "status": f"error: {str(e)}"})
            print(f"Failed to pre-build {fig['name']}: {e}")
            traceback.print_exc()

    return jsonify({"results": results})


# Always initialize DB (works with both gunicorn and direct python run)
init_db()


# Clean up corrupted prefabs on startup (entries saved with the fallback image)
def cleanup_corrupted_prefabs():
    try:
        db = sqlite3.connect(DATABASE)
        cur = db.execute(
            "DELETE FROM prefab_figures WHERE image_url = ? OR image_url IS NULL OR image_url = ''",
            (FALLBACK_IMAGE_URL,)
        )
        removed = cur.rowcount
        db.commit()
        db.close()
        if removed:
            print(f"Startup cleanup: removed {removed} prefab(s) with fallback/empty image.")
    except Exception as e:
        print(f"Cleanup error: {e}")

cleanup_corrupted_prefabs()


# ===== AUTO-PREBUILD ON STARTUP =====
# Google Imagen has a 70 images/day limit on paid tier 1.
# Each figure needs 1 image. We build at most MAX_PREBUILD_PER_STARTUP figures
# per deploy to stay well within quota, leaving room for user requests.
MAX_PREBUILD_PER_STARTUP = 10

def auto_prebuild():
    """Background thread: rebuild prefab cache gradually (handles Render's ephemeral disk)."""
    # Wait for the server to fully start
    time.sleep(5)

    # Use a direct DB connection (no Flask request context in background thread)
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    count = db.execute("SELECT COUNT(*) FROM prefab_figures").fetchone()[0]
    db.close()

    if count >= len(SUGGESTION_FIGURES):
        print(f"Auto-prebuild: {count} prefab figures already cached, skipping.")
        return

    print(f"Auto-prebuild: only {count}/{len(SUGGESTION_FIGURES)} figures cached. Building up to {MAX_PREBUILD_PER_STARTUP} this startup...")

    built = 0
    errors = 0
    quota_hit = False
    for fig in SUGGESTION_FIGURES:
        # Stop if we've built enough this startup or hit quota
        if built >= MAX_PREBUILD_PER_STARTUP or quota_hit:
            break

        slug = figure_slug(fig["name"])

        # Check if already cached (use direct DB, not get_db)
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM prefab_figures WHERE slug = ?", (slug,)).fetchone()
        db.close()

        if row and row["image_url"]:
            continue  # Already cached

        try:
            build_figure(fig["name"], fig["location"], fig["era"])
            built += 1
            print(f"Auto-prebuild [{built}/{MAX_PREBUILD_PER_STARTUP}]: {fig['name']} ✓")
            time.sleep(3)  # Delay between builds to avoid rate limits
        except Exception as e:
            error_str = str(e).lower()
            # Stop immediately if we hit Google's quota limit
            if "429" in str(e) or "quota" in error_str or "resource_exhausted" in error_str:
                print(f"Auto-prebuild: hit API quota limit, stopping. Will continue next restart.")
                quota_hit = True
            else:
                errors += 1
                print(f"Auto-prebuild error for {fig['name']}: {e}")
                traceback.print_exc()
                time.sleep(5)  # Longer delay after errors

    remaining = len(SUGGESTION_FIGURES) - count - built
    print(f"Auto-prebuild done: {built} built, {errors} errors. {remaining} remaining for next restart.")


# Start auto-prebuild in background thread (only if not already populated)
prebuild_thread = threading.Thread(target=auto_prebuild, daemon=True)
prebuild_thread.start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=True, port=port)
