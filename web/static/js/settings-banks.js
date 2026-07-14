let isDraggingBank = false;
let dragSourceEl = null;

function getBankIcon(key) {
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
function getBankIconGradient(key) {
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
        if (key === activeKey) item.classList.add('active');

        item.innerHTML = `
            <div class="bank-accordion-header" onclick="toggleBankAccordion('${key}')">
                <div style="display: flex; align-items: center; gap: 14px;">
                    <div class="bank-icon-badge" style="background: ${getBankIconGradient(key)};">${getBankIcon(key)}</div>
                    <span class="bank-title" style="font-weight: 600; color: #fff; font-size: 1rem; letter-spacing: 0.3px;">${key}</span>
                </div>
                <div style="display: flex; align-items: center;">
                    <span class="accordion-arrow" style="font-size: 0.85rem; color: var(--text-muted); transition: transform 0.25s ease; display: inline-block;">▼</span>
                </div>
            </div>
            <div class="bank-accordion-body">
                <form onsubmit="saveAccordionBankSettings(event, '${key}')" style="display: flex; flex-direction: column; gap: 16px; margin-top: 16px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 16px;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                        <div class="form-group" style="margin: 0;">
                            <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px;">Команда в Telegram</label>
                            <input type="text" id="bank-acc-cmd-${key}" value="${template.command || ''}" required class="form-control" style="width: 100%;">
                        </div>
                        <div class="form-group" style="margin: 0;">
                            <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px;">Довжина SMS-коду (цифр)</label>
                            <input type="number" id="bank-acc-len-${key}" value="${template.code_length || 4}" required min="1" max="10" class="form-control" style="width: 100%;">
                        </div>
                    </div>
                    <div class="form-group" style="margin: 0;">
                        <label class="form-label" style="font-size: 0.8rem; margin-bottom: 6px;">Текст інструкції для клієнта</label>
                        <textarea id="bank-acc-text-${key}" required class="form-control" rows="3" style="width: 100%; resize: vertical; min-height: 80px; font-family: inherit;">${template.text || ''}</textarea>
                    </div>
                    <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 4px;">
                        <button type="button" class="btn btn-danger btn-sm" onclick="deleteAccordionBank('${key}')" style="padding: 8px 16px; font-size: 0.8rem;">Видалити банк</button>
                        <button type="submit" class="btn btn-primary" style="padding: 8px 20px; font-weight: 600; font-size: 0.85rem;">Зберегти зміни</button>
                    </div>
                </form>
            </div>
        `;
        container.appendChild(item);
        addDragAndDropListeners(item);
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
    } else {
        localStorage.removeItem('active_bank_accordion');
    }
}
function showAddAccordionBank() {
    const pane = document.getElementById('bank-add-pane');
    if (pane) {
        pane.style.display = 'flex';
        pane.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}
function hideAddAccordionBank() {
    const pane = document.getElementById('bank-add-pane');
    if (pane) {
        pane.style.display = 'none';
        document.getElementById('add-bank-form').reset();
    }
}
async function handleCreateAccordionBank(event) {
    if (event) event.preventDefault();
    const key = document.getElementById('new-bank-key').value.trim();
    const command = document.getElementById('new-bank-command').value.trim();
    const code_length = parseInt(document.getElementById('new-bank-code-length').value) || 4;
    const text = document.getElementById('new-bank-text').value.trim();

    try {
        const res = await fetch('/api/settings/templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, command, text, code_length })
        });
        if (res.ok) {
            showToast(`Банк ${key} успішно створено!`, "success");
            hideAddAccordionBank();
            localStorage.setItem('active_bank_accordion', key);
            await loadSettings();
        } else {
            const err = await res.json();
            showToast("Помилка збереження: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Не вдалося створити банк", "error");
    }
}
async function saveAccordionBankSettings(event, key) {
    if (event) event.preventDefault();
    const command = document.getElementById(`bank-acc-cmd-${key}`).value.trim();
    const code_length = parseInt(document.getElementById(`bank-acc-len-${key}`).value) || 4;
    const text = document.getElementById(`bank-acc-text-${key}`).value.trim();

    try {
        const res = await fetch('/api/settings/templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, command, text, code_length })
        });
        if (res.ok) {
            showToast(`Налаштування банку ${key} збережено!`, "success");
            localStorage.setItem('active_bank_accordion', key);
            await loadSettings();
        } else {
            const err = await res.json();
            showToast("Помилка збереження: " + err.detail, "error");
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
