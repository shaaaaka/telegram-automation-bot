let isDraggingBank = false;
let dragSourceEl = null;

// Global function to insert a placeholder tag at cursor position in report template textarea
window.insertPlaceholderTag = function(keyOrId, tagName) {
    const textarea = document.getElementById(keyOrId === 'new-bank' ? 'new-bank-report-tpl' : `bank-acc-report-tpl-${keyOrId}`);
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    const before = text.substring(0, start);
    const after  = text.substring(end, text.length);
    textarea.value = before + tagName + after;
    textarea.selectionStart = textarea.selectionEnd = start + tagName.length;
    textarea.focus();
    if (keyOrId === 'new-bank') {
        updateTelegramMockupPreview('new-bank');
    } else {
        updateTelegramMockupPreview(keyOrId);
    }
    if (keyOrId !== 'new-bank') {
        checkAccordionFormChanges(keyOrId);
    }
};

// Global function to switch tabs inside a bank accordion item
window.switchBankAccordionTab = function(key, tabName, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const accordionItem = document.getElementById(`bank-accordion-item-${key}`);
    if (!accordionItem) return;

    // Save tab choice to localStorage
    localStorage.setItem(`active_bank_subtab_${key}`, tabName);

    // Remove active class from all sub-tab buttons
    accordionItem.querySelectorAll('.tab-btn-sub').forEach(btn => {
        btn.classList.remove('active');
    });

    // Add active class to clicked button
    const clickedBtn = event ? event.currentTarget : accordionItem.querySelector(`button[onclick*="'${tabName}'"]`);
    if (clickedBtn) {
        clickedBtn.classList.add('active');
    }

    // Hide all tab contents
    accordionItem.querySelectorAll('.bank-tab-content').forEach(content => {
        content.style.display = 'none';
    });

    // Show selected tab content
    const targetContent = document.getElementById(`bank-tab-content-${key}-${tabName}`);
    if (targetContent) {
        targetContent.style.display = 'block';
        // Auto-grow textareas inside the newly shown tab
        setTimeout(() => {
            targetContent.querySelectorAll('textarea').forEach(ta => {
                autoGrowTextarea(ta);
            });
            const chatBody = targetContent.querySelector('.telegram-mockup-chat-body');
            if (chatBody) {
                chatBody.scrollTop = chatBody.scrollHeight;
            }
        }, 10);
    }
};

window.checkAccordionFormChanges = function(key) {
    const btnSave = document.getElementById(`bank-acc-save-btn-${key}`);
    const btnCancel = document.getElementById(`bank-acc-cancel-btn-${key}`);
    if (!btnSave) return;

    const template = (window.bankTemplates && window.bankTemplates[key]) ? window.bankTemplates[key] : {};

    // Get current values
    const displayName = document.getElementById(`bank-acc-display-name-${key}`)?.value?.trim() || '';
    const command = document.getElementById(`bank-acc-cmd-${key}`)?.value?.trim() || '';
    const codeLength = parseInt(document.getElementById(`bank-acc-len-${key}`)?.value) || 4;
    const reqScreenshots = parseInt(document.getElementById(`bank-acc-req-scr-${key}`)?.value) || 1;
    const text = document.getElementById(`bank-acc-text-${key}`)?.value?.trim() || '';
    const aiRules = document.getElementById(`bank-acc-airules-${key}`)?.value?.trim() || '';
    const description = document.getElementById(`bank-acc-desc-${key}`)?.value?.trim() || '';
    const reportTpl = document.getElementById(`bank-acc-report-tpl-${key}`)?.value || '';
    const activeInput = document.getElementById(`bank-acc-active-${key}`);
    const activeVal = activeInput ? (activeInput.checked ? 1 : 0) : 1;
    const originalActive = template.hasOwnProperty('is_active') ? template.is_active : 1;

    // Check files
    const logoInput = document.getElementById(`bank-acc-logo-${key}`);
    const logoChanged = logoInput && logoInput.files && logoInput.files.length > 0;

    const downloadScreenshotInput = document.getElementById(`bank-acc-download-screenshot-${key}`);
    const downloadChanged = downloadScreenshotInput && downloadScreenshotInput.files && downloadScreenshotInput.files.length > 0;

    const screenshotInput = document.getElementById(`bank-acc-screenshot-${key}`);
    const screenshotChanged = screenshotInput && screenshotInput.files && screenshotInput.files.length > 0;

    const successScreenshotInput = document.getElementById(`bank-acc-success-screenshot-${key}`);
    const successChanged = successScreenshotInput && successScreenshotInput.files && successScreenshotInput.files.length > 0;

    const deletionScreenshotInput = document.getElementById(`bank-acc-deletion-screenshot-${key}`);
    const deletionChanged = deletionScreenshotInput && deletionScreenshotInput.files && deletionScreenshotInput.files.length > 0;

    const downloadRemoved = document.getElementById(`bank-acc-download-screenshot-removed-${key}`)?.value === '1';
    const screenshotRemoved = document.getElementById(`bank-acc-screenshot-removed-${key}`)?.value === '1';
    const successRemoved = document.getElementById(`bank-acc-success-screenshot-removed-${key}`)?.value === '1';
    const deletionRemoved = document.getElementById(`bank-acc-deletion-screenshot-removed-${key}`)?.value === '1';

    const deletionReqInput = document.getElementById(`bank-acc-deletion-req-${key}`);
    const deletionReqVal = deletionReqInput?.value || 'none';
    const originalDeletionReq = template.deletion_requirement || 'none';

    // Normalizations for text comparisons
    const normTpl = reportTpl.replace(/\r\n/g, '\n').trim();
    const originalTpl = (template.report_template || `{pib}\n{dob}\n{ipn}\n{phone}\n\nДроп - @{username}\n\nLine {line_id} Return: {line_phone} | {bank}\n\n{code}`).replace(/\r\n/g, '\n').trim();

    let hasChanges = false;
    if (displayName !== (template.display_name || key)) hasChanges = true;
    if (command !== (template.command || '')) hasChanges = true;
    if (codeLength !== (template.code_length || 4)) hasChanges = true;
    if (reqScreenshots !== (template.required_screenshots || 1)) hasChanges = true;
    if (text !== (template.text || '')) hasChanges = true;
    if (aiRules !== (template.ai_rules || '')) hasChanges = true;
    if (description !== (template.description || '')) hasChanges = true;
    if (activeVal !== originalActive) hasChanges = true;
    if (normTpl !== originalTpl) hasChanges = true;
    if (deletionReqVal !== originalDeletionReq) hasChanges = true;
    if (logoChanged || downloadChanged || screenshotChanged || successChanged || deletionChanged || downloadRemoved || screenshotRemoved || successRemoved || deletionRemoved) hasChanges = true;

    if (hasChanges) {
        btnSave.disabled = false;
        btnSave.style.opacity = '1';
        btnSave.style.cursor = 'pointer';
        btnSave.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
        btnSave.style.boxShadow = '0 4px 15px rgba(16, 185, 129, 0.4)';
        btnSave.style.border = 'none';
        btnSave.style.color = '#ffffff';
        if (btnCancel) {
            btnCancel.setAttribute('data-has-changes', 'true');
        }
    } else {
        btnSave.disabled = true;
        btnSave.style.opacity = '0.4';
        btnSave.style.cursor = 'not-allowed';
        btnSave.style.background = 'rgba(255,255,255,0.05)';
        btnSave.style.boxShadow = 'none';
        btnSave.style.border = '1px solid rgba(255,255,255,0.1)';
        btnSave.style.color = 'rgba(255,255,255,0.6)';
        if (btnCancel) {
            btnCancel.setAttribute('data-has-changes', 'false');
        }
    }
};

window.toggleBankActiveLabel = function(key) {
    const cb = document.getElementById(`bank-acc-active-${key}`);
    const label = document.getElementById(`bank-acc-active-label-${key}`);
    if (cb && label) {
        if (cb.checked) {
            label.textContent = 'Активний';
            label.style.background = 'rgba(52,211,153,0.1)';
            label.style.border = '1px solid rgba(52,211,153,0.25)';
            label.style.color = '#34d399';
        } else {
            label.textContent = 'Пауза';
            label.style.background = 'rgba(255,255,255,0.03)';
            label.style.border = '1px solid rgba(255,255,255,0.08)';
            label.style.color = 'var(--text-muted)';
        }
    }
    // Trigger validation
    checkAccordionFormChanges(key);
};

window.toggleRelinkInstructionVisibility = function(key) {
    const cb = document.getElementById(`bank-acc-allow-relink-${key}`);
    const wrapper = document.getElementById(`relink-instruction-wrapper-${key}`);
    if (cb && wrapper) {
        if (cb.checked) {
            wrapper.style.display = 'flex';
            const textarea = document.getElementById(`bank-acc-relink-instr-${key}`);
            if (textarea) {
                setTimeout(() => {
                    if (window.autoGrowTextarea) window.autoGrowTextarea(textarea);
                    else if (typeof autoGrowTextarea === 'function') autoGrowTextarea(textarea);
                }, 20);
            }
        } else {
            wrapper.style.display = 'none';
        }
    }
    // Trigger validation
    checkAccordionFormChanges(key);
};

function autoGrowTextarea(element) {
    if (!element) return;
    element.style.height = "auto";
    element.style.overflowY = "hidden";
    element.style.height = (element.scrollHeight) + "px";
}

window.getTelegramMockupHtml = function(rawTemplate, bankKey) {
    let text = rawTemplate || `{pib}\n{dob}\n{ipn}\n{phone}\n\nДроп - @{username}\n\nLine {line_id} Return: {line_phone} | {bank}\n\n{code}`;
    
    // Replace placeholders with mock data
    const replacements = {
        "{pib}": "<b>МАТЮНІН ОЛЕГ ОЛЕГОВИЧ</b>",
        "{dob}": "29.01.2007",
        "{ipn}": "3911006569",
        "{phone}": "+380 (97) 134 46 82",
        "{username}": "fantom1529",
        "{line}": `Line 17 Return: 380950369906 | ${bankKey === 'new-bank' ? 'new-bank' : bankKey}`,
        "{line_id}": "17",
        "{line_phone}": "380950369906",
        "{code}": "<b>1234</b>",
        "{card}": "5457082534505537",
        "{bank}": bankKey === 'new-bank' ? 'new-bank' : bankKey,
        "{target_phone}": "943554053",
        "{target_email}": "jotbidnor@macr2.com",
        "{card_details}": "4421 4421 4213 4921\n12/29\n432",
        "{pincode}": "42134"
    };
    
    for (let place in replacements) {
        text = text.replaceAll(place, replacements[place]);
    }
    return text;
};

