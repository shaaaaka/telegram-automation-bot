// --- Tab 2: CRM Chat Room Tab & WebSockets ---

let chatSidebarTab = 'active'; // 'active' or 'completed'
try {
    const savedSidebarTab = localStorage.getItem('chatSidebarTab');
    if (savedSidebarTab === 'active' || savedSidebarTab === 'completed') {
        chatSidebarTab = savedSidebarTab;
    }
} catch (e) {}
let cachedCompletedSessions = [];
let chatUnreadCounts = {};
let selectedChatClientId = null;
let chatWs = null;

function setChatSidebarTab(type) {
    chatSidebarTab = type;
    try {
        localStorage.setItem('chatSidebarTab', type);
    } catch (e) {}
    document.querySelectorAll('.sidebar-tab').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(`chat-sidebar-tab-${type}`);
    if (activeBtn) activeBtn.classList.add('active');
    
    if (type === 'completed') {
        loadCompletedSessions();
    } else {
        renderChatSidebar();
    }
}

async function loadCompletedSessions() {
    try {
        const res = await fetch('/api/sessions/completed');
        cachedCompletedSessions = await res.json();
        renderChatSidebar();
    } catch (err) {
        console.error("Failed to load completed sessions:", err);
    }
}

function loadChatSessions() {
    document.querySelectorAll('.sidebar-tab').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(`chat-sidebar-tab-${chatSidebarTab}`);
    if (activeBtn) activeBtn.classList.add('active');

    if (chatSidebarTab === 'completed') {
        loadCompletedSessions();
    } else {
        renderChatSidebar();
    }
}

function renderChatSidebar() {
    const container = document.getElementById('chat-sidebar-list-container');
    if (!container) return;
    container.innerHTML = '';
    
    const searchQuery = document.getElementById('chat-search-input').value.toLowerCase().trim();
    const list = chatSidebarTab === 'completed' ? cachedCompletedSessions : lastFetchedSessions;
    
    const savedId = localStorage.getItem('selectedChatClientId');
    if (savedId && selectedChatClientId === null && list && list.length > 0) {
        const parsedSavedId = parseInt(savedId);
        if (list.some(s => s.client_id === parsedSavedId)) {
            setTimeout(() => {
                if (selectedChatClientId === null) {
                    selectChatClient(parsedSavedId);
                }
            }, 0);
        }
    }

    if (!list || list.length === 0) {
        container.innerHTML = '<div style="padding:20px;text-align:center;color:rgba(255,255,255,0.3);font-size:0.85rem;">Список порожній</div>';
        return;
    }
    
    list.forEach(session => {
        const displayName = extractDisplayName(session.client_data, session.username);
        if (searchQuery && !displayName.toLowerCase().includes(searchQuery) && !String(session.client_id).includes(searchQuery)) {
            return;
        }
        
        const item = document.createElement('div');
        item.className = `chat-item ${selectedChatClientId === session.client_id ? 'active' : ''}`;
        item.onclick = () => selectChatClient(session.client_id);
        
        const avatarChar = displayName.replace(/^@/, '').substring(0, 1).toUpperCase() || 'К';
        const unreadCount = chatUnreadCounts[session.client_id] || 0;
        
        let previewText = '';
        if (session.last_message) {
            let senderLabel = '';
            if (session.last_message.sender === 'client') {
                senderLabel = 'Клієнт';
            } else if (session.last_message.sender === 'bot') {
                senderLabel = 'Бот';
            } else {
                senderLabel = 'Оператор';
            }
            
            let msgPreview = session.last_message.text || '';
            if (session.last_message.photo) {
                msgPreview = '📷 Фотографія';
            }
            msgPreview = msgPreview.replace(/<\/?[^>]+(>|$)/g, "");
            previewText = `${senderLabel}: ${msgPreview}`;
        } else {
            previewText = session.status === 'completed' ? 'Архівна сесія' : 'Немає повідомлень';
        }
        
        item.innerHTML = `
            <div class="chat-item-avatar">
                <span id="sidebar-avatar-placeholder-${session.client_id}" style="display: none;">${avatarChar}</span>
                <img src="/api/avatar/${session.client_id}" onerror="this.remove(); const el = document.getElementById('sidebar-avatar-placeholder-${session.client_id}'); if(el) el.style.display='inline-flex';">
            </div>
            <div class="chat-item-info">
                <div class="chat-item-top">
                    <span class="chat-item-name">${displayName}</span>
                    <span class="chat-item-time">${formatChatTime(session.created_at)}</span>
                </div>
                <div class="chat-item-bottom" style="display: flex; justify-content: space-between; align-items: center; min-height: 18px; margin-top: 4px;">
                    <span class="chat-item-preview" style="max-width: 80%; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-size: 0.78rem; color: rgba(255, 255, 255, 0.4);">${previewText}</span>
                    ${unreadCount > 0 ? `<span class="chat-item-badge" style="margin-left: auto;">${unreadCount}</span>` : ''}
                </div>
            </div>
        `;
        container.appendChild(item);
    });
}

