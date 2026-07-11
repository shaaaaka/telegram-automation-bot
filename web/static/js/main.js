// --- Global State Variables ---
let availableBanks = [];
let allLines = null;
let currentLinesFilter = 'all';
let currentTab = 'control';

// UI State Caches
let tempSelectedBanks = {};  // client_id -> Array of bank names
let tempSelectedLines = {};  // client_id -> lineId (string)
let tempMessageInputs = {};  // client_id -> string (text typed in textarea)
let expandedSessions = new Set(); // Expanded client cards
let openActionTrays = new Set();  // Opened action trays

try {
    const storedExpanded = JSON.parse(localStorage.getItem('expandedSessions') || '[]');
    expandedSessions = new Set(storedExpanded);
} catch (e) {
    console.error("Failed to load expandedSessions:", e);
}

// SLA & Notification Timers
let statusTransitionTimes = {}; // client_id -> Timestamp (Date.now())
try {
    statusTransitionTimes = JSON.parse(localStorage.getItem('statusTransitionTimes') || '{}');
} catch (e) {
    console.error("Failed to load statusTransitionTimes:", e);
}

let previousSessionStates = {}; // client_id -> status
try {
    previousSessionStates = JSON.parse(localStorage.getItem('previousSessionStates') || '{}');
} catch (e) {
    console.error("Failed to load previousSessionStates:", e);
}

let previousUnroutedCount = 0;
let lastFetchedSessions = null;   // Active sessions cache
let lastUnroutedCodes = [];     // Unrouted codes cache

// Audio Context (Web Audio API)
let audioCtx = null;
let soundEnabled = localStorage.getItem('notification_sound_enabled') !== '0';
let soundVolume = parseFloat(localStorage.getItem('notification_volume')) || 0.5;
let soundProfile = localStorage.getItem('notification_sound_profile') || 'classic';

// Toast Notification System
function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const panelLines = document.querySelector('.panel-lines');
    const activeTabEl = document.querySelector('.tab-content.active');
    if (panelLines && activeTabEl && activeTabEl.id === 'tab-content-control') {
        if (container.parentElement !== panelLines) {
            panelLines.appendChild(container);
        }
        container.classList.add('inside-panel');
    } else {
        if (container.parentElement !== document.body) {
            document.body.appendChild(container);
        }
        container.classList.remove('inside-panel');
    }

    // De-duplicate active messages
    const existingToasts = container.querySelectorAll('.toast');
    for (let t of existingToasts) {
        if (t.innerText.trim() === message.trim()) {
            return;
        }
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerText = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// Custom Promise-based Confirmation Modal
function showConfirm(message, type = 'danger') {
    return new Promise((resolve) => {
        const modal = document.getElementById('custom-modal');
        const msgEl = document.getElementById('custom-modal-message');
        const confirmBtn = document.getElementById('custom-modal-confirm-btn');
        const cancelBtn = document.getElementById('custom-modal-cancel-btn');
        
        if (!modal || !msgEl || !confirmBtn || !cancelBtn) {
            resolve(confirm(message));
            return;
        }

        msgEl.innerText = message;
        
        confirmBtn.className = 'btn btn-sm';
        if (type === 'danger') {
            confirmBtn.classList.add('btn-danger');
        } else if (type === 'success') {
            confirmBtn.classList.add('btn-success');
        } else {
            confirmBtn.classList.add('btn-primary');
        }

        modal.classList.add('active');

        const cleanUp = (result) => {
            modal.classList.remove('active');
            confirmBtn.removeEventListener('click', onConfirmClick);
            cancelBtn.removeEventListener('click', onCancelClick);
            modal.removeEventListener('click', onOverlayClick);
            resolve(result);
        };

        function onConfirmClick() { cleanUp(true); }
        function onCancelClick() { cleanUp(false); }
        function onOverlayClick(e) {
            if (e.target === modal) {
                cleanUp(false);
            }
        }

        confirmBtn.addEventListener('click', onConfirmClick);
        cancelBtn.addEventListener('click', onCancelClick);
        modal.addEventListener('click', onOverlayClick);
    });
}

// Basic Helpers
function escapeHtml(text) {
    if (!text) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast("Скопійовано: " + text, "success");
    }).catch(err => {
        console.error("Failed to copy:", err);
        showToast("Не вдалося скопіювати", "error");
    });
}

