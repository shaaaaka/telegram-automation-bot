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
        const pumbPhoneEl = document.getElementById('settings-pumb-target-phone');
        if (pumbPhoneEl) pumbPhoneEl.value = data.settings.pumb_target_phone || '943554053';

        const pumbEmailEl = document.getElementById('settings-pumb-target-email');
        if (pumbEmailEl) pumbEmailEl.value = data.settings.pumb_target_email || 'jotbidnor@macr2.com';

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
        if (typeof window.setupAutoGrowTextareas === 'function') {
            window.setupAutoGrowTextareas();
        }
        if (typeof window.initCustomSoundSelect === 'function') {
            window.initCustomSoundSelect();
        }

        window.bankTemplates = data.templates;
        window.bankProfiles = data.profiles;

        // Render bank accordion items
        const activeAccordionKey = localStorage.getItem('active_bank_accordion') || null;
        renderBankAccordion(data.templates, activeAccordionKey);

        if (typeof window.loadBankProfiles === 'function') {
            window.loadBankProfiles(data.profiles);
        }

        if (typeof renderChatPageTemplates === 'function') {
            renderChatPageTemplates();
        }

        // Restore active settings subtab
        let savedSubtab = localStorage.getItem('active_settings_subtab') || 'general';
        if (!['general', 'banks', 'chats', 'ai', 'theme'].includes(savedSubtab)) {
            savedSubtab = 'general';
        }
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

    const pumbPhoneElem = document.getElementById('settings-pumb-target-phone');
    const pumbTargetPhone = pumbPhoneElem ? pumbPhoneElem.value.trim() : null;
    const pumbEmailElem = document.getElementById('settings-pumb-target-email');
    const pumbTargetEmail = pumbEmailElem ? pumbEmailElem.value.trim() : null;

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
                pumb_target_phone: pumbTargetPhone,
                pumb_target_email: pumbTargetEmail,
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
    // Find active button by ID or fallback selector
    const activeBtn = document.getElementById(`subtab-btn-${subtabId}`) || document.querySelector(`.settings-subtab-btn[onclick*="${subtabId}"]`);
    if (activeBtn) activeBtn.classList.add('active');

    // 2. Show/hide subtab contents
    document.querySelectorAll('.settings-subtab-content').forEach(pane => {
        pane.classList.remove('active');
        pane.style.display = 'none';
    });
    const activePane = document.getElementById(`settings-content-${subtabId}`);
    if (activePane) {
        activePane.classList.add('active');
        activePane.style.display = 'block';
    }

    // 3. Show/hide global save button container and the main form for non-form subtabs
    const saveBtn = document.getElementById('settings-save-btn-container');
    const generalForm = document.getElementById('general-settings-form');
    if (saveBtn) {
        if (subtabId === 'banks' || subtabId === 'ai' || subtabId === 'theme') {
            saveBtn.style.display = 'none';
        } else {
            saveBtn.style.display = 'flex';
        }
    }
    if (generalForm) {
        if (subtabId === 'general' || subtabId === 'chats') {
            generalForm.style.display = 'flex';
        } else {
            generalForm.style.display = 'none';
        }
    }

    // 4. Load AI settings if active
    if (subtabId === 'ai' && typeof loadAISettings === 'function') {
        loadAISettings();
    }

    // Restore active bank settings pane (Banks / Profiles)
    if (subtabId === 'banks' && typeof switchBankSettingsPane === 'function') {
        const savedBankPane = sessionStorage.getItem('active_bank_settings_pane') || 'banks';
        switchBankSettingsPane(savedBankPane);
    }

    // 5. Update theme cards active state if theme subtab
    if (subtabId === 'theme') {
        if (typeof window.switchThemeSubtab === 'function') {
            window.switchThemeSubtab();
        }
        if (typeof window.updateSettingsThemeCardsActiveState === 'function') {
            window.updateSettingsThemeCardsActiveState();
        }
        if (typeof window.updateSettingsFontCardsActiveState === 'function') {
            window.updateSettingsFontCardsActiveState();
        }
    }
}

