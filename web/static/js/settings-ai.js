// --- AI Settings, Rules & Examples Management ---

async function loadAISettings() {
    try {
        const res = await fetch('/api/settings/ai?nocache=' + Date.now());
        if (!res.ok) throw new Error("Status code: " + res.status);
        const data = await res.json();
        
        // 1. Fill basic parameters
        document.getElementById('ai-settings-income').value = data.ai_income_limit || '25000';
        document.getElementById('ai-settings-turnover').value = data.ai_turnover_limit || '30000';
        document.getElementById('ai-settings-pwd-kd').value = data.ai_password_kd || '12345';
        document.getElementById('ai-settings-pwd-other').value = data.ai_password_other || '1111, 1234 або 1232';
        
        // 2. Render Rules List
        renderAIRules(data.rules || []);
        
        // 3. Render Examples List
        renderAIExamples(data.examples || []);
    } catch (err) {
        showToast("Помилка завантаження налаштувань ШІ", "danger");
    }
}

async function saveAISettings(event) {
    if (event) event.preventDefault();
    try {
        const income = document.getElementById('ai-settings-income').value.trim();
        const turnover = document.getElementById('ai-settings-turnover').value.trim();
        const pwdKD = document.getElementById('ai-settings-pwd-kd').value.trim();
        const pwdOther = document.getElementById('ai-settings-pwd-other').value.trim();
        
        const res = await fetch('/api/settings/ai', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ai_income_limit: income,
                ai_turnover_limit: turnover,
                ai_password_kd: pwdKD,
                ai_password_other: pwdOther
            })
        });
        
        if (res.ok) {
            showToast("Базові параметри ШІ збережено!", "success");
            await loadAISettings();
        } else {
            const err = await res.json();
            showToast("Помилка збереження: " + (err.detail || "невідома помилка"), "danger");
        }
    } catch (err) {
        showToast("Помилка підключення до сервера", "danger");
    }
}

// --- Rules CRUD ---

function showAddRuleForm() {
    document.getElementById('ai-rule-add-form').style.display = 'flex';
    document.getElementById('ai-rule-form-title').innerText = "Нове правило для ШІ";
    document.getElementById('edit-rule-id').value = "";
    document.getElementById('ai-rule-text').value = "";
    document.getElementById('ai-rule-category').value = "general";
    document.getElementById('btn-save-ai-rule').innerText = "Створити";
}

function hideAddRuleForm() {
    document.getElementById('ai-rule-add-form').style.display = 'none';
}

function editAIRule(id, text, category) {
    document.getElementById('ai-rule-add-form').style.display = 'flex';
    document.getElementById('ai-rule-form-title').innerText = "Редагувати правило";
    document.getElementById('edit-rule-id').value = id;
    document.getElementById('ai-rule-text').value = text;
    document.getElementById('ai-rule-category').value = category;
    document.getElementById('btn-save-ai-rule').innerText = "Зберегти зміни";
    document.getElementById('ai-rule-add-form').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function saveNewRule() {
    const text = document.getElementById('ai-rule-text').value.trim();
    const category = document.getElementById('ai-rule-category').value;
    const ruleId = document.getElementById('edit-rule-id').value;
    
    if (!text) {
        showToast("Будь ласка, введіть текст правила", "warning");
        return;
    }
    
    try {
        let url = '/api/settings/ai/rules';
        let method = 'POST';
        
        if (ruleId) {
            url = `/api/settings/ai/rules/${ruleId}`;
            method = 'PUT';
        }
        
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rule_text: text,
                category: category,
                is_active: 1
            })
        });
        
        if (res.ok) {
            showToast(ruleId ? "Правило успішно оновлено!" : "Правило додано успішно!", "success");
            hideAddRuleForm();
            await loadAISettings();
        } else {
            showToast("Не вдалося зберегти правило", "danger");
        }
    } catch (err) {
        showToast("Помилка сервера при збереженні правила", "danger");
    }
}

async function toggleAIRule(id, checkbox) {
    try {
        const isChecked = checkbox.checked ? 1 : 0;
        const res = await fetch(`/api/settings/ai/rules/${id}/toggle?is_active=${isChecked}`, {
            method: 'POST'
        });
        if (res.ok) {
            showToast(isChecked ? "Правило активовано" : "Правило вимкнено", "success");
        } else {
            checkbox.checked = !checkbox.checked;
            showToast("Не вдалося змінити статус", "danger");
        }
    } catch (err) {
        checkbox.checked = !checkbox.checked;
        showToast("Помилка підключення", "danger");
    }
}

