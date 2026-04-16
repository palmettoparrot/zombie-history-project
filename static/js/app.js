// ===== STATE =====
let currentFigure = null;
let sessionId = null;
let isRecording = false;
let recognition = null;
let currentUser = null;       // null = not logged in
let authPromptShown = false;  // only show once per visit
let pendingAwaken = false;    // true if user clicked Awaken before auth

// ===== DOM ELEMENTS =====
const landingPage = document.getElementById('landing-page');
const loadingOverlay = document.getElementById('loading-overlay');
const loadingText = document.getElementById('loading-text');
const loadingSubtext = document.getElementById('loading-subtext');
const confirmationSection = document.getElementById('confirmation-section');
const confirmationImage = document.getElementById('confirmation-image');
const confirmationText = document.getElementById('confirmation-text');
const imageLoadingText = document.getElementById('image-loading-text');
const chatSection = document.getElementById('chat-section');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const chatSendBtn = document.getElementById('chat-send-btn');
const chatMicBtn = document.getElementById('chat-mic-btn');
const chatSidebarImage = document.getElementById('chat-sidebar-image');
const chatFigureName = document.getElementById('chat-figure-name');
const chatFigureDetail = document.getElementById('chat-figure-detail');
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const typingIndicator = document.getElementById('typing-indicator');

// ===== ZOMBIE VOICE (Text-to-Speech) =====
let zombieVoice = null;

// Voice mapping — ENGLISH VOICES ONLY. Non-English voices can't speak English properly.
// We use different English dialects (UK, US, Australian, Indian, Irish, South African)
// and vary pitch/rate per region to differentiate characters.
//
// Available English dialects in most browsers:
//   en-GB (British), en-US (American), en-AU (Australian),
//   en-IN (Indian English), en-IE (Irish), en-ZA (South African)
//
// Strategy: map each region to the English dialect that sounds most distinct/appropriate,
// plus pitch/rate tweaks to further differentiate.

const REGION_VOICE_MAP = {
    // --- Regions with a natural English dialect match ---
    british:    { male: ['Daniel', 'Google UK English Male', 'en-GB'],
                  female: ['Martha', 'Kate', 'Google UK English Female', 'en-GB'] },
    irish:      { male: ['Moira', 'en-IE', 'Daniel', 'en-GB'],
                  female: ['Moira', 'en-IE', 'Martha', 'en-GB'] },
    scottish:   { male: ['Fiona', 'en-GB', 'Daniel'],
                  female: ['Fiona', 'en-GB', 'Martha'] },
    american:   { male: ['Alex', 'Fred', 'Google US English', 'en-US'],
                  female: ['Samantha', 'Allison', 'Ava', 'Google US English', 'en-US'] },
    'aboriginal-australian': { male: ['Gordon', 'Lee', 'en-AU', 'Daniel', 'Google UK English Male'],
                               female: ['Karen', 'en-AU', 'Google UK English Female'] },
    caribbean:  { male: ['en-GB', 'Daniel', 'Google UK English Male'],
                  female: ['en-GB', 'Martha', 'Google UK English Female'] },
    indian:     { male: ['Rishi', 'en-IN', 'Google UK English Male'],
                  female: ['Lekha', 'Veena', 'en-IN', 'Google UK English Female'] },
    african:    { male: ['en-ZA', 'Daniel', 'Arthur', 'Fred'],
                  female: ['Tessa', 'en-ZA', 'Martha'] },

    // --- Non-English regions: use the most distinct-sounding English voice available ---
    // Indian English is the most "non-Western" English accent available, good for nearby regions
    arabic:     { male: ['Rishi', 'en-IN', 'Daniel', 'en-GB'],
                  female: ['Lekha', 'en-IN', 'Martha', 'en-GB'] },
    egyptian:   { male: ['Rishi', 'en-IN', 'Daniel', 'en-GB'],
                  female: ['Lekha', 'en-IN', 'Martha', 'en-GB'] },
    persian:    { male: ['Rishi', 'en-IN', 'Daniel', 'en-GB'],
                  female: ['Lekha', 'en-IN', 'Martha', 'en-GB'] },
    turkish:    { male: ['Rishi', 'en-IN', 'Daniel', 'en-GB'],
                  female: ['Lekha', 'en-IN', 'Martha', 'en-GB'] },
    greek:      { male: ['Daniel', 'en-GB', 'Google UK English Male'],
                  female: ['Martha', 'en-GB', 'Google UK English Female'] },

    // East Asian — use Australian English (most distinct from British/American)
    japanese:   { male: ['Gordon', 'Lee', 'en-AU', 'Daniel', 'Fred'],
                  female: ['Karen', 'en-AU', 'Martha'] },
    chinese:    { male: ['Gordon', 'Lee', 'en-AU', 'Daniel', 'Fred'],
                  female: ['Karen', 'en-AU', 'Martha'] },
    korean:     { male: ['Gordon', 'Lee', 'en-AU', 'Daniel', 'Fred'],
                  female: ['Karen', 'en-AU', 'Martha'] },
    mongolian:  { male: ['Gordon', 'Lee', 'en-AU', 'Daniel', 'Fred'],
                  female: ['Karen', 'en-AU', 'Martha'] },

    // European — use British English (closest culturally)
    french:     { male: ['Daniel', 'en-GB', 'Google UK English Male'],
                  female: ['Martha', 'Kate', 'en-GB', 'Google UK English Female'] },
    italian:    { male: ['Daniel', 'en-GB', 'Google UK English Male'],
                  female: ['Martha', 'en-GB', 'Google UK English Female'] },
    spanish:    { male: ['Daniel', 'en-GB', 'Google US English', 'en-US'],
                  female: ['Martha', 'en-GB', 'Samantha', 'en-US'] },
    german:     { male: ['Daniel', 'en-GB', 'Google UK English Male'],
                  female: ['Martha', 'en-GB', 'Google UK English Female'] },
    scandinavian: { male: ['Daniel', 'en-GB', 'Google UK English Male'],
                    female: ['Martha', 'en-GB', 'Google UK English Female'] },
    russian:    { male: ['Daniel', 'en-GB', 'Google UK English Male'],
                  female: ['Martha', 'en-GB', 'Google UK English Female'] },

    // Americas
    mesoamerican: { male: ['Google US English', 'Alex', 'en-US'],
                    female: ['Samantha', 'Google US English', 'en-US'] },
};

