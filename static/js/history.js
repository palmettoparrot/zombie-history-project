// ===== STATE =====
let currentFigure = null;
let sessionId = null;

// ===== DOM ELEMENTS =====
const historyPage = document.getElementById('history-page');
const loadingOverlay = document.getElementById('loading-overlay');
const loadingText = document.getElementById('loading-text');
const loadingSubtext = document.getElementById('loading-subtext');
const chatSection = document.getElementById('chat-section');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const chatSendBtn = document.getElementById('chat-send-btn');
const chatPortrait = document.getElementById('chat-portrait');
const chatScene = document.getElementById('chat-scene');
const chatFigureName = document.getElementById('chat-figure-name');
const chatFigureDetail = document.getElementById('chat-figure-detail');
const typingIndicator = document.getElementById('typing-indicator');

// ===== BACKGROUND =====
function initBackground() {
    const canvas = document.getElementById('background-canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const particles = [];
    for (let i = 0; i < 50; i++) {
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

// ===== HELPERS =====
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showLoading() {
    loadingOverlay.classList.add('active');
}

function hideLoading() {
    loadingOverlay.classList.remove('active');
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addZombieMessage(text) {
    const div = document.createElement('div');
    div.className = 'message message-zombie';
    div.innerHTML = `<div class="message-sender">${escapeHtml(currentFigure?.name || 'The Dead')}</div>${escapeHtml(text)}`;
    chatMessages.insertBefore(div, typingIndicator);
    scrollToBottom();
}

function addUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'message message-user';
    div.textContent = text;
    chatMessages.insertBefore(div, typingIndicator);
    scrollToBottom();
}

function showTyping() {
    typingIndicator.classList.add('active');
    scrollToBottom();
}

function hideTyping() {
    typingIndicator.classList.remove('active');
}

// ===== RESUME CONVERSATION =====
async function resumeConversation(sid) {
    showLoading();
    try {
        const response = await fetch(`/api/resume/${sid}`);
        if (!response.ok) throw new Error('Failed to resume');
        const data = await response.json();

        sessionId = data.session_id;
        currentFigure = data.figure;

        hideLoading();

        // Show chat
        historyPage.style.display = 'none';
        chatSection.classList.add('active');

        chatPortrait.src = data.figure.image_url || '';
        chatScene.src = data.figure.image_url || '';
        chatFigureName.textContent = data.figure.name;
        chatFigureDetail.textContent = `${data.figure.location} — ${data.figure.era}`;

        // Clear and replay messages
        const oldMessages = chatMessages.querySelectorAll('.message');
        oldMessages.forEach(m => m.remove());

        data.messages.forEach(msg => {
            if (msg.role === 'assistant') {
                addZombieMessage(msg.content);
            } else {
                addUserMessage(msg.content);
            }
        });

        chatInput.focus();
    } catch (err) {
        hideLoading();
        alert('Could not reawaken this zombie: ' + err.message);
    }
}

// ===== SEND MESSAGE =====
async function handleChatSend() {
    const message = chatInput.value.trim();
    if (!message) return;

    chatInput.value = '';
    chatSendBtn.disabled = true;
    chatInput.disabled = true;

    addUserMessage(message);
    showTyping();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, message }),
        });
        const result = await response.json();
        hideTyping();
        addZombieMessage(result.message);
    } catch (err) {
        hideTyping();
        addZombieMessage("*bones rattle* ...forgive me, my mind went dark for a moment. Try again?");
    } finally {
        chatSendBtn.disabled = false;
        chatInput.disabled = false;
        chatInput.focus();
    }
}

// ===== EVENT LISTENERS =====

// History card clicks
document.querySelectorAll('.history-page-card').forEach(card => {
    card.addEventListener('click', (e) => {
        if (e.target.classList.contains('history-page-delete-btn')) return;
        resumeConversation(card.dataset.sessionId);
    });
});

// Delete buttons
document.querySelectorAll('.history-page-delete-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const sid = btn.dataset.sessionId;
        const card = btn.closest('.history-page-card');
        const name = card.querySelector('.history-page-card-name')?.textContent || 'this zombie';

        if (confirm(`Lay ${name} to rest permanently?`)) {
            await fetch(`/api/delete_conversation/${sid}`, { method: 'DELETE' });
            card.remove();

            // Check if grid is empty
            const grid = document.querySelector('.history-page-grid');
            if (grid && grid.children.length === 0) {
                location.reload();
            }
        }
    });
});

// Chat send
chatSendBtn.addEventListener('click', handleChatSend);
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleChatSend();
});

// Back button
document.getElementById('chat-back-btn').addEventListener('click', async () => {
    if (sessionId) {
        await fetch('/api/end_conversation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
        });
        sessionId = null;
    }
    chatSection.classList.remove('active');
    historyPage.style.display = 'flex';
});

// ===== INIT =====
initBackground();
