// ===== SHARED UTILITIES =====
// Common functions used by both app.js and history.js

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatZombieText(text) {
    // Split text on *action* patterns, preserving the delimiters
    // Each *...* block becomes its own styled line
    const parts = text.split(/(\*[^*]+\*)/g);
    let html = '';
    for (const part of parts) {
        if (!part) continue;
        if (part.startsWith('*') && part.endsWith('*')) {
            // Action/stage direction — strip asterisks, style differently
            const action = part.slice(1, -1).trim();
            html += `<div class="action-text">${escapeHtml(action)}</div>`;
        } else {
            // Dialogue text
            const trimmed = part.trim();
            if (trimmed) {
                html += `<div class="dialogue-text">${escapeHtml(trimmed)}</div>`;
            }
        }
    }
    return html;
}

function scrollToBottom(container) {
    container.scrollTop = container.scrollHeight;
}

function addZombieMessage(container, typingIndicator, figureName, text) {
    const div = document.createElement('div');
    div.className = 'message message-zombie';
    div.innerHTML = `<div class="message-sender">${escapeHtml(figureName || 'The Dead')}</div>${formatZombieText(text)}`;
    container.insertBefore(div, typingIndicator);
    scrollToBottom(container);

    // Play sound effects for any action text
    playActionSounds(text);
}

function addUserMessage(container, typingIndicator, text) {
    const div = document.createElement('div');
    div.className = 'message message-user';
    div.textContent = text;
    container.insertBefore(div, typingIndicator);
    scrollToBottom(container);
}

function showTyping(typingIndicator, container) {
    typingIndicator.classList.add('active');
    scrollToBottom(container);
}

function hideTyping(typingIndicator) {
    typingIndicator.classList.remove('active');
}

// ===== BACKGROUND PARTICLES =====
function initBackground() {
    const canvas = document.getElementById('background-canvas');
    if (!canvas) return;
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

    let animating = true;

    function animate() {
        if (!animating) return;
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

    // Pause animation when tab is not visible (saves battery)
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            animating = false;
        } else {
            animating = true;
            animate();
        }
    });
}

// ===== TOAST NOTIFICATIONS =====
// Replaces alert() with non-blocking in-page toasts
function showToast(message, type = 'error', duration = 5000) {
    // Create container if it doesn't exist
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    // Trigger animation
    requestAnimationFrame(() => toast.classList.add('visible'));

    // Auto-dismiss
    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    }, duration);

    // Click to dismiss
    toast.addEventListener('click', () => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    });
}

// ===== SOUND EFFECTS ENGINE =====
// Plays atmospheric sound effects when zombie action text matches keywords.
// Sounds play at low volume underneath the zombie's voice.

const SOUND_EFFECTS_VOLUME = 0.35;  // Keep effects quieter than voice