// Known voice genders for macOS/Chrome — used to avoid gender mismatches on fallback
const KNOWN_FEMALE_NAMES = ['karen', 'samantha', 'allison', 'ava', 'martha', 'kate', 'moira', 'fiona', 'lekha', 'veena', 'tessa', 'victoria', 'zoe', 'nicky', 'serena', 'catherine', 'kathy', 'flo', 'grandma', 'shelley', 'sandy', 'female'];
const KNOWN_MALE_NAMES = ['daniel', 'alex', 'fred', 'lee', 'rishi', 'gordon', 'tom', 'oliver', 'aaron', 'ralph', 'arthur', 'albert', 'reed', 'rocko', 'eddy', 'grandpa', 'junior', 'male'];

function voiceMatchesGender(voice, wantGender) {
    const name = voice.name.toLowerCase();
    if (wantGender === 'female') {
        // Accept if it's known female, or at least not known male
        if (KNOWN_MALE_NAMES.some(m => name.includes(m))) return false;
        return true;
    } else {
        // Accept if it's known male, or at least not known female
        if (KNOWN_FEMALE_NAMES.some(f => name.includes(f))) return false;
        return true;
    }
}

// Per-region voice adjustments — pitch and rate overrides to give cultural character
// These layer ON TOP of the base zombie pitch (0.35 male, 0.55 female)
const REGION_VOICE_TWEAKS = {
    'aboriginal-australian': { pitchOffset: -0.10, rate: 0.72 },  // deeper, slower, more gravitas
    mongolian:   { pitchOffset: -0.08, rate: 0.75 },  // deep and commanding
    japanese:    { pitchOffset: 0, rate: 0.78 },       // measured, deliberate
    chinese:     { pitchOffset: 0, rate: 0.78 },
    arabic:      { pitchOffset: -0.05, rate: 0.78 },   // deeper
    egyptian:    { pitchOffset: -0.05, rate: 0.76 },
    persian:     { pitchOffset: -0.03, rate: 0.78 },
    african:     { pitchOffset: -0.08, rate: 0.74 },   // deep, resonant
    mesoamerican:{ pitchOffset: -0.05, rate: 0.76 },
    indian:      { pitchOffset: 0, rate: 0.80 },
    caribbean:   { pitchOffset: -0.05, rate: 0.76 },
    russian:     { pitchOffset: -0.05, rate: 0.78 },
    scandinavian:{ pitchOffset: -0.03, rate: 0.78 },
};