function copyTextToClipboard(text, event) {
    if (event) event.stopPropagation();
    navigator.clipboard.writeText(text).then(() => {
        const tooltip = document.createElement('div');
        tooltip.innerText = 'Скопійовано!';
        tooltip.style.position = 'fixed';
        tooltip.style.left = `${event.clientX + 10}px`;
        tooltip.style.top = `${event.clientY - 10}px`;
        tooltip.style.background = '#10b981';
        tooltip.style.color = 'white';
        tooltip.style.padding = '4px 8px';
        tooltip.style.borderRadius = '4px';
        tooltip.style.fontSize = '0.75rem';
        tooltip.style.zIndex = '10000';
        tooltip.style.pointerEvents = 'none';
        tooltip.style.fontFamily = 'sans-serif';
        tooltip.style.fontWeight = 'bold';
        tooltip.style.boxShadow = '0 2px 10px rgba(0,0,0,0.3)';
        document.body.appendChild(tooltip);
        
        setTimeout(() => {
            tooltip.style.transition = 'opacity 0.2s ease';
            tooltip.style.opacity = '0';
            setTimeout(() => tooltip.remove(), 200);
        }, 800);
    }).catch(err => {
        console.error("Could not copy text: ", err);
    });
}

// Web Audio API Sound System
function initAudio() {
    try {
        if (!audioCtx) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (AudioContextClass) {
                audioCtx = new AudioContextClass();
                if (audioCtx.state === 'suspended') {
                    audioCtx.resume().catch(err => console.log("AudioContext resume failed:", err));
                }
            } else {
                console.warn("Web Audio API not supported in this browser");
            }
        }
    } catch (e) {
        console.error("AudioContext initialization failed:", e);
    }
}

function toggleSound() {
    soundEnabled = !soundEnabled;
    localStorage.setItem('notification_sound_enabled', soundEnabled ? '1' : '0');
    const btns = [
        document.getElementById('sound-toggle-btn'),
        document.getElementById('settings-sound-toggle-btn')
    ];
    btns.forEach(btn => {
        if (btn) {
            if (soundEnabled) {
                btn.innerHTML = '🔊 <span class="hide-mobile">Звук увімкнено</span>';
                btn.classList.remove('sound-disabled');
                initAudio();
            } else {
                btn.innerHTML = '🔇 <span class="hide-mobile">Звук вимкнено</span>';
                btn.classList.add('sound-disabled');
            }
        }
    });
}

function playSound(type) {
    if (!soundEnabled) return;
    initAudio();
    if (!audioCtx || audioCtx.state === 'suspended') return;

    try {
        const now = audioCtx.currentTime;
        let oscType = 'sine';
        let fMultiplier = 1.0;
        let durationScale = 1.0;
        
        if (soundProfile === 'retro') {
            oscType = 'square';
            fMultiplier = 0.85;
            durationScale = 0.8;
        } else if (soundProfile === 'digital') {
            oscType = 'triangle';
            fMultiplier = 1.25;
            durationScale = 0.9;
        } else if (soundProfile === 'soft') {
            oscType = 'sine';
            fMultiplier = 0.75;
            durationScale = 1.35;
        }
        
        function playToneWithProfile(freq, duration, delay) {
            try {
                if (!audioCtx) return;
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                
                osc.type = oscType;
                osc.frequency.setValueAtTime(freq * fMultiplier, now + delay);
                
                const vol = parseFloat(soundVolume);
                const maxGain = vol * 0.25;
                
                gain.gain.setValueAtTime(maxGain, now + delay);
                gain.gain.exponentialRampToValueAtTime(0.001, now + delay + duration * durationScale);
                
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                
                osc.start(now + delay);
                osc.stop(now + delay + duration * durationScale);
            } catch (e) {
                console.error(e);
            }
        }

        if (type === 'new_client') {
            playToneWithProfile(523.25, 0.08, 0);
            playToneWithProfile(659.25, 0.08, 0.08);
            playToneWithProfile(783.99, 0.12, 0.16);
        } else if (type === 'waiting_code') {
            playToneWithProfile(880, 0.06, 0);
            playToneWithProfile(880, 0.06, 0.1);
        } else if (type === 'unrouted_code') {
            playToneWithProfile(440, 0.12, 0);
            playToneWithProfile(554.37, 0.18, 0.08);
        } else if (type === 'new_message') {
            playToneWithProfile(587.33, 0.15, 0);
        }
    } catch (e) {
        console.error("Sound playback error:", e);
    }
}

document.addEventListener('click', () => {
    initAudio();
}, { once: true });

function getBankClass(bankName) {
    const name = bankName.toLowerCase();
    if (name.includes('приват') || name.includes('privat')) return 'bank-privat';
    if (name.includes('моно') || name.includes('mono')) return 'bank-mono';
    if (name.includes('сенс') || name.includes('sense')) return 'bank-sense';
    if (name.includes('а-банк') || name.includes('абанк') || name.includes('a-bank')) return 'bank-abank';
    if (name.includes('ощад') || name.includes('oschad')) return 'bank-oschad';
    return 'bank-default';
}

