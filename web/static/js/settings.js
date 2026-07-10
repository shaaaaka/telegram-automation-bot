// --- Tab 4 & 5: Bot Settings, AI Parameters & Training Rules ---

async function loadBannedUsers() {
    try {
        const res = await fetch('/api/banned-users');
        if (!res.ok) throw new Error("Status code: " + res.status);
        const users = await res.json();
        
        const countEl = document.getElementById('banned-users-count');
        if (countEl) countEl.innerText = `Всього: ${users.length}`;
        
        const tbody = document.getElementById('banned-users-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';
        
        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: rgba(255,255,255,0.4); padding: 20px;">Немає заблокованих користувачів</td></tr>';
            return;
        }
        
        users.forEach(user => {
            const tr = document.createElement('tr');
            
            let dateStr = user.banned_at;
            try {
                const date = new Date(user.banned_at);
                dateStr = date.toLocaleString('uk-UA');
            } catch(e) {}
            
            tr.innerHTML = `
                <td style="padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); color: rgba(255,255,255,0.8);">${user.client_id}</td>
                <td style="padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); color: rgba(255,255,255,0.8);">${user.username ? '@' + user.username : 'Невідомий'}</td>
                <td style="padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); color: rgba(255,255,255,0.6);">${dateStr}</td>
                <td style="padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <button class="btn btn-primary btn-sm" onclick="unbanUser(${user.client_id})">
                        Розбанити
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        showToast("Помилка завантаження заблокованих користувачів", "danger");
    }
}

async function loadSettings() {
    try {
        const res = await fetch('/api/settings');
        if (!res.ok) throw new Error("Status code: " + res.status);
        const data = await res.json();
        
        const remindersEnabled = data.settings.reminders_enabled !== '0';
        document.getElementById('settings-reminders-enabled').checked = remindersEnabled;
        document.getElementById('settings-reminder-delay').value = data.settings.reminder_delay_minutes || 5;
        document.getElementById('settings-reminder-text').value = data.settings.reminder_text || '';
        document.getElementById('settings-giver-format').value = data.settings.giver_request_format || 'Запрос {line_id} {bank_name}';
        document.getElementById('settings-giver-retry-format').value = data.settings.giver_request_retry_format || 'Запрос {line_id} {bank_name} (ПОВТОРНО)';
        document.getElementById('settings-client-assign-format').value = data.settings.client_number_assigned_format || 'Банк: *{bank_name}*\nНомер телефону:\n\n`+{phone_number}`\n\nКоли надішлете SMS і вам знадобиться код, тисніть кнопку нижче.';
        
        document.getElementById('settings-admin-id').value = data.settings.admin_id || '';
        document.getElementById('settings-anketa-chat-id').value = data.settings.anketa_chat_id || '';
        document.getElementById('settings-giver-chat-id').value = data.settings.giver_chat_id || '';
        document.getElementById('settings-archive-group-id').value = data.settings.archive_group_id || '';
        
        toggleReminderInputs();
        if (typeof syncSoundControlsUI === 'function') {
            syncSoundControlsUI();
        }

        const tableBody = document.getElementById('settings-templates-table-body');
        if (!tableBody) return;
        tableBody.innerHTML = '';

        const keys = Object.keys(data.templates);
        if (keys.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="4" class="empty-state">Немає збережених шаблонів</td></tr>';
            return;
        }

        window.bankTemplates = data.templates;
        keys.forEach(key => {
            const template = data.templates[key];
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-weight: 600;">${key}</td>
                <td style="font-family: monospace; font-size: 0.85rem; color: var(--accent-primary);">${template.command}</td>
                <td style="text-align: center; font-weight: 600;">${template.code_length || 4}</td>
                <td style="font-size: 0.85rem; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${template.text}">${template.text}</td>
                <td style="text-align: right;">
                    <button class="btn btn-primary btn-sm" onclick="editTemplate('${key}')" style="padding: 4px 8px; font-size: 0.75rem; margin-right: 4px;">Редагувати</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteTemplate('${key}')" style="padding: 4px 8px; font-size: 0.75rem;">Видалити</button>
                </td>
            `;
            tableBody.appendChild(tr);
        });
        
        if (typeof renderChatPageTemplates === 'function') {
            renderChatPageTemplates();
        }
    } catch (err) {
        showToast("Не вдалося завантажити налаштування", "error");
    }
}