function getStoredFontWeight(fontName) {
    if (!fontName) fontName = localStorage.getItem('crm_chat_font_family') || 'Inter';
    const perFont = localStorage.getItem(`crm_chat_font_weight_${fontName}`);
    if (perFont) return perFont;
    const global = localStorage.getItem('crm_chat_font_weight') || '600';
    return global;
}

function getWeightLabel(numericWeight) {
    if (numericWeight < 450) return 'Тонкий';
    if (numericWeight < 550) return 'Середній';
    if (numericWeight < 650) return 'Напівжирний';
    return 'Жирний';
}

window.applyChatFont = function(fontName, fontWeight) {
    if (!fontName) fontName = localStorage.getItem('crm_chat_font_family') || 'Inter';
    if (!fontWeight) fontWeight = getStoredFontWeight(fontName);

    let fontCss = `'${fontName}', sans-serif`;
    if (fontName === 'JetBrains Mono') {
        fontCss = `'JetBrains Mono', monospace`;
    }

    const chatLayout = document.getElementById('chat-page-layout-container');
    if (chatLayout) {
        chatLayout.style.setProperty('--chat-font-family', fontCss);
        chatLayout.style.setProperty('--chat-font-weight', fontWeight);
    }

    // Also expose for settings preview cards
    document.documentElement.style.setProperty('--settings-font-family', fontCss);
    document.documentElement.style.setProperty('--settings-font-weight', fontWeight);

    // Fallback style block for cases where the chat layout isn't in the DOM yet
    let styleEl = document.getElementById('dynamic-chat-font-style');
    if (!styleEl) {
        styleEl = document.createElement('style');
        styleEl.id = 'dynamic-chat-font-style';
        document.head.appendChild(styleEl);
    }
    styleEl.textContent = `
        .chat-page-layout {
            --chat-font-family: ${fontCss};
            --chat-font-weight: ${fontWeight};
        }
    `;

    window.updateSettingsFontCardsActiveState(fontName);
    window.updateSettingsFontCardsWeightPreview();
    window.updateSettingsFontWeightActiveState(fontWeight);
};

window.selectChatFont = function(fontName) {
    const activeCard = document.querySelector('.settings-font-card.active');
    if (activeCard && activeCard.dataset.font === fontName) {
        window.deselectFontCard();
        return;
    }
    localStorage.setItem('crm_chat_font_family', fontName);
    localStorage.setItem('crm_font_card_active', fontName);
    window.applyChatFont(fontName);
    if (typeof showToast === 'function') {
        showToast(`Шрифт чату змінено на ${fontName}!`, "success");
    }
};

let fontWeightDebounceTimer = null;

window.updateFontWeightPreview = function(weight) {
    const slider = document.getElementById('settings-font-weight-slider');
    const valueLabel = document.getElementById('settings-font-weight-value');
    const numericWeight = Number(weight) || 600;
    const progress = ((numericWeight - 400) / 300) * 100;
    if (slider) {
        slider.style.setProperty('--value', `${progress}%`);
    }
    if (valueLabel) {
        valueLabel.textContent = getWeightLabel(numericWeight);
    }

    if (fontWeightDebounceTimer) clearTimeout(fontWeightDebounceTimer);
    fontWeightDebounceTimer = setTimeout(() => {
        window.selectChatFontWeight(weight, false);
    }, 120);
};

window.selectChatFontWeight = function(weight, showNotification = true) {
    const fontName = localStorage.getItem('crm_chat_font_family') || 'Inter';
    localStorage.setItem(`crm_chat_font_weight_${fontName}`, weight);
    window.applyChatFont(null, weight);
    if (showNotification && typeof showToast === 'function') {
        showToast(`Жирність шрифту змінено на ${getWeightLabel(Number(weight) || 600)}!`, "success");
    }
};