function getBankIcon(key, logoPath = null) {
    if (logoPath) {
        return `<img src="${logoPath}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 10px;">`;
    }
    const k = key.toLowerCase();
    if (k.includes('izi')) return `<img src="/static/images/izibank.png" style="width: 100%; height: 100%; object-fit: cover; border-radius: 10px;">`;
    if (k.includes('amo')) return `<img src="/static/images/amobank.png" style="width: 100%; height: 100%; object-fit: cover; border-radius: 10px;">`;
    if (k.includes('lviv')) return `<img src="/static/images/lvivbank.png" style="width: 100%; height: 100%; object-fit: cover; border-radius: 10px;">`;
    if (k.includes('kd')) return `<img src="/static/images/bank_kd.png" style="width: 100%; height: 100%; object-fit: cover; border-radius: 10px;">`;
    if (k.includes('alliance')) return `<img src="/static/images/alliance.png" style="width: 100%; height: 100%; object-fit: cover; border-radius: 10px;">`;
    if (k.includes('mono')) return '🐱';
    if (k.includes('privat')) return '💚';
    if (k.includes('pumb') || k.includes('пумб')) return '❤️';
    return '🏦';
}
function getBankIconGradient(key, logoPath = null) {
    if (logoPath) return 'transparent';
    const k = key.toLowerCase();
    // For specific banks with image logos, we don't need a gradient background
    if (k.includes('izi') || k.includes('amo') || k.includes('lviv') || k.includes('kd') || k.includes('alliance')) {
        return 'transparent';
    }
    return 'linear-gradient(135deg, #64748b, #475569)'; // grey
}
function saveBankOrder() {
    const listActive = document.getElementById('bank-settings-accordion-active');
    const listPaused = document.getElementById('bank-settings-accordion-paused');
    const order = [];
    if (listActive) {
        listActive.querySelectorAll('.bank-accordion-item').forEach(item => {
            order.push(item.id.replace('bank-accordion-item-', ''));
        });
    }
    if (listPaused) {
        listPaused.querySelectorAll('.bank-accordion-item').forEach(item => {
            order.push(item.id.replace('bank-accordion-item-', ''));
        });
    }
    localStorage.setItem('bank_accordion_order', JSON.stringify(order));
}
function addDragAndDropListeners(item) {
    const header = item.querySelector('.bank-accordion-header');
    if (!header) return;

    header.setAttribute('draggable', 'true');

    header.addEventListener('dragstart', (e) => {
        isDraggingBank = true;
        dragSourceEl = item;
        item.style.opacity = '0.4';
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', item.id);
    });

    header.addEventListener('dragover', (e) => {
        if (e.preventDefault) {
            e.preventDefault();
        }
        e.dataTransfer.dropEffect = 'move';
        return false;
    });

    header.addEventListener('dragenter', (e) => {
        const targetItem = e.target.closest('.bank-accordion-item');
        if (targetItem && targetItem !== dragSourceEl) {
            targetItem.style.border = '1px dashed var(--accent-primary)';
            targetItem.style.transform = 'translateY(2px)';
        }
    });

    header.addEventListener('dragleave', (e) => {
        const targetItem = e.target.closest('.bank-accordion-item');
        if (targetItem) {
            targetItem.style.border = '';
            targetItem.style.transform = '';
        }
    });

    header.addEventListener('drop', (e) => {
        if (e.stopPropagation) {
            e.stopPropagation();
        }
        
        const targetItem = e.target.closest('.bank-accordion-item');
        if (dragSourceEl && targetItem && dragSourceEl !== targetItem && dragSourceEl.parentNode === targetItem.parentNode) {
            const list = dragSourceEl.parentNode;
            const children = Array.from(list.children);
            const sourceIndex = children.indexOf(dragSourceEl);
            const targetIndex = children.indexOf(targetItem);
            
            if (sourceIndex < targetIndex) {
                list.insertBefore(dragSourceEl, targetItem.nextSibling);
            } else {
                list.insertBefore(dragSourceEl, targetItem);
            }
            
            saveBankOrder();
        }
        return false;
    });

    header.addEventListener('dragend', (e) => {
        setTimeout(() => { isDraggingBank = false; }, 50);
        document.querySelectorAll('.bank-accordion-item').forEach(el => {
            el.style.opacity = '1';
            el.style.border = '';
            el.style.transform = '';
        });
    });
}
function getPumbRebindTab2HTML(itemKey, template) {
    const cardText = template.text || "Надішліть, будь ласка, дані вашої гривневої картки ПУМБ:\n\n• Номер картки\n• Термін дії\n• CVV";
    const anketaText = template.relink_instruction_text || "Змініть анкетні дані та пошту\n\n• Вкажіть пошту: {target_email}\n\nЯкщо щось не зрозуміло то пишіть";
    const phoneText = template.instruction_text || "Тепер міняємо номер телефону:\n{target_phone}\n\nКоли потрібен буде СМС код, то пишіть до чату \"Код\"\nЯк зміниться надішлете скріншот що номер змінився";
    const pinText = template.success_text || "Вкажіть ПІН-код / пароль який використовується для входу?";
    const delText = template.deletion_text || "🗑 Надішліть скріншот видалення додатка ПУМБ з вашого телефону.";

    return `
        <div style="display: flex; flex-direction: column; gap: 16px;">
            <div style="background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.25); border-radius: 12px; padding: 14px; color: #e0e7ff; font-size: 0.85rem; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.2rem;">🔄</span>
                <div><b>Конструктор кроків ПУМБ:</b> Налаштуйте текстові повідомлення та фото для кожного з 6 кроків перев'язу ПУМБ.</div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">

                <!-- Step 1: Diya Screenshots -->
                <div style="background: rgba(255,255,255,0.015); border: 1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; justify-content: space-between; gap: 12px;">
                    <div>
                        <div style="font-size: 0.85rem; font-weight: 700; color: #818cf8; margin-bottom: 4px;">Крок 1: 7 Скріншотів з Дії</div>
                        <div style="font-size: 0.74rem; color: rgba(255,255,255,0.5);">ШІ (OCR) автоматично розпізнає ПІБ, дату народження та ІПН з документів.</div>
                    </div>
                    <div style="background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.25); border-radius: 8px; padding: 8px 10px; color: #4ade80; font-size: 0.75rem; font-weight: 600; text-align: center;">
                        🟢 ШІ OCR Увімкнено (ПІБ / ІПН)
                    </div>
                </div>

                <!-- Step 2: Card Details -->
                <div style="background: rgba(255,255,255,0.015); border: 1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; justify-content: space-between; gap: 12px;">
                    <div>
                        <div style="font-size: 0.85rem; font-weight: 700; color: #a5b4fc; margin-bottom: 4px;">Крок 2: Запит картки ПУМБ</div>
                        <div style="font-size: 0.74rem; color: rgba(255,255,255,0.5); margin-bottom: 8px;">Текст прохання реквізитів картки (Номер, Термін, CVV).</div>
                    </div>
                    <textarea id="bank-acc-text-${itemKey}" class="form-control auto-grow-textarea" rows="3" style="font-size: 0.78rem; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; color: #fff; padding: 8px 10px; width: 100%; box-sizing: border-box; font-family: inherit;" placeholder="Текст запиту картки...">${cardText}</textarea>
                </div>

                <!-- Step 3: Anketa & Email -->
                <div style="background: rgba(255,255,255,0.015); border: 1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; justify-content: space-between; gap: 12px;">
                    <div>
                        <div style="font-size: 0.85rem; font-weight: 700; color: #a5b4fc; margin-bottom: 4px;">Крок 3: Анкетні дані та пошта</div>
                        <div style="font-size: 0.74rem; color: rgba(255,255,255,0.5); margin-bottom: 8px;">Надсилається разом з фото Anketa.jpg.</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: center; gap: 6px;">
                        <span id="anketa-filename-${itemKey}" class="file-upload-filename-pill selected" style="font-size: 0.72rem;">Anketa.jpg (активне фото)</span>
                        <div class="custom-file-upload-wrapper" style="width: 100%; max-width: 180px;">
                            <label for="bank-acc-anketa-${itemKey}" class="custom-file-upload-label" style="justify-content: center; width: 100%; padding: 6px 10px; font-size: 0.75rem;">
                                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
                                Обрати нову Anketa.jpg
                            </label>
                            <input type="file" id="bank-acc-anketa-${itemKey}" accept="image/*" style="display: none;" onchange="document.getElementById('anketa-filename-${itemKey}').textContent = this.files[0] ? this.files[0].name : 'Anketa.jpg'">
                        </div>
                    </div>
                    <textarea id="bank-acc-relink-instr-${itemKey}" class="form-control auto-grow-textarea" rows="3" style="font-size: 0.78rem; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; color: #fff; padding: 8px 10px; width: 100%; box-sizing: border-box; font-family: inherit;" placeholder="Текст прохання пошти...">${anketaText}</textarea>
                </div>

                <!-- Step 4: Phone Change -->
                <div style="background: rgba(255,255,255,0.015); border: 1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; justify-content: space-between; gap: 12px;">
                    <div>
                        <div style="font-size: 0.85rem; font-weight: 700; color: #a5b4fc; margin-bottom: 4px;">Крок 4: Зміна номера телефону</div>
                        <div style="font-size: 0.74rem; color: rgba(255,255,255,0.5); margin-bottom: 8px;">Інструкція зміни номера та передачі СМС-коду.</div>
                    </div>
                    <textarea id="bank-acc-instruction-text-${itemKey}" class="form-control auto-grow-textarea" rows="3" style="font-size: 0.78rem; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; color: #fff; padding: 8px 10px; width: 100%; box-sizing: border-box; font-family: inherit;" placeholder="Текст зміни номера...">${phoneText}</textarea>
                </div>

                <!-- Step 5: PIN Code -->
                <div style="background: rgba(255,255,255,0.015); border: 1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; justify-content: space-between; gap: 12px;">
                    <div>
                        <div style="font-size: 0.85rem; font-weight: 700; color: #a5b4fc; margin-bottom: 4px;">Крок 5: Ввід ПІН-коду</div>
                        <div style="font-size: 0.74rem; color: rgba(255,255,255,0.5); margin-bottom: 8px;">Запит ПІН-коду / паролю входу в додаток.</div>
                    </div>
                    <textarea id="bank-acc-success-text-${itemKey}" class="form-control auto-grow-textarea" rows="3" style="font-size: 0.78rem; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; color: #fff; padding: 8px 10px; width: 100%; box-sizing: border-box; font-family: inherit;" placeholder="Текст прохання ПІН-коду...">${pinText}</textarea>
                </div>

                <!-- Step 6: App Deletion -->
                <div style="background: rgba(255,255,255,0.015); border: 1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; justify-content: space-between; gap: 12px;">
                    <div>
                        <div style="font-size: 0.85rem; font-weight: 700; color: #a5b4fc; margin-bottom: 4px;">Крок 6: Видалення додатка ПУМБ</div>
                        <div style="font-size: 0.74rem; color: rgba(255,255,255,0.5); margin-bottom: 8px;">Запит скріншоту видалення додатка з телефону.</div>
                    </div>
                    <textarea id="bank-acc-deletion-text-${itemKey}" class="form-control auto-grow-textarea" rows="3" style="font-size: 0.78rem; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; color: #fff; padding: 8px 10px; width: 100%; box-sizing: border-box; font-family: inherit;" placeholder="Текст запиту видалення...">${delText}</textarea>
                </div>

            </div>
        </div>
    `;
}