async function deleteAIRule(id) {
    if (!confirm("Ви впевнені, що хочете видалити це правило?")) return;
    try {
        const res = await fetch(`/api/settings/ai/rules/${id}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showToast("Правило видалено", "success");
            await loadAISettings();
        } else {
            showToast("Не вдалося видалити правило", "danger");
        }
    } catch (err) {
        showToast("Помилка при видаленні", "danger");
    }
}

function renderAIRules(rules) {
    const container = document.getElementById('ai-rules-list-container');
    if (!container) return;
    container.innerHTML = '';
    
    if (rules.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: rgba(255,255,255,0.4); padding: 15px;">Правила відсутні</div>';
        return;
    }
    
    // Category human-readable names and colors
    const catMetadata = {
        'general': { label: 'Загальне', color: '#60a5fa', bg: 'rgba(59, 130, 246, 0.12)', border: 'rgba(59, 130, 246, 0.25)' },
        'bank_rules': { label: 'Пін-коди', color: '#c084fc', bg: 'rgba(168, 85, 247, 0.12)', border: 'rgba(168, 85, 247, 0.25)' },
        'troubleshooting': { label: 'Технічні проблеми', color: '#f97316', bg: 'rgba(249, 115, 22, 0.12)', border: 'rgba(249, 115, 22, 0.25)' },
        'limits': { label: 'Виплати / ліміти', color: '#34d399', bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.25)' }
    };
    
    rules.forEach(rule => {
        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.alignItems = 'center';
        item.style.justifyContent = 'space-between';
        item.style.padding = '12px 16px';
        item.style.background = 'rgba(255,255,255,0.015)';
        item.style.border = '1px solid rgba(255,255,255,0.04)';
        item.style.borderRadius = '10px';
        item.style.gap = '12px';
        
        const meta = catMetadata[rule.category] || { label: rule.category, color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.12)', border: 'rgba(148, 163, 184, 0.25)' };
        
        item.innerHTML = `
            <div style="display: flex; align-items: center; gap: 12px; flex-grow: 1; min-width: 0;">
                <span style="font-size: 0.72rem; font-weight: 600; text-transform: uppercase; color: ${meta.color}; background: ${meta.bg}; border: 1px solid ${meta.border}; padding: 3px 8px; border-radius: 6px; white-space: nowrap;">
                    ${meta.label}
                </span>
                <span style="font-size: 0.88rem; color: rgba(255,255,255,0.85); overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
                    ${rule.rule_text}
                </span>
            </div>
            <div style="display: flex; align-items: center; gap: 14px; flex-shrink: 0;">
                <label class="switch-container" style="display: flex; align-items: center; cursor: pointer;">
                    <div class="switch">
                        <input type="checkbox" ${rule.is_active === 1 ? 'checked' : ''} onchange="toggleAIRule(${rule.id}, this)">
                        <span class="slider"></span>
                    </div>
                </label>
                <div style="display: flex; gap: 6px;">
                    <button class="btn btn-secondary btn-sm" onclick="editAIRule(${rule.id}, \`${rule.rule_text.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/"/g, '&quot;')}\`, '${rule.category}')" style="padding: 5px 9px; font-size: 0.78rem; display: inline-flex; align-items: center;"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
                    <button class="btn btn-secondary btn-sm" onclick="deleteAIRule(${rule.id})" style="padding: 5px 9px; font-size: 0.78rem; border-color: rgba(239, 68, 68, 0.2); color: #ef4444; display: inline-flex; align-items: center;"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg></button>
                </div>
            </div>
        `;
        container.appendChild(item);
    });
}

// --- Examples CRUD ---

function showAddExampleForm() {
    document.getElementById('ai-example-add-form').style.display = 'flex';
    document.getElementById('ai-example-form-title').innerText = "Новий приклад для ШІ";
    document.getElementById('edit-example-id').value = "";
    document.getElementById('ai-example-q').value = "";
    document.getElementById('ai-example-a').value = "";
    document.getElementById('btn-save-ai-example').innerText = "Створити";
}

function hideAddExampleForm() {
    document.getElementById('ai-example-add-form').style.display = 'none';
}

function editAIExample(id, clientMsg, botResp) {
    document.getElementById('ai-example-add-form').style.display = 'flex';
    document.getElementById('ai-example-form-title').innerText = "Редагувати приклад";
    document.getElementById('edit-example-id').value = id;
    document.getElementById('ai-example-q').value = clientMsg;
    document.getElementById('ai-example-a').value = botResp;
    document.getElementById('btn-save-ai-example').innerText = "Зберегти зміни";
    document.getElementById('ai-example-add-form').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function saveNewExample() {
    const q = document.getElementById('ai-example-q').value.trim();
    const a = document.getElementById('ai-example-a').value.trim();
    const exampleId = document.getElementById('edit-example-id').value;
    
    if (!q || !a) {
        showToast("Будь ласка, заповніть запитання та відповідь", "warning");
        return;
    }
    
    try {
        let url = '/api/settings/ai/examples';
        let method = 'POST';
        
        if (exampleId) {
            url = `/api/settings/ai/examples/${exampleId}`;
            method = 'PUT';
        }
        
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                client_message: q,
                bot_response: a,
                is_active: 1
            })
        });
        
        if (res.ok) {
            showToast(exampleId ? "Приклад успішно оновлено!" : "Приклад додано успішно!", "success");
            hideAddExampleForm();
            await loadAISettings();
        } else {
            showToast("Не вдалося зберегти приклад", "danger");
        }
    } catch (err) {
        showToast("Помилка сервера при збереженні прикладу", "danger");
    }
}