// Tab Switching Routing
function switchTab(tabId) {
    // Show bottom navigation bar when switching tabs
    document.body.classList.remove('nav-hidden');
    
    if (tabId === 'ai') {
        tabId = 'settings';
    }
    currentTab = tabId;
    localStorage.setItem('activeTab', tabId);
    
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(`tab-btn-${tabId}`);
    if (activeBtn) activeBtn.classList.add('active');

    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    const activeContent = document.getElementById(`tab-content-${tabId}`);
    if (activeContent) activeContent.classList.add('active');

    if (tabId === 'stats') {
        loadStats();
    } else if (tabId === 'settings') {
        loadSettings();
    } else if (tabId === 'chat') {
        loadChatSessions();
    } else if (tabId === 'banned') {
        loadBannedUsers();
    }
}

// Main poll loop (every 3 seconds)
async function pollData() {
    try {
        // 1. Connection status poll
        const statusRes = await fetch('/api/status');
        const statusData = await statusRes.json();
        const statusBadge = document.getElementById('bot-status');
        if (statusBadge) {
            const isConfigured = statusData.bot_configured ? 'true' : 'false';
            if (statusBadge.dataset.lastConfigured !== isConfigured) {
                statusBadge.dataset.lastConfigured = isConfigured;
                if (statusData.bot_configured) {
                    statusBadge.innerHTML = '<span class="status-dot-inline" style="background:#10b981;box-shadow:0 0 8px #10b981;display:inline-block;width:8px;height:8px;border-radius:50%;"></span><span class="hide-mobile" style="margin-left:8px;">Бот Онлайн</span>';
                    statusBadge.style.color = '#10b981';
                    statusBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                    statusBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                } else {
                    statusBadge.innerHTML = '<span class="status-dot-inline" style="background:#ef4444;box-shadow:0 0 8px #ef4444;display:inline-block;width:8px;height:8px;border-radius:50%;"></span><span class="hide-mobile" style="margin-left:8px;">Помилка бота</span>';
                    statusBadge.style.color = '#ef4444';
                    statusBadge.style.borderColor = 'rgba(239, 68, 68, 0.2)';
                    statusBadge.style.background = 'rgba(239, 68, 68, 0.1)';
                }
            }
        }

        // 2. Lines poll
        const linesRes = await fetch('/api/lines');
        const newLines = await linesRes.json();
        if (!isLinesDataEqual(allLines, newLines)) {
            allLines = newLines;
            renderLines();
            if (lastFetchedSessions && lastFetchedSessions.length > 0) {
                renderSessions(lastFetchedSessions);
            }
            
            try {
                const banksRes = await fetch('/api/banks');
                const banksData = await banksRes.json();
                availableBanks = banksData.banks || [];
            } catch (e) {
                console.error("Failed to load banks list:", e);
            }
        }

        // 3. Sessions poll
        const sessionsRes = await fetch('/api/sessions');
        const sessions = await sessionsRes.json();
        
        let isInitialFetch = Object.keys(previousSessionStates).length === 0;
        let playNewClient = false;
        let playWaitingCode = false;

        sessions.forEach(s => {
            const oldStatus = previousSessionStates[s.client_id];
            if (oldStatus === undefined) {
                if (!isInitialFetch) {
                    playNewClient = true;
                }
                if (!statusTransitionTimes[s.client_id]) {
                    statusTransitionTimes[s.client_id] = Date.now();
                }
            } else if (oldStatus !== s.status) {
                if (s.status === 'waiting_code') {
                    playWaitingCode = true;
                }
                statusTransitionTimes[s.client_id] = Date.now();
            }
            previousSessionStates[s.client_id] = s.status;
        });

        // Cleanup expired sessions
        const currentIds = sessions.map(s => s.client_id);
        Object.keys(previousSessionStates).forEach(id => {
            if (!currentIds.includes(parseInt(id))) {
                delete previousSessionStates[id];
                delete statusTransitionTimes[id];
            }
        });

        let expandedChanged = false;
        expandedSessions.forEach(id => {
            if (!currentIds.includes(parseInt(id))) {
                expandedSessions.delete(id);
                expandedChanged = true;
            }
        });
        if (expandedChanged) {
            try {
                localStorage.setItem('expandedSessions', JSON.stringify(Array.from(expandedSessions)));
            } catch (e) {}
        }

        try {
            localStorage.setItem('statusTransitionTimes', JSON.stringify(statusTransitionTimes));
            localStorage.setItem('previousSessionStates', JSON.stringify(previousSessionStates));
        } catch (e) {}

        if (playNewClient) {
            playSound('new_client');
        } else if (playWaitingCode) {
            playSound('waiting_code');
        }

        const sessionsChanged = !isSessionsDataEqual(lastFetchedSessions, sessions);
        lastFetchedSessions = sessions;
        
        if (sessionsChanged) {
            renderSessions(sessions);
            if (currentTab === 'chat') {
                renderChatSidebar();
            }
        }
        

        // Removed obsolete activeChatClientId check

        // 4. Unrouted codes poll
        const unroutedRes = await fetch('/api/unrouted-codes');
        const unroutedData = await unroutedRes.json();
        const newUnroutedCodes = unroutedData.codes || [];
        
        const currentUnroutedCount = newUnroutedCodes.length;
        if (currentUnroutedCount > previousUnroutedCount) {
            playSound('unrouted_code');
        }
        previousUnroutedCount = currentUnroutedCount;

        const waitingIdsCurrent = sessions.filter(s => s.status === 'waiting_code').map(s => `${s.client_id}-${s.line_id}`);
        const waitingIdsPrevious = lastFetchedSessions.filter(s => s.status === 'waiting_code').map(s => `${s.client_id}-${s.line_id}`);
        
        const unroutedChanged = !isUnroutedCodesEqual(lastUnroutedCodes, newUnroutedCodes) || !isArraysEqual(waitingIdsCurrent, waitingIdsPrevious);
        lastUnroutedCodes = newUnroutedCodes;

        if (unroutedChanged) {
            renderUnroutedCodes(newUnroutedCodes, sessions);
        }

    } catch (err) {
        console.error("API polling error:", err);
        const statusBadge = document.getElementById('bot-status');
        if (statusBadge) {
            statusBadge.innerHTML = '<span class="status-dot-inline" style="background:#ef4444;box-shadow:0 0 8px #ef4444;display:inline-block;width:8px;height:8px;border-radius:50%;"></span><span class="hide-mobile" style="margin-left:8px;">Помилка мережі</span>';
            statusBadge.style.color = '#ef4444';
            statusBadge.style.borderColor = 'rgba(239, 68, 68, 0.2)';
            statusBadge.style.background = 'rgba(239, 68, 68, 0.1)';
        }
    }
}

