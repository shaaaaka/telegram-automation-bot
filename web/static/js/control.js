// --- Tab 1: Control Panel Management ---

// Render lines list table
function renderLines() {
    const tbody = document.getElementById('lines-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    let filtered = allLines || [];
    if (currentLinesFilter === 'free') {
        filtered = filtered.filter(l => l.status === 'available');
    } else if (currentLinesFilter === 'busy') {
        filtered = filtered.filter(l => l.status === 'busy');
    } else if (currentLinesFilter === 'success') {
        filtered = filtered.filter(l => l.status === 'success');
    } else if (currentLinesFilter === 'banned') {
        filtered = filtered.filter(l => l.status === 'banned');
    }

    const lineFilters = ['all', 'free', 'busy', 'success', 'banned'];
    lineFilters.forEach(f => {
        const btn = document.getElementById(`filter-${f}-btn`);
        if (btn) {
            if (currentLinesFilter === f) {
                btn.classList.remove('btn-secondary');
                btn.classList.add('btn-primary');
            } else {
                btn.classList.remove('btn-primary');
                btn.classList.add('btn-secondary');
            }
            btn.style.background = '';
        }
    });

    if (filtered.length === 0) {
        let emptyMessage = 'Наразі немає доданих телефонних ліній';
        if (currentLinesFilter === 'free') {
            emptyMessage = 'Наразі немає вільних телефонних ліній';
        } else if (currentLinesFilter === 'busy') {
            emptyMessage = 'Наразі немає зайнятих телефонних ліній';
        } else if (currentLinesFilter === 'success') {
            emptyMessage = 'Наразі немає успішно зареєстрованих ліній';
        } else if (currentLinesFilter === 'banned') {
            emptyMessage = 'Наразі немає ліній із відмовами';
        }
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${emptyMessage}</td></tr>`;
        return;
    }

    filtered.forEach(line => {
        const tr = document.createElement('tr');
        let statusText = 'Зайнята';
        let statusClass = 'line-status-busy';
        if (line.status === 'available') {
            statusText = 'Вільна';
            statusClass = 'line-status-free';
        } else if (line.status === 'success') {
            statusText = 'Успішна';
            statusClass = 'line-status-success';
        } else if (line.status === 'banned') {
            statusText = 'Відмова';
            statusClass = 'line-status-banned';
        }
        
        let displayName = line.bank;
        if (window.bankTemplates && window.bankTemplates[line.bank]) {
            displayName = window.bankTemplates[line.bank].display_name || line.bank;
        }
        tr.innerHTML = `
            <td>${line.line_id}</td>
            <td><span class="phone-number-copy" onclick="copyToClipboard('+${line.phone_number}')">+${line.phone_number}</span></td>
            <td>${displayName}</td>
            <td><div class="status-wrapper"><span class="line-status-dot ${statusClass}"></span><span>${statusText}</span></div></td>
            <td>
                <button type="button" class="btn-delete-line" onclick="handleDeleteLine(${line.id}, ${line.line_id}, '${line.bank}')" title="Видалити лінію">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        <line x1="10" y1="11" x2="10" y2="17"></line>
                        <line x1="14" y1="11" x2="14" y2="17"></line>
                    </svg>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// Add Custom Line select controls
function toggleCustomSelect() {
    const container = document.getElementById('bank-select-container');
    if (container) container.classList.toggle('active');
}

function selectCustomOption(optionEl, event) {
    if (event) event.stopPropagation();
    const val = optionEl.getAttribute('data-value');
    document.getElementById('add-bank').value = val;
    document.getElementById('custom-select-value').innerText = val;
    document.getElementById('custom-select-value').style.color = '#ffffff';
    
    const options = document.querySelectorAll('#custom-select-options-list .add-bank-option');
    options.forEach(opt => opt.classList.remove('selected'));
    optionEl.classList.add('selected');
    
    const container = document.getElementById('bank-select-container');
    if (container) container.classList.remove('active');
}

document.addEventListener('click', function(event) {
    const container = document.getElementById('bank-select-container');
    if (container && !container.contains(event.target)) {
        container.classList.remove('active');
    }
});

// Manual line addition
async function handleAddLine(event) {
    event.preventDefault();
    const rawPhone = document.getElementById('add-phone').value.trim();
    let phone_number = rawPhone;
    let line_id = null;

    const lineMatch = rawPhone.match(/^(?:Line\s+)?(\d+)\s+Return:\s*(\d+)(?:\s+(.+))?$/i);
    if (lineMatch) {
        line_id = parseInt(lineMatch[1]);
        phone_number = lineMatch[2];
    } else {
        phone_number = rawPhone.replace(/[^0-9]/g, '');
    }

    const bank = document.getElementById('add-bank').value.trim();

    try {
        const res = await fetch('/api/lines', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: 0, line_id, phone_number, bank })
        });
        if (res.ok) {
            document.getElementById('add-line-form').reset();
            document.getElementById('add-bank').value = '';
            document.getElementById('custom-select-value').innerText = 'Банк';
            document.getElementById('custom-select-value').style.color = 'rgba(255, 255, 255, 0.4)';
            const options = document.querySelectorAll('#custom-select-options-list .add-bank-option');
            options.forEach(opt => opt.classList.remove('selected'));
            
            showToast("Лінію додано успішно!", "success");
            pollData();
        } else {
            const err = await res.json();
            showToast("Помилка: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося додати лінію", "error");
    }
}

async function clearLines() {
    const confirmed = await showConfirm("Ви впевнені, що хочете видалити ВСІ лінії з бази даних?", "danger");
    if (!confirmed) return;
    try {
        const res = await fetch('/api/lines/clear', { method: 'POST' });
        if (res.ok) {
            showToast("Базу ліній очищено.", "success");
            pollData();
        }
    } catch (err) {
        showToast("Помилка при очищенні ліній", "error");
    }
}

async function handleDeleteLine(lineId, lineNo, bank) {
    const label = lineNo ? `Line ${lineNo}` : `ID ${lineId}`;
    const confirmed = await showConfirm(`Ви впевнені, що хочете видалити ${label}?`, 'danger');
    if (!confirmed) return;
    try {
        const res = await fetch(`/api/lines/${lineId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showToast("Лінію видалено успішно!", "success");
            pollData();
        } else {
            const err = await res.json();
            showToast("Помилка: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося видалити лінію", "error");
    }
}

// Render Unrouted Codes banner
function renderUnroutedCodes(codes, sessions) {
    const container = document.getElementById('unrouted-box');
    const itemsList = document.getElementById('unrouted-list-items');
    
    if (!codes || codes.length === 0) {
        if (container) container.style.display = 'none';
        return;
    }

    if (container) container.style.display = 'block';
    if (!itemsList) return;
    itemsList.innerHTML = '';

    const waitingSessions = (sessions || []).filter(s => s.status === 'waiting_code');

    codes.forEach(codeItem => {
        const div = document.createElement('div');
        div.className = 'unrouted-item';
        
        let selectOptions = `<option value="">-- Оберіть клієнта --</option>`;
        waitingSessions.forEach(s => {
            const line = (allLines || []).find(l => l.id === s.line_id);
            const bankName = line ? line.bank : 'Невідомий банк';
            const displayName = extractDisplayName(s.client_data, s.username);
            selectOptions += `<option value="${s.client_id}">${displayName} (Line ${s.line_id} - ${bankName})</option>`;
        });

        div.innerHTML = `
            <div>
                Код: <span class="code-box" onclick="copyToClipboard('${codeItem.code}')">${codeItem.code}</span>
                <span class="received-time">Отримано о: ${codeItem.received_at}</span>
            </div>
            <div class="routing-actions">
                <select id="route-select-${codeItem.code}">
                    ${selectOptions}
                </select>
                <button class="btn btn-success btn-sm" onclick="routeCodeToClient('${codeItem.code}')">Перенаправити</button>
            </div>
        `;
        itemsList.appendChild(div);
    });
}

// Manual code routing
async function routeCodeToClient(code) {
    const select = document.getElementById(`route-select-${code}`);
    const clientId = select ? select.value : '';
    if (!clientId) {
        showToast("Будь ласка, оберіть клієнта для цього коду!", "error");
        return;
    }

    try {
        const res = await fetch(`/api/sessions/${clientId}/route-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        if (res.ok) {
            showToast("Код успішно перенаправлено клієнту!", "success");
            pollData();
        } else {
            const err = await res.json();
            showToast("Помилка: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося перенаправити код", "error");
    }
}

// Format client registration metadata
function renderClientDataHTML(session) {
    const rawData = session.client_data;
    if (!rawData) return '<div class="no-data">Немає даних</div>';
    const lines = rawData.split('\n');
    let html = '<div class="client-data-text-block">';
    lines.forEach(line => {
        const trimmed = line.trim();
        if (!trimmed) {
            html += '<div style="height: 10px;"></div>';
            return;
        }
        const colonIdx = trimmed.indexOf(':');
        if (colonIdx !== -1) {
            const key = trimmed.substring(0, colonIdx).trim();
            const val = trimmed.substring(colonIdx + 1).trim();
            html += `
                <div class="client-data-line">
                    <span class="client-data-key">${key}:</span>
                    <span class="client-data-val" onclick="copyTextToClipboard('${val}', event)" title="Клікніть, щоб скопіювати">${val}</span>
                </div>
            `;
        } else {
            html += `
                <div class="client-data-raw-line">${trimmed}</div>
            `;
        }
    });
    html += '</div>';
    return html;
}

// Render dropdown tray for success/failure tags
function renderVerifierActionsHTML(session) {
    if (Number(session.is_verified) === 1) {
        return `
            <button class="btn btn-primary btn-sm" onclick="completeSessionBank(${session.client_id}, 'release')" ${!session.line_id ? 'disabled' : ''}>
                Завершити реєстрацію банку
            </button>
        `;
    }
    
    // Якщо банки обрані, але ще не перевірений дроп
    const selectedBanksStr = session.selected_banks;
    const selected = selectedBanksStr ? selectedBanksStr.split(',').filter(Boolean) : [];
    if (selected.length === 0) {
        // Якщо банки не обрані, не показуємо кнопки перевірки в футері
        return '';
    }

    const isRegistering = session.status === 'registering' || !session.client_data || session.client_data.includes('Невідомо');
    
    if (session.status === 'waiting_verification') {
        return `
            <span class="session-status status-waiting_verification">
                Очікує перевірки
            </span>
            <button class="btn btn-secondary btn-sm" onclick="verifyManually(${session.client_id})" ${isRegistering ? 'disabled title="Анкету ще не заповнено клієнтом"' : ''}>
                Схвалити вручну
            </button>
        `;
    }
    
    return `
        <button class="btn btn-primary btn-sm" onclick="sendToVerifier(${session.client_id})" ${isRegistering ? 'disabled title="Анкету ще не заповнено клієнтом"' : ''}>
            Надіслати
        </button>
        <button class="btn btn-secondary btn-sm" onclick="verifyManually(${session.client_id})" ${isRegistering ? 'disabled title="Анкету ще не заповнено клієнтом"' : ''}>
            Схвалити вручну
        </button>
    `;
}

// Render dropdown tray for success/failure tags
function renderActionTrayHTML(session) {
    if (Number(session.is_verified) !== 1) {
        return '';
    }
    const isTrayOpen = openActionTrays.has(session.client_id);
    const disabledAttr = !session.line_id ? 'disabled' : '';
    return `
        <div class="action-tray-container ${isTrayOpen ? 'open' : ''}">
            <button class="btn btn-secondary btn-sm action-tray-toggle" onclick="toggleActionTray(${session.client_id}, event)" ${disabledAttr}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 18 15 12 9 6"></polyline>
                </svg>
            </button>
            <div class="action-tray-content">
                <button class="btn btn-success btn-sm" onclick="completeSessionBank(${session.client_id}, 'success')" ${disabledAttr}>
                    Зареєстрував
                </button>
                <button class="btn btn-danger btn-sm" onclick="completeSessionBank(${session.client_id}, 'failure')" ${disabledAttr}>
                    Відмова
                </button>
            </div>
        </div>
    `;
}

// Render main Client Cards list
function renderSessions(sessions) {
    const activeId = document.activeElement ? document.activeElement.id : null;
    const selectionStart = document.activeElement && (document.activeElement.tagName === 'TEXTAREA' || document.activeElement.tagName === 'INPUT') ? document.activeElement.selectionStart : null;
    const selectionEnd = document.activeElement && (document.activeElement.tagName === 'TEXTAREA' || document.activeElement.tagName === 'INPUT') ? document.activeElement.selectionEnd : null;

    let filtered = sessions || [];

    const activeCountEl = document.getElementById('active-sessions-count');
    if (activeCountEl) {
        activeCountEl.innerText = `Активних: ${sessions.length}`;
    }
    
    const container = document.getElementById('sessions-container');
    if (!container) return;

    if (container.querySelector('.session-card-placeholder')) {
        container.innerHTML = '';
    }

    const existingCards = {};
    Array.from(container.children).forEach(child => {
        if (child.classList.contains('session-card')) {
            const id = child.getAttribute('data-id');
            if (id) existingCards[id] = child;
        }
    });

    const activeClientIds = new Set();



    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <span>🔌</span>
                <span>Немає активних сесій</span>
            </div>
        `;
    } else {
        const emptyState = container.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        filtered.forEach(session => {
            activeClientIds.add(session.client_id);
            const isExpanded = expandedSessions.has(session.client_id);
            const isFinishLine = session.line_id && session.success_photo_id;

            let card = existingCards[session.client_id];
            let isNewCard = !card;
            if (isNewCard) {
                card = document.createElement('div');
                card.setAttribute('data-id', session.client_id);
            }

            const targetClassName = `session-card ${session.status} ${isExpanded ? 'expanded' : ''} ${isFinishLine ? 'finish-line' : ''}`;
            if (card.className !== targetClassName) {
                card.className = targetClassName;
            }

            const displayName = extractDisplayName(session.client_data, session.username) + (isFinishLine ? ' 💳' : '');

            let statusText = 'Новий';
            if (session.status === 'registering') statusText = 'В анкеті';
            if (session.status === 'registered') statusText = 'Новий';
            if (session.status === 'number_assigned') statusText = 'Номер видано';
            if (session.status === 'waiting_code') statusText = 'Очікує код';
            if (session.status === 'waiting_verification') statusText = 'Перевірка';
            if (session.status === 'completed') statusText = 'Завершено';

            let bankChipsHTML = '';
            let selectedList;
            if (tempSelectedBanks[session.client_id] !== undefined) {
                selectedList = tempSelectedBanks[session.client_id];
            } else {
                selectedList = session.selected_banks ? session.selected_banks.split(',') : [];
            }
            
            const remainingBanksStr = session.remaining_banks;
            const remainingList = remainingBanksStr ? remainingBanksStr.split(',').filter(Boolean) : [];
            const bankStatuses = session.bank_statuses || {};
            
            const historyBanks = Object.keys(bankStatuses);
            // Build order dynamically from templates order in Settings
            const savedOrderStr = localStorage.getItem('bank_accordion_order');
            let customOrder = [];
            if (savedOrderStr) {
                try {
                    customOrder = JSON.parse(savedOrderStr);
                } catch(e) {}
            }
            if (!customOrder || customOrder.length === 0) {
                customOrder = ["bank.kd", "izibank", "alliance", "lvivbank", "amobank"];
            }

            const allPossibleBanks = [];
            const seenLower = new Set();
            const inputSources = [...availableBanks, ...selectedList, ...historyBanks];

            // 1. Add all banks from customOrder (preserving settings order)
            customOrder.forEach(b => {
                const lower = b.toLowerCase();
                if (!seenLower.has(lower) && lower !== 'ecobank' && lower !== 'pumb') {
                    seenLower.add(lower);
                    const matched = inputSources.find(x => x.toLowerCase() === lower);
                    allPossibleBanks.push(matched || b);
                }
            });

            // 2. Add any remaining unique banks (fallback)
            inputSources.forEach(b => {
                if (b) {
                    const lower = b.toLowerCase();
                    if (!seenLower.has(lower) && lower !== 'ecobank' && lower !== 'pumb') {
                        seenLower.add(lower);
                        allPossibleBanks.push(b);
                    }
                }
            });

            // 3. Sort allPossibleBanks to match customOrder index
            allPossibleBanks.sort((a, b) => {
                const idxA = customOrder.findIndex(x => x.toLowerCase() === a.toLowerCase());
                const idxB = customOrder.findIndex(x => x.toLowerCase() === b.toLowerCase());
                if (idxA !== -1 && idxB !== -1) return idxA - idxB;
                if (idxA !== -1) return -1;
                if (idxB !== -1) return 1;
                return a.localeCompare(b);
            });

            const isRegistering = session.status === 'registering';

            allPossibleBanks.forEach(bank => {
                const isSelected = selectedList.some(x => x.toLowerCase() === bank.toLowerCase());
                const isRemaining = remainingList.some(x => x.toLowerCase() === bank.toLowerCase());
                const bankClass = getBankClass(bank);
                const historyKey = Object.keys(bankStatuses).find(x => x.toLowerCase() === bank.toLowerCase());
                const hasHistory = historyKey !== undefined;

                // Hide chip if bank is paused globally, and client is not active on it or has no history
                const isGloballyActive = typeof availableBanks !== 'undefined' && availableBanks.some(x => x.toLowerCase() === bank.toLowerCase());
                if (!isGloballyActive && !isSelected && !hasHistory && !isRemaining) {
                    return;
                }

                let chipClasses = `bank-chip ${bankClass}`;
                let statusIcon = '';
                let onclickAttr = '';

                if (isRemaining) {
                    chipClasses += ' selected';
                    if (hasHistory) {
                        onclickAttr = ''; // Не дозволяємо віджати назад в архів
                    } else {
                        onclickAttr = `onclick="toggleBankChip(this, ${session.client_id}, '${bank}', '')"`;
                    }
                } else {
                    if (hasHistory) {
                        const status = bankStatuses[historyKey] || 'released';
                        if (status === 'success') {
                            chipClasses += ' success-done';
                            statusIcon = '<span class="chip-status-icon">✓</span>';
                            onclickAttr = '';
                        } else if (status === 'failure' || status === 'banned') {
                            chipClasses += ' failure-done';
                            statusIcon = '<span class="chip-status-icon">✗</span>';
                            onclickAttr = '';
                        } else {
                            chipClasses += ' released-done';
                            statusIcon = '<span class="chip-status-icon">↻</span>';
                            onclickAttr = `onclick="toggleBankChip(this, ${session.client_id}, '${bank}', 'readd')"`;
                        }
                    } else {
                        onclickAttr = `onclick="toggleBankChip(this, ${session.client_id}, '${bank}', 'readd')"`;
                    }
                }
                
                if (isRegistering) {
                    chipClasses += ' disabled';
                    onclickAttr = '';
                }

                bankChipsHTML += `
                    <div class="${chipClasses}" ${onclickAttr}>
                        <input type="checkbox" data-bank="${bank}" ${isSelected ? 'checked' : ''} style="display: none;">
                        ${statusIcon}
                        <span>${(function() {
                            let displayName = bank;
                            if (window.bankTemplates && window.bankTemplates[bank]) {
                                displayName = window.bankTemplates[bank].display_name || bank;
                            }
                            return displayName;
                        })()}</span>
                    </div>
                `;
            });

            let assignmentHTML = '';
            const selectedBanksStr = session.selected_banks;
            const selected = selectedBanksStr ? selectedBanksStr.split(',').filter(Boolean) : [];
            const remaining = remainingList;

            if (session.status === 'registering') {
                assignmentHTML = `
                    <div class="assignment-box bank-select-prompt info-box" style="background: rgba(156, 163, 175, 0.05); border-color: rgba(156, 163, 175, 0.2); color: #9ca3af;">
                        <span>📝 Клієнт заповнює реєстраційні дані в боті...</span>
                    </div>
                `;
            } else if (selected.length === 0) {
                assignmentHTML = `
                    <div class="assignment-box bank-select-prompt">
                        <span>⚠️ Будь ласка, оберіть один або кілька банків вище для початку роботи.</span>
                    </div>
                `;
            } else if (Number(session.is_verified) !== 1) {
                assignmentHTML = '';
            } else if (remaining.length > 0) {
                if (session.line_id) {
                    const activeLine = (allLines || []).find(l => l.id === session.line_id);
                    const phoneNum = activeLine ? `+${activeLine.phone_number}` : 'Невідомий';
                    let bankName = 'Банк';
                    if (activeLine) {
                        bankName = activeLine.bank;
                        if (window.bankTemplates && window.bankTemplates[bankName]) {
                            bankName = window.bankTemplates[bankName].display_name || bankName;
                        }
                    }
                    assignmentHTML = `
                        <div class="assignment-box active-line-capsule-container">
                            <div class="section-label">Призначено лінію</div>
                            <div class="active-line-capsule">
                                <span class="capsule-line">Line ${activeLine ? activeLine.line_id : session.line_id} (${bankName})</span>
                                <span class="capsule-divider">•</span>
                                <span class="capsule-phone" onclick="copyToClipboard('${phoneNum}')" title="Клікніть, щоб скопіювати">${phoneNum}</span>
                            </div>
                        </div>
                    `;
                } else {
                    const freeLines = (allLines || []).filter(l => l.status === 'available' && remaining.some(b => b.toLowerCase() === l.bank.toLowerCase()));
                    const currentTempLineId = tempSelectedLines[session.client_id] || "";

                    let selectOptions = freeLines.map(l => {
                        const isSelected = String(l.id) === String(currentTempLineId);
                        return `<option value="${l.id}" ${isSelected ? 'selected' : ''}>Line ${l.line_id} (${l.bank})</option>`;
                    }).join('');
                    
                    let customOptionsHTML = '';
                    let currentTriggerText = 'Оберіть лінію';
                    
                    if (freeLines.length === 0) {
                        currentTriggerText = `Немає вільних ліній`;
                        customOptionsHTML = `<div class="custom-select-option disabled">Немає вільних ліній</div>`;
                        selectOptions = `<option value="">Немає вільних ліній</option>`;
                    } else {
                        if (currentTempLineId !== "") {
                            const selectedLine = freeLines.find(l => String(l.id) === String(currentTempLineId));
                            if (selectedLine) {
                                currentTriggerText = `Line ${selectedLine.line_id} (${selectedLine.bank})`;
                            }
                        }
                        
                        selectOptions = `<option value="" ${currentTempLineId === "" ? 'selected' : ''}>Оберіть лінію</option>` + selectOptions;
                        
                        customOptionsHTML += `
                            <div class="custom-select-option ${currentTempLineId === "" ? 'selected' : ''}" data-value="">
                                Оберіть лінію
                            </div>
                        `;
                        
                        freeLines.forEach(l => {
                            const isSelected = String(l.id) === String(currentTempLineId);
                            customOptionsHTML += `
                                <div class="custom-select-option ${isSelected ? 'selected' : ''}" data-value="${l.id}">
                                    <span>Line ${l.line_id} (${l.bank})</span>
                                </div>
                            `;
                        });
                    }

                    assignmentHTML = `
                        <div class="assignment-box">
                            <div class="section-label">Призначити наступну лінію</div>
                            <div class="assign-controls">
                                <select id="line-select-${session.client_id}" onchange="onLineSelectChange(this, ${session.client_id})" style="display: none;">
                                    ${selectOptions}
                                </select>
                                
                                <div class="custom-select-wrapper" id="custom-select-wrapper-${session.client_id}">
                                    <div class="custom-select-trigger ${freeLines.length === 0 ? 'disabled' : ''}" onclick="toggleCustomDropdown(${session.client_id}, event)">
                                        <span id="custom-select-trigger-text-${session.client_id}">${currentTriggerText}</span>
                                        <svg class="custom-select-arrow" width="16" height="16" viewBox="0 0 24 24"><path d="M7 10l5 5 5-5z"/></svg>
                                    </div>
                                    <div class="custom-select-options" id="custom-select-options-${session.client_id}">
                                        ${customOptionsHTML}
                                    </div>
                                </div>
                                
                                <button class="btn btn-primary btn-sm" onclick="assignLine(${session.client_id})" ${freeLines.length === 0 ? 'disabled' : ''}>Призначити</button>
                            </div>
                        </div>
                    `;
                }
            } else {
                assignmentHTML = `
                    <div class="assignment-box banks-completed-message">
                        <span>Усі обрані банки успішно завершено! Очікує закриття сесії.</span>
                    </div>
                `;
            }

            const usernameHTML = (session.username && session.username !== "Немає юзернейму")
                ? `<span class="client-username-sub">@${session.username}</span>`
                : '';

            const newHTML = `
                <div class="card-header-bar" onclick="toggleExpand(${session.client_id})">
                    <div class="header-left">
                        <span class="client-name-formatted">${displayName}</span>
                        ${usernameHTML}
                    </div>
                    <div class="header-right">
                        <span class="sla-timer" data-client-id="${session.client_id}" data-status="${session.status}">⏳ Запуск...</span>
                        <span class="session-status status-${session.status}">${statusText}</span>
                        <button class="btn-chat-modal-circle" onclick="event.stopPropagation(); openChatModal(${session.client_id}, event)" title="Відкрити чат">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
                                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                            </svg>
                        </button>
                        <svg class="chevron-icon" width="20" height="20" viewBox="0 0 24 24" onclick="toggleExpand(${session.client_id}); event.stopPropagation();" style="margin-left: 4px; cursor: pointer;"><path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/></svg>
                    </div>
                </div>
                
                <div class="card-body-details">
                    <div class="section-label">Реєстраційні дані</div>
                    <div class="client-data">
                        ${renderClientDataHTML(session)}
                    </div>
                    
                    <div class="banks-selection">
                        <div class="section-label">Обрані банки</div>
                        <div class="banks-checkboxes" id="banks-checkboxes-${session.client_id}">
                            ${bankChipsHTML}
                        </div>
                    </div>
                    
                    ${assignmentHTML}
                    
                    <div class="action-footer">
                        <div class="action-footer-left">
                            <button class="btn btn-outline-danger btn-sm" onclick="banUser(${session.client_id})">
                                Забанити
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="terminateSession(${session.client_id})">
                                ${session.status === 'registering' ? 'Скасувати реєстрацію' : 'Закрити сесію'}
                            </button>
                        </div>
                        <div class="action-footer-right">
                            ${renderActionTrayHTML(session)}
                            ${renderVerifierActionsHTML(session)}
                        </div>
                    </div>
                </div>
            `;

            if (card.innerHTML.trim() !== newHTML.trim()) {
                card.innerHTML = newHTML;
            }

            container.appendChild(card);
        });

        Object.keys(existingCards).forEach(id => {
            if (!activeClientIds.has(parseInt(id))) {
                existingCards[id].remove();
            }
        });
    }

    if (activeId) {
        const el = document.getElementById(activeId);
        if (el) {
            el.focus();
            if (selectionStart !== null && selectionEnd !== null) {
                try {
                    el.setSelectionRange(selectionStart, selectionEnd);
                } catch (e) {}
            }
        }
    }

    updateTimers();
}

// Toggle client selected bank
async function toggleBankChip(element, clientId, bank, action = '') {
    if (action === 'readd') {
        try {
            const res = await fetch(`/api/sessions/${clientId}/banks/readd?bank=${encodeURIComponent(bank)}`, {
                method: 'POST'
            });
            if (res.ok) {
                pollData();
            } else {
                showToast("Помилка при спробі додати банк назад", "error");
            }
        } catch (err) {
            console.error("Failed to re-add bank:", err);
            showToast("Не вдалося зв'язатися з сервером", "error");
        }
        return;
    }

    const checkbox = element.querySelector('input');
    const container = document.getElementById(`banks-checkboxes-${clientId}`);
    if (!container) return;
    
    checkbox.checked = !checkbox.checked;
    if (checkbox.checked) {
        element.classList.add('selected');
    } else {
        element.classList.remove('selected');
    }
    
    const checkedInputs = container.querySelectorAll('input[type="checkbox"]:checked');
    const selected_banks = Array.from(checkedInputs).map(input => input.getAttribute('data-bank'));
    tempSelectedBanks[clientId] = selected_banks;

    try {
        const res = await fetch(`/api/sessions/${clientId}/banks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ selected_banks })
        });
        if (res.ok) {
            delete tempSelectedBanks[clientId];
            pollData();
        } else {
            console.error("Failed to auto-save banks");
        }
    } catch (err) {
        console.error("Auto-save banks request error:", err);
    }
}