async function toggleReminderInputs(isManual = false) {
    const enabled = document.getElementById('settings-reminders-enabled').checked;
    document.getElementById('settings-reminder-delay').disabled = !enabled;
    document.getElementById('settings-reminder-text').disabled = !enabled;
    if (!enabled) {
        document.getElementById('settings-reminder-delay').removeAttribute('required');
        document.getElementById('settings-reminder-text').removeAttribute('required');
    } else {
        document.getElementById('settings-reminder-delay').setAttribute('required', '');
        document.getElementById('settings-reminder-text').setAttribute('required', '');
    }

    if (isManual) {
        const delay = document.getElementById('settings-reminder-delay').value || '5';
        const text = document.getElementById('settings-reminder-text').value || '';
        const enabledStr = enabled ? '1' : '0';

        try {
            const res = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    reminder_delay_minutes: String(delay),
                    reminder_text: text,
                    reminders_enabled: enabledStr
                })
            });
            if (res.ok) {
                showToast(enabled ? "Нагадування увімкнено!" : "Нагадування повністю вимкнено!", "success");
            }
        } catch (err) {
            console.error("Failed to save reminder toggle state:", err);
        }
    }
}

async function saveGeneralSettings(event) {
    if (event) event.preventDefault();
    const enabled = document.getElementById('settings-reminders-enabled').checked ? '1' : '0';
    const delay = document.getElementById('settings-reminder-delay').value;
    const text = document.getElementById('settings-reminder-text').value;
    const giverFormat = document.getElementById('settings-giver-format').value;
    const giverRetryFormat = document.getElementById('settings-giver-retry-format').value;
    const clientAssignFormat = document.getElementById('settings-client-assign-format').value;
    const adminId = document.getElementById('settings-admin-id').value.trim();
    const anketaChatId = document.getElementById('settings-anketa-chat-id').value.trim();
    const giverChatId = document.getElementById('settings-giver-chat-id').value.trim();
    const archiveGroupId = document.getElementById('settings-archive-group-id').value.trim();

    try {
        const res = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                reminder_delay_minutes: String(delay),
                reminder_text: text,
                reminders_enabled: enabled,
                giver_request_format: giverFormat,
                giver_request_retry_format: giverRetryFormat,
                client_number_assigned_format: clientAssignFormat,
                admin_id: adminId,
                anketa_chat_id: anketaChatId,
                giver_chat_id: giverChatId,
                archive_group_id: archiveGroupId
            })
        });
        if (res.ok) {
            showToast("Налаштування збережено!", "success");
        } else {
            const err = await res.json();
            showToast("Помилка збереження: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Помилка відправки запиту", "error");
    }
}

function editTemplate(key) {
    const template = window.bankTemplates ? window.bankTemplates[key] : null;
    if (!template) return;

    document.getElementById('template-key').value = key;
    document.getElementById('template-key').disabled = true;
    document.getElementById('template-command').value = template.command || '';
    document.getElementById('template-code-length').value = template.code_length || 4;
    document.getElementById('template-text').value = template.text || '';
    
    document.querySelector('#add-template-form button[type="submit"]').textContent = 'Зберегти';
    document.querySelector('.divider-top .section-label').textContent = 'Редагувати шаблон';
    
    if (!document.getElementById('cancel-edit-btn')) {
        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.id = 'cancel-edit-btn';
        cancelBtn.className = 'btn btn-secondary btn-sm';
        cancelBtn.style.height = '38px';
        cancelBtn.style.marginLeft = '8px';
        cancelBtn.textContent = 'Скасувати';
        cancelBtn.onclick = resetTemplateForm;
        document.getElementById('add-template-form').appendChild(cancelBtn);
    }
}

function resetTemplateForm() {
    document.getElementById('add-template-form').reset();
    document.getElementById('template-key').disabled = false;
    document.getElementById('template-code-length').value = 4;
    document.querySelector('#add-template-form button[type="submit"]').textContent = 'Додати';
    document.querySelector('.divider-top .section-label').textContent = 'Додати новий шаблон';
    const cancelBtn = document.getElementById('cancel-edit-btn');
    if (cancelBtn) {
        cancelBtn.remove();
    }
}

async function handleAddTemplate(event) {
    event.preventDefault();
    const key = document.getElementById('template-key').value.trim();
    const command = document.getElementById('template-command').value.trim();
    const code_length = parseInt(document.getElementById('template-code-length').value) || 4;
    const text = document.getElementById('template-text').value.trim();
    const isEdit = document.getElementById('template-key').disabled;

    try {
        const res = await fetch('/api/settings/templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, command, text, code_length })
        });
        if (res.ok) {
            showToast(isEdit ? `Шаблон ${key} оновлено!` : `Шаблон ${key} додано!`, "success");
            resetTemplateForm();
            loadSettings();
        } else {
            const err = await res.json();
            showToast("Помилка: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося зберегти шаблон", "error");
    }
}

