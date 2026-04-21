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

// ===== ZOMBIE VOICE (ElevenLabs Text-to-Speech) =====
let currentZombieAudio = null;   // Currently playing Audio object
let zombieVoiceEnabled = true;   // User can toggle voice on/off

async function speakZombie(text) {
    if (!zombieVoiceEnabled) return;

    // Stop any currently playing zombie speech
    stopZombieSpeech();

    const gender = (currentFigure?.voice_gender || 'male').toLowerCase();
    const region = (currentFigure?.voice_region || 'british').toLowerCase();

    try {
        const response = await fetch('/api/speak', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, gender, region }),
        });

        if (!response.ok) {
            console.warn('ElevenLabs TTS failed, falling back to browser voice');
            speakZombieFallback(text, gender, region);
            return;
        }

        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);
        const audio = new Audio(audioUrl);
        audio.volume = 1.0;
        currentZombieAudio = audio;

        audio.onended = () => {
            URL.revokeObjectURL(audioUrl);
            currentZombieAudio = null;
        };
        audio.onerror = () => {
            URL.revokeObjectURL(audioUrl);
            currentZombieAudio = null;
        };

        await audio.play();
    } catch (err) {
        console.warn('ElevenLabs error:', err.message, '— falling back to browser voice');
        speakZombieFallback(text, gender, region);
    }
}

function stopZombieSpeech() {
    if (currentZombieAudio) {
        currentZombieAudio.pause();
        currentZombieAudio = null;
    }
    // Also stop any browser fallback speech
    if (window.speechSynthesis) window.speechSynthesis.cancel();
}