function onLineSelectChange(selectElement, clientId) {
    tempSelectedLines[clientId] = selectElement.value;
}

function toggleCustomDropdown(clientId, event) {
    event.stopPropagation();
    
    document.querySelectorAll('.custom-select-options.active').forEach(optionsPanel => {
        if (optionsPanel.id !== `custom-select-options-${clientId}`) {
            optionsPanel.classList.remove('active');
            const wrapper = optionsPanel.parentElement;
            if (wrapper) wrapper.querySelector('.custom-select-trigger').classList.remove('active');
        }
    });

    const trigger = event.currentTarget;
    const optionsPanel = document.getElementById(`custom-select-options-${clientId}`);
    if (optionsPanel) {
        const isActive = optionsPanel.classList.contains('active');
        if (isActive) {
            optionsPanel.classList.remove('active');
            trigger.classList.remove('active');
        } else {
            optionsPanel.classList.add('active');
            trigger.classList.add('active');
            
            const options = optionsPanel.querySelectorAll('.custom-select-option');
            options.forEach(opt => {
                opt.onclick = (e) => {
                    e.stopPropagation();
                    const val = opt.getAttribute('data-value');
                    
                    const nativeSelect = document.getElementById(`line-select-${clientId}`);
                    if (nativeSelect) {
                        nativeSelect.value = val;
                        onLineSelectChange(nativeSelect, clientId);
                    }
                    
                    options.forEach(o => o.classList.remove('selected'));
                    opt.classList.add('selected');
                    
                    const textSpan = document.getElementById(`custom-select-trigger-text-${clientId}`);
                    if (textSpan) {
                        textSpan.innerText = opt.querySelector('span') ? opt.querySelector('span').innerText : opt.innerText.trim();
                    }
                    
                    optionsPanel.classList.remove('active');
                    trigger.classList.remove('active');
                };
            });
        }
    }
}

