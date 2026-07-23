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
const chatLogsCache = {};
let unreadMessagesInCurrentChat = 0;

function showScrollBottomButton(increment = 0) {
    const btn = document.getElementById('chat-scroll-bottom-btn');
    const badge = document.getElementById('chat-scroll-bottom-badge');
    if (!btn || !badge) return;
    
    unreadMessagesInCurrentChat += increment;
    
    btn.classList.add('visible');
    if (unreadMessagesInCurrentChat > 0) {
        badge.style.display = 'flex';
        badge.textContent = unreadMessagesInCurrentChat;
    } else {
        badge.style.display = 'none';
    }
}

function hideScrollBottomButton() {
    const btn = document.getElementById('chat-scroll-bottom-btn');
    const badge = document.getElementById('chat-scroll-bottom-badge');
    if (btn) btn.classList.remove('visible');
    if (badge) badge.style.display = 'none';
    unreadMessagesInCurrentChat = 0;
}

function scrollChatToBottomWithReset() {
    scrollToBottom('chat-window-body-container', true);
    hideScrollBottomButton();
}

window.updateGlobalUnreadChatBadge = function() {
    let totalUnread = 0;
    if (typeof chatUnreadCounts !== 'undefined') {
        for (const clientId in chatUnreadCounts) {
            totalUnread += chatUnreadCounts[clientId] || 0;
        }
    }
    
    const tabBtn = document.getElementById('tab-btn-chat');
    if (tabBtn) {
        let badge = tabBtn.querySelector('.tab-badge');
        if (totalUnread > 0) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'tab-badge';
                tabBtn.appendChild(badge);
            }
            badge.textContent = totalUnread;
        } else {
            if (badge) badge.remove();
        }
    }
};

window.updateSessionCardUnreadBadge = function(clientId) {
    const card = document.querySelector(`.session-card[data-id="${clientId}"]`);
    if (card) {
        const btn = card.querySelector('.btn-chat-modal-circle');
        if (btn) {
            let badge = btn.querySelector('.badge');
            const unreadCount = (typeof chatUnreadCounts !== 'undefined' && chatUnreadCounts[clientId]) || 0;
            if (unreadCount > 0) {
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'badge';
                    btn.appendChild(badge);
                }
                badge.textContent = unreadCount;
            } else {
                if (badge) badge.remove();
            }
        }
    }
};