// Keyword-to-sound mapping. Each entry: { keywords: [...], sounds: [...], volume?: number }
// When action text matches ANY keyword, one of the sounds plays.
// Order matters — first match wins, so put specific matches before generic ones.
const SOUND_MAP = [
    // Bones & skeletal
    {
        keywords: ['bone', 'skeleton', 'skull', 'rib', 'jaw', 'spine', 'knuckle', 'crack', 'snap', 'pops'],
        sounds: ['bone-crack.mp3', 'bone-snap.mp3'],
    },
    // Finger/limb falling off
    {
        keywords: ['finger falls', 'hand falls', 'arm falls', 'drops off', 'falls off', 'detach', 'limb'],
        sounds: ['bone-snap.mp3', 'body-drop.mp3'],
    },
    // Rising from grave / earth
    {
        keywords: ['burst', 'rises', 'risen', 'emerge', 'crawl', 'grave', 'earth', 'ground', 'dirt', 'soil', 'tomb', 'crypt', 'coffin', 'burial', 'dig', 'claws through'],
        sounds: ['earth-break.mp3', 'earth-dig.mp3', 'earth-rumble.mp3', 'earth-move.mp3'],
    },
    // Squish / flesh / body horror
    {
        keywords: ['squish', 'squelch', 'ooze', 'flesh', 'peel', 'rot', 'decay', 'eyeball', 'eye pop', 'eye dangle', 'maggot', 'worm', 'slime', 'goo', 'moist', 'wet'],
        sounds: ['squish.mp3'],
    },
    // Chains & metal
    {
        keywords: ['chain', 'shackle', 'manacle', 'iron', 'metal', 'sword', 'blade', 'shield', 'armor', 'armour', 'helm', 'weapon'],
        sounds: ['chains.mp3', 'metal-clink.mp3', 'metal-clank.mp3'],
    },
    // Fire & flames
    {
        keywords: ['fire', 'flame', 'burn', 'torch', 'candle', 'ember', 'smoke', 'pyre', 'inferno'],
        sounds: ['fire.mp3'],
    },
    // Footsteps & movement
    {
        keywords: ['step', 'walk', 'stride', 'lumber', 'shuffle', 'approach', 'pace', 'march'],
        sounds: ['footsteps.mp3', 'footsteps-crunch.mp3'],
    },
    // Heavy impact / thud
    {
        keywords: ['slam', 'pound', 'smash', 'crash', 'punch', 'strike', 'hit', 'thud', 'stomp', 'kick'],
        sounds: ['thud.mp3', 'body-drop.mp3'],
    },
    // Falling / dropping
    {
        keywords: ['fall', 'drop', 'collapse', 'tumble', 'crumble', 'topple'],
        sounds: ['body-drop.mp3', 'thud.mp3'],
    },
    // Creaking — doors, joints, wood
    {
        keywords: ['creak', 'groan', 'croak', 'wheeze', 'door', 'gate', 'hinge', 'wood', 'floorboard', 'stiff', 'joint'],
        sounds: ['creak.mp3', 'creak-long.mp3'],
    },
    // Ghostly / supernatural
    {
        keywords: ['ghost', 'spirit', 'haunt', 'phantom', 'spectral', 'ethereal', 'shadow', 'darkness', 'beyond', 'otherworld', 'void', 'whisper', 'moan', 'wail', 'howl'],
        sounds: ['ghost.mp3'],
        volume: 0.25,  // Extra subtle for atmosphere
    },
    // Crown / jewelry / adjusting items (use metal clink)
    {
        keywords: ['crown', 'jewel', 'ring', 'necklace', 'amulet', 'medallion', 'tiara', 'scepter', 'adjust', 'straighten'],
        sounds: ['metal-clink.mp3'],
        volume: 0.25,
    },
];

// Audio cache — preload sounds so they play instantly
const soundCache = {};

function preloadSounds() {
    const allSounds = new Set();
    SOUND_MAP.forEach(entry => entry.sounds.forEach(s => allSounds.add(s)));
    allSounds.forEach(filename => {
        const audio = new Audio(`/static/sounds/${filename}`);
        audio.preload = 'auto';
        soundCache[filename] = audio;
    });
}

function playSound(filename, volume) {
    try {
        // Clone the cached audio so multiple sounds can overlap
        const src = soundCache[filename];
        if (!src) return;
        const audio = src.cloneNode();
        audio.volume = volume;
        audio.play().catch(() => {});  // Ignore autoplay restrictions silently
    } catch (e) {
        // Sound effects are non-critical — never break the app
    }
}

function playActionSounds(text) {
    // Extract all action text between asterisks
    const actions = [];
    const regex = /\*([^*]+)\*/g;
    let match;
    while ((match = regex.exec(text)) !== null) {
        actions.push(match[1].toLowerCase());
    }
    if (actions.length === 0) return;

    // For each action block, find the first matching sound category
    const played = new Set();  // Don't play the same sound file twice per message
    let delay = 0;

    actions.forEach(action => {
        for (const entry of SOUND_MAP) {
            const matched = entry.keywords.some(kw => action.includes(kw));
            if (matched) {
                // Pick a random sound from the category
                const candidates = entry.sounds.filter(s => !played.has(s));
                if (candidates.length === 0) break;
                const sound = candidates[Math.floor(Math.random() * candidates.length)];
                played.add(sound);

                const vol = entry.volume || SOUND_EFFECTS_VOLUME;

                // Stagger multiple sounds slightly so they don't all hit at once
                setTimeout(() => playSound(sound, vol), delay);
                delay += 600;  // 600ms gap between effects
                break;  // Only one sound per action block
            }
        }
    });
}

// Preload sounds on page load
preloadSounds();