function selectZombieVoice(gender, region) {
    const synth = window.speechSynthesis;
    const voices = synth.getVoices();
    if (!voices.length) return;

    // Only consider English voices
    const englishVoices = voices.filter(v => v.lang.startsWith('en'));
    if (!englishVoices.length) {
        zombieVoice = voices[0];
        return;
    }

    const g = (gender || 'male').toLowerCase();
    const r = (region || 'british').toLowerCase();

    const regionMap = REGION_VOICE_MAP[r];
    const prefs = regionMap ? (regionMap[g] || regionMap['male']) : null;

    if (prefs) {
        for (const pref of prefs) {
            // Try as voice name fragment — must match gender
            let match = englishVoices.find(v => v.name.includes(pref) && voiceMatchesGender(v, g));
            if (match) {
                zombieVoice = match;
                console.log(`Zombie voice: ${match.name} (matched "${pref}" for ${r}/${g})`);
                return;
            }
            // Try as language code prefix — MUST match gender
            match = englishVoices.find(v => v.lang.startsWith(pref) && voiceMatchesGender(v, g));
            if (match) {
                zombieVoice = match;
                console.log(`Zombie voice: ${match.name} (lang "${pref}" for ${r}/${g})`);
                return;
            }
        }
    }

    // Fallback: any English voice matching the right gender
    let fallback = englishVoices.find(v => voiceMatchesGender(v, g));
    zombieVoice = fallback || englishVoices[0];
    console.log(`Zombie voice fallback: ${zombieVoice.name}`);
}

function speakZombie(text) {
    // Strip action text between asterisks — don't read stage directions aloud
    const cleanText = text.replace(/\*[^*]+\*/g, '... ');

    const synth = window.speechSynthesis;
    synth.cancel();

    const utterance = new SpeechSynthesisUtterance(cleanText);

    // Zombie-ify the voice: lower pitch, slightly slow
    const gender = (currentFigure?.voice_gender || 'male').toLowerCase();
    const region = (currentFigure?.voice_region || 'british').toLowerCase();
    const tweaks = REGION_VOICE_TWEAKS[region] || {};

    let basePitch = gender === 'female' ? 0.55 : 0.35;
    utterance.pitch = Math.max(0.01, basePitch + (tweaks.pitchOffset || 0));
    utterance.rate = tweaks.rate || 0.82;
    utterance.volume = 1.0;

    if (zombieVoice) utterance.voice = zombieVoice;

    console.log(`Speaking as ${region}/${gender}: pitch=${utterance.pitch.toFixed(2)}, rate=${utterance.rate}, voice=${zombieVoice?.name}`);
    synth.speak(utterance);
}

// ===== SPEECH RECOGNITION (Mic input) =====
function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        // Hide mic button if not supported
        chatMicBtn.style.display = 'none';
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        chatInput.value = transcript;
        stopRecording();
        // Auto-send after speech is captured
        handleChatSend();
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        stopRecording();
    };

    recognition.onend = () => {
        stopRecording();
    };
}

function startRecording() {
    if (!recognition) return;
    isRecording = true;
    chatMicBtn.classList.add('recording');
    chatMicBtn.title = 'Listening...';
    // Stop zombie from talking while user speaks
    window.speechSynthesis.cancel();
    recognition.start();
}

function stopRecording() {
    isRecording = false;
    chatMicBtn.classList.remove('recording');
    chatMicBtn.title = 'Speak to the dead';
    try { recognition.stop(); } catch(e) {}
}

// ===== AUTH SYSTEM =====
const authModal = document.getElementById('auth-modal');
const authError = document.getElementById('auth-error');
const authRegisterForm = document.getElementById('auth-register-form');
const authLoginForm = document.getElementById('auth-login-form');
const userStatus = document.getElementById('user-status');
const pastConversationsLink = document.getElementById('past-conversations-link');

function showAuthError(msg) {
    authError.textContent = msg;
    authError.classList.add('visible');
}

function hideAuthError() {
    authError.classList.remove('visible');
}

function showAuthModal() {
    hideAuthError();
    authModal.classList.add('active');
}

function hideAuthModal() {
    authModal.classList.remove('active');
}