window.updateAllUnreadBadges = function(clientId) {
    window.updateGlobalUnreadChatBadge();
    if (clientId) {
        window.updateSessionCardUnreadBadge(clientId);
    } else {
        if (typeof chatUnreadCounts !== 'undefined') {
            for (const cid in chatUnreadCounts) {
                window.updateSessionCardUnreadBadge(cid);
            }
        }
    }
};

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
                    <span class="chat-item-time">${formatChatTime((session.last_message && session.last_message.created_at) ? session.last_message.created_at : session.created_at)}</span>
                </div>
                <div class="chat-item-bottom" style="display: flex; justify-content: space-between; align-items: center; min-height: 18px; margin-top: 4px;">
                    <span class="chat-item-preview" style="max-width: 80%; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-size: 0.78rem; color: rgba(255, 255, 255, 0.4);">${previewText}</span>
                    ${unreadCount > 0 ? `<span class="chat-item-badge" style="margin-left: auto;">${unreadCount}</span>` : ''}
                </div>
            </div>
        `;
        container.appendChild(item);
    });

    // Оновлюємо ім'я та аватар в шапці активного вікна чату, якщо дані змінились у фоні
    if (selectedChatClientId !== null && list) {
        const activeSession = list.find(s => s.client_id === selectedChatClientId);
        if (activeSession) {
            const currentDisplayName = extractDisplayName(activeSession.client_data, activeSession.username);
            const windowNameEl = document.querySelector('.chat-window-name');
            if (windowNameEl && windowNameEl.textContent !== currentDisplayName) {
                windowNameEl.textContent = currentDisplayName;
            }
            const avatarPlaceholder = document.getElementById(`avatar-placeholder-${selectedChatClientId}`);
            if (avatarPlaceholder) {
                avatarPlaceholder.textContent = currentDisplayName.replace(/^@/, '').substring(0, 1).toUpperCase() || 'К';
            }
        }
    }
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

function closeChatActionsMenu() {
    const dropdown = document.getElementById('chat-actions-dropdown');
    if (dropdown) {
        dropdown.classList.remove('active');
    }
}

// Close actions dropdown when clicking outside
document.addEventListener('click', function(e) {
    const btn = document.querySelector('.chat-actions-btn');
    const dropdown = document.getElementById('chat-actions-dropdown');
    if (dropdown && dropdown.classList.contains('active') && !dropdown.contains(e.target) && e.target !== btn) {
        dropdown.classList.remove('active');
    }
});

async function clearChatHistory(clientId) {
    closeChatActionsMenu();
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
    closeChatActionsMenu();
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
                            <div class="chat-no-selection-icon" style="color: rgba(139, 92, 246, 0.25); display: flex; justify-content: center; align-items: center; margin-bottom: 8px;">
                                <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                                </svg>
                            </div>
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
                const btn = document.querySelector('.btn-toggle-ai-bottom');
                if (btn) {
                    if (data.is_paused) {
                        btn.className = 'btn-toggle-ai-bottom paused';
                        btn.title = 'ШІ вимкнено. Натисніть, щоб увімкнути.';
                    } else {
                        btn.className = 'btn-toggle-ai-bottom active';
                        btn.title = 'ШІ працює. Натисніть, щоб вимкнути.';
                    }
                }
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

window.openClientControlCard = function(clientId) {
    if (!clientId) return;

    if (window.switchTab) {
        window.switchTab('control');
    }
    
    if (window.expandedSessions) {
        window.expandedSessions.add(Number(clientId));
        try {
            localStorage.setItem('expandedSessions', JSON.stringify(Array.from(window.expandedSessions)));
        } catch (e) {}
    }

    setTimeout(() => {
        const card = document.querySelector(`.session-card[data-id="${clientId}"]`);
        if (card) {
            card.classList.add('expanded');
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            card.style.transition = 'box-shadow 0.4s ease, border-color 0.4s ease';
            card.style.boxShadow = '0 0 25px rgba(139, 92, 246, 0.7)';
            card.style.borderColor = '#8b5cf6';
            
            setTimeout(() => {
                card.style.boxShadow = '';
                card.style.borderColor = '';
            }, 2500);
        } else {
            if (window.showToast) {
                window.showToast("Сесія відсутня в активних або знаходиться в архіві", "warning");
            }
        }
    }, 150);
};

async function selectChatClient(clientId) {
    if (window.resetViewportScale) window.resetViewportScale();
    selectedChatClientId = clientId;
    try {
        localStorage.setItem('selectedChatClientId', clientId);
    } catch (e) {}
    chatUnreadCounts[clientId] = 0;
    renderChatSidebar();
    if (typeof window.updateAllUnreadBadges === 'function') {
        window.updateAllUnreadBadges(clientId);
    }
    
    const layout = document.getElementById('chat-page-layout-container');
    if (layout) {
        layout.classList.add('chat-selected');
    }
    document.body.classList.add('hide-nav-bar');
    
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
                <button class="chat-back-btn" onclick="backToChatList()" title="Назад">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="19" y1="12" x2="5" y2="12"></line>
                        <polyline points="12 19 5 12 12 5"></polyline>
                    </svg>
                </button>
                <div class="chat-window-avatar">
                    <span id="avatar-placeholder-${session.client_id}" style="display: none;">${displayName.replace(/^@/, '').substring(0, 1).toUpperCase() || 'К'}</span>
                    <img src="/api/avatar/${session.client_id}" onerror="this.remove(); const el = document.getElementById('avatar-placeholder-${session.client_id}'); if(el) el.style.display='inline-flex';">
                </div>
                <div class="chat-window-details">
                    <span class="chat-window-name">${displayName}</span>
                </div>
            </div>
            <div class="chat-window-actions">
                <button class="chat-actions-btn" id="chat-info-toggle-btn" onclick="toggleClientInfoPanel()" title="Профіль клієнта" style="margin-right: 4px;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="15" y1="3" x2="15" y2="21"></line>
                    </svg>
                </button>
                <button class="chat-actions-btn" onclick="toggleChatActionsMenu(event)" title="Опції чату">⋮</button>
                <div class="chat-actions-dropdown" id="chat-actions-dropdown">
                    <button class="dropdown-item" onclick="clearChatHistory(${session.client_id})">Очистити історію</button>
                    <button class="dropdown-item danger" onclick="deleteChatCompletely(${session.client_id})">Видалити чат повністю</button>
                </div>
            </div>
        </div>
        <div class="chat-window-body" id="chat-window-body-container">
            <div style="text-align:center;color:rgba(255,255,255,0.3);padding:20px;">Завантаження повідомлень...</div>
        </div>
        <div class="chat-window-footer">
            <div style="display: flex; align-items: center; gap: 12px; width: 100%;">
                <button class="btn-toggle-ai-bottom ${session.is_paused ? 'paused' : 'active'}" onclick="toggleAISetting(${session.client_id})" title="${session.is_paused ? 'ШІ вимкнено. Натисніть, щоб увімкнути.' : 'ШІ працює. Натисніть, щоб вимкнути.'}">
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="11" width="18" height="10" rx="3"></rect>
                        <path d="M12 2v3M9 5h6M5 11V9a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v2"></path>
                        <circle cx="8" cy="16" r="1.5" fill="currentColor"></circle>
                        <circle cx="16" cy="16" r="1.5" fill="currentColor"></circle>
                    </svg>
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
        <!-- Floating Scroll to Bottom Button -->
        <div class="chat-scroll-bottom-btn" id="chat-scroll-bottom-btn" onclick="scrollChatToBottomWithReset()">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <polyline points="19 12 12 19 5 12"></polyline>
            </svg>
            <span class="badge" id="chat-scroll-bottom-badge" style="display: none;">0</span>
        </div>
    `;
    
    if (window.renderClientInfoPanel) {
        window.renderClientInfoPanel(session);
    }
    
    // Render from cache instantly if available to prevent black screen transition
    const bodyContainer = document.getElementById('chat-window-body-container');
    if (bodyContainer && chatLogsCache[clientId]) {
        renderChatLogsFromArray(bodyContainer, chatLogsCache[clientId]);
    }
    
    if (bodyContainer) {
        bodyContainer.addEventListener('scroll', () => {
            const isAtBottom = bodyContainer.scrollHeight - bodyContainer.scrollTop - bodyContainer.clientHeight < 100;
            if (isAtBottom) {
                hideScrollBottomButton();
            } else {
                showScrollBottomButton(0);
            }
        });
    }
    hideScrollBottomButton();
    
    await refreshChatPageMessages(clientId);
    
    // Auto-focus the input textarea
    const textarea = document.getElementById('chat-msg-input');
    if (textarea) {
        textarea.focus();
        setupCannedTemplatesAutocomplete('chat-msg-input', () => selectedChatClientId);
    }
}