async function deleteTemplate(key) {
    const confirmed = await showConfirm(`Ви впевнені, що хочете видалити шаблон для банку ${key}?`, 'danger');
    if (!confirmed) return;

    try {
        const res = await fetch(`/api/settings/templates/${key}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showToast(`Шаблон ${key} видалено.`, "success");
            loadSettings();
        } else {
            showToast("Помилка видалення", "error");
        }
    } catch (err) {
        showToast("Помилка відправки запиту", "error");
    }
}

async function loadLearnableChats() {
    try {
        const res = await fetch('/api/ai/learnable-chats');
        if (!res.ok) throw new Error("Learnable chats fetch failed");
        const chats = await res.json();
        
        const select = document.getElementById('ai-learn-chat-select');
        if (!select) return;
        select.innerHTML = '<option value="all">Аналізувати всі недавні чати з адміном (останні 10)</option>';
        
        chats.forEach(chat => {
            const opt = document.createElement('option');
            opt.value = chat.client_id;
            const displayName = extractDisplayName(chat.client_data, chat.username);
            const statusLabel = chat.status === 'completed' ? 'Архів' : 'Активний';
            opt.textContent = `${displayName} (${statusLabel}, ID: ${chat.client_id})`;
            select.appendChild(opt);
        });
    } catch (err) {
        console.error("Failed to load learnable chats list:", err);
    }
}

async function loadAISettings() {
    try {
        const settingsRes = await fetch('/api/ai/settings');
        if (!settingsRes.ok) throw new Error("Settings fetch failed");
        const settings = await settingsRes.json();
        
        document.getElementById('ai-settings-income').value = settings.ai_income_limit || '25000';
        document.getElementById('ai-settings-turnover').value = settings.ai_turnover_limit || '30000';
        document.getElementById('ai-settings-pwd-kd').value = settings.ai_password_kd || '12345';
        document.getElementById('ai-settings-pwd-other').value = settings.ai_password_other || '1111, 1234 або 1232';
        
        await loadAIRules();
        await loadAIExamples();
        await loadLearnableChats();
    } catch (err) {
        showToast("Не вдалося завантажити налаштування ШІ", "error");
    }
}

async function saveAISettings(event) {
    event.preventDefault();
    const income = document.getElementById('ai-settings-income').value.trim();
    const turnover = document.getElementById('ai-settings-turnover').value.trim();
    const pwdKd = document.getElementById('ai-settings-pwd-kd').value.trim();
    const pwdOther = document.getElementById('ai-settings-pwd-other').value.trim();
    
    try {
        const res = await fetch('/api/ai/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ai_income_limit: income,
                ai_turnover_limit: turnover,
                ai_password_kd: pwdKd,
                ai_password_other: pwdOther
            })
        });
        if (res.ok) {
            showToast("Параметри ШІ успішно збережено!", "success");
        } else {
            const err = await res.json();
            showToast("Помилка збереження: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Помилка відправки запиту", "error");
    }
}

async function loadAIRules() {
    try {
        const res = await fetch('/api/ai/rules');
        if (!res.ok) throw new Error("Rules fetch failed");
        const rules = await res.json();
        
        const tableBody = document.getElementById('ai-rules-table-body');
        if (!tableBody) return;
        tableBody.innerHTML = '';
        
        if (rules.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="4" class="empty-state">Немає збережених правил та інструкцій ШІ</td></tr>';
            return;
        }
        
        rules.forEach(rule => {
            const tr = document.createElement('tr');
            const isActive = rule.is_active === 1;
            const catMap = {
                'general': 'Загальне',
                'bank_rules': 'Правила банків',
                'troubleshooting': 'Помилки',
                'limits': 'Виплати/ліміти'
            };
            const catLabel = catMap[rule.category] || rule.category;
            
            const catStyles = {
                'general': 'background: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.3); padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;',
                'bank_rules': 'background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;',
                'troubleshooting': 'background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;',
                'limits': 'background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600;'
            };
            const catStyle = catStyles[rule.category] || catStyles['general'];
            
            tr.innerHTML = `
                <td style="font-weight: 500;"><span style="${catStyle}">${catLabel}</span></td>
                <td style="font-size: 0.85rem; max-width: 400px; white-space: normal; line-height: 1.4; text-align: left;">${escapeHtml(rule.rule_text)}</td>
                <td>
                    <label class="switch">
                        <input type="checkbox" ${isActive ? 'checked' : ''} onchange="toggleAIRule(${rule.id})">
                        <span class="slider"></span>
                    </label>
                </td>
                <td>
                    <button class="btn btn-danger btn-sm" onclick="deleteAIRule(${rule.id})" style="padding: 4px 8px; font-size: 0.75rem;">Видалити</button>
                </td>
            `;
            tableBody.appendChild(tr);
        });
    } catch (err) {
        console.error("Failed to load AI rules:", err);
    }
}

async function handleAddRule(event) {
    event.preventDefault();
    const category = document.getElementById('new-rule-category').value;
    const ruleText = document.getElementById('new-rule-text').value.trim();
    
    try {
        const res = await fetch('/api/ai/rules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rule_text: ruleText, category: category })
        });
        if (res.ok) {
            showToast("Правило успішно додано!", "success");
            document.getElementById('new-rule-text').value = '';
            await loadAIRules();
        } else {
            showToast("Помилка додавання правила", "error");
        }
    } catch (err) {
        showToast("Помилка відправки запиту", "error");
    }
}

async function toggleAIRule(ruleId) {
    try {
        const res = await fetch(`/api/ai/rules/${ruleId}/toggle`, {
            method: 'PUT'
        });
        if (res.ok) {
            showToast("Статус правила змінено!", "success");
        } else {
            showToast("Не вдалося змінити статус", "error");
        }
    } catch (err) {
        showToast("Помилка з'єднання", "error");
    }
}

async function deleteAIRule(ruleId) {
    const confirmed = await showConfirm("Ви впевнені, що хочете видалити це правило?", "danger");
    if (!confirmed) return;
    
    try {
        const res = await fetch(`/api/ai/rules/${ruleId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showToast("Правило видалено!", "success");
            await loadAIRules();
        } else {
            showToast("Помилка видалення правила", "error");
        }
    } catch (err) {
        showToast("Помилка з'єднання", "error");
    }
}

async function loadAIExamples() {
    try {
        const res = await fetch('/api/ai/examples');
        if (!res.ok) throw new Error("Examples fetch failed");
        const examples = await res.json();
        
        const tableBody = document.getElementById('ai-examples-table-body');
        if (!tableBody) return;
        tableBody.innerHTML = '';
        
        if (examples.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="3" class="empty-state">Немає прикладів few-shot діалогів</td></tr>';
            return;
        }
        
        examples.forEach(ex => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-size: 0.85rem; font-style: italic; line-height: 1.4; text-align: left;">"${escapeHtml(ex.client_message)}"</td>
                <td style="font-size: 0.85rem; color: var(--accent-primary); line-height: 1.4; text-align: left;">${escapeHtml(ex.bot_response)}</td>
                <td>
                    <button class="btn btn-danger btn-sm" onclick="deleteAIExample(${ex.id})" style="padding: 4px 8px; font-size: 0.75rem;">Видалити</button>
                </td>
            `;
            tableBody.appendChild(tr);
        });
    } catch (err) {
        console.error("Failed to load AI examples:", err);
    }
}

async function handleAddExample(event) {
    event.preventDefault();
    const clientMsg = document.getElementById('new-example-client').value.trim();
    const botResponse = document.getElementById('new-example-bot').value.trim();
    
    try {
        const res = await fetch('/api/ai/examples', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ client_message: clientMsg, bot_response: botResponse })
        });
        if (res.ok) {
            showToast("Приклад успішно додано!", "success");
            document.getElementById('new-example-client').value = '';
            document.getElementById('new-example-bot').value = '';
            await loadAIExamples();
        } else {
            showToast("Помилка додавання прикладу", "error");
        }
    } catch (err) {
        showToast("Помилка відправки запиту", "error");
    }
}

async function deleteAIExample(exampleId) {
    const confirmed = await showConfirm("Ви впевнені, що хочете видалити цей приклад діалогу?", "danger");
    if (!confirmed) return;
    
    try {
        const res = await fetch(`/api/ai/examples/${exampleId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showToast("Приклад видалено!", "success");
            await loadAIExamples();
        } else {
            showToast("Помилка видалення прикладу", "error");
        }
    } catch (err) {
        showToast("Помилка з'єднання", "error");
    }
}

async function runAILearn() {
    const btn = document.getElementById('btn-ai-learn');
    const select = document.getElementById('ai-learn-chat-select');
    if (!btn || !select) return;
    const selectedVal = select.value;
    
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '⏳ Аналізуємо чати (це може зайняти до 30 секунд)...';
    
    const bodyPayload = {};
    if (selectedVal !== 'all') {
        bodyPayload.client_ids = [parseInt(selectedVal)];
    }
    
    try {
        const res = await fetch('/api/ai/learn', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyPayload)
        });
        if (res.ok) {
            const data = await res.json();
            showToast(data.message, "success");
            
            const proposedList = document.getElementById('ai-proposed-list');
            if (proposedList) {
                proposedList.innerHTML = '';
                
                if (data.proposed_rules && data.proposed_rules.length > 0) {
                    document.getElementById('ai-proposed-container').style.display = 'block';
                    
                    data.proposed_rules.forEach(rule => {
                        const card = document.createElement('div');
                        card.className = 'proposed-rule-card';
                        card.style = 'border: 1px solid var(--border-color); background: var(--panel-bg); padding: 12px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);';
                        card.innerHTML = `
                            <div style="flex: 1; font-size: 0.85rem; line-height: 1.4; text-align: left;">
                                <strong>Виявлено в чаті з @${rule.username}:</strong><br>
                                <span style="color: var(--text-color); font-style: italic;">"${escapeHtml(rule.rule_text)}"</span>
                            </div>
                            <div style="display: flex; gap: 8px;">
                                <button class="btn btn-primary btn-sm" onclick="approveProposedRule(${rule.id})" style="padding: 4px 8px; font-size: 0.75rem;">Затвердити</button>
                                <button class="btn btn-secondary btn-sm" onclick="dismissProposedRule(${rule.id})" style="padding: 4px 8px; font-size: 0.75rem;">Ігнорувати</button>
                            </div>
                        `;
                        proposedList.appendChild(card);
                    });
                } else {
                    document.getElementById('ai-proposed-container').style.display = 'none';
                }
            }
            
            await loadAIRules();
        } else {
            showToast("Помилка при запуску навчання ШІ", "error");
        }
    } catch (err) {
        showToast("Помилка з'єднання з сервером", "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

async function approveProposedRule(ruleId) {
    try {
        const res = await fetch(`/api/ai/rules/${ruleId}/toggle`, {
            method: 'PUT'
        });
        if (res.ok) {
            showToast("Правило затверджено та активовано!", "success");
            await loadAIRules();
            const btn = document.querySelector(`button[onclick="approveProposedRule(${ruleId})"]`);
            if (btn) {
                const card = btn.closest('.proposed-rule-card');
                if (card) {
                    card.remove();
                    const proposedList = document.getElementById('ai-proposed-list');
                    if (proposedList && proposedList.children.length === 0) {
                        document.getElementById('ai-proposed-container').style.display = 'none';
                    }
                }
            }
        }
    } catch (err) {
        showToast("Не вдалося затвердити правило", "error");
    }
}

async function dismissProposedRule(ruleId) {
    try {
        const res = await fetch(`/api/ai/rules/${ruleId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showToast("Пропозицію відхилено.", "success");
            await loadAIRules();
            const btn = document.querySelector(`button[onclick="dismissProposedRule(${ruleId})"]`);
            if (btn) {
                const card = btn.closest('.proposed-rule-card');
                if (card) {
                    card.remove();
                    const proposedList = document.getElementById('ai-proposed-list');
                    if (proposedList && proposedList.children.length === 0) {
                        document.getElementById('ai-proposed-container').style.display = 'none';
                    }
                }
            }
        }
    } catch (err) {
        showToast("Не вдалося видалити пропозицію", "error");
    }
}

// Add Shift+Enter / Enter shortcuts for adding template
const templateTextEl = document.getElementById('template-text');
if (templateTextEl) {
    templateTextEl.addEventListener('keydown', function(event) {
        if (event.key === 'Enter') {
            if (!event.shiftKey) {
                event.preventDefault();
                const form = document.getElementById('add-template-form');
                if (form) form.requestSubmit();
            }
        }
    });
}

function switchSettingsSubtab(subtabId) {
    // 1. Update subtab button classes
    document.querySelectorAll('.settings-subtab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    // Find active button
    const activeBtn = document.querySelector(`.settings-subtab-btn[onclick="switchSettingsSubtab('${subtabId}')"]`);
    if (activeBtn) activeBtn.classList.add('active');

    // 2. Show/hide subtab contents
    document.querySelectorAll('.settings-subtab-content').forEach(pane => {
        pane.classList.remove('active');
    });
    const activePane = document.getElementById(`settings-content-${subtabId}`);
    if (activePane) activePane.classList.add('active');

    // 3. Show/hide global save button container
    const saveBtn = document.getElementById('settings-save-btn-container');
    if (saveBtn) {
        if (subtabId === 'banks') {
            saveBtn.style.display = 'none';
        } else {
            saveBtn.style.display = 'flex';
        }
    }
}