function getBankAccordionItemHTML(itemKey, bankKey, template, activeSubTab, options = {}) {
    const isPaused = template.is_active === 0;
    const isPumb = bankKey.toLowerCase() === 'pumb' || itemKey.toLowerCase() === 'pumb';
    const displayName = template.display_name || bankKey;
    const avatarHTML = `<div style="width: 30px; height: 30px; border-radius: 50%; background: ${getBankIconGradient(bankKey, template.logo_path)}; display: flex; align-items: center; justify-content: center; overflow: hidden; flex-shrink: 0; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">${getBankIcon(bankKey, template.logo_path)}</div>`;
    const formSubmit = options.noActions ? 'event.preventDefault();' : `saveAccordionBankSettings(event, '${bankKey}')`;
    const toggleHandler = options.toggleHandler || `toggleBankAccordion('${itemKey}')`;
    const actionButtons = options.noActions ? '<div class="bank-action-buttons-row" style="display: none;"></div>' : `<div class="bank-action-buttons-row">
                        <div>
                            <button type="button" class="btn btn-danger btn-sm" onclick="deleteAccordionBank('${itemKey}')" style="padding: 8px 16px; font-size: 0.8rem;">Видалити банк</button>
                        </div>
                        <div class="bank-action-right-group">
                            <button type="button" id="bank-acc-cancel-btn-${itemKey}" data-has-changes="false" class="btn btn-secondary btn-sm" onclick="cancelAccordionEdit('${itemKey}')" style="padding: 8px 16px; font-size: 0.8rem; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: rgba(255,255,255,0.7);">Скасувати</button>
                            <button type="submit" id="bank-acc-save-btn-${itemKey}" disabled class="btn btn-primary" style="padding: 8px 20px; font-weight: 600; font-size: 0.85rem; opacity: 0.4; cursor: not-allowed; transition: all 0.2s ease;">Зберегти зміни</button>
                        </div>
                    </div>`;
    return `
            <div class="bank-accordion-header" onclick="${toggleHandler}">
                <div style="display: flex; align-items: center; gap: 14px;">
                    <div class="bank-icon-badge" style="background: ${getBankIconGradient(bankKey, template.logo_path)};">${getBankIcon(bankKey, template.logo_path)}</div>
                    <span class="bank-title" style="font-weight: 600; color: #fff; font-size: 1rem; letter-spacing: 0.3px;">${displayName}</span>
                    ${isPaused ? `<span class="bank-status-badge-paused" style="font-size: 0.65rem; font-weight: 700; padding: 2px 8px; border-radius: 6px; background: rgba(244,63,94,0.1); border: 1px solid rgba(244,63,94,0.25); color: #fb7185; text-transform: uppercase; letter-spacing: 0.5px; user-select: none;">Пауза</span>` : ''}
                </div>
                <div style="display: flex; align-items: center;">
                    <svg class="accordion-arrow" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="var(--text-muted)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="transition: transform 0.25s ease; display: inline-block; transform-origin: center;">
                        <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                </div>
            </div>
            <div class="bank-accordion-body">
                <form onsubmit="${formSubmit}" style="display: flex; flex-direction: column; margin-top: 16px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 16px;">
                    
                    <!-- Sub-tabs bar -->
                    <div class="bank-accordion-tabs-bar">
                        <button type="button" class="tab-btn-sub ${activeSubTab === 'general' ? 'active' : ''}" onclick="switchBankAccordionTab('${itemKey}', 'general', event)">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="12" cy="12" r="3"></circle>
                                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l-.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                            </svg>
                            Загальні
                        </button>
                        <button type="button" class="tab-btn-sub ${activeSubTab === 'media' ? 'active' : ''}" onclick="switchBankAccordionTab('${itemKey}', 'media', event)">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                                <polyline points="21 15 16 10 5 21"></polyline>
                            </svg>
                            Інструкції
                        </button>
                        <button type="button" class="tab-btn-sub ${activeSubTab === 'ai' ? 'active' : ''}" onclick="switchBankAccordionTab('${itemKey}', 'ai', event)">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                <rect x="4" y="4" width="16" height="16" rx="2"></rect>
                                <rect x="9" y="9" width="6" height="6"></rect>
                                <line x1="9" y1="1" x2="9" y2="4"></line>
                                <line x1="15" y1="1" x2="15" y2="4"></line>
                                <line x1="9" y1="20" x2="9" y2="23"></line>
                                <line x1="15" y1="20" x2="15" y2="23"></line>
                                <line x1="20" y1="9" x2="23" y2="9"></line>
                                <line x1="20" y1="15" x2="23" y2="15"></line>
                                <line x1="1" y1="9" x2="4" y2="9"></line>
                                <line x1="1" y1="15" x2="4" y2="15"></line>
                            </svg>
                            ШІ & Верифікатор
                        </button>
                    </div>

                    <!-- TAB 1: General Parameters -->
                    <div id="bank-tab-content-${itemKey}-general" class="bank-tab-content" style="${activeSubTab === 'general' ? '' : 'display: none;'}">
                        <div class="bank-general-grid">
                            <!-- Card 1: Logo + Назва банку -->
                            <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; align-items: center; gap: 16px; justify-content: center;">
                                <!-- Logo Upload Box -->
                                <div style="display: flex; flex-direction: column; align-items: center; gap: 4px; flex-shrink: 0;">
                                    <div id="logo-preview-${itemKey}" 
                                         class="bank-media-preview-box" 
                                         style="width: 64px; height: 64px; border-radius: 50%; border: ${template.logo_path ? '1.5px solid rgba(255,255,255,0.2)' : '2px dashed rgba(255,255,255,0.15)'}; background: ${template.logo_path ? `url('${template.logo_path}') no-repeat center/cover` : 'rgba(255,255,255,0.03)'}; display: flex; align-items: center; justify-content: center; transition: all 0.25s ease; cursor: pointer; position: relative; flex-shrink: 0;"
                                         onclick="document.getElementById('bank-acc-logo-${itemKey}').click()">
                                        ${!template.logo_path ? `
                                            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                                            </svg>
                                        ` : ''}
                                        <div class="hover-zoom-overlay" style="position: absolute; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 50%;">
                                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                                        </div>
                                    </div>
                                    <input type="file" id="bank-acc-logo-${itemKey}" accept="image/*" style="display: none;" onchange="handleFilePreview(this, 'logo-preview-${itemKey}', 'logo-filename-${itemKey}', true)" data-original="${template.logo_path || ''}">
                                    <span id="logo-filename-${itemKey}" class="file-upload-filename-pill" style="font-size: 0.6rem; max-width: 64px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">Логотип</span>
                                    <button type="button" id="logo-reset-${itemKey}" class="btn-reset-file" style="display: none; padding: 2px 6px; font-size: 0.6rem;" onclick="resetFileSelection('${itemKey}', 'logo')">Відхилити</button>
                                </div>
                                
                                <!-- Vertical Divider -->
                                <div style="width: 1px; height: 44px; background: rgba(255,255,255,0.08); flex-shrink: 0;"></div>

                                <!-- Bank Name Input -->
                                <div style="flex-grow: 1; display: flex; flex-direction: column; justify-content: center;">
                                    <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px;">Назва банку</label>
                                    <input type="text" id="bank-acc-display-name-${itemKey}" value="${displayName}" required class="form-control" style="width: 100%;">
                                </div>
                            </div>
                            
                            <!-- Card 2: Команда в Telegram -->
                            <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; gap: 8px;">
                                <label class="form-label" style="font-size: 0.8rem; margin: 0;">Команда в Telegram</label>
                                <input type="text" id="bank-acc-cmd-${itemKey}" value="${template.command || ''}" required class="form-control" style="width: 100%; text-align: center;">
                            </div>

                            <!-- Card 3: Довжина коду -->
                            <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; gap: 8px;">
                                <label class="form-label" style="font-size: 0.8rem; margin: 0;">Довжина коду (цифр)</label>
                                <input type="number" id="bank-acc-len-${itemKey}" value="${template.code_length || 4}" required min="1" max="10" class="form-control" style="width: 100%; max-width: 100px; text-align: center;">
                            </div>

                            <!-- Card 4: Необхідно скріншотів -->
                            <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; justify-content: center; position: relative; overflow: visible; align-items: center; text-align: center; gap: 8px;">
                                <label class="form-label" style="font-size: 0.8rem; margin: 0;">Необхідно скріншотів</label>
                                <div class="custom-select-wrapper" id="custom-select-wrapper-${itemKey}" style="width: 100%; max-width: 140px;">
                                    <div class="custom-select-trigger" onclick="toggleCustomSelectDropdown('${itemKey}', event); event.stopPropagation();">
                                        <span id="custom-select-value-${itemKey}">${template.required_screenshots || 1} скріншот${(template.required_screenshots || 1) == 1 ? '' : (template.required_screenshots || 1) < 5 ? 'и' : 'ів'}</span>
                                        <svg class="custom-select-arrow" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5">
                                            <polyline points="6 9 12 15 18 9"></polyline>
                                        </svg>
                                    </div>
                                    <div class="custom-select-options" id="custom-select-options-${itemKey}">
                                        <div class="custom-select-option ${template.required_screenshots == 1 ? 'selected' : ''}" data-value="1" onclick="selectRequiredScreenshotsOption('${itemKey}', 1, event)">1 скріншот</div>
                                        <div class="custom-select-option ${template.required_screenshots == 2 ? 'selected' : ''}" data-value="2" onclick="selectRequiredScreenshotsOption('${itemKey}', 2, event)">2 скріншоти</div>
                                        <div class="custom-select-option ${template.required_screenshots == 3 ? 'selected' : ''}" data-value="3" onclick="selectRequiredScreenshotsOption('${itemKey}', 3, event)">3 скріншоти</div>
                                        <div class="custom-select-option ${template.required_screenshots == 4 ? 'selected' : ''}" data-value="4" onclick="selectRequiredScreenshotsOption('${itemKey}', 4, event)">4 скріншоти</div>
                                        <div class="custom-select-option ${template.required_screenshots == 5 ? 'selected' : ''}" data-value="5" onclick="selectRequiredScreenshotsOption('${itemKey}', 5, event)">5 скріншотів</div>
                                    </div>
                                    <input type="hidden" id="bank-acc-req-scr-${itemKey}" value="${template.required_screenshots || 1}">
                                </div>
                            </div>

                            <!-- Card 5: Статус банку -->
                            <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 8px;">
                                <label class="form-label" style="font-size: 0.8rem; margin: 0;">Статус банку</label>
                                <div style="display: flex; align-items: center; height: 38px; justify-content: center; width: 100%;">
                                    <label class="bank-status-switch" style="margin: 0; flex-shrink: 0;">
                                        <input type="checkbox" id="bank-acc-active-${itemKey}" ${template.is_active !== 0 ? 'checked' : ''} onchange="toggleBankActiveLabel('${itemKey}')">
                                        <span class="bank-status-slider"></span>
                                    </label>
                                </div>
                            </div>
                        </div>

                        <!-- Relinking Settings Block (General Tab) -->
                        <div style="margin-top: 20px; padding: 18px 20px; background: linear-gradient(135deg, rgba(255,255,255,0.02), rgba(255,255,255,0.005)); border: 1px solid rgba(255,255,255,0.07); border-radius: 16px; display: flex; flex-direction: column; gap: 16px; transition: all 0.3s ease;">
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px;">
                                <div style="display: flex; align-items: center; gap: 14px; text-align: left;">
                                    <div style="width: 40px; height: 40px; border-radius: 12px; background: linear-gradient(135deg, rgba(139, 92, 246, 0.18), rgba(99, 102, 241, 0.18)); border: 1px solid rgba(139, 92, 246, 0.3); display: flex; align-items: center; justify-content: center; color: #c084fc; flex-shrink: 0; box-shadow: 0 4px 12px rgba(139, 92, 246, 0.15);">
                                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
                                            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
                                        </svg>
                                    </div>
                                    <div style="display: flex; flex-direction: column; gap: 3px;">
                                        <div style="font-size: 0.92rem; font-weight: 600; color: #ffffff; letter-spacing: -0.2px;">
                                            Режим «Перев'яз» для цього банку
                                        </div>
                                        <div style="font-size: 0.76rem; color: rgba(255,255,255,0.6); line-height: 1.35;">
                                            Дозволяє клієнтам перев'язати існуючий акаунт банку до нового номера телефону
                                        </div>
                                    </div>
                                </div>
                                <label class="switch" style="margin: 0; flex-shrink: 0;">
                                    <input type="checkbox" id="bank-acc-allow-relink-${itemKey}" ${template.allow_relink ? 'checked' : ''} onchange="toggleRelinkInstructionVisibility('${itemKey}')">
                                    <span class="slider"></span>
                                </label>
                            </div>
                            
                            <div id="relink-instruction-wrapper-${itemKey}" style="display: ${template.allow_relink ? 'flex' : 'none'}; flex-direction: column; gap: 10px; text-align: left; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.06); margin-top: 4px;">
                                <label class="form-label" style="font-size: 0.8rem; margin: 0; color: rgba(255,255,255,0.8); font-weight: 500;">
                                    Інструкція перев'язу для клієнта (необов'язково)
                                </label>
                                <textarea id="bank-acc-relink-instr-${itemKey}" class="form-control auto-grow-textarea" rows="2" style="width: 100%; min-height: 65px; box-sizing: border-box; font-family: inherit; font-size: 0.82rem; line-height: 1.45; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; color: #fff; padding: 10px 12px;" placeholder="Наприклад: Зайдіть у Профіль -> Налаштування -> Змінити номер телефону...">${template.relink_instruction_text || ''}</textarea>
                                <div style="font-size: 0.74rem; color: rgba(255,255,255,0.45); display: flex; align-items: center; gap: 6px;">
                                    <span>💡</span>
                                    <span>Цей текст буде надіслано клієнту після того, як ШІ підтвердить успішну перевірку скріншота.</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- TAB 2: Media Instructions -->
                    <div id="bank-tab-content-${itemKey}-media" class="bank-tab-content" style="${activeSubTab === 'media' ? '' : 'display: none;'}">
                        ${isPumb ? getPumbRebindTab2HTML(itemKey, template) : `
                        <div class="bank-media-grid">
                            <!-- Download Screenshot Card -->
                            <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 14px; justify-content: space-between; position: relative; overflow: hidden; min-height: 330px;">
                                <div style="display: flex; flex-direction: column; align-items: center; gap: 6px; width: 100%;">
                                    <span style="font-size: 0.8rem; font-weight: 600; color: rgba(255,255,255,0.5); letter-spacing: 0.5px; text-transform: uppercase;">Який банк завантажити</span>
                                    <span id="download-screenshot-filename-${itemKey}" class="file-upload-filename-pill ${template.download_screenshot_path ? 'selected' : ''}" style="max-width: 100%; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-size: 0.75rem;">${template.download_screenshot_path ? 'Файли завантажено' : 'Файл не обрано'}</span>
                                </div>
                                
                                <div id="download-screenshot-preview-${itemKey}" 
                                     style="display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; align-items: center; width: 100%; min-height: 120px; flex-shrink: 0;">
                                     ${getMediaGroupHTML(template.download_screenshot_path, 'download')}
                                </div>
 
                                <div style="width: 100%; display: flex; flex-direction: column; gap: 8px; align-items: center;">
                                    <input type="hidden" id="bank-acc-download-screenshot-removed-${itemKey}" value="0">
                                    <div class="custom-file-upload-wrapper" style="width: 100%; max-width: 200px;">
                                        <label for="bank-acc-download-screenshot-${itemKey}" class="custom-file-upload-label" style="justify-content: center; width: 100%; padding: 8px 14px;">
                                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                                            </svg>
                                            Обрати скріншоти
                                        </label>
                                        <input type="file" id="bank-acc-download-screenshot-${itemKey}" accept="image/*" multiple style="display: none;" onchange="handleMultipleFilePreview(this, 'download-screenshot-preview-${itemKey}', 'download-screenshot-filename-${itemKey}')" data-original="${template.download_screenshot_path || ''}">
                                    </div>
                                    <button type="button" id="download-screenshot-reset-${itemKey}" class="btn-reset-file" style="display: none;" onclick="resetFileSelection('${itemKey}', 'download-screenshot')">Відхилити</button>
                                    <button type="button" id="download-screenshot-delete-${itemKey}" class="btn-delete-media" style="display: ${template.download_screenshot_path ? 'inline-flex' : 'none'};" onclick="removeSavedImage('${itemKey}', 'download-screenshot')">
                                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <polyline points="3 6 5 6 21 6"></polyline>
                                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                        </svg>
                                        Вилучити фото
                                    </button>
                                </div>

                                <div style="width: 100%; display: flex; flex-direction: column; gap: 6px; text-align: center;">
                                    <span style="font-size: 0.72rem; font-weight: 600; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.5px;">Текст інструкції</span>
                                    <textarea id="bank-acc-text-${itemKey}" class="form-control auto-grow-textarea" rows="2" style="font-size: 0.78rem; text-align: center; resize: none; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; color: #fff; padding: 6px 10px; width: 100%; box-sizing: border-box; min-height: 50px;" placeholder="Введіть текст інструкції..." required>${template.text || ''}</textarea>
                                </div>
                            </div>
 
                            <!-- Instruction Screenshot Card -->
                            <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 14px; justify-content: space-between; position: relative; overflow: hidden; min-height: 330px;">
                                <div style="display: flex; flex-direction: column; align-items: center; gap: 6px; width: 100%;">
                                    <span style="font-size: 0.8rem; font-weight: 600; color: rgba(255,255,255,0.5); letter-spacing: 0.5px; text-transform: uppercase;">Скріншот-інструкція як проходити</span>
                                    <span id="screenshot-filename-${itemKey}" class="file-upload-filename-pill ${template.screenshot_path ? 'selected' : ''}" style="max-width: 100%; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-size: 0.75rem;">${template.screenshot_path ? 'Файли завантажено' : 'Файл не обрано'}</span>
                                </div>
                                
                                <div id="screenshot-preview-${itemKey}" 
                                     style="display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; align-items: center; width: 100%; min-height: 120px; flex-shrink: 0;">
                                     ${getMediaGroupHTML(template.screenshot_path, 'screenshot')}
                                </div>
 
                                <div style="width: 100%; display: flex; flex-direction: column; gap: 8px; align-items: center;">
                                    <input type="hidden" id="bank-acc-screenshot-removed-${itemKey}" value="0">
                                    <div class="custom-file-upload-wrapper" style="width: 100%; max-width: 200px;">
                                        <label for="bank-acc-screenshot-${itemKey}" class="custom-file-upload-label" style="justify-content: center; width: 100%; padding: 8px 14px;">
                                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                                            </svg>
                                            Обрати скріншоти
                                        </label>
                                        <input type="file" id="bank-acc-screenshot-${itemKey}" accept="image/*" multiple style="display: none;" onchange="handleMultipleFilePreview(this, 'screenshot-preview-${itemKey}', 'screenshot-filename-${itemKey}')" data-original="${template.screenshot_path || ''}">
                                    </div>
                                    <button type="button" id="screenshot-reset-${itemKey}" class="btn-reset-file" style="display: none;" onclick="resetFileSelection('${itemKey}', 'screenshot')">Відхилити</button>
                                    <button type="button" id="screenshot-delete-${itemKey}" class="btn-delete-media" style="display: ${template.screenshot_path ? 'inline-flex' : 'none'};" onclick="removeSavedImage('${itemKey}', 'screenshot')">
                                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <polyline points="3 6 5 6 21 6"></polyline>
                                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                        </svg>
                                        Вилучити фото
                                    </button>
                                </div>

                                <div style="width: 100%; display: flex; flex-direction: column; gap: 6px; text-align: center;">
                                    <span style="font-size: 0.72rem; font-weight: 600; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.5px;">Опис кроків</span>
                                    <textarea id="bank-acc-instruction-text-${itemKey}" class="form-control auto-grow-textarea" rows="2" style="font-size: 0.78rem; text-align: center; resize: none; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; color: #fff; padding: 6px 10px; width: 100%; box-sizing: border-box; min-height: 50px;" placeholder="Опис кроків проходження...">${template.instruction_text || ''}</textarea>
                                </div>
                            </div>
 
                            <!-- Success Screenshot Card -->
                            <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 14px; justify-content: space-between; position: relative; overflow: hidden; min-height: 330px;">
                                <div style="display: flex; flex-direction: column; align-items: center; gap: 6px; width: 100%;">
                                    <span style="font-size: 0.8rem; font-weight: 600; color: rgba(255,255,255,0.5); letter-spacing: 0.5px; text-transform: uppercase;">Зразок успішного екрану</span>
                                    <span id="success-screenshot-filename-${itemKey}" class="file-upload-filename-pill ${template.success_screenshot_path ? 'selected' : ''}" style="max-width: 100%; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-size: 0.75rem;">${template.success_screenshot_path ? 'Файли завантажено' : 'Файл не обрано'}</span>
                                </div>
                                
                                <div id="success-screenshot-preview-${itemKey}" 
                                     style="display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; align-items: center; width: 100%; min-height: 120px; flex-shrink: 0;">
                                     ${getMediaGroupHTML(template.success_screenshot_path, 'success')}
                                </div>
 
                                <div style="width: 100%; display: flex; flex-direction: column; gap: 8px; align-items: center;">
                                    <input type="hidden" id="bank-acc-success-screenshot-removed-${itemKey}" value="0">
                                    <div class="custom-file-upload-wrapper" style="width: 100%; max-width: 200px;">
                                        <label for="bank-acc-success-screenshot-${itemKey}" class="custom-file-upload-label" style="justify-content: center; width: 100%; padding: 8px 14px;">
                                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                                            </svg>
                                            Обрати скріншоти
                                        </label>
                                        <input type="file" id="bank-acc-success-screenshot-${itemKey}" accept="image/*" multiple style="display: none;" onchange="handleMultipleFilePreview(this, 'success-screenshot-preview-${itemKey}', 'success-screenshot-filename-${itemKey}')" data-original="${template.success_screenshot_path || ''}">
                                    </div>
                                    <button type="button" id="success-screenshot-reset-${itemKey}" class="btn-reset-file" style="display: none;" onclick="resetFileSelection('${itemKey}', 'success-screenshot')">Відхилити</button>
                                    <button type="button" id="success-screenshot-delete-${itemKey}" class="btn-delete-media" style="display: ${template.success_screenshot_path ? 'inline-flex' : 'none'};" onclick="removeSavedImage('${itemKey}', 'success-screenshot')">
                                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <polyline points="3 6 5 6 21 6"></polyline>
                                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                        </svg>
                                        Вилучити фото
                                    </button>
                                </div>

                                <div style="width: 100%; display: flex; flex-direction: column; gap: 6px; text-align: center;">
                                    <span style="font-size: 0.72rem; font-weight: 600; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.5px;">Текст при успіху</span>
                                    <textarea id="bank-acc-success-text-${itemKey}" class="form-control auto-grow-textarea" rows="2" style="font-size: 0.78rem; text-align: center; resize: none; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; color: #fff; padding: 6px 10px; width: 100%; box-sizing: border-box; min-height: 50px;" placeholder="Текст запиту успішного екрану...">${template.success_text || ''}</textarea>
                                </div>
                            </div>

                            <!-- Deletion Screenshot Card -->
                            <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; align-items: center; text-align: center; justify-content: space-between; gap: 14px; position: relative; overflow: hidden; min-height: 330px; transition: all 0.3s ease;">
                                <div id="deletion-disabled-overlay-${itemKey}" style="position: absolute; inset: 0; background: rgba(15,23,36,0.85); display: ${(template.deletion_requirement || 'none') === 'none' ? 'flex' : 'none'}; flex-direction: column; align-items: center; justify-content: center; gap: 8px; z-index: 10; backdrop-filter: blur(4px); transition: all 0.3s ease;">
                                    <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                                        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                                    </svg>
                                    <span style="font-size: 0.8rem; font-weight: 600; color: rgba(255,255,255,0.5);">Вимогу відключено</span>
                                </div>
                                <div style="display: flex; flex-direction: column; align-items: center; gap: 6px; width: 100%;">
                                    <span style="font-size: 0.8rem; font-weight: 600; color: rgba(255,255,255,0.5); letter-spacing: 0.5px; text-transform: uppercase;">Зразок видалення додатку</span>
                                    <span id="deletion-screenshot-filename-${itemKey}" class="file-upload-filename-pill ${template.deletion_screenshot_path ? 'selected' : ''}" style="max-width: 100%; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-size: 0.75rem;">
                                        ${template.deletion_screenshot_path ? 'Файли завантажено' : 'Файл не обрано'}
                                    </span>
                                </div>
                                
                                <div id="deletion-screenshot-preview-${itemKey}" 
                                     style="display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; align-items: center; width: 100%; min-height: 120px; flex-shrink: 0;">
                                     ${getMediaGroupHTML(template.deletion_screenshot_path, 'deletion')}
                                </div>
 
                                <div style="width: 100%; display: flex; flex-direction: column; gap: 8px; align-items: center;">
                                    <input type="hidden" id="bank-acc-deletion-screenshot-removed-${itemKey}" value="0">
                                    <div class="custom-file-upload-wrapper" style="width: 100%; max-width: 200px;">
                                        <label id="deletion-screenshot-label-${itemKey}" for="bank-acc-deletion-screenshot-${itemKey}" class="custom-file-upload-label" style="justify-content: center; width: 100%; padding: 8px 14px;">
                                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                                            </svg>
                                            ${template.deletion_requirement === 'screenshot' ? 'Обрати скріншот' : (template.deletion_requirement === 'video' ? 'Обрати відео' : 'Обрати скріншоти/відео')}
                                        </label>
                                        <input type="file" id="bank-acc-deletion-screenshot-${itemKey}" accept="${template.deletion_requirement === 'screenshot' ? 'image/*' : (template.deletion_requirement === 'video' ? 'video/*' : 'image/*,video/*')}" multiple style="display: none;" onchange="handleMultipleFilePreview(this, 'deletion-screenshot-preview-${itemKey}', 'deletion-screenshot-filename-${itemKey}')" data-original="${template.deletion_screenshot_path || ''}">
                                    </div>
                                    <button type="button" id="deletion-screenshot-reset-${itemKey}" class="btn-reset-file" style="display: none;" onclick="resetFileSelection('${itemKey}', 'deletion-screenshot')">Відхилити</button>
                                    <button type="button" id="deletion-screenshot-delete-${itemKey}" class="btn-delete-media" style="display: ${template.deletion_screenshot_path ? 'inline-flex' : 'none'};" onclick="removeSavedImage('${itemKey}', 'deletion-screenshot')">
                                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <polyline points="3 6 5 6 21 6"></polyline>
                                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                        </svg>
                                        Вилучити фото
                                    </button>
                                </div>

                                <div style="width: 100%; display: flex; flex-direction: column; gap: 6px; text-align: center;">
                                    <span style="font-size: 0.72rem; font-weight: 600; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.5px;">Текст для видалення</span>
                                    <textarea id="bank-acc-deletion-text-${itemKey}" class="form-control auto-grow-textarea" rows="2" style="font-size: 0.78rem; text-align: center; resize: none; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; color: #fff; padding: 6px 10px; width: 100%; box-sizing: border-box; min-height: 50px;" placeholder="Текст запиту видалення додатку...">${template.deletion_text || ''}</textarea>
                                </div>
                            </div>
                        </div>

                        <!-- AI Deletion Requirement Global Setting Row -->
                        <input type="hidden" id="bank-acc-deletion-req-${itemKey}" value="${template.deletion_requirement || 'none'}">
                        <div class="bank-deletion-settings-row">
                            <div class="bank-deletion-settings-info">
                                <span style="font-size: 0.82rem; font-weight: 600; color: rgba(255,255,255,0.85); letter-spacing: 0.2px;">Вимога видалення додатку в боті (ШІ)</span>
                                <span style="font-size: 0.7rem; color: rgba(255,255,255,0.45); line-height: 1.3;">Оберіть, який доказ видалення додатку бот повинен запросити у клієнта та автоматично перевірити через ШІ</span>
                            </div>
                            <div class="bank-deletion-settings-control">
                                <div style="display: flex; background: rgba(0, 0, 0, 0.22); border: 1px solid rgba(255, 255, 255, 0.05); padding: 4px; border-radius: 10px; width: 100%; box-sizing: border-box; justify-content: space-between; align-items: center; gap: 4px;">
                                    <div id="del-tab-${itemKey}-none" class="del-tab-btn ${(template.deletion_requirement || 'none') === 'none' ? 'active' : ''}" onclick="selectDeletionTab('${itemKey}', 'none')" style="flex: 1; text-align: center; font-size: 0.78rem; font-weight: 600; padding: 8px 6px; border-radius: 7px; cursor: pointer; color: ${(template.deletion_requirement || 'none') === 'none' ? '#fff' : 'rgba(255, 255, 255, 0.4)'}; background: ${(template.deletion_requirement || 'none') === 'none' ? 'rgba(255,255,255,0.08)' : 'transparent'}; border: 1px solid ${(template.deletion_requirement || 'none') === 'none' ? 'rgba(255,255,255,0.08)' : 'transparent'}; transition: all 0.2s ease; user-select: none;">
                                        Нічого
                                    </div>
                                    <div id="del-tab-${itemKey}-screenshot" class="del-tab-btn ${(template.deletion_requirement || 'none') === 'screenshot' ? 'active' : ''}" onclick="selectDeletionTab('${itemKey}', 'screenshot')" style="flex: 1; text-align: center; font-size: 0.78rem; font-weight: 600; padding: 8px 6px; border-radius: 7px; cursor: pointer; color: ${(template.deletion_requirement || 'none') === 'screenshot' ? '#fff' : 'rgba(255, 255, 255, 0.4)'}; background: ${(template.deletion_requirement || 'none') === 'screenshot' ? 'rgba(255,255,255,0.08)' : 'transparent'}; border: 1px solid ${(template.deletion_requirement || 'none') === 'screenshot' ? 'rgba(255,255,255,0.08)' : 'transparent'}; transition: all 0.2s ease; user-select: none;">
                                        Скріншот
                                    </div>
                                    <div id="del-tab-${itemKey}-video" class="del-tab-btn ${(template.deletion_requirement || 'none') === 'video' ? 'active' : ''}" onclick="selectDeletionTab('${itemKey}', 'video')" style="flex: 1; text-align: center; font-size: 0.78rem; font-weight: 600; padding: 8px 6px; border-radius: 7px; cursor: pointer; color: ${(template.deletion_requirement || 'none') === 'video' ? '#fff' : 'rgba(255, 255, 255, 0.4)'}; background: ${(template.deletion_requirement || 'none') === 'video' ? 'rgba(255,255,255,0.08)' : 'transparent'}; border: 1px solid ${(template.deletion_requirement || 'none') === 'video' ? 'rgba(255,255,255,0.08)' : 'transparent'}; transition: all 0.2s ease; user-select: none;">
                                        Відео
                                    </div>
                                </div>
                            </div>
                        </div>
                        `}
                    </div>

                    <!-- TAB 3: AI & Verifier -->
                    <div id="bank-tab-content-${itemKey}-ai" class="bank-tab-content" style="${activeSubTab === 'ai' ? '' : 'display: none;'}">
                        <!-- Verifier Report Template and Mockup Side-by-Side -->
                        <div class="bank-ai-split-grid">
                            <div style="display: flex; flex-direction: column; gap: 10px; width: 100%; height: 100%;">
                                <div class="bank-settings-section-title" style="margin: 0 0 10px 0; font-size: 0.85rem; font-weight: 600; color: rgba(255,255,255,0.7); display: flex; align-items: center; gap: 8px; height: 20px; box-sizing: border-box;">
                                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--accent-primary);">
                                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                        <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                                    </svg>
                                    Шаблон повідомлення для верифікатора
                                </div>
                                <textarea id="bank-acc-report-tpl-${itemKey}" class="form-control auto-grow-textarea" rows="6" style="width: 100%; font-family: monospace; font-size: 0.78rem; line-height: 1.4; resize: none; height: 180px; overflow-y: auto;" oninput="updateTelegramMockupPreview('${itemKey}')" placeholder="Шаблон звіту...">${template.report_template || (isPumb ? `Перев'яз ПУМБ\n\n{pib}\n\n{target_phone}\n{target_email}\n\n{card_details}\n\n{pincode}` : `{pib}\n{dob}\n{ipn}\n{phone}\n\nДроп - @{username}\n\nLine {line_id} Return: {line_phone} | {bank}\n\n{code}`)}</textarea>
                                <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 4px; text-align: left;">
                                    <span style="font-size: 0.75rem; color: rgba(255,255,255,0.35); font-weight: 500;">💡 Доступні змінні (натисніть для вставки):</span>
                                    <div class="tag-pills-container">
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{pib}')">{pib}</div>
                                        ${isPumb ? `
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{target_phone}')">{target_phone}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{target_email}')">{target_email}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{card_details}')">{card_details}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{pincode}')">{pincode}</div>
                                        ` : `
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{dob}')">{dob}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{ipn}')">{ipn}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{phone}')">{phone}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{line}')">{line}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{line_id}')">{line_id}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{line_phone}')">{line_phone}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{code}')">{code}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{card}')">{card}</div>
                                        `}
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{username}')">{username}</div>
                                        <div class="tag-pill" onclick="insertPlaceholderTag('${itemKey}', '{bank}')">{bank}</div>
                                    </div>
                                </div>
                                
                                <!-- AI instructions inside left column -->
                                <div style="display: flex; flex-direction: column; gap: 12px; margin-top: 4px; border-top: 1px solid rgba(255,255,255,0.04); padding-top: 12px; width: 100%;">
                                    <div class="form-group" style="margin: 0;">
                                        <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px; color: rgba(255,255,255,0.6);">Специфічні правила ШІ для банку</label>
                                        <textarea id="bank-acc-airules-${itemKey}" class="form-control auto-grow-textarea" rows="2" style="width: 100%; font-family: inherit; font-size: 0.78rem;" placeholder="Наприклад: Перевіряти ліміти...">${template.ai_rules || ''}</textarea>
                                    </div>
                                    <div class="form-group" style="margin: 0;">
                                        <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px; color: rgba(255,255,255,0.6);">Опис вигляду банку для ШІ (як виглядає додаток, кольори)</label>
                                        <textarea id="bank-acc-desc-${itemKey}" class="form-control auto-grow-textarea" rows="2" style="width: 100%; font-family: inherit; font-size: 0.78rem;" placeholder="Наприклад: Додаток має...">${template.description || ''}</textarea>
                                    </div>
                                </div>
                            </div>

                            <!-- Telegram Mockup Phone Chat Container -->
                            <div class="telegram-mockup-wrapper" style="width: 100%; display: flex; flex-direction: column; text-align: left; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; align-items: center; align-self: start; position: sticky; top: 20px;">
                                <div style="margin: 0 0 10px 0; font-size: 0.85rem; font-weight: 600; color: rgba(255,255,255,0.7); display: flex; align-items: center; gap: 8px; height: 20px; box-sizing: border-box; width: 100%;">
                                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--accent-primary);"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
                                    Прев'ю в Telegram
                                </div>
                                
                                <!-- Chat Window Container -->
                                <div id="telegram-mockup-container-${itemKey}" class="telegram-mockup-chat-container" style="background: #0e1621; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; width: 100%; max-width: 360px; height: ${localStorage.getItem('telegram_mockup_custom_height') || '535px'}; min-height: 360px; max-height: 900px; resize: vertical; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.4); position: relative;" onmouseup="saveTelegramMockupCustomHeight(this)" ontouchend="saveTelegramMockupCustomHeight(this)">
                                    
                                    <!-- Chat Header -->
                                    <div style="background: #17212b; border-bottom: 1px solid rgba(255,255,255,0.06); padding: 10px 14px; display: flex; align-items: center; gap: 10px; height: 50px; box-sizing: border-box; flex-shrink: 0; z-index: 5;">
                                        ${avatarHTML}
                                        <div style="display: flex; flex-direction: column; text-align: left; justify-content: center;">
                                            <span style="font-size: 0.86rem; font-weight: 600; color: #fff; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 160px;">${displayName}</span>
                                            <span style="font-size: 0.70rem; color: #708190; line-height: 1.2;">bot</span>
                                        </div>
                                        <div style="margin-left: auto; color: #708190; display: flex; gap: 12px; align-items: center;">
                                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                                            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/></svg>
                                        </div>
                                    </div>
                                    
                                    <!-- Chat Body (with Telegram message bubbles pattern) -->
                                    <div class="telegram-mockup-chat-body" style="padding: 14px; display: flex; flex-direction: column; gap: 12px; background-image: radial-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 0); background-size: 16px 16px; overflow-y: auto; flex-grow: 1;">
                                        
                                        <!-- Message Bubble -->
                                        <div class="telegram-message-bubble" style="background: #182533; border: 1px solid rgba(255,255,255,0.03); border-radius: 14px 14px 0 14px; width: 100%; max-width: 290px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); align-self: flex-end; display: flex; flex-direction: column; position: relative; flex-shrink: 0; overflow: hidden;">
                                            <div id="telegram-mockup-image-${itemKey}" class="telegram-mockup-scrollable-image" style="display: ${template.success_screenshot_path ? 'block' : 'none'}; border-bottom: 1px solid rgba(255,255,255,0.04); background: rgba(255,255,255,0.02);">
                                                <img src="${template.success_screenshot_path ? template.success_screenshot_path.split(',')[0].trim() : ''}" style="width: 100%; height: auto; display: block;" onload="const cb = this.closest('.telegram-mockup-chat-body'); if(cb) cb.scrollTop = cb.scrollHeight;">
                                            </div>
                                            <div id="telegram-mockup-text-${itemKey}" style="font-size: 0.82rem; color: #fff; line-height: 1.45; white-space: pre-line; word-break: break-word; padding: 12px 14px;">${window.getTelegramMockupHtml(template.report_template, bankKey)}</div>
                                        </div>
                                        
                                    </div>
                                    
                                    <!-- Chat Footer -->
                                    <div style="background: #17212b; border-top: 1px solid rgba(255,255,255,0.06); padding: 8px 12px; display: flex; align-items: center; gap: 10px; height: 44px; box-sizing: border-box; flex-shrink: 0; z-index: 5;">
                                        <div style="color: #708190; cursor: pointer; display: flex; align-items: center;">
                                            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/></svg>
                                        </div>
                                        <div style="flex-grow: 1; background: #242f3d; border-radius: 18px; padding: 6px 12px; font-size: 0.8rem; color: #708190; display: flex; justify-content: space-between; align-items: center; height: 28px; box-sizing: border-box;">
                                            <span>Повідомлення...</span>
                                            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" style="transform: rotate(45deg); cursor: pointer;"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                                        </div>
                                        <div style="color: #5288c1; cursor: pointer; display: flex; align-items: center;">
                                            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        
                    </div>

                    ${actionButtons}
                </form>
            </div>`;
}

function renderBankAccordion(templates, activeKey) {
    const containerActive = document.getElementById('bank-settings-accordion-active');
    const containerPaused = document.getElementById('bank-settings-accordion-paused');
    const pausedWrapper = document.getElementById('bank-settings-accordion-paused-wrapper');
    if (!containerActive || !containerPaused) return;

    containerActive.innerHTML = '';
    containerPaused.innerHTML = '';

    let keys = Object.keys(templates);
    const savedOrder = localStorage.getItem('bank_accordion_order');
    if (savedOrder) {
        try {
            const orderArr = JSON.parse(savedOrder);
            keys.sort((a, b) => {
                const idxA = orderArr.indexOf(a);
                const idxB = orderArr.indexOf(b);
                if (idxA === -1 && idxB === -1) return 0;
                if (idxA === -1) return 1;
                if (idxB === -1) return -1;
                return idxA - idxB;
            });
        } catch (e) {
            console.error("Error parsing bank order", e);
        }
    }

    if (keys.length === 0) {
        containerActive.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 32px; background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.03); border-radius: 12px;">Немає збережених банків. Додайте перший банк за допомогою кнопки вище.</div>';
        if (pausedWrapper) pausedWrapper.style.display = 'none';
        return;
    }

    let hasPaused = false;

    keys.forEach(key => {
        const template = templates[key];
        const item = document.createElement('div');
        item.className = 'bank-accordion-item';
        item.id = `bank-accordion-item-${key}`;
        
        const isPaused = template.is_active === 0;
        if (isPaused) {
            item.classList.add('bank-paused');
            hasPaused = true;
        }
        if (key === activeKey) {
            item.classList.add('active');
            // Run immediately to resize textareas on page load
            setTimeout(() => {
                item.querySelectorAll('textarea').forEach(ta => {
                    autoGrowTextarea(ta);
                });
            }, 10);

            // Run again after a delay to ensure final size is perfect
            setTimeout(() => {
                item.querySelectorAll('textarea').forEach(ta => {
                    autoGrowTextarea(ta);
                });
                if (window.updateTelegramMockupPreview) {
                    window.updateTelegramMockupPreview(key);
                }
            }, 350);
        }

        const activeSubTab = localStorage.getItem(`active_bank_subtab_${key}`) || 'general';

        item.innerHTML = getBankAccordionItemHTML(key, key, template, activeSubTab, {});
        if (isPaused) {
            containerPaused.appendChild(item);
        } else {
            containerActive.appendChild(item);
        }
        addDragAndDropListeners(item);

        // Add auto-grow input listeners
        item.querySelectorAll('textarea').forEach(ta => {
            ta.addEventListener('input', function() {
                autoGrowTextarea(this);
            });
        });

        // Add form change tracking listeners
        const form = item.querySelector('form');
        if (form) {
            form.addEventListener('input', () => checkAccordionFormChanges(key));
            form.addEventListener('change', () => checkAccordionFormChanges(key));
        }
    });

    if (pausedWrapper) {
        pausedWrapper.style.display = hasPaused ? 'block' : 'none';
    }
}
function toggleBankAccordion(key) {
    if (isDraggingBank) return;
    const el = document.getElementById(`bank-accordion-item-${key}`);
    if (!el) return;
    
    const isActive = el.classList.contains('active');
    
    // Collapse all items
    document.querySelectorAll('.bank-accordion-item').forEach(item => {
        item.classList.remove('active');
    });
    
    if (!isActive) {
        el.classList.add('active');
        localStorage.setItem('active_bank_accordion', key);
        
        // Restore active sub-tab choice
        const savedTab = localStorage.getItem(`active_bank_subtab_${key}`) || 'general';
        if (window.switchBankAccordionTab) {
            window.switchBankAccordionTab(key, savedTab);
        }

        // Run immediately to start growing before/during transition
        setTimeout(() => {
            el.querySelectorAll('textarea').forEach(ta => {
                autoGrowTextarea(ta);
            });
        }, 10);

        // Run again after transition is complete
        setTimeout(() => {
            el.querySelectorAll('textarea').forEach(ta => {
                autoGrowTextarea(ta);
            });
            if (window.updateTelegramMockupPreview) {
                window.updateTelegramMockupPreview(key);
            }
        }, 350);
    } else {
        localStorage.removeItem('active_bank_accordion');
    }
}
function showAddAccordionBank() {
    const pane = document.getElementById('bank-add-pane');
    if (pane) {
        pane.style.display = 'flex';
        pane.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        setTimeout(() => {
            if (window.updateTelegramMockupPreview) {
                window.updateTelegramMockupPreview('new-bank');
            }
            // Trigger autogrow on load for all textareas in the add bank pane
            pane.querySelectorAll('textarea').forEach(ta => {
                autoGrowTextarea(ta);
            });
        }, 50);
    }
}
function hideAddAccordionBank() {
    const pane = document.getElementById('bank-add-pane');
    if (pane) {
        pane.style.display = 'none';
        document.getElementById('add-bank-form').reset();
        
        // Reset custom select display
        const displayVal = document.getElementById('custom-select-value-new-bank');
        if (displayVal) displayVal.textContent = '1 скріншот';
        document.querySelectorAll('#custom-select-options-new-bank .custom-select-option').forEach(el => {
            if (el.getAttribute('data-value') === '1') el.classList.add('selected');
            else el.classList.remove('selected');
        });
        
        // Reset file label pills
        const logoLbl = document.getElementById('new-logo-filename');
        if (logoLbl) {
            logoLbl.textContent = 'Файл не обрано';
            logoLbl.classList.remove('selected');
        }
        const scrLbl = document.getElementById('new-screenshot-filename');
        if (scrLbl) {
            scrLbl.textContent = 'Файл не обрано';
            scrLbl.classList.remove('selected');
        }
        const dlLbl = document.getElementById('new-download-screenshot-filename');
        if (dlLbl) {
            dlLbl.textContent = 'Файл не обрано';
            dlLbl.classList.remove('selected');
        }
        const successLbl = document.getElementById('new-success-screenshot-filename');
        if (successLbl) {
            successLbl.textContent = 'Файл не обрано';
            successLbl.classList.remove('selected');
        }

        // Reset previews to placeholder SVGs
        const logoPreview = document.getElementById('new-bank-logo-preview');
        if (logoPreview) {
            logoPreview.style.backgroundImage = 'none';
            logoPreview.style.borderColor = 'rgba(255,255,255,0.1)';
            logoPreview.innerHTML = `
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5"/>
                    <polyline points="21 15 16 10 5 21"/>
                </svg>
            `;
        }
        const scrPreview = document.getElementById('new-bank-screenshot-preview');
        if (scrPreview) {
            scrPreview.innerHTML = `
                <div class="bank-media-preview-box placeholder" 
                     style="width: 100px; height: 150px; border-radius: 12px; border: 2px dashed rgba(255,255,255,0.12); background: rgba(255,255,255,0.02); display: flex; align-items: center; justify-content: center;">
                    <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                        <line x1="12" y1="18" x2="12.01" y2="18"/>
                    </svg>
                </div>
            `;
        }
        const dlPreview = document.getElementById('new-bank-download-screenshot-preview');
        if (dlPreview) {
            dlPreview.style.backgroundImage = 'none';
            dlPreview.style.borderColor = 'rgba(255,255,255,0.1)';
            dlPreview.innerHTML = `
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5"/>
                    <polyline points="21 15 16 10 5 21"/>
                </svg>
            `;
        }
        const successPreview = document.getElementById('new-bank-success-screenshot-preview');
        if (successPreview) {
            successPreview.style.backgroundImage = 'none';
            successPreview.style.borderColor = 'rgba(255,255,255,0.1)';
            successPreview.innerHTML = `
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                    <circle cx="12" cy="10" r="3"/>
                    <path d="M12 18H12.01"/>
                </svg>
            `;
        }

        // Reset Telegram Mockup
        const mockupImg = document.getElementById('new-telegram-mockup-image');
        if (mockupImg) {
            mockupImg.style.display = 'none';
            mockupImg.style.backgroundImage = 'none';
            const innerImg = mockupImg.querySelector('img');
            if (innerImg) {
                innerImg.src = '';
            }
        }
        const mockupKey = document.getElementById('new-telegram-mockup-bank-key');
        if (mockupKey) {
            mockupKey.textContent = 'new-bank';
        }
    }
}
async function handleCreateAccordionBank(event) {
    if (event) event.preventDefault();
    const display_name = document.getElementById('new-bank-display-name').value.trim();
    const key = document.getElementById('new-bank-key').value.trim();
    const description = document.getElementById('new-bank-desc').value.trim();
    const command = document.getElementById('new-bank-command').value.trim();
    const code_length = parseInt(document.getElementById('new-bank-code-length').value) || 4;
    const text = document.getElementById('new-bank-text').value.trim();
    const ai_rules = document.getElementById('new-bank-airules').value.trim();
    const report_template = document.getElementById('new-bank-report-tpl').value;
    const required_screenshots = parseInt(document.getElementById('new-bank-req-scr').value) || 1;
    const instruction_text = document.getElementById('new-bank-instruction-text').value.trim();
    const success_text = document.getElementById('new-bank-success-text').value.trim();

    const formData = new FormData();
    formData.append('key', key);
    formData.append('description', description);
    formData.append('display_name', display_name);
    formData.append('command', command);
    formData.append('text', text);
    formData.append('code_length', code_length);
    formData.append('ai_rules', ai_rules);
    formData.append('report_template', report_template);
    formData.append('required_screenshots', required_screenshots);
    formData.append('is_active', 1);
    formData.append('instruction_text', instruction_text);
    formData.append('success_text', success_text);

    const logoInput = document.getElementById('new-bank-logo');
    if (logoInput && logoInput.files.length > 0) {
        formData.append('logo_file', logoInput.files[0]);
    }
    const screenshotInput = document.getElementById('new-bank-screenshot');
    if (screenshotInput && screenshotInput.files.length > 0) {
        for (let i = 0; i < screenshotInput.files.length; i++) {
            formData.append('screenshot_files', screenshotInput.files[i]);
        }
    }
    const downloadScreenshotInput = document.getElementById('new-bank-download-screenshot');
    if (downloadScreenshotInput && downloadScreenshotInput.files.length > 0) {
        for (let i = 0; i < downloadScreenshotInput.files.length; i++) {
            formData.append('download_screenshot_files', downloadScreenshotInput.files[i]);
        }
    }
    const successScreenshotInput = document.getElementById('new-bank-success-screenshot');
    if (successScreenshotInput && successScreenshotInput.files.length > 0) {
        for (let i = 0; i < successScreenshotInput.files.length; i++) {
            formData.append('success_screenshot_files', successScreenshotInput.files[i]);
        }
    }

    try {
        const res = await fetch('/api/settings/templates', {
            method: 'POST',
            body: formData
        });
        if (res.ok) {
            showToast(`Банк ${key} успішно створено!`, "success");
            hideAddAccordionBank();
            localStorage.setItem('active_bank_accordion', key);
            await loadSettings();
            if (window.updateAvailableBanks) {
                await window.updateAvailableBanks();
            }
        } else {
            const err = await res.json();
            showToast("Помилка збереження: " + (err.detail || err.message), "error");
        }
    } catch (err) {
        showToast("Не вдалося створити банк", "error");
    }
}
async function saveAccordionBankSettings(event, key) {
    if (event) event.preventDefault();
    const display_name = document.getElementById(`bank-acc-display-name-${key}`).value.trim();
    const description = document.getElementById(`bank-acc-desc-${key}`).value.trim();
    const command = document.getElementById(`bank-acc-cmd-${key}`).value.trim();
    const code_length = parseInt(document.getElementById(`bank-acc-len-${key}`).value) || 4;
    const text = document.getElementById(`bank-acc-text-${key}`).value.trim();
    const ai_rules = document.getElementById(`bank-acc-airules-${key}`).value.trim();
    const report_template = document.getElementById(`bank-acc-report-tpl-${key}`).value;
    const required_screenshots = parseInt(document.getElementById(`bank-acc-req-scr-${key}`).value) || 1;
    const instruction_text = document.getElementById(`bank-acc-instruction-text-${key}`).value.trim();
    const success_text = document.getElementById(`bank-acc-success-text-${key}`).value.trim();
    const deletion_text = document.getElementById(`bank-acc-deletion-text-${key}`).value.trim();

    const isActiveInput = document.getElementById(`bank-acc-active-${key}`);
    const is_active = isActiveInput ? (isActiveInput.checked ? 1 : 0) : 1;

    const formData = new FormData();
    formData.append('key', key);
    formData.append('description', description);
    formData.append('display_name', display_name);
    formData.append('command', command);
    formData.append('text', text);
    formData.append('code_length', code_length);
    formData.append('ai_rules', ai_rules);
    formData.append('report_template', report_template);
    formData.append('required_screenshots', required_screenshots);
    formData.append('is_active', is_active);
    formData.append('instruction_text', instruction_text);
    formData.append('success_text', success_text);
    formData.append('deletion_text', deletion_text);

    const deletionReqInput = document.getElementById(`bank-acc-deletion-req-${key}`);
    const deletion_requirement = deletionReqInput ? deletionReqInput.value : 'none';
    formData.append('deletion_requirement', deletion_requirement);

    const allowRelinkInput = document.getElementById(`bank-acc-allow-relink-${key}`);
    const allow_relink = allowRelinkInput && allowRelinkInput.checked ? 1 : 0;
    formData.append('allow_relink', allow_relink);

    const relinkInstrInput = document.getElementById(`bank-acc-relink-instr-${key}`);
    if (relinkInstrInput) {
        formData.append('relink_instruction_text', relinkInstrInput.value.trim());
    }

    const downloadRemovedInput = document.getElementById(`bank-acc-download-screenshot-removed-${key}`);
    const download_removed = downloadRemovedInput ? downloadRemovedInput.value : '0';
    formData.append('download_screenshot_removed', download_removed === '1' ? '1' : '0');

    const screenshotsRemovedInput = document.getElementById(`bank-acc-screenshot-removed-${key}`);
    const screenshots_removed = screenshotsRemovedInput ? screenshotsRemovedInput.value : '0';
    formData.append('screenshots_removed', screenshots_removed === '1' ? '1' : '0');

    const successRemovedInput = document.getElementById(`bank-acc-success-screenshot-removed-${key}`);
    const success_removed = successRemovedInput ? successRemovedInput.value : '0';
    formData.append('success_screenshot_removed', success_removed === '1' ? '1' : '0');

    const deletionRemovedInput = document.getElementById(`bank-acc-deletion-screenshot-removed-${key}`);
    const deletion_removed = deletionRemovedInput ? deletionRemovedInput.value : '0';
    formData.append('deletion_screenshot_removed', deletion_removed === '1' ? '1' : '0');

    const logoInput = document.getElementById(`bank-acc-logo-${key}`);
    if (logoInput && logoInput.files.length > 0) {
        formData.append('logo_file', logoInput.files[0]);
    }
    const screenshotInput = document.getElementById(`bank-acc-screenshot-${key}`);
    if (screenshotInput && screenshotInput.files.length > 0) {
        for (let i = 0; i < screenshotInput.files.length; i++) {
            formData.append('screenshot_files', screenshotInput.files[i]);
        }
    }
    const downloadScreenshotInput = document.getElementById(`bank-acc-download-screenshot-${key}`);
    if (downloadScreenshotInput && downloadScreenshotInput.files.length > 0) {
        for (let i = 0; i < downloadScreenshotInput.files.length; i++) {
            formData.append('download_screenshot_files', downloadScreenshotInput.files[i]);
        }
    }
    const successScreenshotInput = document.getElementById(`bank-acc-success-screenshot-${key}`);
    if (successScreenshotInput && successScreenshotInput.files.length > 0) {
        for (let i = 0; i < successScreenshotInput.files.length; i++) {
            formData.append('success_screenshot_files', successScreenshotInput.files[i]);
        }
    }
    const deletionScreenshotInput = document.getElementById(`bank-acc-deletion-screenshot-${key}`);
    if (deletionScreenshotInput && deletionScreenshotInput.files.length > 0) {
        for (let i = 0; i < deletionScreenshotInput.files.length; i++) {
            formData.append('deletion_screenshot_files', deletionScreenshotInput.files[i]);
        }
    }

    try {
        const res = await fetch('/api/settings/templates', {
            method: 'POST',
            body: formData
        });
        if (res.ok) {
            showToast(`Налаштування банку ${key} збережено!`, "success");
            localStorage.setItem('active_bank_accordion', key);
            await loadSettings();
            if (window.updateAvailableBanks) {
                await window.updateAvailableBanks();
            }
        } else {
            const err = await res.json();
            showToast("Помилка збереження: " + (err.detail || err.message), "error");
        }
    } catch (err) {
        showToast("Не вдалося зберегти налаштування банку", "error");
    }
}
async function deleteAccordionBank(key) {
    if (!key) return;
    
    const confirmed = await showConfirm(`Ви впевнені, що хочете видалити банк ${key}?`, 'danger');
    if (!confirmed) return;

    try {
        const res = await fetch(`/api/settings/templates/${key}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showToast(`Банк ${key} успішно видалено.`, "success");
            localStorage.removeItem('active_bank_accordion');
            await loadSettings();
            if (window.updateAvailableBanks) {
                await window.updateAvailableBanks();
            }
        } else {
            showToast("Помилка видалення банку", "error");
        }
    } catch (err) {
        showToast("Помилка з'єднання", "error");
    }
}