function backToChatList() {
    if (window.resetViewportScale) window.resetViewportScale();
    selectedChatClientId = null;
    try {
        localStorage.removeItem('selectedChatClientId');
    } catch (e) {}
    const layout = document.getElementById('chat-page-layout-container');
    if (layout) {
        layout.classList.remove('chat-selected');
    }
    document.body.classList.remove('hide-nav-bar');
    const activeItems = document.querySelectorAll('.chat-item.active');
    activeItems.forEach(item => item.classList.remove('active'));
    
    const windowContainer = document.getElementById('chat-window-container');
    if (windowContainer) {
        windowContainer.innerHTML = `
            <div class="chat-no-selection">
                <div class="chat-no-selection-icon" style="color: rgba(139, 92, 246, 0.25); display: flex; justify-content: center; align-items: center; margin-bottom: 8px;">
                    <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                    </svg>
                </div>
                <p>Оберіть чат зі списку ліворуч, щоб розпочати листування</p>
            </div>
        `;
    }
    renderChatSidebar();
}


function renderChatLogsFromArray(container, logs) {
    container.innerHTML = '';
    if (!logs || logs.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.2);padding:40px;">Історія повідомлень порожня</div>';
        return;
    }
    
    const getSenderGroup = (sender) => {
        if (sender === 'client') return 'client';
        if (sender === 'bot') return 'bot';
        return 'support'; // admin or operator
    };

    const groupedLogs = groupPhotoLogs(logs);
    groupedLogs.forEach((log, index) => {
        const nextLog = groupedLogs[index + 1];
        const hideAvatar = nextLog && getSenderGroup(nextLog.sender) === getSenderGroup(log.sender);
        renderSingleChatMessage(container, log, hideAvatar);
    });
    
    scrollToBottom('chat-window-body-container', true);
}

