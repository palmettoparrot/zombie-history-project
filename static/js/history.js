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

// ===== HELPERS =====
// Core functions (escapeHtml, formatZombieText, addZombieMessage, etc.) are in shared.js

function showLoading() {
    loadingOverlay.classList.add('active');
}

function hideLoading() {
    loadingOverlay.classList.remove('active');
}

function histAddZombieMessage(text) {
    addZombieMessage(chatMessages, typingIndicator, currentFigure?.name, text);
}

function histAddUserMessage(text) {
    addUserMessage(chatMessages, typingIndicator, text);
}

function histShowTyping() {
    showTyping(typingIndicator, chatMessages);
}

function histHideTyping() {
    hideTyping(typingIndicator);
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
                histAddZombieMessage(msg.content);
            } else {
                histAddUserMessage(msg.content);
            }
        });

        chatInput.focus();
    } catch (err) {
        hideLoading();
        showToast('Could not reawaken this zombie: ' + err.message);
    }
}

// ===== SEND MESSAGE =====
async function handleChatSend() {
    const message = chatInput.value.trim();
    if (!message) return;

    chatInput.value = '';
    chatSendBtn.disabled = true;
    chatInput.disabled = true;

    histAddUserMessage(message);
    histShowTyping();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, message }),
        });
        const result = await response.json();
        histHideTyping();
        histAddZombieMessage(result.message);
    } catch (err) {
        histHideTyping();
        histAddZombieMessage("*bones rattle* ...forgive me, my mind went dark for a moment. Try again?");
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
