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
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state" style="text-align: center; color: rgba(255,255,255,0.4); padding: 20px;">Немає заблокованих користувачів</td></tr>';
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
        const res = await fetch('/api/settings?nocache=' + Date.now());
        if (!res.ok) throw new Error("Status code: " + res.status);
        const data = await res.json();
        
        const remindersEnabled = data.settings.reminders_enabled !== '0';
        document.getElementById('settings-reminders-enabled').checked = remindersEnabled;
        document.getElementById('settings-reminder-delay').value = data.settings.reminder_delay_minutes || 5;
        document.getElementById('settings-reminder-text').value = data.settings.reminder_text || '';
        document.getElementById('settings-giver-format').value = data.settings.giver_request_format || 'Запрос {line_id} {bank_name}';
        document.getElementById('settings-giver-retry-format').value = data.settings.giver_request_retry_format || 'Запрос {line_id} {bank_name} (ПОВТОРНО)';
        document.getElementById('settings-client-assign-format').value = data.settings.client_number_assigned_format || 'Банк: *{bank_name}*\nНомер телефону:\n\n`+{phone_number}`\n\nКоли надішлете SMS і вам знадобиться код, тисніть кнопку нижче.';
        document.getElementById('settings-sms-cooldown').value = data.settings.sms_cooldown_seconds || 30;
        
        document.getElementById('settings-admin-id').value = data.settings.admin_id || '';
        document.getElementById('settings-anketa-chat-id').value = data.settings.anketa_chat_id || '';
        document.getElementById('settings-giver-chat-id').value = data.settings.giver_chat_id || '';
        document.getElementById('settings-archive-group-id').value = data.settings.archive_group_id || '';

        document.getElementById('settings-sleep-enabled').checked = data.settings.sleep_mode_enabled === '1';
        document.getElementById('settings-sleep-start').value = data.settings.sleep_mode_start || '22:00';
        document.getElementById('settings-sleep-end').value = data.settings.sleep_mode_end || '08:00';
        document.getElementById('settings-sleep-timezone').value = data.settings.sleep_mode_timezone || 'Europe/Kyiv';
        document.getElementById('settings-sleep-reply').value = data.settings.sleep_mode_reply || 'На жаль, зараз не робочий час. Поверніться пізніше.';
        toggleSleepInputs();

        toggleReminderInputs();
        if (typeof syncSoundControlsUI === 'function') {
            syncSoundControlsUI();
        }

        window.bankTemplates = data.templates;
        
        // Render bank accordion items
        const activeAccordionKey = localStorage.getItem('active_bank_accordion') || null;
        renderBankAccordion(data.templates, activeAccordionKey);
        
        if (typeof renderChatPageTemplates === 'function') {
            renderChatPageTemplates();
        }

        // Restore active settings subtab
        const savedSubtab = localStorage.getItem('active_settings_subtab') || 'general';
        switchSettingsSubtab(savedSubtab);
    } catch (err) {
        console.error("loadSettings error:", err);
        showToast("Не вдалося завантажити налаштування: " + err.message, "error");
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
function toggleSleepInputs() {
    const enabled = document.getElementById('settings-sleep-enabled').checked;
    document.getElementById('settings-sleep-start').disabled = !enabled;
    document.getElementById('settings-sleep-end').disabled = !enabled;
    document.getElementById('settings-sleep-timezone').disabled = !enabled;
    document.getElementById('settings-sleep-reply').disabled = !enabled;
    if (!enabled) {
        document.getElementById('settings-sleep-start').removeAttribute('required');
        document.getElementById('settings-sleep-end').removeAttribute('required');
    } else {
        document.getElementById('settings-sleep-start').setAttribute('required', '');
        document.getElementById('settings-sleep-end').setAttribute('required', '');
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
    const smsCooldown = document.getElementById('settings-sms-cooldown').value;
    const sleepEnabled = document.getElementById('settings-sleep-enabled').checked ? '1' : '0';
    const sleepStart = document.getElementById('settings-sleep-start').value;
    const sleepEnd = document.getElementById('settings-sleep-end').value;
    const sleepTimezone = document.getElementById('settings-sleep-timezone').value;
    const sleepReply = document.getElementById('settings-sleep-reply').value;

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
                archive_group_id: archiveGroupId,
                sms_cooldown_seconds: String(smsCooldown),
                sleep_mode_enabled: sleepEnabled,
                sleep_mode_start: sleepStart,
                sleep_mode_end: sleepEnd,
                sleep_mode_timezone: sleepTimezone,
                sleep_mode_reply: sleepReply
            })
        });
        if (res.ok) {
            showToast("Налаштування збережено!", "success");
            await loadSettings();
        } else {
            const err = await res.json();
            showToast("Помилка збереження: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Помилка відправки запиту", "error");
    }
}
function switchSettingsSubtab(subtabId) {
    localStorage.setItem('active_settings_subtab', subtabId);
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