// SLA timers updates
function updateTimers() {
    const timers = document.querySelectorAll('.sla-timer');
    timers.forEach(el => {
        const clientId = el.getAttribute('data-client-id');
        const status = el.getAttribute('data-status');
        const start = statusTransitionTimes[clientId];
        if (!start) return;
        
        const elapsed = Math.floor((Date.now() - start) / 1000);
        const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
        const seconds = String(elapsed % 60).padStart(2, '0');
        
        el.innerText = `⏳ ${minutes}:${seconds}`;
        
        if (elapsed > 120 && (status === 'waiting_code' || status === 'registered')) {
            el.style.color = 'var(--accent-danger)';
            el.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            el.style.background = 'rgba(239, 68, 68, 0.08)';
            el.style.fontWeight = 'bold';
        } else {
            el.style.color = 'var(--accent-warning)';
            el.style.borderColor = 'rgba(245, 158, 11, 0.15)';
            el.style.background = 'rgba(245, 158, 11, 0.05)';
            el.style.fontWeight = 'normal';
        }
    });
}

function setLinesFilter(filter) {
    currentLinesFilter = filter;
    renderLines();
}

function isSessionsDataEqual(arr1, arr2) {
    if (!arr1 || !arr2) return false;
    if (arr1.length !== arr2.length) return false;
    for (let i = 0; i < arr1.length; i++) {
        const s1 = arr1[i];
        const s2 = arr2[i];
        if (s1.client_id !== s2.client_id ||
            s1.username !== s2.username ||
            s1.client_data !== s2.client_data ||
            s1.line_id !== s2.line_id ||
            s1.client_message_id !== s2.client_message_id ||
            s1.selected_banks !== s2.selected_banks ||
            s1.remaining_banks !== s2.remaining_banks ||
            s1.is_verified !== s2.is_verified ||
            s1.status !== s2.status) {
            return false;
        }
    }
    return true;
}

function isLinesDataEqual(arr1, arr2) {
    if (!arr1 || !arr2) return false;
    if (arr1.length !== arr2.length) return false;
    for (let i = 0; i < arr1.length; i++) {
        const l1 = arr1[i];
        const l2 = arr2[i];
        if (l1.id !== l2.id ||
            l1.phone_number !== l2.phone_number ||
            l1.bank !== l2.bank ||
            l1.status !== l2.status) {
            return false;
        }
    }
    return true;
}

