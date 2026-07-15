let isDraggingBank = false;
let dragSourceEl = null;

function autoGrowTextarea(element) {
    if (!element) return;
    element.style.height = "auto";
    element.style.height = (element.scrollHeight) + "px";
}

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
    const list = document.getElementById('bank-settings-accordion');
    if (!list) return;
    const items = list.querySelectorAll('.bank-accordion-item');
    const order = [];
    items.forEach(item => {
        const key = item.id.replace('bank-accordion-item-', '');
        order.push(key);
    });
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
        if (dragSourceEl && targetItem && dragSourceEl !== targetItem) {
            const list = document.getElementById('bank-settings-accordion');
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
function renderBankAccordion(templates, activeKey) {
    const container = document.getElementById('bank-settings-accordion');
    if (!container) return;
    container.innerHTML = '';

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
        container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 32px; background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.03); border-radius: 12px;">Немає збережених банків. Додайте перший банк за допомогою кнопки вище.</div>';
        return;
    }

    keys.forEach(key => {
        const template = templates[key];
        const item = document.createElement('div');
        item.className = 'bank-accordion-item';
        item.id = `bank-accordion-item-${key}`;
        if (key === activeKey) {
            item.classList.add('active');
            setTimeout(() => {
                item.querySelectorAll('textarea').forEach(ta => {
                    autoGrowTextarea(ta);
                });
                if (window.updateTelegramMockupPreview) {
                    window.updateTelegramMockupPreview(key);
                }
            }, 250);
        }

        item.innerHTML = `
            <div class="bank-accordion-header" onclick="toggleBankAccordion('${key}')">
                <div style="display: flex; align-items: center; gap: 14px;">
                    <div class="bank-icon-badge" style="background: ${getBankIconGradient(key, template.logo_path)};">${getBankIcon(key, template.logo_path)}</div>
                    <span class="bank-title" style="font-weight: 600; color: #fff; font-size: 1rem; letter-spacing: 0.3px;">${key}</span>
                </div>
                <div style="display: flex; align-items: center;">
                    <span class="accordion-arrow" style="font-size: 0.85rem; color: var(--text-muted); transition: transform 0.25s ease; display: inline-block;">▼</span>
                </div>
            </div>
            <div class="bank-accordion-body">
                <form onsubmit="saveAccordionBankSettings(event, '${key}')" style="display: flex; flex-direction: column; margin-top: 16px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 16px;">
                    
                    <div class="bank-settings-section-title">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--accent-primary);">
                            <circle cx="12" cy="12" r="3"></circle>
                            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l-.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                        </svg>
                        Основні параметри
                    </div>
                    <div style="display: flex; gap: 20px; align-items: center; background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.03); border-radius: 12px; padding: 12px;">
                        <!-- Logo Upload Box -->
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                            <div id="logo-preview-${key}" 
                                 class="bank-media-preview-box" 
                                 style="width: 64px; height: 64px; border-radius: 50%; border: 2px dashed rgba(255,255,255,0.15); background: ${template.logo_path ? `url('${template.logo_path}') no-repeat center/cover` : 'rgba(255,255,255,0.03)'}; display: flex; align-items: center; justify-content: center; transition: all 0.25s ease; cursor: pointer; position: relative; flex-shrink: 0;"
                                 onclick="document.getElementById('bank-acc-logo-${key}').click()">
                                ${!template.logo_path ? `
                                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                                    </svg>
                                ` : ''}
                                <div class="hover-zoom-overlay" style="position: absolute; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 50%;">
                                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                                </div>
                            </div>
                            <input type="file" id="bank-acc-logo-${key}" accept="image/*" style="display: none;" onchange="handleFilePreview(this, 'logo-preview-${key}', 'logo-filename-${key}', true)" data-original="${template.logo_path || ''}">
                            <span id="logo-filename-${key}" class="file-upload-filename-pill" style="font-size: 0.65rem; max-width: 80px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; margin-top: 2px;">Логотип</span>
                            <button type="button" id="logo-reset-${key}" class="btn-reset-file" style="display: none;" onclick="resetFileSelection('${key}', 'logo')">Відхилити</button>
                        </div>

                        <!-- Technical Inputs Grid -->
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; flex-grow: 1;">
                            <div class="form-group" style="margin: 0;">
                                <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px;">Команда в Telegram</label>
                                <input type="text" id="bank-acc-cmd-${key}" value="${template.command || ''}" required class="form-control" style="width: 100%;">
                            </div>
                            <div class="form-group" style="margin: 0;">
                                <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px;">Довжина коду (цифр)</label>
                                <input type="number" id="bank-acc-len-${key}" value="${template.code_length || 4}" required min="1" max="10" class="form-control" style="width: 100%;">
                            </div>
                            <div class="form-group" style="margin: 0;">
                                <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px;">Необхідно скріншотів</label>
                                <div class="custom-select-wrapper" id="custom-select-wrapper-${key}">
                                    <div class="custom-select-trigger" onclick="toggleCustomSelectDropdown('${key}', event); event.stopPropagation();">
                                        <span id="custom-select-value-${key}">${template.required_screenshots || 1} скріншот${(template.required_screenshots || 1) == 1 ? '' : (template.required_screenshots || 1) < 5 ? 'и' : 'ів'}</span>
                                        <svg class="custom-select-arrow" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5">
                                            <polyline points="6 9 12 15 18 9"></polyline>
                                        </svg>
                                    </div>
                                    <div class="custom-select-options" id="custom-select-options-${key}">
                                        <div class="custom-select-option ${template.required_screenshots == 1 ? 'selected' : ''}" data-value="1" onclick="selectRequiredScreenshotsOption('${key}', 1, event)">1 скріншот</div>
                                        <div class="custom-select-option ${template.required_screenshots == 2 ? 'selected' : ''}" data-value="2" onclick="selectRequiredScreenshotsOption('${key}', 2, event)">2 скріншоти</div>
                                        <div class="custom-select-option ${template.required_screenshots == 3 ? 'selected' : ''}" data-value="3" onclick="selectRequiredScreenshotsOption('${key}', 3, event)">3 скріншоти</div>
                                        <div class="custom-select-option ${template.required_screenshots == 4 ? 'selected' : ''}" data-value="4" onclick="selectRequiredScreenshotsOption('${key}', 4, event)">4 скріншоти</div>
                                        <div class="custom-select-option ${template.required_screenshots == 5 ? 'selected' : ''}" data-value="5" onclick="selectRequiredScreenshotsOption('${key}', 5, event)">5 скріншотів</div>
                                    </div>
                                    <input type="hidden" id="bank-acc-req-scr-${key}" value="${template.required_screenshots || 1}">
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="bank-settings-section-title" style="margin-top: 12px;">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--accent-primary);">
                            <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"></path>
                            <path d="M8 12h8"></path>
                            <path d="M12 8v8"></path>
                        </svg>
                        Медіа-інструкції для клієнта
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 10px;">
                        <!-- Download Screenshot Card -->
                        <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 14px; justify-content: space-between; position: relative; overflow: hidden;">
                            <div style="display: flex; flex-direction: column; align-items: center; gap: 6px; width: 100%;">
                                <span style="font-size: 0.8rem; font-weight: 600; color: rgba(255,255,255,0.5); letter-spacing: 0.5px; text-transform: uppercase;">Який банк завантажити</span>
                                <span id="download-screenshot-filename-${key}" class="file-upload-filename-pill" style="max-width: 100%; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-size: 0.75rem; color: var(--accent-primary);">Файл не обрано</span>
                            </div>
                            
                            <div id="download-screenshot-preview-${key}" 
                                 class="bank-media-preview-box" 
                                 style="width: ${template.download_screenshot_path ? 'auto' : '100px'}; height: ${template.download_screenshot_path ? 'auto' : '150px'}; border-radius: 12px; border: ${template.download_screenshot_path ? '1px solid rgba(255,255,255,0.08)' : '2px dashed rgba(255,255,255,0.12)'}; background: ${template.download_screenshot_path ? 'transparent' : 'rgba(255,255,255,0.02)'}; display: flex; align-items: center; justify-content: center; transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); cursor: ${template.download_screenshot_path ? 'pointer' : 'default'}; position: relative; box-shadow: 0 4px 12px rgba(0,0,0,0.2); flex-shrink: 0; overflow: hidden;"
                                 ${template.download_screenshot_path ? `onclick="openLightbox('${template.download_screenshot_path}')"` : ''}>
                                ${!template.download_screenshot_path ? `
                                    <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                                        <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                                        <line x1="12" y1="18" x2="12.01" y2="18"/>
                                    </svg>
                                ` : `
                                    <img src="${template.download_screenshot_path}" style="max-width: 150px; max-height: 150px; width: auto; height: auto; border-radius: 12px; object-fit: contain; display: block;">
                                    <div class="hover-zoom-overlay" style="position: absolute; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 12px;">
                                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
                                    </div>
                                `}
                            </div>

                            <div style="width: 100%; display: flex; flex-direction: column; gap: 8px; align-items: center;">
                                <div class="custom-file-upload-wrapper" style="width: 100%; max-width: 200px;">
                                    <label for="bank-acc-download-screenshot-${key}" class="custom-file-upload-label" style="justify-content: center; width: 100%; padding: 8px 14px;">
                                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                                        </svg>
                                        Обрати скріншот
                                    </label>
                                    <input type="file" id="bank-acc-download-screenshot-${key}" accept="image/*" style="display: none;" onchange="handleFilePreview(this, 'download-screenshot-preview-${key}', 'download-screenshot-filename-${key}', false)" data-original="${template.download_screenshot_path || ''}">
                                </div>
                                <button type="button" id="download-screenshot-reset-${key}" class="btn-reset-file" style="display: none;" onclick="resetFileSelection('${key}', 'download-screenshot')">Відхилити</button>
                            </div>
                        </div>

                        <!-- Instruction Screenshot Card -->
                        <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 14px; justify-content: space-between; position: relative; overflow: hidden; min-height: 245px;">
                            <div style="display: flex; flex-direction: column; align-items: center; gap: 6px; width: 100%;">
                                <span style="font-size: 0.8rem; font-weight: 600; color: rgba(255,255,255,0.5); letter-spacing: 0.5px; text-transform: uppercase;">Скріншот-інструкція як проходити</span>
                                <span id="screenshot-filename-${key}" class="file-upload-filename-pill" style="max-width: 100%; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-size: 0.75rem; color: var(--accent-primary);">Файл не обрано</span>
                            </div>
                            
                            <div id="screenshot-preview-${key}" 
                                 style="display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; align-items: center; width: 100%; min-height: 120px; flex-shrink: 0;">
                                ${getScreenshotsHTML(template.screenshot_path)}
                            </div>

                            <div style="width: 100%; display: flex; flex-direction: column; gap: 8px; align-items: center;">
                                <div class="custom-file-upload-wrapper" style="width: 100%; max-width: 200px;">
                                    <label for="bank-acc-screenshot-${key}" class="custom-file-upload-label" style="justify-content: center; width: 100%; padding: 8px 14px;">
                                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                                        </svg>
                                        Обрати скріншоти
                                    </label>
                                    <input type="file" id="bank-acc-screenshot-${key}" accept="image/*" multiple style="display: none;" onchange="handleMultipleFilePreview(this, 'screenshot-preview-${key}', 'screenshot-filename-${key}')" data-original="${template.screenshot_path || ''}">
                                </div>
                                <button type="button" id="screenshot-reset-${key}" class="btn-reset-file" style="display: none;" onclick="resetFileSelection('${key}', 'screenshot')">Відхилити</button>
                            </div>
                        </div>

                        <!-- Success Screenshot Card -->
                        <div style="background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 14px; justify-content: space-between; position: relative; overflow: hidden; min-height: 245px;">
                            <div style="display: flex; flex-direction: column; align-items: center; gap: 6px; width: 100%;">
                                <span style="font-size: 0.8rem; font-weight: 600; color: rgba(255,255,255,0.5); letter-spacing: 0.5px; text-transform: uppercase;">Зразок успішного екрану</span>
                                <span id="success-screenshot-filename-${key}" class="file-upload-filename-pill" style="max-width: 100%; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-size: 0.75rem; color: var(--accent-primary);">Файл не обрано</span>
                            </div>
                            
                            <div id="success-screenshot-preview-${key}" 
                                 class="bank-media-preview-box" 
                                 style="width: ${template.success_screenshot_path ? 'auto' : '100px'}; height: ${template.success_screenshot_path ? 'auto' : '150px'}; border-radius: 12px; border: ${template.success_screenshot_path ? '1px solid rgba(255,255,255,0.08)' : '2px dashed rgba(255,255,255,0.12)'}; background: ${template.success_screenshot_path ? 'transparent' : 'rgba(255,255,255,0.02)'}; display: flex; align-items: center; justify-content: center; transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); cursor: ${template.success_screenshot_path ? 'pointer' : 'default'}; position: relative; box-shadow: 0 4px 12px rgba(0,0,0,0.2); flex-shrink: 0; overflow: hidden;"
                                 ${template.success_screenshot_path ? `onclick="openLightbox('${template.success_screenshot_path}')"` : ''}>
                                ${!template.success_screenshot_path ? `
                                    <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                                        <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
                                        <circle cx="12" cy="10" r="3"/>
                                        <path d="M12 18H12.01"/>
                                    </svg>
                                ` : `
                                    <img src="${template.success_screenshot_path}" style="max-width: 150px; max-height: 150px; width: auto; height: auto; border-radius: 12px; object-fit: contain; display: block;">
                                    <div class="hover-zoom-overlay" style="position: absolute; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 12px;">
                                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
                                    </div>
                                `}
                            </div>

                            <div style="width: 100%; display: flex; flex-direction: column; gap: 8px; align-items: center;">
                                <div class="custom-file-upload-wrapper" style="width: 100%; max-width: 200px;">
                                    <label for="bank-acc-success-screenshot-${key}" class="custom-file-upload-label" style="justify-content: center; width: 100%; padding: 8px 14px;">
                                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                                        </svg>
                                        Обрати файл
                                    </label>
                                    <input type="file" id="bank-acc-success-screenshot-${key}" accept="image/*" style="display: none;" onchange="handleFilePreview(this, 'success-screenshot-preview-${key}', 'success-screenshot-filename-${key}', false)" data-original="${template.success_screenshot_path || ''}">
                                </div>
                                <button type="button" id="success-screenshot-reset-${key}" class="btn-reset-file" style="display: none;" onclick="resetFileSelection('${key}', 'success-screenshot')">Відхилити</button>
                            </div>
                        </div>
                    </div>

                    <!-- Verifier Report Template and Mockup Side-by-Side -->
                    <div style="display: grid; grid-template-columns: 1fr 340px; gap: 20px; margin-top: 20px; align-items: start; background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.04); border-radius: 14px; padding: 18px;">
                        <div style="display: flex; flex-direction: column; gap: 10px; width: 100%;">
                            <div class="bank-settings-section-title" style="margin: 0; font-size: 0.85rem; font-weight: 600; color: rgba(255,255,255,0.7); display: flex; align-items: center; gap: 8px; min-height: 20px;">
                                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--accent-primary);">
                                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                    <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                                </svg>
                                Шаблон повідомлення для верифікатора
                            </div>
                            <textarea id="bank-acc-report-tpl-${key}" class="form-control auto-grow-textarea" rows="7" style="width: 100%; font-family: monospace; font-size: 0.78rem; line-height: 1.4; resize: vertical;" oninput="updateTelegramMockupPreview('${key}')" placeholder="Шаблон звіту...">${template.report_template || `{pib}\n{dob}\n{ipn}\n{phone}\n\nДроп - @{username}\n\nLine {line_id} Return: {line_phone} | {bank}\n\n{code}`}</textarea>
                            <span style="font-size: 0.72rem; color: rgba(255,255,255,0.4); line-height: 1.3;">
                                Ви можете редагувати цей текст. Доступні змінні для підстановки:
                                <br>
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px; display: inline-block; margin-top: 4px;">{pib}</code>, 
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px;">{dob}</code>, 
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px;">{ipn}</code>, 
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px;">{phone}</code>, 
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px;">{username}</code>, 
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px;">{line}</code>, 
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px;">{line_id}</code>, 
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px;">{line_phone}</code>, 
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px;">{code}</code>, 
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px;">{card}</code>, 
                                <code style="color: var(--accent-primary); background: rgba(255,255,255,0.03); padding: 1px 4px; border-radius: 4px;">{bank}</code>
                            </span>
                        </div>

                        <!-- Telegram Mockup Bubble -->
                        <div class="telegram-mockup-wrapper" style="width: 100%; height: 100%; display: flex; flex-direction: column; text-align: left; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                            <div style="font-size: 0.75rem; font-weight: 600; color: rgba(255,255,255,0.3); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; display: flex; align-items: center; gap: 4px; min-height: 20px;">
                                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
                                Прев'ю в Telegram
                            </div>
                            
                            <div class="telegram-message-bubble" style="background: #182533; border-radius: 10px; padding: 10px 12px; width: 100%; max-width: 320px; box-shadow: 0 1px 2px rgba(0,0,0,0.3); position: relative; display: flex; flex-direction: column; gap: 8px;">
                                <div id="telegram-mockup-image-${key}" style="width: 100%; height: 150px; border-radius: 6px; background: ${template.success_screenshot_path ? `url('${template.success_screenshot_path}')` : 'rgba(255,255,255,0.03)'} no-repeat center/cover; display: ${template.success_screenshot_path ? 'block' : 'none'}; border: 1px solid rgba(255,255,255,0.06);"></div>
                                <div id="telegram-mockup-text-${key}" style="font-size: 0.82rem; color: #fff; line-height: 1.4; white-space: pre-line;"></div>
                                <div style="font-size: 0.65rem; color: #7f91a4; align-self: flex-end; margin-top: -4px;">14:38 ✓✓</div>
                            </div>
                        </div>
                    </div>

                    <div class="bank-settings-section-title" style="margin-top: 8px;">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--accent-primary);">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                        </svg>
                        Інструкції та правила ШІ
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 16px;">
                        <div class="form-group" style="margin: 0;">
                            <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px;">Текст інструкції для клієнта</label>
                            <textarea id="bank-acc-text-${key}" required class="form-control auto-grow-textarea" rows="2" style="width: 100%; font-family: inherit;">${template.text || ''}</textarea>
                        </div>
                        <div class="form-group" style="margin: 0;">
                            <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px;">Специфічні правила ШІ для банку</label>
                            <textarea id="bank-acc-airules-${key}" class="form-control auto-grow-textarea" rows="3" style="width: 100%; font-family: inherit;" placeholder="Наприклад: Перевіряти ліміти...">${template.ai_rules || ''}</textarea>
                        </div>
                        <div class="form-group" style="margin: 0;">
                            <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px;">Опис вигляду банку для ШІ (як виглядає додаток, кольори)</label>
                            <textarea id="bank-acc-desc-${key}" class="form-control auto-grow-textarea" rows="2" style="width: 100%; font-family: inherit;" placeholder="Наприклад: Додаток має темну тему, помаранчеві кольори, скляні плашки...">${template.description || ''}</textarea>
                        </div>
                    </div>

                    <div style="display: flex; justify-content: space-between; margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 16px;">
                        <div>
                            <button type="button" class="btn btn-danger btn-sm" onclick="deleteAccordionBank('${key}')" style="padding: 8px 16px; font-size: 0.8rem;">Видалити банк</button>
                        </div>
                        <div style="display: flex; gap: 12px;">
                            <button type="button" class="btn btn-secondary btn-sm" onclick="cancelAccordionEdit('${key}')" style="padding: 8px 16px; font-size: 0.8rem; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: rgba(255,255,255,0.7);">Скасувати</button>
                            <button type="submit" class="btn btn-primary" style="padding: 8px 20px; font-weight: 600; font-size: 0.85rem;">Зберегти зміни</button>
                        </div>
                    </div>
                </form>
            </div>
        `;
        container.appendChild(item);
        addDragAndDropListeners(item);

        // Add auto-grow input listeners
        item.querySelectorAll('textarea').forEach(ta => {
            ta.addEventListener('input', function() {
                autoGrowTextarea(this);
            });
        });
    });
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
        setTimeout(() => {
            el.querySelectorAll('textarea').forEach(ta => {
                autoGrowTextarea(ta);
            });
            if (window.updateTelegramMockupPreview) {
                window.updateTelegramMockupPreview(key);
            }
        }, 150);
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
        }
        const mockupKey = document.getElementById('new-telegram-mockup-bank-key');
        if (mockupKey) {
            mockupKey.textContent = 'new-bank';
        }
    }
}
async function handleCreateAccordionBank(event) {
    if (event) event.preventDefault();
    const key = document.getElementById('new-bank-key').value.trim();
    const description = document.getElementById('new-bank-desc').value.trim();
    const command = document.getElementById('new-bank-command').value.trim();
    const code_length = parseInt(document.getElementById('new-bank-code-length').value) || 4;
    const text = document.getElementById('new-bank-text').value.trim();
    const ai_rules = document.getElementById('new-bank-airules').value.trim();
    const report_template = document.getElementById('new-bank-report-tpl').value;
    const required_screenshots = parseInt(document.getElementById('new-bank-req-scr').value) || 1;

    const formData = new FormData();
    formData.append('key', key);
    formData.append('description', description);
    formData.append('command', command);
    formData.append('text', text);
    formData.append('code_length', code_length);
    formData.append('ai_rules', ai_rules);
    formData.append('report_template', report_template);
    formData.append('required_screenshots', required_screenshots);

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
        formData.append('download_screenshot_file', downloadScreenshotInput.files[0]);
    }
    const successScreenshotInput = document.getElementById('new-bank-success-screenshot');
    if (successScreenshotInput && successScreenshotInput.files.length > 0) {
        formData.append('success_screenshot_file', successScreenshotInput.files[0]);
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
    const description = document.getElementById(`bank-acc-desc-${key}`).value.trim();
    const command = document.getElementById(`bank-acc-cmd-${key}`).value.trim();
    const code_length = parseInt(document.getElementById(`bank-acc-len-${key}`).value) || 4;
    const text = document.getElementById(`bank-acc-text-${key}`).value.trim();
    const ai_rules = document.getElementById(`bank-acc-airules-${key}`).value.trim();
    const report_template = document.getElementById(`bank-acc-report-tpl-${key}`).value;
    const required_screenshots = parseInt(document.getElementById(`bank-acc-req-scr-${key}`).value) || 1;

    const formData = new FormData();
    formData.append('key', key);
    formData.append('description', description);
    formData.append('command', command);
    formData.append('text', text);
    formData.append('code_length', code_length);
    formData.append('ai_rules', ai_rules);
    formData.append('report_template', report_template);
    formData.append('required_screenshots', required_screenshots);

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
        formData.append('download_screenshot_file', downloadScreenshotInput.files[0]);
    }
    const successScreenshotInput = document.getElementById(`bank-acc-success-screenshot-${key}`);
    if (successScreenshotInput && successScreenshotInput.files.length > 0) {
        formData.append('success_screenshot_file', successScreenshotInput.files[0]);
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
                previewEl.style.borderColor = 'var(--accent-primary)';
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
    const originalPath = input.getAttribute('data-original') || '';
    
    if (resetBtn) resetBtn.style.display = 'none';

    if (filename) {
        filename.textContent = 'Файл не обрано';
        filename.classList.remove('selected');
    }

    if (preview) {
        if (type === 'logo') {
            preview.style.backgroundImage = originalPath ? `url('${originalPath}')` : 'none';
            preview.style.borderColor = originalPath ? 'transparent' : 'rgba(255,255,255,0.15)';
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
                        <line x1="12" y1="18" x2="12.01" y2="18"/>
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
                        <circle cx="12" cy="10" r="3"/>
                        <path d="M12 18H12.01"/>
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
                } else {
                    mockupEl.style.display = 'none';
                    mockupEl.style.backgroundImage = 'none';
                }
            }
        } else if (type === 'screenshot') {
            preview.innerHTML = getScreenshotsHTML(originalPath);
        }
    }
};