function parseUtcToLocal(dateStr) {
    if (!dateStr) return null;
    try {
        let isoStr = dateStr;
        if (!dateStr.includes('T')) {
            isoStr = dateStr.replace(' ', 'T');
        }
        if (!isoStr.endsWith('Z')) {
            isoStr += 'Z';
        }
        const date = new Date(isoStr);
        return isNaN(date.getTime()) ? null : date;
    } catch (e) {
        return null;
    }
}

function formatChatTime(dateStr) {
    const localDate = parseUtcToLocal(dateStr);
    if (!localDate) return dateStr || '';
    const hours = String(localDate.getHours()).padStart(2, '0');
    const minutes = String(localDate.getMinutes()).padStart(2, '0');
    return `${hours}:${minutes}`;
}

function getSessionStatusTextLocal(status) {
    switch (status) {
        case 'registered': return 'Зареєстрований';
        case 'number_assigned': return 'Номер видано';
        case 'waiting_code': return 'Очікує код ⏳';
        case 'completed': return 'Завершено';
        default: return status;
    }
}

function filterChatSidebar() {
    renderChatSidebar();
}

function toggleChatActionsMenu(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('chat-actions-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('active');
    }
}

async function clearChatHistory(clientId) {
    const confirmed = await showConfirm("Ви впевнені, що хочете очистити всю історію повідомлень для цього клієнта?", "danger");
    if (!confirmed) return;
    
    try {
        const res = await fetch(`/api/sessions/${clientId}/clear-chat`, {
            method: 'POST'
        });
        if (res.ok) {
            showToast("Історію чату успішно очищено!", "success");
            if (selectedChatClientId === clientId) {
                refreshChatPageMessages(clientId);
            }
        } else {
            const err = await res.json();
            showToast("Помилка: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося очистити історію", "error");
    }
}

async function deleteChatCompletely(clientId) {
    const confirmed = await showConfirm("Ви впевнені, що хочете ПОВНІСТЮ видалити цей чат, всю його історію та сесію з сайту?", "danger");
    if (!confirmed) return;
    
    try {
        const res = await fetch(`/api/sessions/${clientId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showToast("Чат повністю видалено з сайту!", "success");
            if (selectedChatClientId === clientId) {
                selectedChatClientId = null;
                try {
                    localStorage.removeItem('selectedChatClientId');
                } catch (e) {}
                const windowContainer = document.getElementById('chat-window-container');
                if (windowContainer) {
                    windowContainer.innerHTML = `
                        <div class="chat-no-selection">
                            <div class="chat-no-selection-icon">💬</div>
                            <p>Оберіть чат зі списку ліворуч, щоб розпочати листування</p>
                        </div>
                    `;
                }
            }
            pollData();
            if (chatSidebarTab === 'completed') {
                loadCompletedSessions();
            }
        } else {
            const err = await res.json();
            showToast("Помилка: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося видалити чат", "error");
    }
}

async function toggleAISetting(clientId) {
    try {
        const res = await fetch(`/api/sessions/${clientId}/toggle-ai`, {
            method: 'POST'
        });
        if (res.ok) {
            const data = await res.json();
            showToast(data.is_paused ? "ШІ-бота призупинено для цього клієнта!" : "ШІ-бота активовано для цього клієнта!", "success");
            
            const allSessions = [...(lastFetchedSessions || []), ...(cachedCompletedSessions || [])];
            const session = allSessions.find(s => s.client_id === clientId);
            if (session) {
                session.is_paused = data.is_paused ? 1 : 0;
            }
            
            if (selectedChatClientId === clientId) {
                selectChatClient(clientId);
            }
            renderChatSidebar();
        } else {
            const err = await res.json();
            showToast("Помилка: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося змінити статус ШІ", "error");
    }
}

async function selectChatClient(clientId) {
    selectedChatClientId = clientId;
    try {
        localStorage.setItem('selectedChatClientId', clientId);
    } catch (e) {}
    chatUnreadCounts[clientId] = 0;
    renderChatSidebar();
    
    const layout = document.getElementById('chat-page-layout-container');
    if (layout) {
        layout.classList.add('chat-selected');
    }
    
    const windowContainer = document.getElementById('chat-window-container');
    if (!windowContainer) return;
    
    const allSessions = [...(lastFetchedSessions || []), ...(cachedCompletedSessions || [])];
    const session = allSessions.find(s => s.client_id === clientId);
    if (!session) {
        windowContainer.innerHTML = '<div style="padding:40px;text-align:center;color:red;">Помилка: клієнта не знайдено</div>';
        return;
    }
    
    const displayName = extractDisplayName(session.client_data, session.username);
    
    windowContainer.innerHTML = `
        <div class="chat-window-header">
            <div class="chat-window-client-info">
                <button class="chat-back-btn" onclick="backToChatList()">← Назад</button>
                <div class="chat-window-avatar">
                    <span id="avatar-placeholder-${session.client_id}" style="display: none;">${displayName.replace(/^@/, '').substring(0, 1).toUpperCase() || 'К'}</span>
                    <img src="/api/avatar/${session.client_id}" onerror="this.remove(); const el = document.getElementById('avatar-placeholder-${session.client_id}'); if(el) el.style.display='inline-flex';">
                </div>
                <div class="chat-window-details">
                    <span class="chat-window-name">${displayName}</span>
                </div>
            </div>
            <div class="chat-window-actions">
                <button class="chat-actions-btn" onclick="toggleChatActionsMenu(event)" title="Опції чату">⋮</button>
                <div class="chat-actions-dropdown" id="chat-actions-dropdown">
                    <button class="dropdown-item" onclick="toggleAISetting(${session.client_id})">
                        ${session.is_paused ? '▶ Увімкнути ШІ' : '⏸ Вимкнути ШІ'}
                    </button>
                    <button class="dropdown-item" onclick="clearChatHistory(${session.client_id})">Очистити історію</button>
                    <button class="dropdown-item danger" onclick="deleteChatCompletely(${session.client_id})">Видалити чат повністю</button>
                </div>
            </div>
        </div>
        <div class="chat-window-body" id="chat-window-body-container">
            <div style="text-align:center;color:rgba(255,255,255,0.3);padding:20px;">Завантаження повідомлень...</div>
        </div>
        <div class="chat-window-footer">
            <div class="chat-templates-row" id="chat-page-templates-row">
                <!-- Templates row -->
            </div>
            <div style="display: flex; align-items: center; gap: 12px; width: 100%;">
                <button class="btn-toggle-ai-bottom ${session.is_paused ? 'paused' : 'active'}" onclick="toggleAISetting(${session.client_id})" title="${session.is_paused ? 'ШІ вимкнено. Натисніть, щоб увімкнути.' : 'ШІ працює. Натисніть, щоб вимкнути.'}">
                    🤖
                </button>
                <div class="chat-input-wrapper" style="align-items: center; flex: 1;">
                    <textarea id="chat-msg-input" placeholder="Введіть повідомлення для клієнта..." rows="1" onkeydown="if(event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendChatPageMessage(); }"></textarea>
                    <button class="btn-send-message" onclick="sendChatPageMessage()" title="Надіслати">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="22" y1="2" x2="11" y2="13"></line>
                            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    `;
    
    renderChatPageTemplates();
    await refreshChatPageMessages(clientId);
    
    // Auto-focus the input textarea
    const textarea = document.getElementById('chat-msg-input');
    if (textarea) {
        textarea.focus();
    }
}

function backToChatList() {
    selectedChatClientId = null;
    try {
        localStorage.removeItem('selectedChatClientId');
    } catch (e) {}
    const layout = document.getElementById('chat-page-layout-container');
    if (layout) {
        layout.classList.remove('chat-selected');
    }
    const activeItems = document.querySelectorAll('.chat-item.active');
    activeItems.forEach(item => item.classList.remove('active'));
    
    const windowContainer = document.getElementById('chat-window-container');
    if (windowContainer) {
        windowContainer.innerHTML = `
            <div class="chat-no-selection">
                <div class="chat-no-selection-icon">💬</div>
                <p>Оберіть чат зі списку ліворуч, щоб розпочати листування</p>
            </div>
        `;
    }
    renderChatSidebar();
}

function renderChatPageTemplates() {
    const row = document.getElementById('chat-page-templates-row');
    if (!row) return;
    row.innerHTML = '';
    
    if (window.bankTemplates) {
        Object.keys(window.bankTemplates).forEach(key => {
            const t = window.bankTemplates[key];
            const btn = document.createElement('button');
            btn.className = 'chat-template-btn';
            btn.innerText = key;
            btn.title = t.text;
            btn.onclick = () => {
                const textarea = document.getElementById('chat-msg-input');
                if (textarea) {
                    textarea.value = t.text;
                    textarea.focus();
                }
            };
            row.appendChild(btn);
        });
    }
}

async function refreshChatPageMessages(clientId) {
    try {
        const res = await fetch(`/api/sessions/${clientId}/chat`);
        const logs = await res.json();
        
        const bodyContainer = document.getElementById('chat-window-body-container');
        if (!bodyContainer || selectedChatClientId !== clientId) return;
        
        bodyContainer.innerHTML = '';
        if (!logs || logs.length === 0) {
            bodyContainer.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.2);padding:40px;">Історія повідомлень порожня</div>';
            return;
        }
        
        const getSenderGroup = (sender) => {
            if (sender === 'client') return 'client';
            if (sender === 'bot') return 'bot';
            return 'support'; // admin or operator
        };

        logs.forEach((log, index) => {
            const nextLog = logs[index + 1];
            const hideAvatar = nextLog && getSenderGroup(nextLog.sender) === getSenderGroup(log.sender);
            renderSingleChatMessage(bodyContainer, log, hideAvatar);
        });
        
        scrollToBottom('chat-window-body-container');
    } catch (err) {
        console.error("Failed to load messages:", err);
    }
}

function renderSingleChatMessage(container, log, hideAvatar = false) {
    const allSessions = [...(lastFetchedSessions || []), ...(cachedCompletedSessions || [])];
    const session = allSessions.find(s => s.client_id === selectedChatClientId);
    const displayName = session ? extractDisplayName(session.client_data, session.username) : 'Клієнт';

    const containerDiv = document.createElement('div');
    containerDiv.className = `chat-msg-container ${log.sender}`;
    if (hideAvatar) {
        containerDiv.classList.add('same-sender-next');
    }
    
    let timeStr = '';
    if (log.created_at) {
        const localDate = parseUtcToLocal(log.created_at);
        if (localDate) {
            const hours = String(localDate.getHours()).padStart(2, '0');
            const minutes = String(localDate.getMinutes()).padStart(2, '0');
            timeStr = `${hours}:${minutes}`;
        } else {
            try {
                timeStr = log.created_at.split(' ')[1]?.substring(0, 5) || '';
            } catch (e) {}
        }
    }

    let contentHtml = '';
    let bubbleClass = 'chat-msg-bubble';
    if (log.photo_id) {
        bubbleClass += ' has-photo';
        if (!log.message_text) {
            bubbleClass += ' photo-only';
        }
    }

    if (log.photo_id) {
        contentHtml += `<img class="chat-msg-img" src="/api/photos/${log.photo_id}" onload="scrollToBottom('chat-window-body-container')" onclick="openLightbox(this.src)">`;
    }
    if (log.message_text) {
        let escapedText = escapeHtml(log.message_text);
        escapedText = escapedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        escapedText = escapedText.replace(/`/g, '');
        contentHtml += `<span class="chat-msg-text">${escapedText.replace(/\n/g, '<br>')}</span>`;
    }
    
    let timeClass = 'chat-msg-time-inline';
    if (log.photo_id && !log.message_text) {
        timeClass += ' photo-time';
    }
    contentHtml += `<span class="${timeClass}">${timeStr}</span>`;
    
    let headerHtml = '';
    let avatarLetter = 'К';
    
    if (log.sender === 'client') {
        avatarLetter = displayName.replace(/^@/, '').substring(0, 1).toUpperCase() || 'К';
    } else if (log.sender === 'bot') {
        avatarLetter = '🤖';
        headerHtml = `
            <div class="chat-msg-header" style="display: flex; margin-bottom: 4px;">
                <span class="badge-ai">⚡ AI-агент</span>
            </div>
        `;
    } else {
        avatarLetter = '👤';
        headerHtml = `
            <div class="chat-msg-header" style="display: flex; margin-bottom: 4px;">
                <span class="badge-operator">👤 Оператор</span>
            </div>
        `;
    }
    
    let avatarHtml = '';
    if (!hideAvatar) {
        if (log.sender === 'client') {
            const uniqueMsgId = Math.random().toString(36).substring(2, 9);
            avatarHtml = `
                <div class="chat-msg-avatar" style="position: relative; overflow: hidden;">
                    <span id="msg-avatar-placeholder-${uniqueMsgId}" style="display: none;">${avatarLetter}</span>
                    <img src="/api/avatar/${selectedChatClientId}" onerror="this.remove(); const el = document.getElementById('msg-avatar-placeholder-${uniqueMsgId}'); if(el) el.style.display='inline-flex';">
                </div>
            `;
        } else {
            avatarHtml = `<div class="chat-msg-avatar">${avatarLetter}</div>`;
        }
    } else {
        containerDiv.classList.add('no-avatar');
    }
    
    containerDiv.innerHTML = `
        ${headerHtml}
        <div class="chat-msg-body-row">
            ${avatarHtml}
            <div class="${bubbleClass}">
                ${contentHtml}
            </div>
        </div>
    `;
    container.appendChild(containerDiv);
}

function scrollToBottom(containerId) {
    const container = document.getElementById(containerId);
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

async function sendChatPageMessage() {
    const clientId = selectedChatClientId;
    if (!clientId) return;
    
    const textarea = document.getElementById('chat-msg-input');
    if (!textarea) return;
    
    const message = textarea.value.trim();
    if (!message) return;
    
    try {
        const res = await fetch(`/api/sessions/${clientId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        if (res.ok) {
            textarea.value = '';
        } else {
            showToast("Не вдалося надіслати повідомлення", "error");
        }
    } catch (err) {
        showToast("Помилка відправки запиту", "error");
    }
}

// WebSocket handler
function connectChatWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    chatWs = new WebSocket(`${protocol}//${host}/ws/chat`);
    
    chatWs.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'new_message') {
                handleIncomingWebSocketMessage(data);
            } else if (data.type === 'chat_cleared') {
                if (selectedChatClientId === data.client_id) {
                    const bodyContainer = document.getElementById('chat-window-body-container');
                    if (bodyContainer) {
                        bodyContainer.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.2);padding:40px;">Історія повідомлень порожня</div>';
                    }
                }
            } else if (data.type === 'session_deleted') {
                if (selectedChatClientId === data.client_id) {
                    selectedChatClientId = null;
                    try {
                        localStorage.removeItem('selectedChatClientId');
                    } catch (e) {}
                    const windowContainer = document.getElementById('chat-window-container');
                    if (windowContainer) {
                        windowContainer.innerHTML = `
                            <div class="chat-no-selection">
                                <div class="chat-no-selection-icon">💬</div>
                                <p>Оберіть чат зі списку ліворуч, щоб розпочати листування</p>
                            </div>
                        `;
                    }
                }
                pollData();
                if (chatSidebarTab === 'completed') {
                    loadCompletedSessions();
                }
            } else if (data.type === 'user_banned' || data.type === 'user_unbanned') {
                if (currentTab === 'banned') {
                    loadBannedUsers();
                }
                pollData();
            }
        } catch (e) {
            console.error("Failed to parse WS event:", e);
        }
    };
    
    chatWs.onclose = function() {
        console.log("Chat WS connection lost. Reconnecting in 3s...");
        setTimeout(connectChatWebSocket, 3000);
    };
}