// Assign selected line to client
async function assignLine(clientId) {
    let lineId = tempSelectedLines[clientId];
    if (!lineId) {
        const select = document.getElementById(`line-select-${clientId}`);
        if (select) {
            lineId = select.value;
        }
    }

    if (!lineId) {
        showToast("Оберіть лінію для призначення!", "error");
        return;
    }

    try {
        const res = await fetch(`/api/sessions/${clientId}/assign`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ line_id: parseInt(lineId) })
        });
        if (res.ok) {
            showToast("Лінію успішно призначено!", "success");
            delete tempSelectedLines[clientId];
            pollData();
        } else {
            const err = await res.json();
            showToast("Помилка: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося призначити лінію", "error");
    }
}

async function completeSessionBank(clientId, result = 'success') {
    try {
        const res = await fetch(`/api/sessions/${clientId}/complete?result=${result}`, {
            method: 'POST'
        });
        if (res.ok) {
            if (result === 'success') {
                showToast("Поточний банк успішно завершено!", "success");
            } else if (result === 'release') {
                showToast("Номер успішно звільнено, банк відправлено в повернення.", "info");
            } else {
                showToast("Позначено як відмова банку.", "warning");
            }
            pollData();
        } else {
            const err = await res.json();
            showToast("Помилка: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося завершити верифікацію банку", "error");
    }
}

// Ban / Unban
async function banUser(clientId) {
    const confirmed = await showConfirm("Ви впевнені, що хочете ЗАБЛОКУВАТИ цього користувача? Його поточну сесію буде закрито, і він більше не зможе користуватися ботом.", "danger");
    if (!confirmed) return;
    try {
        const res = await fetch(`/api/users/${clientId}/ban`, {
            method: 'POST'
        });
        if (res.ok) {
            showToast("Користувача заблоковано!", "success");
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
        } else {
            const data = await res.json();
            showToast(data.detail || "Помилка блокування", "danger");
        }
    } catch (err) {
        showToast("Помилка зв'язку з сервером", "danger");
    }
}

async function unbanUser(clientId) {
    try {
        const res = await fetch(`/api/users/${clientId}/unban`, {
            method: 'POST'
        });
        if (res.ok) {
            showToast("Користувача розблоковано!", "success");
            loadBannedUsers();
        } else {
            const data = await res.json();
            showToast(data.detail || "Помилка розблокування", "danger");
        }
    } catch (err) {
        showToast("Помилка зв'язку з сервером", "danger");
    }
}

async function terminateSession(clientId) {
    const confirmed = await showConfirm("Ви впевнені, що хочете остаточно закрити сесію для цього клієнта?", "danger");
    if (!confirmed) return;
    try {
        const res = await fetch(`/api/sessions/${clientId}/terminate`, {
            method: 'POST'
        });
        if (res.ok) {
            showToast("Сесію закрито!", "success");
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
        } else {
            const err = await res.json();
            showToast("Помилка: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося закрити сесію", "error");
    }
}

function toggleActionTray(clientId, event) {
    if (event) event.stopPropagation();
    
    const isOpen = openActionTrays.has(clientId);
    if (isOpen) {
        openActionTrays.delete(clientId);
    } else {
        openActionTrays.add(clientId);
    }
    
    const container = document.querySelector(`.session-card[data-id="${clientId}"] .action-tray-container`);
    if (container) {
        container.classList.toggle('open');
    }
}

function toggleExpand(clientId) {
    const card = document.querySelector(`.session-card[data-id="${clientId}"]`);
    if (expandedSessions.has(clientId)) {
        expandedSessions.delete(clientId);
        if (card) card.classList.remove('expanded');
    } else {
        expandedSessions.add(clientId);
        if (card) card.classList.add('expanded');
    }
    try {
        localStorage.setItem('expandedSessions', JSON.stringify(Array.from(expandedSessions)));
    } catch (e) {}
}

// Open Chat tab from control panel
function openChatModal(clientId, event) {
    if (event) event.stopPropagation();
    switchTab('chat');
    selectChatClient(clientId);
}

// Lightbox view for image verification previews
function openLightbox(src) {
    const overlay = document.getElementById('image-lightbox');
    const img = document.getElementById('lightbox-img');
    if (overlay && img) {
        img.src = src;
        overlay.classList.add('active');
    }
}

function closeLightbox() {
    const overlay = document.getElementById('image-lightbox');
    if (overlay) {
        overlay.classList.remove('active');
    }
}

function extractDisplayName(clientData, username) {
    if (!clientData) return username ? `@${username}` : "Клієнт";
    
    const lines = clientData.split('\n').map(l => l.trim()).filter(Boolean);
    
    for (let line of lines) {
        if (line.toUpperCase().startsWith("ПІБ:")) {
            const namePart = line.substring(4).trim();
            const words = namePart.split(/\s+/).filter(w => w.length > 0);
            if (words.length >= 2) {
                const surname = words[0];
                const firstName = words[1];
                let patronymic = "";
                if (words[2]) {
                    const cleanLetter = words[2].replace(/[^а-яА-ЯёЁіІїЇєЄґҐa-zA-Z]/g, '');
                    if (cleanLetter.length > 0) {
                        patronymic = ` ${cleanLetter[0]}.`;
                    }
                }
                return `${surname} ${firstName}${patronymic}`;
            }
            return namePart;
        }
    }
    
    for (let line of lines) {
        if (/^\+?\d+$/.test(line.replace(/\s+/g, ''))) continue;
        if (/^\d{2}\.\d{2}\.\d{4}$/.test(line)) continue;
        if (line.toUpperCase().startsWith("ІПН:") || line.toUpperCase().startsWith("ДРОП")) continue;
        
        const words = line.split(/\s+/).filter(w => w.length > 0);
        if (words.length >= 2) {
            if (/[а-яА-ЯёЁіІїЇєЄґҐa-zA-Z]/.test(words[0])) {
                const surname = words[0];
                const firstName = words[1];
                let patronymic = "";
                
                if (words[2]) {
                    const cleanLetter = words[2].replace(/[^а-яА-ЯёЁіІїЇєЄґҐa-zA-Z]/g, '');
                    if (cleanLetter.length > 0) {
                        patronymic = ` ${cleanLetter[0]}.`;
                    }
                }
                return `${surname} ${firstName}${patronymic}`;
            }
        }
    }
    
    return username ? `@${username}` : "Клієнт";
}

async function sendClientMessage(clientId) {
    const textarea = document.getElementById(`msg-input-${clientId}`);
    if (!textarea) return;
    const message = textarea.value.trim();
    if (!message) {
        showToast("Введіть текст повідомлення!", "error");
        return;
    }

    try {
        const res = await fetch(`/api/sessions/${clientId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        if (res.ok) {
            showToast("Повідомлення надіслано!", "success");
            textarea.value = "";
            delete tempMessageInputs[clientId];
        } else {
            const err = await res.json();
            showToast("Помилка надсилання: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося надіслати повідомлення", "error");
    }
}

async function sendToVerifier(clientId) {
    try {
        const res = await fetch(`/api/sessions/${clientId}/send-to-verifier`, {
            method: 'POST'
        });
        if (res.ok) {
            showToast("Анкету надіслано верифікатору!", "success");
            if (typeof pollData === 'function') {
                await pollData();
            }
        } else {
            const err = await res.json();
            showToast("Помилка відправки: " + (err.detail || "невідома помилка"), "error");
        }
    } catch (err) {
        showToast("Не вдалося надіслати анкету", "error");
    }
}

async function verifyManually(clientId) {
    try {
        const res = await fetch(`/api/sessions/${clientId}/verify-manually`, {
            method: 'POST'
        });
        if (res.ok) {
            showToast("Анкету схвалено вручну!", "success");
            if (typeof pollData === 'function') {
                await pollData();
            }
        } else {
            const err = await res.json();
            showToast("Помилка схвалення: " + (err.detail || "невідома помилка"), "error");
        }
    } catch (err) {
        showToast("Не вдалося схвалити анкету", "error");
    }
}

// Dynamic population of manual bank selection dropdown
function renderAddLineBanksDropdown() {
    const list = document.getElementById('custom-select-options-list');
    if (!list) return;
    
    // Save currently selected value if any
    const currentValue = document.getElementById('add-bank').value;
    
    list.innerHTML = '';
    if (typeof availableBanks !== 'undefined' && Array.isArray(availableBanks)) {
        availableBanks.forEach(bank => {
            const option = document.createElement('div');
            option.className = 'add-bank-option';
            option.setAttribute('data-value', bank);
            if (bank === currentValue) {
                option.classList.add('selected');
            }
            option.onclick = function(e) { selectCustomOption(this, e); };
            
            // Try to find display name in templates, fallback to key
            let displayName = bank;
            if (window.bankTemplates && window.bankTemplates[bank]) {
                displayName = window.bankTemplates[bank].display_name || bank;
            }
            
            option.textContent = displayName;
            list.appendChild(option);
        });
    }
}

// Expose globally
window.renderAddLineBanksDropdown = renderAddLineBanksDropdown;

// Run once on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderAddLineBanksDropdown);
} else {
    renderAddLineBanksDropdown();
}