async function refreshChatPageMessages(clientId) {
    try {
        const res = await fetch(`/api/sessions/${clientId}/chat`);
        const logs = await res.json();
        
        const bodyContainer = document.getElementById('chat-window-body-container');
        if (!bodyContainer || selectedChatClientId !== clientId) return;
        
        const prevLogsStr = chatLogsCache[clientId] ? JSON.stringify(chatLogsCache[clientId]) : '';
        const newLogsStr = JSON.stringify(logs);
        
        chatLogsCache[clientId] = logs;
        
        if (prevLogsStr !== newLogsStr || !bodyContainer.firstElementChild || bodyContainer.innerHTML.includes('Завантаження повідомлень...')) {
            renderChatLogsFromArray(bodyContainer, logs);
        }
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
    const hasPhoto = log.photo_id || (log.photo_ids && log.photo_ids.length > 0);
    if (hasPhoto) {
        bubbleClass += ' has-photo';
        if (!log.message_text) {
            bubbleClass += ' photo-only';
        }
    }

    if (log.photo_ids && log.photo_ids.length > 1) {
        contentHtml += `<div class="chat-msg-gallery">`;
        log.photo_ids.forEach(pid => {
            contentHtml += `<img class="chat-msg-gallery-img" src="/api/photos/${pid}" onload="scrollToBottom('chat-window-body-container')" onclick="openLightbox(this.src)">`;
        });
        contentHtml += `</div>`;
    } else if (log.photo_id) {
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
    containerDiv._receivedAt = Date.now();
    container.appendChild(containerDiv);
}

function scrollToBottom(containerId, force = false) {
    const container = document.getElementById(containerId);
    if (container) {
        const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150;
        
        if (force || isNearBottom) {
            container.scrollTop = container.scrollHeight;
            // Schedule delayed scrolls to bypass dynamic layout recalculation lag
            setTimeout(() => {
                container.scrollTop = container.scrollHeight;
            }, 50);
            setTimeout(() => {
                container.scrollTop = container.scrollHeight;
            }, 150);
            hideScrollBottomButton();
        } else {
            showScrollBottomButton(0);
        }
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

function connectChatWebSocket() {
    if (chatWs) {
        if (chatWs.readyState === WebSocket.OPEN || chatWs.readyState === WebSocket.CONNECTING) {
            console.log("WebSocket connection is already active or connecting. Skipping duplicate initialization.");
            return;
        }
        // Remove event handlers from old socket to prevent ghost reconnect loops
        chatWs.onmessage = null;
        chatWs.onerror = null;
        chatWs.onclose = null;
        try {
            chatWs.close();
        } catch (e) {}
    }

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
                                <div class="chat-no-selection-icon" style="color: rgba(139, 92, 246, 0.25); display: flex; justify-content: center; align-items: center; margin-bottom: 8px;">
                                    <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                                    </svg>
                                </div>
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
            const isNearBottom = bodyContainer.scrollHeight - bodyContainer.scrollTop - bodyContainer.clientHeight < 100;
            const isChatActiveAndVisible = (typeof currentTab !== 'undefined' && currentTab === 'chat');
            if (data.sender === 'client') {
                playSound('new_message');
                if (!isChatActiveAndVisible) {
                    chatUnreadCounts[data.client_id] = (chatUnreadCounts[data.client_id] || 0) + 1;
                    if (typeof window.updateAllUnreadBadges === 'function') {
                        window.updateAllUnreadBadges(data.client_id);
                    }
                } else if (!isNearBottom) {
                    unreadMessagesInCurrentChat++;
                }
            }
            
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

            // Attempt to merge photos in real-time if received within 5 seconds
            if (data.photo_id && lastMsgContainer && lastMsgContainer._receivedAt && (Date.now() - lastMsgContainer._receivedAt < 5000)) {
                if (getLastMsgSenderGroup(lastMsgContainer) === getSenderGroup(data.sender)) {
                    const lastBubble = lastMsgContainer.querySelector('.chat-msg-bubble');
                    if (lastBubble) {
                        const singleImg = lastBubble.querySelector('.chat-msg-img');
                        if (singleImg) {
                            // Convert single image to gallery
                            const gallery = document.createElement('div');
                            gallery.className = 'chat-msg-gallery';
                            
                            const img1 = singleImg.cloneNode();
                            img1.className = 'chat-msg-gallery-img';
                            
                            const img2 = document.createElement('img');
                            img2.className = 'chat-msg-gallery-img';
                            img2.src = `/api/photos/${data.photo_id}`;
                            img2.onclick = function() { openLightbox(img2.src); };
                            img2.onload = function() { scrollToBottom('chat-window-body-container'); };
                            
                            gallery.appendChild(img1);
                            gallery.appendChild(img2);
                            
                            singleImg.replaceWith(gallery);
                            
                            lastBubble.classList.add('has-photo');
                            if (!lastBubble.querySelector('.chat-msg-text')) {
                                lastBubble.classList.add('photo-only');
                            }
                            
                            // If the incoming message has text and the bubble doesn't, add it
                            if (data.message_text && !lastBubble.querySelector('.chat-msg-text')) {
                                let escapedText = escapeHtml(data.message_text);
                                escapedText = escapedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                                escapedText = escapedText.replace(/`/g, '');
                                const textSpan = document.createElement('span');
                                textSpan.className = 'chat-msg-text';
                                textSpan.innerHTML = escapedText.replace(/\n/g, '<br>');
                                lastBubble.insertBefore(textSpan, lastBubble.querySelector('.chat-msg-time-inline'));
                            }
                            
                            // Update _receivedAt to extend the grouping window for subsequent photos
                            lastMsgContainer._receivedAt = Date.now();
                            scrollToBottom('chat-window-body-container');
                            return;
                        }
                        
                        const existingGallery = lastBubble.querySelector('.chat-msg-gallery');
                        if (existingGallery) {
                            // Add to existing gallery
                            const img = document.createElement('img');
                            img.className = 'chat-msg-gallery-img';
                            img.src = `/api/photos/${data.photo_id}`;
                            img.onclick = function() { openLightbox(img.src); };
                            img.onload = function() { scrollToBottom('chat-window-body-container'); };
                            
                            existingGallery.appendChild(img);
                            
                            // If the incoming message has text and the bubble doesn't, add it
                            if (data.message_text && !lastBubble.querySelector('.chat-msg-text')) {
                                let escapedText = escapeHtml(data.message_text);
                                escapedText = escapedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                                escapedText = escapedText.replace(/`/g, '');
                                const textSpan = document.createElement('span');
                                textSpan.className = 'chat-msg-text';
                                textSpan.innerHTML = escapedText.replace(/\n/g, '<br>');
                                lastBubble.insertBefore(textSpan, lastBubble.querySelector('.chat-msg-time-inline'));
                            }
                            
                            lastMsgContainer._receivedAt = Date.now();
                            scrollToBottom('chat-window-body-container');
                            return;
                        }
                    }
                }
            }

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
            chatUnreadCounts[data.client_id] = (chatUnreadCounts[data.client_id] || 0) + 1;
            if (typeof window.updateAllUnreadBadges === 'function') {
                window.updateAllUnreadBadges(data.client_id);
            }
        }
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
        const oldSrc = preview.src;
        setTimeout(() => {
            if (preview.src === oldSrc) {
                URL.revokeObjectURL(oldSrc);
                preview.src = '';
            }
        }, 350); // wait for fade out animation to finish
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

// --- Canned Templates Autocomplete (Швидкі відповіді) ---

const CANNED_TEMPLATES = [
    {
        key: 'amobank_steps',
        label: '🏦 Надіслати скріншоти AmoBank (4 фото)',
        type: 'media',
        bank: 'amobank'
    }
];

// Inject autocomplete CSS styles
const autocompleteStyle = document.createElement('style');
autocompleteStyle.textContent = `
    .chat-autocomplete-menu {
        position: absolute;
        bottom: 100%;
        left: 0;
        right: 0;
        background: #151321;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.6);
        max-height: 250px;
        overflow-y: auto;
        z-index: 9999;
        margin-bottom: 10px;
        padding: 6px;
        backdrop-filter: blur(10px);
    }
    .chat-autocomplete-item {
        padding: 10px 14px;
        cursor: pointer;
        color: rgba(255, 255, 255, 0.85);
        border-radius: 10px;
        font-size: 0.9rem;
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        gap: 10px;
        font-family: inherit;
    }
    .chat-autocomplete-item:hover, .chat-autocomplete-item.active {
        background: var(--accent-primary, #3b82f6);
        color: #ffffff;
    }
    .chat-autocomplete-menu::-webkit-scrollbar {
        width: 6px;
    }
    .chat-autocomplete-menu::-webkit-scrollbar-track {
        background: transparent;
    }
    .chat-autocomplete-menu::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 10px;
    }
    .chat-autocomplete-menu::-webkit-scrollbar-thumb:hover {
        background: rgba(255, 255, 255, 0.25);
    }
    .chat-msg-gallery {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 6px;
        max-width: 320px;
        margin-bottom: 6px;
        border-radius: 12px;
        overflow: hidden;
    }
    .chat-msg-gallery-img {
        width: 100%;
        height: 120px;
        object-fit: cover;
        cursor: pointer;
        border-radius: 8px;
        transition: transform 0.2s ease;
    }
    .chat-msg-gallery-img:hover {
        transform: scale(1.03);
    }
`;
document.head.appendChild(autocompleteStyle);

// Preprocess messages list to group consecutive photos from the same sender within 5s
function groupPhotoLogs(logs) {
    const grouped = [];
    let i = 0;
    
    while (i < logs.length) {
        const current = logs[i];
        if (!current.photo_id) {
            grouped.push(current);
            i++;
            continue;
        }
        
        // It's a photo. Let's see if we can group it with subsequent photos.
        const currentGroup = {
            ...current,
            photo_ids: [current.photo_id]
        };
        
        let j = i + 1;
        const currentGroupTime = parseUtcToLocal(current.created_at);
        
        while (j < logs.length) {
            const next = logs[j];
            if (!next.photo_id) {
                break;
            }
            if (next.sender !== current.sender) {
                break;
            }
            
            // Check time difference
            const nextTime = parseUtcToLocal(next.created_at);
            if (currentGroupTime && nextTime) {
                const diffMs = Math.abs(nextTime.getTime() - currentGroupTime.getTime());
                if (diffMs > 5000) { // 5 seconds threshold
                    break;
                }
            } else {
                break; 
            }
            
            // Add to group
            currentGroup.photo_ids.push(next.photo_id);
            if (next.message_text && !currentGroup.message_text) {
                currentGroup.message_text = next.message_text;
            }
            j++;
        }
        
        grouped.push(currentGroup);
        i = j;
    }
    return grouped;
}

let currentAutocompleteMenu = null;
let activeAutocompleteIndex = 0;
let filteredAutocompleteTemplates = [];

function setupCannedTemplatesAutocomplete(textareaId, clientIdGetter) {
    const textarea = document.getElementById(textareaId);
    if (!textarea) return;
    
    if (textarea.dataset.autocompleteBound) return;
    textarea.dataset.autocompleteBound = "true";
    
    document.addEventListener('click', function(e) {
        if (currentAutocompleteMenu && !currentAutocompleteMenu.contains(e.target) && e.target !== textarea) {
            closeAutocompleteMenu();
        }
    });

    textarea.addEventListener('keydown', function(e) {
        if (!currentAutocompleteMenu) return;
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeAutocompleteIndex = (activeAutocompleteIndex + 1) % filteredAutocompleteTemplates.length;
            renderAutocompleteActiveItem();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeAutocompleteIndex = (activeAutocompleteIndex - 1 + filteredAutocompleteTemplates.length) % filteredAutocompleteTemplates.length;
            renderAutocompleteActiveItem();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            selectAutocompleteItem(activeAutocompleteIndex, textarea, clientIdGetter);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            closeAutocompleteMenu();
        }
    });

    textarea.addEventListener('input', function() {
        const text = textarea.value;
        const selectionStart = textarea.selectionStart;
        const beforeCursor = text.substring(0, selectionStart);
        const match = beforeCursor.match(/\/(\w*)$/);
        
        if (match) {
            const query = match[1].toLowerCase();
            const clientId = clientIdGetter();
            
            const allSessions = [...(lastFetchedSessions || []), ...(cachedCompletedSessions || [])];
            const session = allSessions.find(s => s.client_id === clientId);
            let currentBank = (session && session.bank) ? session.bank.toLowerCase() : '';
            if (!currentBank && session && session.line_id && typeof allLines !== 'undefined' && allLines) {
                const line = allLines.find(l => l.id === session.line_id || l.line_id === session.line_id);
                if (line && line.bank) {
                    currentBank = line.bank.toLowerCase();
                }
            }
            
            filteredAutocompleteTemplates = CANNED_TEMPLATES.filter(tmpl => {
                if (tmpl.bank !== 'general' && tmpl.bank !== currentBank) {
                    return false;
                }
                if (query) {
                    return tmpl.label.toLowerCase().includes(query) || 
                           (tmpl.text && tmpl.text.toLowerCase().includes(query)) ||
                           tmpl.key.toLowerCase().includes(query);
                }
                return true;
            });
            
            if (filteredAutocompleteTemplates.length > 0) {
                showAutocompleteMenu(textarea, clientIdGetter);
            } else {
                closeAutocompleteMenu();
            }
        } else {
            closeAutocompleteMenu();
        }
    });
}

function showAutocompleteMenu(textarea, clientIdGetter) {
    if (!currentAutocompleteMenu) {
        currentAutocompleteMenu = document.createElement('div');
        currentAutocompleteMenu.className = 'chat-autocomplete-menu';
        
        const wrapper = textarea.closest('.chat-input-wrapper');
        if (wrapper) {
            wrapper.style.position = 'relative';
            wrapper.appendChild(currentAutocompleteMenu);
        } else {
            document.body.appendChild(currentAutocompleteMenu);
        }
    }
    
    activeAutocompleteIndex = 0;
    renderAutocompleteMenuContent(textarea, clientIdGetter);
}

function renderAutocompleteMenuContent(textarea, clientIdGetter) {
    if (!currentAutocompleteMenu) return;
    
    currentAutocompleteMenu.innerHTML = '';
    filteredAutocompleteTemplates.forEach((tmpl, idx) => {
        const item = document.createElement('div');
        item.className = 'chat-autocomplete-item';
        if (idx === activeAutocompleteIndex) {
            item.className += ' active';
        }
        item.textContent = tmpl.label;
        item.addEventListener('click', function() {
            selectAutocompleteItem(idx, textarea, clientIdGetter);
        });
        currentAutocompleteMenu.appendChild(item);
    });
}

function renderAutocompleteActiveItem() {
    if (!currentAutocompleteMenu) return;
    const items = currentAutocompleteMenu.querySelectorAll('.chat-autocomplete-item');
    items.forEach((item, idx) => {
        if (idx === activeAutocompleteIndex) {
            item.classList.add('active');
            item.scrollIntoView({ block: 'nearest' });
        } else {
            item.classList.remove('active');
        }
    });
}

function closeAutocompleteMenu() {
    if (currentAutocompleteMenu) {
        currentAutocompleteMenu.remove();
        currentAutocompleteMenu = null;
    }
}

async function selectAutocompleteItem(idx, textarea, clientIdGetter) {
    const tmpl = filteredAutocompleteTemplates[idx];
    if (!tmpl) return;
    
    const text = textarea.value;
    const selectionStart = textarea.selectionStart;
    const beforeCursor = text.substring(0, selectionStart);
    const afterCursor = text.substring(selectionStart);
    
    const newBefore = beforeCursor.replace(/\/(\w*)$/, '');
    
    closeAutocompleteMenu();
    
    if (tmpl.type === 'text') {
        textarea.value = newBefore + tmpl.text + afterCursor;
        textarea.focus();
        const newPos = newBefore.length + tmpl.text.length;
        textarea.setSelectionRange(newPos, newPos);
    } else if (tmpl.type === 'media') {
        const clientId = clientIdGetter();
        if (!clientId) return;
        
        textarea.value = newBefore + afterCursor;
        textarea.focus();
        
        try {
            showToast("Надсилаю скріншоти AmoBank...", "info");
            
            const response = await fetch(`/api/sessions/${clientId}/send_template`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ template_key: tmpl.key })
            });
            
            if (response.ok) {
                showToast("Скріншоти успішно надіслано!", "success");
                await refreshChatPageMessages(clientId);
            } else {
                const err = await response.json();
                showToast("Помилка відправки: " + (err.detail || "Невідома помилка"), "error");
            }
        } catch (e) {
            showToast("Помилка підключення до сервера", "error");
        }
    }
}