function updateUserUI() {
    if (currentUser) {
        userStatus.innerHTML = `<span class="user-greeting">Welcome, ${currentUser.username}</span> <a class="logout-link" id="logout-link" href="#">(log out)</a>`;
        document.getElementById('logout-link').addEventListener('click', async (e) => {
            e.preventDefault();
            await fetch('/api/auth/logout', { method: 'POST' });
            currentUser = null;
            updateUserUI();
        });
        // Show past conversations link
        pastConversationsLink.style.display = 'block';
        // Hide save hint in chat if visible
        const saveHint = document.getElementById('chat-save-hint');
        if (saveHint) saveHint.style.display = 'none';
    } else {
        userStatus.innerHTML = '<a id="login-link" href="#">Sign in</a> to save your conversations';
        document.getElementById('login-link').addEventListener('click', (e) => {
            e.preventDefault();
            showAuthModal();
        });
        pastConversationsLink.style.display = 'none';
    }
}

async function checkAuthStatus() {
    try {
        const resp = await fetch('/api/auth/status');
        const data = await resp.json();
        if (data.logged_in) {
            currentUser = data.user;
            // Check if they have history
            const histResp = await fetch('/api/history');
            const histData = await histResp.json();
            if (histData.length > 0) {
                pastConversationsLink.style.display = 'block';
            }
        }
        updateUserUI();
    } catch (e) {
        console.error('Auth check failed:', e);
    }
}

// Register form
authRegisterForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideAuthError();
    const username = document.getElementById('auth-username').value.trim();
    const email = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value;

    try {
        const resp = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            showAuthError(data.error || 'Registration failed.');
            return;
        }
        currentUser = data.user;
        updateUserUI();
        hideAuthModal();
        if (pendingAwaken) {
            pendingAwaken = false;
            proceedToAwaken();
        }
    } catch (err) {
        showAuthError('Connection error. Please try again.');
    }
});

// Login form
authLoginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideAuthError();
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;

    try {
        const resp = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            showAuthError(data.error || 'Login failed.');
            return;
        }
        currentUser = data.user;
        updateUserUI();
        hideAuthModal();
        if (pendingAwaken) {
            pendingAwaken = false;
            proceedToAwaken();
        }
    } catch (err) {
        showAuthError('Connection error. Please try again.');
    }
});

// Toggle between register and login forms
document.getElementById('auth-toggle-btn').addEventListener('click', () => {
    hideAuthError();
    const isRegister = authRegisterForm.style.display !== 'none';
    if (isRegister) {
        authRegisterForm.style.display = 'none';
        authLoginForm.style.display = 'flex';
        document.getElementById('auth-toggle-text').textContent = "Don't have an account?";
        document.getElementById('auth-toggle-btn').textContent = 'Create one';
    } else {
        authRegisterForm.style.display = 'flex';
        authLoginForm.style.display = 'none';
        document.getElementById('auth-toggle-text').textContent = 'Already have an account?';
        document.getElementById('auth-toggle-btn').textContent = 'Log in';
    }
});

// Skip button
document.getElementById('auth-skip-btn').addEventListener('click', () => {
    authPromptShown = true; // don't ask again this visit
    hideAuthModal();
    if (pendingAwaken) {
        pendingAwaken = false;
        proceedToAwaken();
    }
});

// Close button
document.getElementById('auth-modal-close').addEventListener('click', () => {
    hideAuthModal();
    pendingAwaken = false; // they closed it, don't auto-proceed
});

// Google Sign-In callback
function handleGoogleCredential(response) {
    fetch('/api/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: response.credential }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.user) {
            currentUser = data.user;
            updateUserUI();
            hideAuthModal();
            if (pendingAwaken) {
                pendingAwaken = false;
                proceedToAwaken();
            }
        } else {
            showAuthError(data.error || 'Google sign-in failed.');
        }
    })
    .catch(() => showAuthError('Google sign-in failed. Please try again.'));
}

// Initialize Google Sign-In if client ID is available
if (window.GOOGLE_CLIENT_ID) {
    window.addEventListener('load', () => {
        if (typeof google !== 'undefined' && google.accounts) {
            google.accounts.id.initialize({
                client_id: window.GOOGLE_CLIENT_ID,
                callback: handleGoogleCredential,
            });
            google.accounts.id.renderButton(
                document.getElementById('google-signin-btn'),
                { theme: 'filled_black', size: 'large', width: 300, text: 'continue_with' }
            );
        }
    });
}

// "Save conversations" button in chat header (for anonymous users)
document.getElementById('chat-save-btn')?.addEventListener('click', () => {
    showAuthModal();
});

