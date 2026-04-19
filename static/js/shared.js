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