window.updateSettingsFontCardsActiveState = function(fontName) {
    if (!fontName) fontName = localStorage.getItem('crm_chat_font_family') || 'Inter';
    const storedActive = localStorage.getItem('crm_font_card_active');
    let activeFontName = fontName;
    if (storedActive === 'none') {
        activeFontName = null;
    } else if (storedActive) {
        activeFontName = storedActive;
    }
    const fontCards = document.querySelectorAll('.settings-font-card');
    const weightControl = document.getElementById('settings-font-weight-control');
    let activeCard = null;
    fontCards.forEach(card => {
        if (card.dataset.font === activeFontName) {
            card.classList.add('active');
            activeCard = card;
        } else {
            card.classList.remove('active');
        }
    });
    if (weightControl) {
        if (activeCard) {
            activeCard.appendChild(weightControl);
            weightControl.style.display = '';
            weightControl.onclick = function(e) {
                e.stopPropagation();
            };
        } else {
            weightControl.style.display = 'none';
        }
    }
};

window.deselectFontCard = function() {
    const fontCards = document.querySelectorAll('.settings-font-card');
    fontCards.forEach(card => card.classList.remove('active'));
    localStorage.setItem('crm_font_card_active', 'none');
};

window.updateSettingsFontCardsWeightPreview = function() {
    const fontCards = document.querySelectorAll('.settings-font-card');
    fontCards.forEach(card => {
        const sample = card.querySelector('.font-preview-sample');
        if (sample) {
            sample.style.fontWeight = getStoredFontWeight(card.dataset.font);
        }
    });
};

window.updateSettingsFontWeightActiveState = function(fontWeight) {
    if (!fontWeight) {
        const fontName = localStorage.getItem('crm_chat_font_family') || 'Inter';
        fontWeight = getStoredFontWeight(fontName);
    }
    const slider = document.getElementById('settings-font-weight-slider');
    const valueLabel = document.getElementById('settings-font-weight-value');
    const numericWeight = Number(fontWeight) || 600;
    const progress = ((numericWeight - 400) / 300) * 100;
    if (slider) {
        slider.value = String(numericWeight);
        slider.style.setProperty('--value', `${progress}%`);
    }
    if (valueLabel) {
        valueLabel.textContent = getWeightLabel(numericWeight);
    }
};

window.switchThemeSubtab = function(subtabName) {
    if (!subtabName) subtabName = localStorage.getItem('crm_theme_subtab') || 'themes';
    localStorage.setItem('crm_theme_subtab', subtabName);

    const btnThemes = document.getElementById('btn-theme-subtab-themes');
    const btnFonts = document.getElementById('btn-theme-subtab-fonts');
    const paneThemes = document.getElementById('theme-subpane-themes');
    const paneFonts = document.getElementById('theme-subpane-fonts');

    if (subtabName === 'fonts') {
        if (btnThemes) btnThemes.classList.remove('active');
        if (btnFonts) btnFonts.classList.add('active');
        if (paneThemes) paneThemes.style.display = 'none';
        if (paneFonts) paneFonts.style.display = 'block';
    } else {
        if (btnThemes) btnThemes.classList.add('active');
        if (btnFonts) btnFonts.classList.remove('active');
        if (paneThemes) paneThemes.style.display = 'block';
        if (paneFonts) paneFonts.style.display = 'none';
    }
};

function attachFontPaneDeselect() {
    const themeContent = document.getElementById('settings-content-theme');
    if (themeContent && !themeContent.dataset.deselectAttached) {
        themeContent.dataset.deselectAttached = '1';
        themeContent.addEventListener('click', function(e) {
            const fontsPane = document.getElementById('theme-subpane-fonts');
            if (!fontsPane || fontsPane.style.display === 'none') return;
            if (!e.target.closest) return;
            if (e.target.closest('.settings-font-card') || e.target.closest('.font-weight-control') || e.target.closest('.theme-subtab-switcher')) return;
            window.deselectFontCard();
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.applyChatFont();
    window.switchThemeSubtab();
    attachFontPaneDeselect();
});

if (document.readyState !== 'loading') {
    window.applyChatFont();
    window.switchThemeSubtab();
    attachFontPaneDeselect();
}