window.cancelAccordionEdit = async function(key) {
    const confirmed = await showConfirm(`Скасувати всі незбережені зміни для банку ${key}?`, 'warning');
    if (!confirmed) return;
    
    localStorage.removeItem('active_bank_accordion');
    await loadSettings();
    showToast("Зміни скасовано", "info");
};

window.updateTelegramMockupPreview = function(key) {
    const textareaId = key === 'new-bank' ? 'new-bank-report-tpl' : `bank-acc-report-tpl-${key}`;
    const previewTextId = key === 'new-bank' ? 'new-telegram-mockup-text' : `telegram-mockup-text-${key}`;
    const textarea = document.getElementById(textareaId);
    const previewTextEl = document.getElementById(previewTextId);
    if (!textarea || !previewTextEl) return;
    
    let text = textarea.value;
    
    // Replace placeholders with mock data
    const replacements = {
        "{pib}": "<b>Горбачевська Софія Антонівна</b>",
        "{dob}": "29.01.2007",
        "{ipn}": "3911006569",
        "{phone}": "+380 (97) 134 46 82",
        "{username}": "fantom1529",
        "{line}": `Line 17 Return: 380950369906 | ${key === 'new-bank' ? (document.getElementById('new-bank-key')?.value?.trim() || 'new-bank') : key}`,
        "{line_id}": "17",
        "{line_phone}": "380950369906",
        "{code}": "<b>1234</b>",
        "{card}": "5457082534505537",
        "{bank}": key === 'new-bank' ? (document.getElementById('new-bank-key')?.value?.trim() || 'new-bank') : key
    };
    
    for (let place in replacements) {
        text = text.replaceAll(place, replacements[place]);
    }
    
    previewTextEl.innerHTML = text;
};

document.addEventListener('DOMContentLoaded', () => {
    const newBankKeyInput = document.getElementById('new-bank-key');
    if (newBankKeyInput) {
        newBankKeyInput.addEventListener('input', function() {
            window.updateTelegramMockupPreview('new-bank');
        });
    }
});