// ===== BACKGROUND ATMOSPHERE =====
function initBackground() {
    const canvas = document.getElementById('background-canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const particles = [];
    const numParticles = 50;

    for (let i = 0; i < numParticles; i++) {
        particles.push({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            size: Math.random() * 2 + 0.5,
            speedX: (Math.random() - 0.5) * 0.3,
            speedY: (Math.random() - 0.5) * 0.2,
            opacity: Math.random() * 0.15 + 0.05,
        });
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        particles.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(90, 154, 74, ${p.opacity})`;
            ctx.fill();

            p.x += p.speedX;
            p.y += p.speedY;

            if (p.x < 0) p.x = canvas.width;
            if (p.x > canvas.width) p.x = 0;
            if (p.y < 0) p.y = canvas.height;
            if (p.y > canvas.height) p.y = 0;
        });

        requestAnimationFrame(animate);
    }

    animate();

    window.addEventListener('resize', () => {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    });
}

// ===== LOADING MESSAGES =====
const loadingMessages = [
    { text: "Disturbing the grave...", sub: "The earth trembles" },
    { text: "Searching the crypts...", sub: "Cobwebs part before you" },
    { text: "The ground cracks open...", sub: "Something stirs below" },
    { text: "Bones reassemble...", sub: "Dust becomes flesh" },
    { text: "A hand reaches upward...", sub: "The dead do not rest easy" },
    { text: "Summoning from the beyond...", sub: "Between worlds, a soul wanders" },
];

function showLoading() {
    const msg = loadingMessages[Math.floor(Math.random() * loadingMessages.length)];
    loadingText.textContent = msg.text;
    loadingSubtext.textContent = msg.sub;
    loadingOverlay.classList.add('active');
}

function hideLoading() {
    loadingOverlay.classList.remove('active');
}

// ===== VIEWS =====
function showLanding() {
    landingPage.style.display = 'flex';
    confirmationSection.classList.remove('active');
    chatSection.classList.remove('active');
    searchInput.value = '';
    searchInput.focus();
}

function showConfirmation(figure) {
    landingPage.style.display = 'none';
    confirmationText.textContent = figure.confirmation_message;

    // Show the confirmation screen immediately — image may still be loading
    if (figure.image_url) {
        confirmationImage.src = figure.image_url;
        confirmationImage.alt = 'Historical scene';
        confirmationImage.classList.remove('image-loading');
        imageLoadingText.style.display = 'none';
    } else {
        // Use transparent pixel so no alt text or broken icon shows
        confirmationImage.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
        confirmationImage.alt = '';
        confirmationImage.classList.add('image-loading');
        imageLoadingText.style.display = 'block';
        // Start polling for the image
        pollForImage(figure.figure_key);
    }

    confirmationSection.classList.add('active');
}

async function pollForImage(figureKey) {
    const maxAttempts = 60; // up to 60 seconds
    for (let i = 0; i < maxAttempts; i++) {
        await new Promise(r => setTimeout(r, 1000));
        try {
            const resp = await fetch('/api/get_image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ figure_key: figureKey }),
            });
            const data = await resp.json();
            if (data.status === 'ready' && data.image_url) {
                confirmationImage.src = data.image_url;
                confirmationImage.alt = 'Historical scene';
                confirmationImage.classList.remove('image-loading');
                imageLoadingText.style.display = 'none';
                // Update current figure with the image URL
                if (currentFigure) {
                    currentFigure.image_url = data.image_url;
                }
                return;
            }
        } catch (e) {
            // Keep polling
        }
    }
}

function showChat(figure, openingMessage) {
    confirmationSection.classList.remove('active');
    landingPage.style.display = 'none';
    chatSection.classList.add('active');

    // Select the right voice for this character's culture and gender
    selectZombieVoice(figure.voice_gender, figure.voice_region);

    chatSidebarImage.src = figure.image_url;
    chatFigureName.textContent = figure.name;
    chatFigureDetail.textContent = `${figure.location} — ${figure.era}`;

    // Clear old messages (keep typing indicator)
    const messages = chatMessages.querySelectorAll('.message');
    messages.forEach(m => m.remove());

    addZombieMessage(openingMessage);
    chatInput.focus();
}

// ===== API CALLS =====
async function identifyFigure(query) {
    const response = await fetch('/api/identify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
    });

    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'Failed to identify figure');
    }

    return await response.json();
}

async function startConversation(figure) {
    const response = await fetch('/api/start_conversation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ figure, figure_key: figure.figure_key }),
    });

    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'Failed to start conversation');
    }

    return await response.json();
}

async function sendMessage(message) {
    const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message }),
    });

    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'Failed to send message');
    }

    return await response.json();
}

async function endConversation() {
    if (sessionId) {
        await fetch('/api/end_conversation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
        });
        sessionId = null;
    }
}

// ===== CHAT MESSAGES =====
function addZombieMessage(text) {
    const div = document.createElement('div');
    div.className = 'message message-zombie';
    div.innerHTML = `<div class="message-sender">${escapeHtml(currentFigure?.name || 'The Dead')}</div>${escapeHtml(text)}`;
    chatMessages.insertBefore(div, typingIndicator);
    scrollToBottom();
    // Auto-speak the zombie's message
    speakZombie(text);
}

function addUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'message message-user';
    div.textContent = text;
    chatMessages.insertBefore(div, typingIndicator);
    scrollToBottom();
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showTyping() {
    typingIndicator.classList.add('active');
    scrollToBottom();
}

function hideTyping() {
    typingIndicator.classList.remove('active');
}

// ===== EVENT HANDLERS =====

// Search / summon
async function handleSearch() {
    const query = searchInput.value.trim();
    if (!query) return;

    searchBtn.disabled = true;
    showLoading();

    try {
        const figure = await identifyFigure(query);
        currentFigure = figure;
        hideLoading();
        showConfirmation(figure);
    } catch (err) {
        hideLoading();
        alert('The spirits could not be reached: ' + err.message);
    } finally {
        searchBtn.disabled = false;
    }
}

searchBtn.addEventListener('click', handleSearch);
searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleSearch();
});

// Suggestion cards
document.querySelectorAll('.suggestion-card').forEach(card => {
    card.addEventListener('click', () => {
        const name = card.dataset.name;
        const era = card.dataset.era || '';
        const location = card.dataset.location || '';
        // Include era and location context so the AI places them correctly
        searchInput.value = `${name} from ${location}, ${era}`;
        handleSearch();
    });
});

// Confirmation buttons
document.getElementById('btn-confirm').addEventListener('click', async () => {
    // If user is not logged in and we haven't shown the auth prompt yet, show it
    if (!currentUser && !authPromptShown) {
        authPromptShown = true;
        pendingAwaken = true;
        showAuthModal();
        return;
    }
    proceedToAwaken();
});

async function proceedToAwaken() {
    confirmationSection.classList.remove('active');
    showLoading();
    loadingText.textContent = "The dead awakens...";
    loadingSubtext.textContent = "Flesh knits over ancient bone";

    try {
        const result = await startConversation(currentFigure);
        sessionId = result.session_id;
        hideLoading();
        showChat(currentFigure, result.message);

        // Show save hint in chat if not logged in
        const saveHint = document.getElementById('chat-save-hint');
        if (!currentUser && saveHint) {
            saveHint.style.display = 'block';
        }
    } catch (err) {
        hideLoading();
        alert('The ritual failed: ' + err.message);
        showLanding();
    }
}

document.getElementById('btn-cancel').addEventListener('click', () => {
    currentFigure = null;
    showLanding();
});

// Chat send
async function handleChatSend() {
    const message = chatInput.value.trim();
    if (!message) return;

    chatInput.value = '';
    chatSendBtn.disabled = true;
    chatInput.disabled = true;

    addUserMessage(message);
    showTyping();

    try {
        const result = await sendMessage(message);
        hideTyping();
        addZombieMessage(result.message);
    } catch (err) {
        hideTyping();
        addZombieMessage("*bones rattle* ...forgive me, my mind went dark for a moment. The connection to the living world falters. Try again?");
    } finally {
        chatSendBtn.disabled = false;
        chatInput.disabled = false;
        chatInput.focus();
    }
}

chatSendBtn.addEventListener('click', handleChatSend);
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleChatSend();
});

// Mic button
chatMicBtn.addEventListener('click', () => {
    if (isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
});

// Back to landing
document.getElementById('chat-back-btn').addEventListener('click', async () => {
    window.speechSynthesis.cancel(); // Stop any zombie speech
    await endConversation();
    currentFigure = null;
    chatSection.classList.remove('active');
    showLanding();
});

// ===== INIT =====
initBackground();
initSpeechRecognition();
checkAuthStatus();
// Pre-load voices (some browsers load async, some sync)
window.speechSynthesis.getVoices();
window.speechSynthesis.onvoiceschanged = () => {
    const voices = window.speechSynthesis.getVoices();
    console.log(`Loaded ${voices.length} voices`);
};
searchInput.focus();