// Browser SpeechSynthesis fallback — used when ElevenLabs is unavailable
function speakZombieFallback(text, gender, region) {
    const synth = window.speechSynthesis;
    if (!synth) return;
    synth.cancel();

    const cleanText = text.replace(/\*[^*]+\*/g, '... ');
    const utterance = new SpeechSynthesisUtterance(cleanText);

    // Zombie-ify: low pitch, slow rate
    utterance.pitch = gender === 'female' ? 0.7 : 0.35;
    utterance.rate = 0.82;
    utterance.volume = 1.0;

    // Try to pick an English voice
    const voices = synth.getVoices();
    const english = voices.filter(v => v.lang.startsWith('en'));
    if (english.length) utterance.voice = english[0];

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
    stopZombieSpeech();
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

// initBackground() is now in shared.js

// ===== LOADING SCREEN =====
const loadingMessages = [
    { text: "Disturbing the grave...", sub: "The earth trembles" },
    { text: "Searching the crypts...", sub: "Cobwebs part before you" },
    { text: "The ground cracks open...", sub: "Something stirs below" },
    { text: "Bones reassemble...", sub: "Dust becomes flesh" },
    { text: "A hand reaches upward...", sub: "The dead do not rest easy" },
    { text: "Summoning from the beyond...", sub: "Between worlds, a soul wanders" },
];

// Loading music
const loadingMusic = new Audio('/static/sounds/dead-awakened.mp3');
loadingMusic.loop = true;
loadingMusic.volume = 0.5;

function showLoading() {
    const msg = loadingMessages[Math.floor(Math.random() * loadingMessages.length)];
    loadingText.textContent = msg.text;
    loadingSubtext.textContent = msg.sub;

    // Reset the image animation so it plays fresh each time
    const img = document.getElementById('loading-image');
    if (img) {
        img.style.animation = 'none';
        // Force reflow to restart animation
        void img.offsetHeight;
        img.style.animation = '';
    }

    loadingOverlay.classList.add('active');

    // Play music (may be blocked by autoplay policy on first interaction,
    // but by this point the user has clicked a button so it should be allowed)
    loadingMusic.currentTime = 0;
    loadingMusic.play().catch(() => {});
}

function hideLoading() {
    loadingOverlay.classList.remove('active');

    // Fade out the music
    const fadeOut = setInterval(() => {
        if (loadingMusic.volume > 0.05) {
            loadingMusic.volume = Math.max(0, loadingMusic.volume - 0.05);
        } else {
            loadingMusic.pause();
            loadingMusic.volume = 0.5;  // Reset for next time
            clearInterval(fadeOut);
        }
    }, 80);
}

// ===== VIEWS =====
function showLanding() {
    landingPage.style.display = 'flex';
    confirmationSection.classList.remove('active');
    chatSection.classList.remove('active');
    searchInput.value = '';
    searchInput.focus();
}

// ===== CONFIRMATION IMAGE-LOADING ATMOSPHERE =====
const cryptMessages = [
    "Prying open the crypt...",
    "The stone scrapes aside...",
    "Something stirs in the dark...",
    "Brushing the dust from their face...",
    "The veil between worlds thins...",
    "Cold fingers reach through the earth...",
    "A shape forms in the shadows...",
    "The dead do not forget their face...",
];

// Atmospheric sounds for the image-loading phase
const cryptThud = new Audio('/static/sounds/thud.mp3');
const cryptCreak = new Audio('/static/sounds/creak-long.mp3');
const cryptRumble = new Audio('/static/sounds/earth-rumble.mp3');
let cryptThudInterval = null;
let cryptMessageInterval = null;
let cryptSoundsPlaying = false;

function startCryptAtmosphere() {
    if (cryptSoundsPlaying) return;
    cryptSoundsPlaying = true;

    // Play a long creak to open
    cryptCreak.volume = 0.3;
    cryptCreak.currentTime = 0;
    cryptCreak.play().catch(() => {});

    // After the creak, start a low rumble
    setTimeout(() => {
        if (!cryptSoundsPlaying) return;
        cryptRumble.volume = 0.15;
        cryptRumble.currentTime = 0;
        cryptRumble.play().catch(() => {});
    }, 1500);

    // Slow rhythmic thuds — like pounding from inside a coffin
    let thudCount = 0;
    cryptThudInterval = setInterval(() => {
        if (!cryptSoundsPlaying) return;
        cryptThud.volume = 0.2 + Math.random() * 0.15; // Slight variation
        cryptThud.currentTime = 0;
        cryptThud.play().catch(() => {});
        thudCount++;
    }, 2200);

    // Cycle through eerie text messages
    let msgIndex = Math.floor(Math.random() * cryptMessages.length);
    imageLoadingText.textContent = cryptMessages[msgIndex];
    cryptMessageInterval = setInterval(() => {
        msgIndex = (msgIndex + 1) % cryptMessages.length;
        // Fade out, swap text, fade in
        imageLoadingText.style.opacity = '0';
        setTimeout(() => {
            imageLoadingText.textContent = cryptMessages[msgIndex];
            imageLoadingText.style.opacity = '1';
        }, 400);
    }, 3500);
}

function stopCryptAtmosphere() {
    cryptSoundsPlaying = false;

    if (cryptThudInterval) {
        clearInterval(cryptThudInterval);
        cryptThudInterval = null;
    }
    if (cryptMessageInterval) {
        clearInterval(cryptMessageInterval);
        cryptMessageInterval = null;
    }

    // Fade out all crypt sounds
    [cryptThud, cryptCreak, cryptRumble].forEach(audio => {
        const fadeOut = setInterval(() => {
            if (audio.volume > 0.03) {
                audio.volume = Math.max(0, audio.volume - 0.03);
            } else {
                audio.pause();
                clearInterval(fadeOut);
            }
        }, 60);
    });
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
        // Start atmospheric sounds and text cycling
        startCryptAtmosphere();
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
                // Stop the atmospheric sounds
                stopCryptAtmosphere();
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
    // Timed out — stop sounds anyway
    stopCryptAtmosphere();
}

function showChat(figure, openingMessage) {
    confirmationSection.classList.remove('active');
    landingPage.style.display = 'none';
    chatSection.classList.add('active');

    chatSidebarImage.src = figure.image_url;
    chatFigureName.textContent = figure.name;
    chatFigureDetail.textContent = `${figure.location} — ${figure.era}`;

    // Clear old messages (keep typing indicator)
    const messages = chatMessages.querySelectorAll('.message');
    messages.forEach(m => m.remove());

    appAddZombieMessage(openingMessage);
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
// Core functions (escapeHtml, formatZombieText, scrollToBottom, etc.) are in shared.js
// These wrappers bind them to this page's DOM elements and add voice

function appAddZombieMessage(text) {
    addZombieMessage(chatMessages, typingIndicator, currentFigure?.name, text);
    // Auto-speak the zombie's message
    speakZombie(text);
}

function appAddUserMessage(text) {
    addUserMessage(chatMessages, typingIndicator, text);
}

function appShowTyping() {
    showTyping(typingIndicator, chatMessages);
}

function appHideTyping() {
    hideTyping(typingIndicator);
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
        showToast('The spirits could not be reached: ' + err.message);
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
    stopCryptAtmosphere();
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
        showToast('The ritual failed: ' + err.message);
        showLanding();
    }
}

document.getElementById('btn-cancel').addEventListener('click', () => {
    stopCryptAtmosphere();
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

    appAddUserMessage(message);
    appShowTyping();

    try {
        const result = await sendMessage(message);
        appHideTyping();
        appAddZombieMessage(result.message);
    } catch (err) {
        appHideTyping();
        appAddZombieMessage("*bones rattle* ...forgive me, my mind went dark for a moment. The connection to the living world falters. Try again?");
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
    stopZombieSpeech(); // Stop any zombie speech
    await endConversation();
    currentFigure = null;
    chatSection.classList.remove('active');
    showLanding();
});

// ===== INIT =====
initBackground();
initSpeechRecognition();
checkAuthStatus();
searchInput.focus();