async function toggleAIExample(id, checkbox) {
    try {
        const isChecked = checkbox.checked ? 1 : 0;
        const res = await fetch(`/api/settings/ai/examples/${id}/toggle?is_active=${isChecked}`, {
            method: 'POST'
        });
        if (res.ok) {
            showToast(isChecked ? "Приклад активовано" : "Приклад вимкнено", "success");
        } else {
            checkbox.checked = !checkbox.checked;
            showToast("Не вдалося змінити статус", "danger");
        }
    } catch (err) {
        checkbox.checked = !checkbox.checked;
        showToast("Помилка підключення", "danger");
    }
}

async function deleteAIExample(id) {
    if (!confirm("Ви впевнені, що хочете видалити цей приклад?")) return;
    try {
        const res = await fetch(`/api/settings/ai/examples/${id}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showToast("Приклад видалено", "success");
            await loadAISettings();
        } else {
            showToast("Не вдалося видалити приклад", "danger");
        }
    } catch (err) {
        showToast("Помилка при видаленні", "danger");
    }
}

function renderAIExamples(examples) {
    const container = document.getElementById('ai-examples-list-container');
    if (!container) return;
    container.innerHTML = '';
    
    if (examples.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: rgba(255,255,255,0.4); padding: 15px;">Приклади відсутні</div>';
        return;
    }
    
    examples.forEach(ex => {
        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.flexDirection = 'column';
        item.style.padding = '14px 16px';
        item.style.background = 'rgba(255,255,255,0.015)';
        item.style.border = '1px solid rgba(255,255,255,0.04)';
        item.style.borderRadius = '12px';
        item.style.gap = '8px';
        
        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; width: 100%;">
                <div style="display: flex; flex-direction: column; gap: 8px; flex-grow: 1; min-width: 0;">
                    <!-- Drop message bubble -->
                    <div style="background: rgba(255, 255, 255, 0.025); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 10px; padding: 10px 14px; display: flex; flex-direction: column; gap: 4px;">
                        <div style="font-size: 0.72rem; color: rgba(255, 255, 255, 0.45); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center; gap: 5px;">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                            Клієнт (Дроп)
                        </div>
                        <div style="font-size: 0.88rem; color: #e2e8f0; line-height: 1.45;">
                            ${ex.client_message}
                        </div>
                    </div>

                    <!-- Bot response bubble -->
                    <div style="background: linear-gradient(135deg, rgba(168, 85, 247, 0.07) 0%, rgba(124, 58, 237, 0.02) 100%); border: 1px solid rgba(168, 85, 247, 0.2); border-left: 3px solid #a855f7; border-radius: 10px; padding: 10px 14px; display: flex; flex-direction: column; gap: 4px;">
                        <div style="font-size: 0.72rem; color: #c084fc; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center; gap: 5px;">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="#c084fc" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="15" x2="23" y2="15"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="15" x2="4" y2="15"/></svg>
                            Відповідь ШІ-Бота
                        </div>
                        <div style="font-size: 0.88rem; color: #f1f5f9; line-height: 1.45;">
                            ${ex.bot_response}
                        </div>
                    </div>
                </div>

                <!-- Action controls -->
                <div style="display: flex; align-items: center; gap: 12px; flex-shrink: 0; margin-top: 4px;">
                    <label class="switch-container" style="display: flex; align-items: center; cursor: pointer;">
                        <div class="switch">
                            <input type="checkbox" ${ex.is_active === 1 ? 'checked' : ''} onchange="toggleAIExample(${ex.id}, this)">
                            <span class="slider"></span>
                        </div>
                    </label>
                    <div style="display: flex; gap: 6px;">
                        <button class="btn btn-secondary btn-sm" onclick="editAIExample(${ex.id}, \`${ex.client_message.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/"/g, '&quot;')}\`, \`${ex.bot_response.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/"/g, '&quot;')}\`)" style="padding: 6px 10px; font-size: 0.78rem; display: inline-flex; align-items: center;"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
                        <button class="btn btn-secondary btn-sm" onclick="deleteAIExample(${ex.id})" style="padding: 6px 10px; font-size: 0.78rem; border-color: rgba(239, 68, 68, 0.2); color: #ef4444; display: inline-flex; align-items: center;"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg></button>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(item);
    });
}

function switchAISubtab(subtabName) {
    // 1. Update active button classes
    document.querySelectorAll('.ai-tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    const activeBtn = document.querySelector(`.ai-tab-btn[onclick="switchAISubtab('${subtabName}')"]`);
    if (activeBtn) activeBtn.classList.add('active');

    // 2. Show/hide subpanes
    document.querySelectorAll('.ai-subpane').forEach(pane => {
        pane.style.display = 'none';
    });
    const activePane = document.getElementById(`ai-subpane-${subtabName}`);
    if (activePane) {
        activePane.style.display = 'flex';
    }
}