window.handleFilePreview = function(input, previewId, labelId, isLogo) {
    const file = input.files[0];
    const previewEl = document.getElementById(previewId);
    const labelEl = document.getElementById(labelId);
    const resetBtnId = labelId.replace('-filename', '-reset');
    const resetBtnEl = document.getElementById(resetBtnId);
    
    if (file) {
        // Update filename label
        labelEl.textContent = file.name;
        labelEl.classList.add('selected');
        if (resetBtnEl) resetBtnEl.style.display = 'inline-flex';
        
        // Show image preview
        const reader = new FileReader();
        reader.onload = function(e) {
            if (isLogo) {
                previewEl.style.backgroundImage = `url('${e.target.result}')`;
                previewEl.style.backgroundSize = 'cover';
                previewEl.style.backgroundPosition = 'center';
                previewEl.style.backgroundRepeat = 'no-repeat';
                previewEl.style.borderStyle = 'solid';
                previewEl.style.borderWidth = '1.5px';
                previewEl.style.borderColor = 'rgba(255,255,255,0.2)';
                previewEl.style.cursor = 'pointer';
                previewEl.innerHTML = `
                    <div class="hover-zoom-overlay" style="position: absolute; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 50%;">
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
                    </div>
                `;
            } else {
                previewEl.style.width = 'auto';
                previewEl.style.height = 'auto';
                previewEl.style.backgroundImage = 'none';
                previewEl.style.borderStyle = 'solid';
                previewEl.style.borderColor = 'var(--accent-primary)';
                previewEl.style.cursor = 'pointer';
                previewEl.innerHTML = `
                    <img src="${e.target.result}" style="max-width: 150px; max-height: 150px; width: auto; height: auto; border-radius: 12px; object-fit: contain; display: block;">
                    <div class="hover-zoom-overlay" style="position: absolute; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 12px;">
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
                    </div>
                `;
            }
            
            previewEl.onclick = function() {
                openLightbox(e.target.result);
            };

            // Update Telegram mockup image if success screenshot
            if (previewId.includes('success-screenshot-preview')) {
                const mockupId = (previewId.includes('new-bank')) ? 'new-telegram-mockup-image' : previewId.replace('success-screenshot-preview', 'telegram-mockup-image');
                const mockupEl = document.getElementById(mockupId);
                if (mockupEl) {
                    mockupEl.style.display = 'block';
                    mockupEl.style.backgroundImage = `url('${e.target.result}')`;
                    const innerImg = mockupEl.querySelector('img');
                    if (innerImg) {
                        innerImg.src = e.target.result;
                        innerImg.style.display = 'block';
                    }
                }
            }
        };
        reader.readAsDataURL(file);
    } else {
        labelEl.textContent = 'Файл не обрано';
        labelEl.classList.remove('selected');
        if (resetBtnEl) resetBtnEl.style.display = 'none';
    }
};