function isUnroutedCodesEqual(arr1, arr2) {
    if (!arr1 || !arr2) return false;
    if (arr1.length !== arr2.length) return false;
    for (let i = 0; i < arr1.length; i++) {
        if (arr1[i].code !== arr2[i].code || arr1[i].received_at !== arr2[i].received_at) {
            return false;
        }
    }
    return true;
}

function isArraysEqual(arr1, arr2) {
    if (!arr1 || !arr2) return false;
    if (arr1.length !== arr2.length) return false;
    for (let i = 0; i < arr1.length; i++) {
        if (arr1[i] !== arr2[i]) return false;
    }
    return true;
}

// --- Global Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    // Restore active tab
    const savedTab = localStorage.getItem('activeTab') || 'control';
    switchTab(savedTab);

    // Sync initial sound state to global header toggle button
    const headerBtn = document.getElementById('sound-toggle-btn');
    if (headerBtn) {
        if (soundEnabled) {
            headerBtn.innerHTML = '🔊 <span class="hide-mobile">Звук увімкнено</span>';
            headerBtn.classList.remove('sound-disabled');
        } else {
            headerBtn.innerHTML = '🔇 <span class="hide-mobile">Звук вимкнено</span>';
            headerBtn.classList.add('sound-disabled');
        }
    }

    // Initial fetch and poll scheduling (every 1s)
    pollData();
    setInterval(pollData, 1000);
    
    // Update SLA timers (every 1s)
    setInterval(updateTimers, 1000);

    // Initialize Chat WebSocket
    if (typeof connectChatWebSocket === 'function') {
        connectChatWebSocket();
    }

    // --- Scroll tracking to auto-hide navigation bar on mobile ---
    let lastScrollTop = 0;
    const scrollThreshold = 10;
    
    function handleScroll(currentScrollTop) {
        if (window.innerWidth > 900) return;
        if (document.body.classList.contains('hide-nav-bar') || document.querySelector('.chat-page-layout.chat-selected')) {
            return;
        }
        if (Math.abs(lastScrollTop - currentScrollTop) <= scrollThreshold) {
            return;
        }
        if (currentScrollTop > lastScrollTop && currentScrollTop > 50) {
            document.body.classList.add('nav-hidden');
        } else {
            document.body.classList.remove('nav-hidden');
        }
        lastScrollTop = currentScrollTop;
    }

    window.addEventListener('scroll', () => {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        handleScroll(scrollTop);
    }, { passive: true });

    // Also listen inside CRM client list scroll
    setTimeout(() => {
        const chatListContainer = document.getElementById('chat-sidebar-list-container');
        if (chatListContainer) {
            chatListContainer.addEventListener('scroll', () => {
                handleScroll(chatListContainer.scrollTop);
            }, { passive: true });
        }
    }, 1000);
});

function updateVolume(val) {
    soundVolume = parseFloat(val) / 100;
    localStorage.setItem('notification_volume', soundVolume);
    const valueEl = document.getElementById('settings-volume-value');
    if (valueEl) valueEl.textContent = val + '%';
}

function updateSoundProfile(profile) {
    soundProfile = profile;
    localStorage.setItem('notification_sound_profile', profile);
    playTestTone();
}

function playTestTone() {
    playSound('new_message');
}

function syncSoundControlsUI() {
    const slider = document.getElementById('settings-volume-slider');
    if (slider) {
        slider.value = Math.round(soundVolume * 100);
    }
    const valueEl = document.getElementById('settings-volume-value');
    if (valueEl) {
        valueEl.textContent = Math.round(soundVolume * 100) + '%';
    }
    const select = document.getElementById('settings-sound-profile');
    if (select) {
        select.value = soundProfile;
    }
    const toggleBtn = document.getElementById('settings-sound-toggle-btn');
    if (toggleBtn) {
        if (soundEnabled) {
            toggleBtn.innerHTML = '🔊 <span>Звук увімкнено</span>';
            toggleBtn.classList.remove('sound-disabled');
        } else {
            toggleBtn.innerHTML = '🔇 <span>Звук вимкнено</span>';
            toggleBtn.classList.add('sound-disabled');
        }
    }
}

function togglePanelCollapse(headerElement, event) {
    // If the click is inside a switch-container, button, or input, don't toggle collapse
    if (event && (event.target.closest('.switch-container') || event.target.closest('button') || event.target.closest('input') || event.target.closest('textarea'))) {
        return;
    }
    const panel = headerElement.closest('.panel');
    if (panel) {
        panel.classList.toggle('collapsed');
    }
}