function handleIncomingWebSocketMessage(data) {
    if (data.type === 'ai_toggled') {
        const allSessions = [...(lastFetchedSessions || []), ...(cachedCompletedSessions || [])];
        const session = allSessions.find(s => s.client_id === data.client_id);
        if (session) {
            session.is_paused = data.is_paused ? 1 : 0;
        }
        if (selectedChatClientId === data.client_id) {
            selectChatClient(data.client_id);
        }
        renderChatSidebar();
        return;
    }

    if (selectedChatClientId === data.client_id) {
        const bodyContainer = document.getElementById('chat-window-body-container');
        if (bodyContainer) {
            if (bodyContainer.innerHTML.includes('Історія повідомлень порожня')) {
                bodyContainer.innerHTML = '';
            }
            
            const lastMsgContainer = bodyContainer.lastElementChild;
            const getSenderGroup = (sender) => {
                if (sender === 'client') return 'client';
                if (sender === 'bot') return 'bot';
                return 'support'; // admin or operator
            };
            const getLastMsgSenderGroup = (container) => {
                if (container.classList.contains('client')) return 'client';
                if (container.classList.contains('bot')) return 'bot';
                return 'support';
            };
            const isSameGroup = lastMsgContainer && getSenderGroup(data.sender) === getLastMsgSenderGroup(lastMsgContainer);

            if (isSameGroup) {
                const prevAvatar = lastMsgContainer.querySelector('.chat-msg-avatar');
                if (prevAvatar) {
                    prevAvatar.remove();
                }
                lastMsgContainer.classList.add('no-avatar');
                lastMsgContainer.classList.add('same-sender-next');
            }

            const logObj = {
                sender: data.sender,
                message_text: data.message_text,
                photo_id: data.photo_id,
                created_at: data.created_at
            };
            renderSingleChatMessage(bodyContainer, logObj);
            scrollToBottom('chat-window-body-container');
        }
    } else {
        if (data.sender === 'client') {
            playSound('new_message');
        }
        chatUnreadCounts[data.client_id] = (chatUnreadCounts[data.client_id] || 0) + 1;
    }
    
    updateSidebarItemPreview(data.client_id, data.message_text || "[Фото]");
}