window.resetFileSelection = function(key, type) {
    let input, preview, filename, resetBtn;
    if (key === 'new-bank') {
        input = document.getElementById(`new-bank-${type}`);
        preview = document.getElementById(`new-bank-${type}-preview`);
        filename = document.getElementById(`new-${type}-filename`);
        resetBtn = document.getElementById(`new-${type}-reset`);
    } else {
        input = document.getElementById(`bank-acc-${type}-${key}`);
        preview = document.getElementById(`${type}-preview-${key}`);
        filename = document.getElementById(`${type}-filename-${key}`);
        resetBtn = document.getElementById(`${type}-reset-${key}`);
    }

    if (!input) return;

    input.value = '';
    input.dispatchEvent(new Event('change', { bubbles: true }));
    const originalPath = input.getAttribute('data-original') || '';
    
    if (resetBtn) resetBtn.style.display = 'none';

    if (filename) {
        if (originalPath) {
            filename.textContent = 'Файл завантажено';
            filename.classList.add('selected');
        } else {
            filename.textContent = 'Файл не обрано';
            filename.classList.remove('selected');
        }
    }

    if (preview) {
        if (type === 'logo') {
            preview.style.backgroundImage = originalPath ? `url('${originalPath}')` : 'none';
            preview.style.borderStyle = originalPath ? 'solid' : 'dashed';
            preview.style.borderWidth = originalPath ? '1.5px' : '2px';
            preview.style.borderColor = originalPath ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.15)';
            preview.innerHTML = originalPath ? `
                <div class="hover-zoom-overlay" style="position: absolute; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 50%;">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                </div>
            ` : `
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                </svg>
            `;
        } else if (type === 'download-screenshot') {
            preview.style.backgroundImage = 'none';
            preview.style.cursor = originalPath ? 'pointer' : 'default';
            if (originalPath) {
                preview.style.width = 'auto';
                preview.style.height = 'auto';
                preview.style.borderStyle = 'solid';
                preview.style.borderColor = 'rgba(255,255,255,0.08)';
                preview.setAttribute('onclick', `openLightbox('${originalPath}')`);
                preview.innerHTML = `
                    <img src="${originalPath}" style="max-width: 150px; max-height: 150px; width: auto; height: auto; border-radius: 12px; object-fit: contain; display: block;">
                    <div class="hover-zoom-overlay" style="position: absolute; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 12px;">
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
                    </div>
                `;
            } else {
                preview.style.width = '100px';
                preview.style.height = '150px';
                preview.style.borderStyle = 'dashed';
                preview.style.borderColor = 'rgba(255,255,255,0.12)';
                preview.removeAttribute('onclick');
                preview.innerHTML = `
                    <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                        <path d="M12 6v8M9 11l3 3 3-3"/>
                        <line x1="9" y1="17" x2="15" y2="17"/>
                    </svg>
                `;
            }
        } else if (type === 'deletion-screenshot') {
            preview.style.backgroundImage = 'none';
            preview.style.cursor = originalPath ? 'pointer' : 'default';
            if (originalPath) {
                preview.style.width = 'auto';
                preview.style.height = 'auto';
                preview.style.borderStyle = 'solid';
                preview.style.borderColor = 'rgba(255,255,255,0.08)';
                preview.setAttribute('onclick', `openLightbox('${originalPath}')`);
                preview.innerHTML = `
                    <img src="${originalPath}" style="max-width: 150px; max-height: 150px; width: auto; height: auto; border-radius: 12px; object-fit: contain; display: block;">
                    <div class="hover-zoom-overlay" style="position: absolute; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 12px;">
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
                    </div>
                `;
            } else {
                preview.style.width = '100px';
                preview.style.height = '150px';
                preview.style.borderStyle = 'dashed';
                preview.style.borderColor = 'rgba(255,255,255,0.12)';
                preview.removeAttribute('onclick');
                preview.innerHTML = `
                    <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                        <path d="M9 7h6M10 7V6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1M7 9h10M8 9l1 9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1l1-9"/>
                    </svg>
                `;
            }
        } else if (type === 'success-screenshot') {
            preview.style.backgroundImage = 'none';
            preview.style.cursor = originalPath ? 'pointer' : 'default';
            if (originalPath) {
                preview.style.width = 'auto';
                preview.style.height = 'auto';
                preview.style.borderStyle = 'solid';
                preview.style.borderColor = 'rgba(255,255,255,0.08)';
                preview.setAttribute('onclick', `openLightbox('${originalPath}')`);
                preview.innerHTML = `
                    <img src="${originalPath}" style="max-width: 150px; max-height: 150px; width: auto; height: auto; border-radius: 12px; object-fit: contain; display: block;">
                    <div class="hover-zoom-overlay" style="position: absolute; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 12px;">
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
                    </div>
                `;
            } else {
                preview.style.width = '100px';
                preview.style.height = '150px';
                preview.style.borderStyle = 'dashed';
                preview.style.borderColor = 'rgba(255,255,255,0.12)';
                preview.removeAttribute('onclick');
                preview.innerHTML = `
                    <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                        <polyline points="9 11 11 13 15 9"/>
                    </svg>
                `;
            }

            // Also revert Telegram mockup image
            const mockupId = (key === 'new-bank') ? 'new-telegram-mockup-image' : `telegram-mockup-image-${key}`;
            const mockupEl = document.getElementById(mockupId);
            if (mockupEl) {
                if (originalPath) {
                    mockupEl.style.display = 'block';
                    mockupEl.style.backgroundImage = `url('${originalPath}')`;
                    const innerImg = mockupEl.querySelector('img');
                    if (innerImg) {
                        innerImg.src = originalPath;
                        innerImg.style.display = 'block';
                    }
                } else {
                    mockupEl.style.display = 'none';
                    mockupEl.style.backgroundImage = 'none';
                    const innerImg = mockupEl.querySelector('img');
                    if (innerImg) {
                        innerImg.src = '';
                    }
                }
            }
        } else if (type === 'screenshot') {
            preview.innerHTML = getScreenshotsHTML(originalPath);
        }
    }
};