// --- Collapsible Client Profile Info Panel ---
window.toggleClientInfoPanel = function(forceState) {
    const panel = document.getElementById('chat-client-info-panel');
    const btn = document.getElementById('chat-info-toggle-btn');
    if (!panel) return;

    let isVisible = panel.classList.contains('visible');
    if (typeof forceState === 'boolean') {
        isVisible = !forceState;
    }

    if (isVisible) {
        panel.classList.remove('visible');
        if (btn) btn.classList.remove('active');
        localStorage.setItem('chat_client_panel_visible', 'false');
    } else {
        panel.classList.add('visible');
        if (btn) btn.classList.add('active');
        localStorage.setItem('chat_client_panel_visible', 'true');
    }
};

function parseClientDataObj(session) {
    if (!session) return {};
    let rawData = session.client_data;
    if (!rawData) return {};

    if (typeof rawData === 'object' && rawData !== null) {
        return rawData;
    }
    
    if (typeof rawData === 'string' && rawData.startsWith('{')) {
        try {
            return JSON.parse(rawData);
        } catch (e) {}
    }
    
    const lines = String(rawData).split('\n').map(l => l.trim()).filter(l => l);
    const parsed = {};
    
    // First, check explicit labeled lines (key: value)
    lines.forEach(line => {
        if (line.includes(':')) {
            const parts = line.split(':');
            const k = parts[0].trim().toLowerCase();
            const v = parts.slice(1).join(':').trim();
            if (k.includes('піб') || k.includes('ім') || k.includes('пiб')) parsed.pib = v;
            else if (k.includes('дата') || k.includes('родж')) parsed.dob = v;
            else if (k.includes('іпн') || k.includes('рнокпп')) parsed.ipn = v;
            else if (k.includes('тел') || k.includes('фон') || (k.includes('номер') && !k.includes('line'))) {
                parsed.phone = v.replace(/Дроп\s*-?\s*@\w+/gi, '').trim();
            }
        }
    });

    // Filter out report template meta lines (like "Line 17 Return...", "Дроп - @...", etc.)
    const cleanLines = lines.filter(line => {
        const l = line.toLowerCase();
        return !l.startsWith('line ') && !l.includes('return:') && !l.startsWith('дроп') && !l.startsWith('@') && !l.match(/^\d{4}$/);
    });

    if (!parsed.pib && cleanLines[0]) {
        parsed.pib = cleanLines[0];
    }

    if (!parsed.dob) {
        const dobLine = lines.find(l => l.match(/\d{2}\.\d{2}\.\d{4}/));
        if (dobLine) parsed.dob = dobLine.match(/\d{2}\.\d{2}\.\d{4}/)[0];
        else if (cleanLines[1]) parsed.dob = cleanLines[1];
    }

    if (!parsed.ipn) {
        const ipnLine = lines.find(l => l.match(/\b\d{10}\b/));
        if (ipnLine) parsed.ipn = ipnLine.match(/\b\d{10}\b/)[0];
        else if (cleanLines[2]) parsed.ipn = cleanLines[2];
    }

    if (!parsed.phone) {
        const phoneLine = lines.find(l => (l.includes('+380') || l.match(/\b0\d{9}\b/)) && !l.toLowerCase().includes('return:'));
        if (phoneLine) {
            parsed.phone = phoneLine.replace(/Дроп\s*-?\s*@\w+/gi, '').trim();
        } else if (cleanLines[3] && (cleanLines[3].includes('+') || cleanLines[3].match(/\d{9,}/))) {
            parsed.phone = cleanLines[3];
        }
    }

    return parsed;
}