function updateSidebarItemPreview(clientId, text) {
    let found = false;
    if (lastFetchedSessions) {
        const session = lastFetchedSessions.find(s => s.client_id === clientId);
        if (session) {
            found = true;
            lastFetchedSessions = [session, ...lastFetchedSessions.filter(s => s.client_id !== clientId)];
        }
    }
    if (!found && cachedCompletedSessions) {
        const session = cachedCompletedSessions.find(s => s.client_id === clientId);
        if (session) {
            cachedCompletedSessions = [session, ...cachedCompletedSessions.filter(s => s.client_id !== clientId)];
        }
    }
    renderChatSidebar();
}

let currentPasteImageBlob = null;

document.addEventListener('paste', function(e) {
    if (!selectedChatClientId) return;
    
    const items = (e.clipboardData || window.clipboardData)?.items;
    if (!items) return;
    for (let index in items) {
        const item = items[index];
        if (item.kind === 'file' && item.type.indexOf('image/') !== -1) {
            const blob = item.getAsFile();
            if (blob) {
                showPhotoUploadModal(blob);
                e.preventDefault();
                break;
            }
        }
    }
});

document.addEventListener('keydown', function(e) {
    if (!selectedChatClientId) return;
    
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.key === 'Escape' || e.key === 'Enter' || e.key === 'Tab' || e.key === 'Shift') return;
    
    const activeEl = document.activeElement;
    if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA')) {
        return;
    }
    
    const textarea = document.getElementById('chat-msg-input');
    if (textarea) {
        textarea.focus();
    }
});