window.cancelAccordionEdit = async function(key) {
    const btnCancel = document.getElementById(`bank-acc-cancel-btn-${key}`);
    const hasChanges = btnCancel && btnCancel.getAttribute('data-has-changes') === 'true';
    
    if (hasChanges) {
        const confirmed = await showConfirm(`Скасувати всі незбережені зміни для банку ${key}?`, 'warning');
        if (!confirmed) return;
        
        localStorage.removeItem('active_bank_accordion');
        await loadSettings();
        showToast("Зміни скасовано", "info");
    } else {
        toggleBankAccordion(key);
    }
};

window.saveTelegramMockupCustomHeight = function(el) {
    if (el && el.style && el.style.height) {
        localStorage.setItem('telegram_mockup_custom_height', el.style.height);
        document.querySelectorAll('.telegram-mockup-chat-container').forEach(c => {
            if (c !== el) {
                c.style.height = el.style.height;
            }
        });
    }
};

window.updateTelegramMockupPreview = function(key) {
    const textareaId = key === 'new-bank' ? 'new-bank-report-tpl' : `bank-acc-report-tpl-${key}`;
    const previewTextId = key === 'new-bank' ? 'new-telegram-mockup-text' : `telegram-mockup-text-${key}`;
    const textarea = document.getElementById(textareaId);
    const previewTextEl = document.getElementById(previewTextId);
    if (!textarea || !previewTextEl) return;
    
    previewTextEl.innerHTML = window.getTelegramMockupHtml(textarea.value, key);
    
    // Automatically scroll to the bottom of the chat body to reveal applicant text data
    const chatBody = previewTextEl.closest('.telegram-mockup-chat-body');
    if (chatBody) {
        chatBody.scrollTop = chatBody.scrollHeight;
    }
};