function getBankNameHelper(bankKey) {
    if (!bankKey) return '';
    if (window.bankTemplates && window.bankTemplates[bankKey] && window.bankTemplates[bankKey].display_name) {
        return window.bankTemplates[bankKey].display_name;
    }
    const map = {
        'izibank': 'IziBank',
        'monobank': 'Monobank',
        'lvivbank': 'BankLviv',
        'alliance': 'Alliance',
        'novapay': 'NovaPay',
        'bank.kd': 'bank.kd',
        'ecobank': 'EcoBank',
        'pumb': 'PUMB'
    };
    return map[bankKey.toLowerCase()] || bankKey;
}

window.renderClientInfoPanel = function(session) {
    const panel = document.getElementById('chat-client-info-panel');
    const btn = document.getElementById('chat-info-toggle-btn');
    if (!panel) return;
    if (!session) {
        panel.innerHTML = '';
        return;
    }

    const cdata = parseClientDataObj(session);
    const displayName = extractDisplayName(session.client_data, session.username);
    
    // Parse selected banks and statuses
    const selectedList = session.selected_banks ? session.selected_banks.split(',').filter(Boolean) : [];
    const bankStatuses = session.bank_statuses || {};
    const historyBanks = Object.keys(bankStatuses);

    const allSessionBanks = [];
    const seenLower = new Set();
    [...selectedList, ...historyBanks, session.bank].forEach(b => {
        if (b) {
            const lower = b.toLowerCase();
            if (!seenLower.has(lower)) {
                seenLower.add(lower);
                allSessionBanks.push(b);
            }
        }
    });

    const currentBankKey = session.bank || session.bank_key || cdata.bank || '';
    const currentBankName = currentBankKey ? getBankNameHelper(currentBankKey) : 'Не вказано';
    
    const pib = cdata.pib || '—';
    const dob = cdata.dob || '—';
    const ipn = cdata.ipn || '—';
    const phone = cdata.phone || '—';
    const username = session.username ? `@${session.username.replace(/^@/, '')}` : '—';
    const bankIconGradient = (window.getBankIconGradient && currentBankKey && window.getBankIconGradient(currentBankKey)) || 'linear-gradient(135deg, #6366f1, #8b5cf6)';
    const bankIcon = (window.getBankIcon && currentBankKey && window.getBankIcon(currentBankKey)) || '🏛️';
    const isCompleted = session.status === 'completed';

    // Build "БАНКИ КЛІЄНТА" grouped HTML
    let selectedBanksHTML = '';
    if (allSessionBanks.length > 0) {
        const pendingPills = [];
        const completedPills = [];
        const failedPills = [];

        allSessionBanks.forEach(bKey => {
            const historyKey = Object.keys(bankStatuses).find(x => x.toLowerCase() === bKey.toLowerCase());
            const status = historyKey ? bankStatuses[historyKey] : (bKey.toLowerCase() === (session.bank || '').toLowerCase() ? 'active' : 'pending');
            const bName = getBankNameHelper(bKey);
            
            if (status === 'release' || status === 'released' || status === 'success') {
                completedPills.push(`<span style="display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 8px; font-size: 0.76rem; font-weight: 600; background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);">✓ ${bName}</span>`);
            } else if (status === 'banned' || status === 'failure') {
                failedPills.push(`<span style="display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 8px; font-size: 0.76rem; font-weight: 600; background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3);">✕ ${bName}</span>`);
            } else {
                pendingPills.push(`<span style="display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 8px; font-size: 0.76rem; font-weight: 600; background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.3);">${bName}</span>`);
            }
        });

        let sectionsHTML = '';

        if (pendingPills.length > 0) {
            sectionsHTML += `
                <div style="display: flex; flex-direction: column; gap: 6px;">
                    <div style="font-size: 0.7rem; color: rgba(255,255,255,0.45); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Обрані / В процесі</div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">${pendingPills.join('')}</div>
                </div>
            `;
        }

        if (completedPills.length > 0) {
            sectionsHTML += `
                <div style="display: flex; flex-direction: column; gap: 6px; ${pendingPills.length > 0 ? 'margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.08);' : ''}">
                    <div style="font-size: 0.7rem; color: #34d399; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Пройдені банки</div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">${completedPills.join('')}</div>
                </div>
            `;
        }

        if (failedPills.length > 0) {
            sectionsHTML += `
                <div style="display: flex; flex-direction: column; gap: 6px; ${(pendingPills.length > 0 || completedPills.length > 0) ? 'margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.08);' : ''}">
                    <div style="font-size: 0.7rem; color: #fb7185; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Непройдені / Збій</div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">${failedPills.join('')}</div>
                </div>
            `;
        }

        selectedBanksHTML = `
            <div style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; padding: 14px; background: rgba(255,255,255,0.015); border: 1px solid rgba(255,255,255,0.05); border-radius: 16px;">
                ${sectionsHTML}
            </div>
        `;
    }

    panel.innerHTML = `
        <div class="client-panel-header">
            <div class="client-panel-title" style="font-size: 0.92rem; font-weight: 700; color: #fff;">Інформація про клієнта</div>
            <button class="client-panel-close-btn" onclick="toggleClientInfoPanel(false)" title="Сховати панель">✕</button>
        </div>
        
        <div class="client-panel-body" style="padding: 20px 16px;">
            <!-- Hero Section (Avatar + Name + Subtitle) -->
            <div style="display: flex; flex-direction: column; align-items: center; text-align: center; margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.06);">
                <div style="width: 68px; height: 68px; border-radius: 50%; background: ${currentBankKey ? bankIconGradient : 'linear-gradient(135deg, #6366f1, #8b5cf6)'}; display: flex; align-items: center; justify-content: center; overflow: hidden; margin-bottom: 12px; box-shadow: 0 6px 20px rgba(0,0,0,0.35); font-size: 1.7rem; font-weight: 700; color: #fff; border: 2px solid rgba(255,255,255,0.1);">
                    ${displayName.replace(/^@/, '').substring(0, 1).toUpperCase() || 'К'}
                </div>
                <div style="font-size: 1.15rem; font-weight: 700; color: #ffffff; line-height: 1.25; margin-bottom: 6px; word-break: normal; overflow-wrap: break-word; max-width: 260px;">${displayName}</div>
                <div style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem; color: rgba(255,255,255,0.55); background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); padding: 4px 12px; border-radius: 12px;">
                    <span style="color: ${isCompleted ? '#fb7185' : (session.is_paused ? '#fb7185' : '#34d399')}; font-weight: 600;">${isCompleted ? 'Архів' : (session.is_paused ? 'Ручний режим' : 'ШІ Активний')}</span>
                </div>
                
                <button onclick="openClientControlCard(${session.client_id})" style="margin-top: 14px; width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; border-radius: 12px; background: linear-gradient(135deg, rgba(139, 92, 246, 0.16), rgba(99, 102, 241, 0.16)); border: 1px solid rgba(139, 92, 246, 0.35); color: #c084fc; font-weight: 600; font-size: 0.84rem; padding: 10px 16px; cursor: pointer; transition: all 0.25s ease; box-shadow: 0 4px 12px rgba(139, 92, 246, 0.08);" onmouseover="this.style.background='linear-gradient(135deg, rgba(139, 92, 246, 0.28), rgba(99, 102, 241, 0.28))'; this.style.boxShadow='0 6px 16px rgba(139, 92, 246, 0.25)'; this.style.transform='translateY(-1px)';" onmouseout="this.style.background='linear-gradient(135deg, rgba(139, 92, 246, 0.16), rgba(99, 102, 241, 0.16))'; this.style.boxShadow='0 4px 12px rgba(139, 92, 246, 0.08)'; this.style.transform='translateY(0)';">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="4" width="18" height="16" rx="3"></rect>
                        <circle cx="9" cy="10" r="2.5"></circle>
                        <path d="M15 8h2M15 12h2M7 16h10"></path>
                    </svg>
                    <span>Перейти до картки клієнта</span>
                </button>
            </div>

            <!-- Selected Banks Section -->
            ${selectedBanksHTML}

            <!-- Details List with Telegram Icons -->
            <div style="display: flex; flex-direction: column; background: rgba(255,255,255,0.015); border: 1px solid rgba(255,255,255,0.05); border-radius: 16px; overflow: hidden;">
                <!-- Telegram Username -->
                <div class="tg-info-item">
                    <svg class="tg-info-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"></path>
                    </svg>
                    <div class="tg-info-content">
                        <div class="tg-info-val" style="color: #60a5fa; font-weight: 600;">${username}</div>
                        <div class="tg-info-label">Ім'я користувача</div>
                    </div>
                </div>

                <!-- PIB -->
                <div class="tg-info-item">
                    <svg class="tg-info-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                        <circle cx="12" cy="7" r="4"></circle>
                    </svg>
                    <div class="tg-info-content">
                        <div class="tg-info-val" style="color: #ffffff; font-weight: 600;">${pib}</div>
                        <div class="tg-info-label">ПІБ Клієнта</div>
                    </div>
                </div>

                <!-- DOB -->
                <div class="tg-info-item">
                    <svg class="tg-info-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                    </svg>
                    <div class="tg-info-content">
                        <div class="tg-info-val">${dob}</div>
                        <div class="tg-info-label">Дата народження</div>
                    </div>
                </div>

                <!-- IPN -->
                <div class="tg-info-item">
                    <svg class="tg-info-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="4" width="18" height="16" rx="2"></rect>
                        <line x1="7" y1="8" x2="17" y2="8"></line>
                        <line x1="7" y1="12" x2="13" y2="12"></line>
                        <line x1="7" y1="16" x2="10" y2="16"></line>
                    </svg>
                    <div class="tg-info-content">
                        <div class="tg-info-val" style="font-family: 'JetBrains Mono', monospace; color: #c084fc; font-weight: 600;">${ipn}</div>
                        <div class="tg-info-label">ІПН / РНОКПП</div>
                    </div>
                </div>

                <!-- Phone -->
                <div class="tg-info-item">
                    <svg class="tg-info-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path>
                    </svg>
                    <div class="tg-info-content">
                        <div class="tg-info-val" style="font-family: 'JetBrains Mono', monospace; color: #34d399; font-weight: 600;">${phone}</div>
                        <div class="tg-info-label">Номер телефону</div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Restore saved panel visibility state (defaults to visible if not set)
    const savedState = localStorage.getItem('chat_client_panel_visible');
    if (savedState === 'true' || savedState === null) {
        panel.classList.add('visible');
        if (btn) btn.classList.add('active');
    } else {
        panel.classList.remove('visible');
        if (btn) btn.classList.remove('active');
    }
};