function showPhotoUploadModal(blob) {
    const preview = document.getElementById('photo-upload-preview');
    if (preview.src) {
        URL.revokeObjectURL(preview.src);
    }
    const url = URL.createObjectURL(blob);
    preview.src = url;
    currentPasteImageBlob = blob;
    document.getElementById('photo-upload-caption').value = '';
    
    const modal = document.getElementById('photo-upload-modal');
    if (modal) {
        modal.classList.add('active');
        setTimeout(() => {
            document.getElementById('photo-upload-caption').focus();
        }, 100);
    }
}

function closePhotoUploadModal() {
    const modal = document.getElementById('photo-upload-modal');
    if (modal) {
        modal.classList.remove('active');
    }
    const preview = document.getElementById('photo-upload-preview');
    if (preview && preview.src) {
        URL.revokeObjectURL(preview.src);
        preview.src = '';
    }
    currentPasteImageBlob = null;
}

async function submitPhotoUpload() {
    if (!currentPasteImageBlob || !selectedChatClientId) return;
    
    const btn = document.getElementById('btn-send-photo');
    if (btn.disabled) return;
    
    btn.disabled = true;
    const oldText = btn.textContent;
    btn.textContent = 'Надсилання...';
    
    const formData = new FormData();
    formData.append('file', currentPasteImageBlob, 'pasted_image.png');
    
    const caption = document.getElementById('photo-upload-caption').value.trim();
    if (caption) {
        formData.append('caption', caption);
    }
    
    try {
        const response = await fetch(`/api/sessions/${selectedChatClientId}/photo`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Failed to upload photo');
        }
        
        closePhotoUploadModal();
        // Refresh message thread history
        await refreshChatPageMessages(selectedChatClientId);
    } catch (err) {
        console.error("Failed to send image:", err);
        alert("Не вдалося надіслати зображення: " + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = oldText;
    }
}