document.addEventListener('DOMContentLoaded', () => {
    const newBankKeyInput = document.getElementById('new-bank-key');
    if (newBankKeyInput) {
        newBankKeyInput.addEventListener('input', function() {
            window.updateTelegramMockupPreview('new-bank');
            
            // Update new bank mockup title dynamically
            const titleEl = document.getElementById('new-telegram-mockup-title');
            if (titleEl) {
                titleEl.textContent = this.value || 'Новий Банк';
            }
            
            // Update new bank mockup avatar dynamically
            const avatarEl = document.getElementById('new-telegram-mockup-avatar');
            if (avatarEl) {
                avatarEl.textContent = (this.value || 'NB').substring(0, 2).toUpperCase();
            }
        });
    }
    

});
window.removeSavedImage = function(key, type) {
    const hiddenRemoved = document.getElementById(`bank-acc-${type}-removed-${key}`);
    if (hiddenRemoved) {
        hiddenRemoved.value = '1';
    }
    
    const fileInput = document.getElementById(`bank-acc-${type}-${key}`);
    if (fileInput) {
        fileInput.value = '';
        fileInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
    
    const filenameEl = document.getElementById(`${type}-filename-${key}`);
    if (filenameEl) {
        filenameEl.textContent = 'Файл не обрано';
        filenameEl.classList.remove('selected');
    }
    
    const deleteBtn = document.getElementById(`${type}-delete-${key}`);
    if (deleteBtn) {
        deleteBtn.style.display = 'none';
    }
    
    const resetBtn = document.getElementById(`${type}-reset-${key}`);
    if (resetBtn) {
        resetBtn.style.display = 'none';
    }
    
    const preview = document.getElementById(`${type}-preview-${key}`);
    if (preview) {
        preview.style.width = '';
        preview.style.height = '';
        preview.style.border = '';
        preview.style.background = '';
        preview.style.cursor = '';
        preview.style.boxShadow = '';
        preview.style.overflow = '';
        preview.removeAttribute('onclick');
        
        let iconHTML = '';
        if (type === 'download-screenshot') {
            iconHTML = `
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                    <path d="M12 6v8M9 11l3 3 3-3"/>
                    <line x1="9" y1="17" x2="15" y2="17"/>
                </svg>
            `;
        } else if (type === 'deletion-screenshot') {
            iconHTML = `
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                    <path d="M9 7h6M10 7V6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1M7 9h10M8 9l1 9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1l1-9"/>
                </svg>
            `;
        } else if (type === 'success-screenshot') {
            iconHTML = `
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                    <polyline points="9 11 11 13 15 9"/>
                </svg>
            `;
            // Hide Telegram mockup image
            const mockupEl = document.getElementById(`telegram-mockup-image-${key}`);
            if (mockupEl) {
                mockupEl.style.display = 'none';
                mockupEl.style.backgroundImage = 'none';
                const innerImg = mockupEl.querySelector('img');
                if (innerImg) {
                    innerImg.src = '';
                }
            }
        } else if (type === 'screenshot') {
            iconHTML = `
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                    <line x1="9" y1="7" x2="15" y2="7"/>
                    <line x1="9" y1="11" x2="15" y2="11"/>
                    <line x1="9" y1="15" x2="13" y2="15"/>
                </svg>
            `;
        }
        
        preview.innerHTML = `
            <div class="bank-media-preview-box placeholder" 
                 style="width: 100px; height: 150px; border-radius: 12px; border: 2px dashed rgba(255,255,255,0.12); background: rgba(255,255,255,0.02); display: flex; align-items: center; justify-content: center;">
                ${iconHTML}
            </div>
        `;
    }
    
    // Mark accordion as changed
    const btnCancel = document.getElementById(`bank-acc-cancel-btn-${key}`);
    if (btnCancel) {
        btnCancel.setAttribute('data-has-changes', 'true');
        btnCancel.textContent = 'Скасувати';
    }
    if (typeof window.checkAccordionFormChanges === 'function') {
        window.checkAccordionFormChanges(key);
    }
};

window.selectDeletionTab = function(key, val) {
    const hiddenInput = document.getElementById(`bank-acc-deletion-req-${key}`);
    if (!hiddenInput) return;
    
    hiddenInput.value = val;
    
    // Update active tab styles
    const tabs = ['none', 'screenshot', 'video'];
    tabs.forEach(t => {
        const tabEl = document.getElementById(`del-tab-${key}-${t}`);
        if (tabEl) {
            if (t === val) {
                tabEl.style.color = '#fff';
                tabEl.style.background = 'rgba(255,255,255,0.08)';
                tabEl.style.borderColor = 'rgba(255,255,255,0.08)';
                tabEl.classList.add('active');
            } else {
                tabEl.style.color = 'rgba(255, 255, 255, 0.4)';
                tabEl.style.background = 'transparent';
                tabEl.style.borderColor = 'transparent';
                tabEl.classList.remove('active');
            }
        }
    });

    // Dynamically update the upload label text and input file accept property
    const labelEl = document.getElementById(`deletion-screenshot-label-${key}`);
    const inputEl = document.getElementById(`bank-acc-deletion-screenshot-${key}`);
    if (labelEl && inputEl) {
        const labelHTML = `
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
            </svg>
        `;
        if (val === 'screenshot') {
            labelEl.innerHTML = labelHTML + " Обрати скріншот";
            inputEl.accept = "image/*";
        } else if (val === 'video') {
            labelEl.innerHTML = labelHTML + " Обрати відео";
            inputEl.accept = "video/*";
        } else {
            labelEl.innerHTML = labelHTML + " Обрати скріншоти/відео";
            inputEl.accept = "image/*,video/*";
        }
    }

    // Toggle disabled overlay
    const overlayEl = document.getElementById(`deletion-disabled-overlay-${key}`);
    if (overlayEl) {
        overlayEl.style.display = val === 'none' ? 'flex' : 'none';
    }
    
    if (typeof window.checkAccordionFormChanges === 'function') {
        window.checkAccordionFormChanges(key);
    }
};

// --- Bank profile visual helpers ---
window.bankProfileDemoTemplates = {
    izibank: { display_name: 'IziBank', command: '/ЗАВАНТАЖі', code_length: 4, required_screenshots: 1, is_active: 1 },
    amobank: { display_name: 'AmoBank', command: '/AMO', code_length: 4, required_screenshots: 2, is_active: 1 },
    banklviv: { display_name: 'BankLviv', command: '/LVIV', code_length: 4, required_screenshots: 1, is_active: 1 },
    bankkd: { display_name: 'bank.kd', command: '/KD', code_length: 4, required_screenshots: 1, is_active: 1 },
    alliance: { display_name: 'Alliance', command: '/ALLIANCE', code_length: 4, required_screenshots: 1, is_active: 1 },
    novapay: { display_name: 'NovaPay', command: '/NOVAPAY', code_length: 4, required_screenshots: 1, is_active: 1 }
};
window.profileBankSelections = { main_profile: ['izibank', 'amobank'] };

try {
    const savedSelections = localStorage.getItem('bank_profile_selections');
    if (savedSelections) {
        window.profileBankSelections = JSON.parse(savedSelections);
    }
} catch (e) {
    console.error('Failed to load profile bank selections', e);
}

try {
    window.profileBankMeta = JSON.parse(localStorage.getItem('bank_profile_meta') || '{}');
} catch (e) {
    window.profileBankMeta = {};
}

window.applyProfileMeta = function(profileItem, profileId) {
    const meta = window.profileBankMeta[profileId] || {};
    const nameInput = profileItem.querySelector('.bank-profile-name-input');
    const keyInput = profileItem.querySelector('.bank-profile-key-input');
    const botUserInput = profileItem.querySelector('.bank-profile-bot-username');
    const botTokenInput = profileItem.querySelector('.bank-profile-bot-token');
    const nameEl = profileItem.querySelector('.bank-profile-name');
    const keyEl = profileItem.querySelector('.bank-profile-key');
    if (nameInput && meta.name !== undefined) nameInput.value = meta.name;
    if (keyInput && meta.key !== undefined) keyInput.value = meta.key;
    if (botUserInput && meta.bot_username !== undefined) botUserInput.value = meta.bot_username || '';
    if (botTokenInput && meta.bot_token !== undefined) botTokenInput.value = meta.bot_token || '';
    if (nameEl && meta.name !== undefined) nameEl.textContent = meta.name;
    if (keyEl && meta.key !== undefined) keyEl.textContent = meta.key;
    const isActive = meta.isActive !== undefined ? meta.isActive : true;
    profileItem.dataset.profileActive = isActive ? 'true' : 'false';
    if (meta.avatar) {
        profileItem.querySelectorAll('.bank-profile-avatar').forEach(avatar => {
            avatar.innerHTML = '';
            avatar.style.backgroundImage = "url('" + meta.avatar + "')";
            avatar.style.backgroundSize = 'cover';
            avatar.style.backgroundPosition = 'center';
            avatar.style.backgroundRepeat = 'no-repeat';
            avatar.style.border = '1.5px solid rgba(255,255,255,0.2)';
        });
    }
};

window.toggleProfileStatus = function(input) {
    const item = input && input.closest ? input.closest('.bank-profile-item') : null;
    if (!item) return;
    const profileId = item.dataset.profileId;
    const checked = input.checked;
    item.dataset.profileActive = checked ? 'true' : 'false';
    if (profileId) {
        if (!window.profileBankMeta[profileId]) window.profileBankMeta[profileId] = {};
        window.profileBankMeta[profileId].isActive = checked;
        saveBankProfileMeta();
    }
};

function saveBankProfilesOrder() {
    try {
        const order = [];
        document.querySelectorAll('#bank-profiles-list .bank-profile-item').forEach(item => {
            if (item.dataset.profileId) order.push(item.dataset.profileId);
        });
        localStorage.setItem('bank_profiles_order', JSON.stringify(order));
    } catch (e) {}
}

function saveBankProfilesOpen() {
    try {
        const openIds = [];
        document.querySelectorAll('#bank-profiles-list .bank-profile-item.active').forEach(item => {
            if (item.dataset.profileId) openIds.push(item.dataset.profileId);
        });
        sessionStorage.setItem('bank_profiles_open', JSON.stringify(openIds));
    } catch (e) {}
}

function saveBankProfileMeta() {
    try {
        localStorage.setItem('bank_profile_meta', JSON.stringify(window.profileBankMeta));
    } catch (e) {}
}

window.createBankProfile = function(profileId, name, key, isActive, isNew, botUsername, botToken, avatarDataUrl) {
    const list = document.getElementById('bank-profiles-list');
    const template = document.getElementById('bank-profile-template');
    if (!list || !template) return null;
    const clone = template.content.cloneNode(true);
    const item = clone.querySelector('.bank-profile-item');
    const nameInput = clone.querySelector('.bank-profile-name-input');
    const keyInput = clone.querySelector('.bank-profile-key-input');
    const botUserInput = clone.querySelector('.bank-profile-bot-username');
    const botTokenInput = clone.querySelector('.bank-profile-bot-token');
    const nameLabel = clone.querySelector('.bank-profile-name');
    const keyLabel = clone.querySelector('.bank-profile-key');
    if (item) {
        item.dataset.profileId = profileId;
        // Only auto-open a brand-new profile for editing;
        // loaded profiles stay collapsed by default.
        if (isNew) item.classList.add('active');
        if (isNew) item.dataset.isNew = 'true';
    }
    if (nameInput) nameInput.value = name || '';
    if (keyInput) keyInput.value = key || '';
    if (botUserInput) botUserInput.value = botUsername || '';
    if (botTokenInput) botTokenInput.value = botToken || '';
    if (nameLabel) nameLabel.textContent = name || '';
    if (keyLabel) keyLabel.textContent = key || '';
    window.profileBankMeta[profileId] = {
        name: name || '',
        key: key || profileId,
        bot_username: botUsername || '',
        bot_token: botToken || '',
        avatar: avatarDataUrl || '',
        isActive: isActive !== false
    };
    list.appendChild(clone);
    if (!window.profileBankSelections[profileId]) window.profileBankSelections[profileId] = [];
    renderProfileBankSelector(item, profileId);
    renderProfileBankAccordions(item, profileId);
    applyProfileMeta(item, profileId);
    return item;
};

window.addBankProfileVisual = function() {
    const list = document.getElementById('bank-profiles-list');
    if (!list) return;
    const count = list.querySelectorAll('.bank-profile-item').length + 1;
    const newName = 'Новий профіль ' + count;
    const newKey = 'new_profile_' + count;
    const item = window.createBankProfile(newKey, newName, newKey, true, true);
    if (item) {
        if (typeof saveProfileBankSelections === 'function') saveProfileBankSelections();
        saveBankProfileMeta();
        saveBankProfilesOrder();
        saveBankProfilesOpen();
    }
};

window.toggleBankProfile = function(header) {
    const item = header && header.closest ? header.closest('.bank-profile-item') : null;
    if (!item) return;
    item.classList.toggle('active');
    saveBankProfilesOpen();
};

window.switchBankSettingsPane = function(pane) {
    sessionStorage.setItem('active_bank_settings_pane', pane);
    const banksPane = document.getElementById('bank-banks-pane');
    const profilesPane = document.getElementById('bank-profiles-pane');
    const banksTab = document.getElementById('bank-tab-banks');
    const profilesTab = document.getElementById('bank-tab-profiles');
    if (banksPane) banksPane.style.display = pane === 'banks' ? 'block' : 'none';
    if (profilesPane) profilesPane.style.display = pane === 'profiles' ? 'block' : 'none';
    if (banksTab) banksTab.classList.toggle('active', pane === 'banks');
    if (profilesTab) profilesTab.classList.toggle('active', pane === 'profiles');
};

window.loadBankProfiles = function(profiles) {
    const list = document.getElementById('bank-profiles-list');
    if (!list) return;
    if (!profiles) profiles = window.bankProfiles;
    if (!profiles) {
        console.warn('[loadBankProfiles] no profiles provided and none cached');
        return;
    }
    console.log('[loadBankProfiles] received profiles:', Object.keys(profiles), profiles);

    window.bankProfiles = profiles;

    const sorted = Object.values(profiles).sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    let openIds = [];
    try {
        // Use sessionStorage so each tab starts with collapsed profiles,
        // while preserving manual open/close state during the same session.
        openIds = JSON.parse(sessionStorage.getItem('bank_profiles_open') || '[]');
    } catch (e) {}

    list.innerHTML = '';
    window.profileBankSelections = {};
    const templates = window.getProfileBankTemplates();

    sorted.forEach(profile => {
        const profileId = profile.profile_key;
        const isActive = profile.is_active !== 0;
        const item = window.createBankProfile(
            profileId,
            profile.name || profileId,
            profileId,
            isActive,
            false,
            profile.bot_username || '',
            profile.bot_token || '',
            profile.avatar_data_url || ''
        );
        if (openIds.includes(profileId)) item.classList.add('active');

        const selected = (profile.selected_banks || [])
            .map(b => normalizeBankKey(b))
            .filter(k => templates[k]);
        window.profileBankSelections[profileId] = selected;
    });

    window.renderAllProfileBanks();
    saveBankProfilesOrder();
    saveBankProfilesOpen();
};

function normalizeBankKey(str) {
    return String(str || '').toLowerCase().replace(/[ .\-]/g, '').replace(/bank/g, '');
}

window.getProfileBankTemplates = function() {
    const demo = window.bankProfileDemoTemplates || {};
    const backend = window.bankTemplates || {};
    const result = {};

    Object.keys(demo).forEach(k => {
        const key = normalizeBankKey(k);
        if (key) result[key] = { ...demo[k], key: k };
    });

    if (Array.isArray(backend)) {
        backend.forEach((item, i) => {
            if (!item || typeof item !== 'object') return;
            const rawKey = item.key || item.display_name || item.name || String(i);
            const key = normalizeBankKey(rawKey);
            if (key) result[key] = { ...item, key: rawKey };
        });
    } else {
        Object.keys(backend).forEach(k => {
            const key = normalizeBankKey(k);
            if (key) result[key] = { ...backend[k], key: k };
        });
    }

    return result;
};

function saveProfileBankSelections() {
    try {
        localStorage.setItem('bank_profile_selections', JSON.stringify(window.profileBankSelections));
    } catch (e) {
        console.error('Failed to save profile bank selections', e);
    }
}

window.addBankToProfile = function(profileId, bankKey) {
    if (!profileId || !bankKey) return;
    if (!window.profileBankSelections[profileId]) window.profileBankSelections[profileId] = [];
    if (!window.profileBankSelections[profileId].includes(bankKey)) {
        window.profileBankSelections[profileId].push(bankKey);
        saveProfileBankSelections();
    }
    const profileItem = document.querySelector(`.bank-profile-item[data-profile-id="${profileId}"]`);
    if (profileItem) {
        renderProfileBankSelector(profileItem, profileId);
        renderProfileBankAccordions(profileItem, profileId);
    }
};

window.removeBankFromProfile = function(profileId, bankKey) {
    if (!profileId || !bankKey || !window.profileBankSelections[profileId]) return;
    window.profileBankSelections[profileId] = window.profileBankSelections[profileId].filter(k => k !== bankKey);
    saveProfileBankSelections();
    const profileItem = document.querySelector(`.bank-profile-item[data-profile-id="${profileId}"]`);
    if (profileItem) {
        renderProfileBankSelector(profileItem, profileId);
        renderProfileBankAccordions(profileItem, profileId);
    }
};

window.renderAllProfileBanks = function() {
    document.querySelectorAll('.bank-profile-item[data-profile-id]').forEach(item => {
        const profileId = item.dataset.profileId;
        if (profileId) {
            renderProfileBankSelector(item, profileId);
            renderProfileBankAccordions(item, profileId);
            applyProfileMeta(item, profileId);
        }
    });
};

window.toggleBankInProfile = function(profileId, bankKey) {
    if (!profileId || !bankKey) return;
    const selected = window.profileBankSelections[profileId] || [];
    if (selected.includes(bankKey)) {
        window.removeBankFromProfile(profileId, bankKey);
    } else {
        window.addBankToProfile(profileId, bankKey);
    }
};

window.deleteBankProfile = async function(btn) {
    const item = btn && btn.closest ? btn.closest('.bank-profile-item') : null;
    if (!item) return;
    const profileId = item.dataset.profileId;
    if (profileId) {
        try {
            await fetch(`/api/settings/profiles/${encodeURIComponent(profileId)}`, { method: 'DELETE' });
        } catch (e) {
            console.error('Failed to delete profile on server', e);
        }
        delete window.profileBankSelections[profileId];
        delete window.profileBankMeta[profileId];
        if (typeof saveProfileBankSelections === 'function') {
            saveProfileBankSelections();
        }
        saveBankProfileMeta();
    }
    item.remove();
    saveBankProfilesOrder();
    saveBankProfilesOpen();
};

window.confirmDeleteBankProfile = async function(btn) {
    const item = btn && btn.closest ? btn.closest('.bank-profile-item') : null;
    if (!item) return;
    const nameEl = item.querySelector('.bank-profile-name');
    const name = nameEl ? nameEl.textContent : 'цей профіль';
    if (typeof showConfirm !== 'function') {
        if (confirm(`Видалити профіль "${name}"?`)) {
            deleteBankProfile(btn);
        }
        return;
    }
    const confirmed = await showConfirm(`Ви впевнені, що хочете видалити профіль "${name}"?`, 'danger');
    if (confirmed) deleteBankProfile(btn);
};

window.saveBankProfile = async function(btn) {
    const item = btn && btn.closest ? btn.closest('.bank-profile-item') : null;
    if (!item) return;
    const oldProfileId = item.dataset.profileId;
    const nameInput = item.querySelector('.bank-profile-name-input');
    const keyInput = item.querySelector('.bank-profile-key-input');
    const botUserInput = item.querySelector('.bank-profile-bot-username');
    const botTokenInput = item.querySelector('.bank-profile-bot-token');
    const nameEl = item.querySelector('.bank-profile-name');
    const keyEl = item.querySelector('.bank-profile-key');

    const newKey = (keyInput ? keyInput.value : oldProfileId).trim();
    const name = (nameInput ? nameInput.value : '').trim();
    if (!newKey) {
        showToast('Ключ профілю не може бути порожнім', 'error');
        return;
    }

    const templates = window.getProfileBankTemplates();
    const selectedBanks = (window.profileBankSelections[oldProfileId] || [])
        .map(k => (templates[k] && templates[k].key) || k);

    const profileMeta = window.profileBankMeta[oldProfileId] || {};
    const payload = {
        profile_key: newKey,
        name: name,
        selected_banks: selectedBanks,
        bot_username: (botUserInput ? botUserInput.value : '').replace(/^@/, '').trim() || null,
        bot_token: (botTokenInput ? botTokenInput.value : '').trim() || null,
        avatar_data_url: profileMeta.avatar || null,
        is_active: 1
    };

    console.log('[saveBankProfile] saving payload:', payload);
    try {
        const res = await fetch('/api/settings/profiles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        console.log('[saveBankProfile] response status:', res.status);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            console.error('[saveBankProfile] server error:', err);
            showToast('Помилка збереження: ' + (err.detail || res.status), 'error');
            return;
        }

        if (nameInput && nameEl) nameEl.textContent = name;
        if (keyInput && keyEl) keyEl.textContent = newKey;
        item.dataset.profileId = newKey;
        item.dataset.isNew = 'false';

        window.profileBankMeta[newKey] = window.profileBankMeta[newKey] || {};
        window.profileBankMeta[newKey].name = name;
        window.profileBankMeta[newKey].key = newKey;
        window.profileBankMeta[newKey].bot_username = botUserInput ? botUserInput.value : '';
        window.profileBankMeta[newKey].bot_token = botTokenInput ? botTokenInput.value : '';

        if (oldProfileId !== newKey) {
            window.profileBankSelections[newKey] = window.profileBankSelections[oldProfileId] || [];
            delete window.profileBankSelections[oldProfileId];
            window.profileBankMeta[newKey] = { ...window.profileBankMeta[oldProfileId], ...window.profileBankMeta[newKey] };
            delete window.profileBankMeta[oldProfileId];
            try {
                await fetch(`/api/settings/profiles/${encodeURIComponent(oldProfileId)}`, { method: 'DELETE' });
            } catch (e) { console.error(e); }
        }

        saveBankProfileMeta();
        saveProfileBankSelections();
        saveBankProfilesOrder();
        showToast('Профіль збережено', 'success');
        if (typeof loadSettings === 'function') await loadSettings();
    } catch (e) {
        showToast('Помилка збереження профілю: ' + e.message, 'error');
    }
};

window.renderProfileBankSelector = function(profileItem, profileId) {
    const strip = profileItem.querySelector('.bank-profile-bank-strip');
    if (!strip) return;
    const selected = window.profileBankSelections[profileId] || [];
    const templates = window.getProfileBankTemplates();
    const allKeys = Object.keys(templates);
    if (allKeys.length === 0) {
        strip.innerHTML = '<div style="padding: 10px 12px; color: var(--text-muted); font-size: 0.8rem;">Немає доступних банків</div>';
        return;
    }
    strip.innerHTML = allKeys.map(key => {
        const t = templates[key] || {};
        const name = t.display_name || key;
        const icon = getBankIcon(key, t.logo_path);
        const gradient = getBankIconGradient(key, t.logo_path);
        const isSelected = selected.includes(key) ? 'selected' : '';
        return `<div class="bank-profile-bank-option ${isSelected}" onclick="toggleBankInProfile('${profileId}', '${key}')">
            <div style="width: 24px; height: 24px; border-radius: 50%; background: ${gradient}; display: flex; align-items: center; justify-content: center; overflow: hidden; flex-shrink: 0;">${icon}</div>
            <span>${name}</span>
        </div>`;
    }).join('');
};

window.renderProfileBankAccordions = function(profileItem, profileId) {
    const container = profileItem.querySelector('.bank-profile-accordion-list');
    if (!container) return;
    const selected = window.profileBankSelections[profileId] || [];
    const templates = window.getProfileBankTemplates();
    container.innerHTML = '';
    if (selected.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 24px;">Немає банків у профілі. Додайте банки зі списку вище.</div>';
        return;
    }
    selected.forEach(bankKey => {
        const template = templates[bankKey];
        if (!template) return;
        const itemKey = profileId + '_' + bankKey;
        const item = document.createElement('div');
        item.className = 'bank-accordion-item';
        item.id = 'bank-accordion-item-' + itemKey;
        item.innerHTML = getBankAccordionItemHTML(itemKey, bankKey, template, 'general', { noActions: true, toggleHandler: 'toggleProfileBankAccordion(this)' });
        container.appendChild(item);
        item.querySelectorAll('textarea').forEach(ta => {
            ta.addEventListener('input', function() { autoGrowTextarea(this); });
            autoGrowTextarea(ta);
        });
    });
};

window.toggleProfileBankAccordion = function(header) {
    const item = header && header.closest ? header.closest('.bank-accordion-item') : null;
    if (!item) return;
    const list = item.closest('.bank-profile-accordion-list');
    const wasActive = item.classList.contains('active');
    if (list) list.querySelectorAll('.bank-accordion-item').forEach(el => el.classList.remove('active'));
    if (!wasActive) {
        item.classList.add('active');
        const key = item.id.replace('bank-accordion-item-', '');
        const savedTab = localStorage.getItem('active_bank_subtab_' + key) || 'general';
        if (window.switchBankAccordionTab) window.switchBankAccordionTab(key, savedTab);
        setTimeout(() => { item.querySelectorAll('textarea').forEach(ta => autoGrowTextarea(ta)); }, 10);
        setTimeout(() => {
            item.querySelectorAll('textarea').forEach(ta => autoGrowTextarea(ta));
            if (window.updateTelegramMockupPreview) window.updateTelegramMockupPreview(key);
        }, 350);
    }
};


