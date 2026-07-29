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

function stripMessageQuotes(text) {
    return (text || '').toString().trim().replace(/^[\s'"`"«»“”‘’]+|[\s'"`"«»“”‘’]+$/g, '');
}

// Save the active chat scroll position before page reload so it can be restored afterwards.
window.addEventListener('beforeunload', function() {
    if (selectedChatClientId) {
        const container = document.getElementById('chat-window-body-container');
        if (container) {
            try {
                sessionStorage.setItem('chat_scroll_' + selectedChatClientId, container.scrollTop);
            } catch (e) {}
        }
    }
});

// Mark photo wrappers/galleries as loaded once their images load so blur/placeholder is hidden.
window.addEventListener('load', function(e) {
    const target = e.target;
    if (target && target.classList && (target.classList.contains('chat-msg-img') || target.classList.contains('chat-msg-gallery-img'))) {
        const wrapper = target.closest('.chat-msg-photo-wrapper, .chat-msg-gallery');
        if (wrapper) wrapper.classList.add('loaded');
    }
}, true);

let lightboxPhotos = [];
let lightboxIndex = 0;

function updateLightboxNavUI() {
    const prevBtn = document.getElementById('lightbox-prev');
    const nextBtn = document.getElementById('lightbox-next');
    const counter = document.getElementById('lightbox-counter');
    const hasMany = lightboxPhotos.length > 1;
    if (prevBtn) prevBtn.style.display = hasMany ? 'flex' : 'none';
    if (nextBtn) nextBtn.style.display = hasMany ? 'flex' : 'none';
    if (counter) {
        counter.style.display = hasMany ? 'block' : 'none';
        counter.textContent = `${lightboxIndex + 1} / ${lightboxPhotos.length}`;
    }
}

window.openLightbox = function(src, photos, index) {
    console.log('[Lightbox] openLightbox called with src:', src);
    if (!src) return;
    const overlay = document.getElementById('image-lightbox');
    const img = document.getElementById('lightbox-img');
    const video = document.getElementById('lightbox-video');
    if (!overlay) {
        console.error('[Lightbox] overlay element not found');
        return;
    }

    lightboxPhotos = (Array.isArray(photos) && photos.length > 0) ? photos.slice() : [src];
    lightboxIndex = Math.min(Math.max(index || 0, 0), lightboxPhotos.length - 1);

    const isVideo = String(src).toLowerCase().endsWith('.mp4') ||
                    String(src).toLowerCase().endsWith('.mov') ||
                    String(src).toLowerCase().endsWith('.webm') ||
                    String(src).startsWith('data:video/');

    if (isVideo) {
        if (img) img.style.display = 'none';
        if (video) {
            video.src = src;
            video.style.display = 'block';
            video.play().catch(() => {});
        }
    } else {
        if (video) {
            try { video.pause(); } catch(e) {}
            video.style.display = 'none';
        }
        if (img) {
            img.src = src;
            img.style.display = 'block';
            img.onerror = function(e) { console.error('[Lightbox] image failed to load', e); };
        }
    }

    overlay.classList.add('active');
    updateLightboxNavUI();
};

window.lightboxNav = function(dir) {
    if (!lightboxPhotos || lightboxPhotos.length < 2) return;
    lightboxIndex = (lightboxIndex + dir + lightboxPhotos.length) % lightboxPhotos.length;
    const src = lightboxPhotos[lightboxIndex];
    const img = document.getElementById('lightbox-img');
    const video = document.getElementById('lightbox-video');
    if (video) {
        try { video.pause(); } catch(e) {}
        video.style.display = 'none';
    }
    if (img) {
        img.style.display = 'block';
        img.src = src;
    }
    updateLightboxNavUI();
};

window.closeLightbox = function(source) {
    console.log('[Lightbox] closeLightbox called, source:', source || 'unknown');
    const overlay = document.getElementById('image-lightbox');
    const video = document.getElementById('lightbox-video');
    if (video) {
        try { video.pause(); } catch(e) {}
    }
    if (overlay) {
        overlay.classList.remove('active');
    }
    lightboxPhotos = [];
    lightboxIndex = 0;
    updateLightboxNavUI();
};

// Keyboard navigation for the lightbox gallery: arrows switch photos, Esc closes.
document.addEventListener('keydown', function(e) {
    const overlay = document.getElementById('image-lightbox');
    if (!overlay || !overlay.classList.contains('active')) return;
    if (e.key === 'Escape') {
        e.preventDefault();
        window.closeLightbox('keyboard');
    } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        window.lightboxNav(-1);
    } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        window.lightboxNav(1);
    }
});

// Global Capture-Phase Failsafe Click Handler for Lightbox Previews
document.addEventListener('click', function(e) {
    const target = e.target;
    if (!target || !target.closest) return;
    let img = null;
    const moreCell = target.closest('.chat-msg-gallery-more-cell');
    if (moreCell) {
        img = moreCell.querySelector('img.chat-msg-gallery-img');
    } else {
        img = target.closest('.chat-msg-img, .chat-msg-gallery-img, .chat-reply-thumb, .chat-msg-quote-thumb');
    }
    const src = img ? img.src : (target.tagName === 'IMG' && target.src && target.src.includes('/api/photos/') ? target.src : null);
    if (src) {
        console.log('[Lightbox] Click detected on photo, src:', src);
        e.preventDefault();
        e.stopPropagation();
        if (typeof window.openLightbox === 'function') {
            let photos = null;
            let index = 0;
            const gallery = img && img.closest ? img.closest('.chat-msg-gallery') : null;
            if (gallery) {
                const allImgs = Array.from(gallery.querySelectorAll('.chat-msg-gallery-img'));
                if (allImgs.length > 1) {
                    photos = allImgs.map(i => i.src);
                    index = Math.max(0, allImgs.indexOf(img));
                }
            }
            window.openLightbox(src, photos, index);
        } else {
            console.error('[Lightbox] window.openLightbox is not a function');
        }
    }
}, true);

window.handlePhotoError = function(img) {
    if (!img) return;
    img._retryCount = (img._retryCount || 0) + 1;
    if (img._retryCount > 8) return;
    const delay = Math.min(img._retryCount * 700, 3000);
    setTimeout(() => {
        try {
            const url = new URL(img.src, window.location.origin);
            url.searchParams.set('_r', Date.now());
            img.src = url.toString();

            const wrapper = img.closest('.chat-msg-photo-wrapper');
            if (wrapper) {
                const blurBg = wrapper.querySelector('.chat-msg-photo-blur-bg');
                if (blurBg) {
                    blurBg.style.backgroundImage = `url("${url.toString()}")`;
                }
            }
        } catch (e) {}
    }, delay);
};

// --- Telegram-style adaptive album mosaic engine ---
// Computes a pixel-perfect mosaic (absolutely positioned tiles) from the real
// aspect ratios of the photos, mirroring Telegram's album layouts for 2..N photos.

const ALBUM_GAP = 2;

function clampAlbumRatio(r) {
    if (!r || !isFinite(r) || r <= 0) r = 1;
    return Math.min(Math.max(r, 0.4), 3.2);
}

// Simple row of photos: widths proportional to aspect ratios, preserving each photo's aspect.
function buildAlbumRow(rowRatios, widthPx, yOffset) {
    const availW = widthPx - (rowRatios.length - 1) * ALBUM_GAP;
    const sumR = rowRatios.reduce((a, b) => a + b, 0) || 1;
    const h = availW / sumR;
    const widths = rowRatios.map(r => h * r);
    const tiles = [];
    let x = 0;
    rowRatios.forEach((r, i) => {
        tiles.push({ x: Math.round(x), y: Math.round(yOffset), w: Math.round(widths[i]), h: Math.round(h) });
        x += widths[i] + ALBUM_GAP;
    });
    return { tiles: tiles, height: h };
}

// Big left photo spanning full block height + stacked right column (Telegram 3/4-photo style).
function buildAlbumBigLeft(leftRatio, rightRatios, widthPx, yOffset) {
    const n = rightRatios.length;
    const invSum = rightRatios.reduce((a, r) => a + 1 / r, 0) || 1;
    let wR = (widthPx - ALBUM_GAP * ((n - 1) * leftRatio + 1)) / (invSum * leftRatio + 1);
    if (!isFinite(wR) || wR <= 0) wR = widthPx / 2;
    let H = wR * invSum + (n - 1) * ALBUM_GAP;
    let wL = H * leftRatio;
    if (wL + ALBUM_GAP + wR > widthPx) {
        wL = Math.max(widthPx * 0.35, widthPx - ALBUM_GAP - wR);
        H = wL / leftRatio;
    }
    wR = widthPx - ALBUM_GAP - wL;
    const tiles = [{ x: 0, y: Math.round(yOffset), w: Math.round(wL), h: Math.round(H) }];
    const heights = rightRatios.map(r => wR / r);
    const sumH = heights.reduce((a, b) => a + b, 0) || 1;
    const scale = (H - (n - 1) * ALBUM_GAP) / sumH;
    const scaledHeights = heights.map(h => h * scale);
    let y = yOffset;
    rightRatios.forEach((r, i) => {
        tiles.push({ x: Math.round(wL + ALBUM_GAP), y: Math.round(y), w: Math.round(wR), h: Math.round(scaledHeights[i]) });
        y += scaledHeights[i] + ALBUM_GAP;
    });
    return { tiles: tiles, height: H };
}

// Main entry: returns { width, height, tiles: [{x,y,w,h}] } for a Telegram-style mosaic.
window.computeAlbumLayout = function(rawRatios, widthPx) {
    const ratios = rawRatios.map(clampAlbumRatio);
    const n = ratios.length;
    const avgR = ratios.reduce((a, b) => a + b, 0) / n;
    let tiles = [];
    let totalH = 0;

    if (n === 2) {
        const row = buildAlbumRow(ratios, widthPx, 0);
        tiles = row.tiles;
        totalH = row.height;
    } else if (n === 3) {
        const block = buildAlbumBigLeft(ratios[0], ratios.slice(1), widthPx, 0);
        tiles = block.tiles;
        totalH = block.height;
    } else if (n === 4) {
        if (avgR < 0.85) {
            // Portrait set: one tall left photo + three stacked right (as in Telegram mobile).
            const block = buildAlbumBigLeft(ratios[0], ratios.slice(1), widthPx, 0);
            tiles = block.tiles;
            totalH = block.height;
        } else {
            const r1 = buildAlbumRow(ratios.slice(0, 2), widthPx, 0);
            const r2 = buildAlbumRow(ratios.slice(2), widthPx, r1.height + ALBUM_GAP);
            tiles = r1.tiles.concat(r2.tiles);
            totalH = r1.height + ALBUM_GAP + r2.height;
        }
    } else {
        let rowSizes;
        if (n === 5) rowSizes = [2, 3];
        else if (n === 6) rowSizes = null;
        else if (n === 7) rowSizes = [2, 2, 3];
        else if (n === 8) rowSizes = [2, 3, 3];
        else if (n === 9) rowSizes = [3, 3, 3];
        else if (n === 10) rowSizes = [2, 2, 3, 3];
        else {
            rowSizes = [];
            let rem = n;
            while (rem > 0) {
                const s = Math.min(3, rem);
                rowSizes.push(s);
                rem -= s;
            }
            if (rowSizes.length > 1 && rowSizes[rowSizes.length - 1] === 1) {
                rowSizes[rowSizes.length - 2] = 2;
                rowSizes[rowSizes.length - 1] = 2;
            }
        }

        if (n === 6) {
            if (avgR < 0.85) {
                // Portrait set: big-left block on top + row of three below (Telegram mobile).
                const block = buildAlbumBigLeft(ratios[0], ratios.slice(1, 3), widthPx, 0);
                const row = buildAlbumRow(ratios.slice(3), widthPx, block.height + ALBUM_GAP);
                tiles = block.tiles.concat(row.tiles);
                totalH = block.height + ALBUM_GAP + row.height;
            } else {
                rowSizes = [3, 3];
            }
        }

        if (rowSizes) {
            let y = 0;
            let idx = 0;
            rowSizes.forEach(size => {
                const row = buildAlbumRow(ratios.slice(idx, idx + size), widthPx, y);
                tiles = tiles.concat(row.tiles);
                y += row.height + ALBUM_GAP;
                idx += size;
            });
            totalH = y - ALBUM_GAP;
        }
    }

    // Cap total mosaic height; all tiles scale proportionally so no cropping.
    const maxTotal = n <= 2 ? 420 : (n <= 4 ? 520 : 480);
    let finalWidth = widthPx;
    if (totalH > maxTotal) {
        const f = maxTotal / totalH;
        tiles = tiles.map(t => ({ x: Math.round(t.x * f), y: Math.round(t.y * f), w: Math.max(1, Math.round(t.w * f)), h: Math.max(60, Math.round(t.h * f)) }));
        totalH = maxTotal;
        finalWidth = widthPx * f;
    }

    return { width: Math.round(finalWidth), height: Math.round(totalH), tiles: tiles };
};

// Apply Telegram-style CSS grid layouts to an album gallery.
// Each visible tile (including the more-cell overlay) gets explicit grid-column/row,
// and every photo is set to fill its cell with cover + top-center positioning.
function clearContainerHeights(gallery) {
    const bubble = gallery.closest('.chat-msg-bubble');
    const mediaWrapper = gallery.closest('.chat-msg-media-wrapper');
    const photoWrapper = gallery.closest('.chat-msg-photo-wrapper');
    [bubble, mediaWrapper, photoWrapper].forEach(el => {
        if (!el) return;
        el.style.removeProperty('height');
        el.style.removeProperty('min-height');
        el.style.removeProperty('max-height');
    });
}

function sortGalleryImages(gallery) {
    const imgs = Array.from(gallery.querySelectorAll('img.chat-msg-gallery-img')).filter(img => {
        return !img.classList.contains('chat-msg-gallery-img-hidden') && !img.closest('.chat-msg-gallery-more-cell');
    });
    imgs.sort((a, b) => {
        const am = parseInt(a.dataset.msgId, 10) || 0;
        const bm = parseInt(b.dataset.msgId, 10) || 0;
        if (am !== bm) return am - bm;
        // Preserve original DOM order when msgId is equal/missing.
        return Array.from(gallery.children).indexOf(a) - Array.from(gallery.children).indexOf(b);
    });
    imgs.forEach(img => gallery.appendChild(img));
}

function applyAlbumGridLayout(gallery) {
    gallery.classList.add('loaded');
    clearContainerHeights(gallery);

    const cells = Array.from(gallery.children).filter(el => {
        return !el.classList.contains('chat-msg-gallery-img-hidden') && window.getComputedStyle(el).display !== 'none';
    });

    const totalCount = cells.length;
    if (totalCount === 0) return;

    // Overflow albums render at most 9 visible tiles (the 9th is the more-cell).
    const visibleCells = totalCount > 9 ? cells.slice(0, 9) : cells;
    const n = visibleCells.length;

    const setImportant = (el, prop, value) => el.style.setProperty(prop, value, 'important');

    const getImg = (cell) => {
        if (cell.classList.contains('chat-msg-gallery-more-cell')) {
            return cell.querySelector('img.chat-msg-gallery-img');
        }
        if (cell.classList.contains('chat-msg-gallery-img')) {
            return cell;
        }
        return null;
    };

    // Reset previous grid definitions on the gallery.
    gallery.style.removeProperty('grid-template-columns');
    gallery.style.removeProperty('grid-template-rows');

    // Ensure every photo fills its cell and is aligned to the top.
    visibleCells.forEach(cell => {
        const img = getImg(cell);
        if (!img) return;
        setImportant(img, 'width', '100%');
        setImportant(img, 'height', '100%');
        setImportant(img, 'min-width', '0');
        setImportant(img, 'min-height', '0');
        setImportant(img, 'max-width', 'none');
        setImportant(img, 'max-height', 'none');
        img.removeAttribute('width');
        img.removeAttribute('height');
        setImportant(img, 'object-fit', 'cover');
        setImportant(img, 'object-position', 'top center');
        setImportant(img, 'display', 'block');
        setImportant(img, 'border-radius', '0');
        img.style.removeProperty('position');
        img.style.removeProperty('left');
        img.style.removeProperty('top');
    });

    // Compute average aspect ratio of loaded photos to decide 4-photo layout.
    const ratios = visibleCells.map(cell => {
        const img = getImg(cell);
        if (img && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0) {
            return img.naturalWidth / img.naturalHeight;
        }
        return 1;
    });
    const avgRatio = ratios.reduce((a, b) => a + b, 0) / ratios.length;

    let cols = '';
    let rows = '';
    const cellStyles = [];

    if (n === 1) {
        cols = 'minmax(0, 1fr)';
        rows = 'minmax(420px, 520px)';
        cellStyles.push({ col: '1', row: '1' });
    } else if (n === 2) {
        cols = 'repeat(2, minmax(0, 1fr))';
        rows = 'minmax(380px, 520px)';
        cellStyles.push({ col: '1', row: '1' });
        cellStyles.push({ col: '2', row: '1' });
    } else if (n === 3) {
        cols = 'minmax(0, 2fr) minmax(0, 1fr)';
        rows = 'repeat(2, 300px)';
        cellStyles.push({ col: '1', row: '1 / span 2' });
        cellStyles.push({ col: '2', row: '1' });
        cellStyles.push({ col: '2', row: '2' });
    } else if (n === 4) {
        if (avgRatio < 0.85) {
            cols = 'minmax(0, 2fr) minmax(0, 1fr)';
            rows = 'repeat(3, 260px)';
            cellStyles.push({ col: '1', row: '1 / span 3' });
            cellStyles.push({ col: '2', row: '1' });
            cellStyles.push({ col: '2', row: '2' });
            cellStyles.push({ col: '2', row: '3' });
        } else {
            cols = 'repeat(2, minmax(0, 1fr))';
            rows = 'repeat(2, 260px)';
            cellStyles.push({ col: '1', row: '1' });
            cellStyles.push({ col: '2', row: '1' });
            cellStyles.push({ col: '1', row: '2' });
            cellStyles.push({ col: '2', row: '2' });
        }
    } else if (n === 5) {
        cols = 'repeat(6, minmax(0, 1fr))';
        rows = '460px 240px';
        cellStyles.push({ col: '1 / span 3', row: '1' });
        cellStyles.push({ col: '4 / span 3', row: '1' });
        cellStyles.push({ col: '1 / span 2', row: '2' });
        cellStyles.push({ col: '3 / span 2', row: '2' });
        cellStyles.push({ col: '5 / span 2', row: '2' });
    } else if (n === 6) {
        // 3 columns × 2 rows: 1/2/3 on top, 4/5/6 on bottom.
        cols = 'repeat(3, minmax(0, 1fr))';
        rows = 'repeat(2, 360px)';
        cellStyles.push({ col: '1', row: '1' });
        cellStyles.push({ col: '2', row: '1' });
        cellStyles.push({ col: '3', row: '1' });
        cellStyles.push({ col: '1', row: '2' });
        cellStyles.push({ col: '2', row: '2' });
        cellStyles.push({ col: '3', row: '2' });
    } else if (n === 7) {
        cols = 'repeat(6, minmax(0, 1fr))';
        rows = 'repeat(3, 260px)';
        cellStyles.push({ col: '1 / span 3', row: '1' });
        cellStyles.push({ col: '4 / span 3', row: '1' });
        cellStyles.push({ col: '1 / span 3', row: '2' });
        cellStyles.push({ col: '4 / span 3', row: '2' });
        cellStyles.push({ col: '1 / span 2', row: '3' });
        cellStyles.push({ col: '3 / span 2', row: '3' });
        cellStyles.push({ col: '5 / span 2', row: '3' });
    } else if (n === 8) {
        cols = 'repeat(6, minmax(0, 1fr))';
        rows = 'repeat(3, 260px)';
        cellStyles.push({ col: '1 / span 3', row: '1' });
        cellStyles.push({ col: '4 / span 3', row: '1' });
        cellStyles.push({ col: '1 / span 2', row: '2' });
        cellStyles.push({ col: '3 / span 2', row: '2' });
        cellStyles.push({ col: '5 / span 2', row: '2' });
        cellStyles.push({ col: '1 / span 2', row: '3' });
        cellStyles.push({ col: '3 / span 2', row: '3' });
        cellStyles.push({ col: '5 / span 2', row: '3' });
    } else {
        // 9 (or fallback for many): 3x3
        cols = 'repeat(3, minmax(0, 1fr))';
        rows = 'repeat(3, 260px)';
        for (let i = 0; i < n; i++) {
            const col = (i % 3) + 1;
            const row = Math.floor(i / 3) + 1;
            cellStyles.push({ col: String(col), row: String(row) });
        }
    }

    setImportant(gallery, 'grid-template-columns', cols);
    setImportant(gallery, 'grid-template-rows', rows);

    visibleCells.forEach((cell, i) => {
        const style = cellStyles[i];
        if (!style) return;
        setImportant(cell, 'grid-column', style.col);
        setImportant(cell, 'grid-row', style.row);
    });
}

window.checkGalleryImgLayout = function(img) {
    if (!img) return;
    const gallery = img.closest('.chat-msg-gallery');
    if (!gallery) return;

    const images = Array.from(gallery.querySelectorAll('.chat-msg-gallery-img'));
    images.forEach(i => {
        if (!i._hasLoadListener) {
            i._hasLoadListener = true;
            i.addEventListener('load', function() { checkGalleryImgLayout(i); });
            i.addEventListener('error', function() { checkGalleryImgLayout(i); });
        }
    });

    applyAlbumGridLayout(gallery);
};

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

async function setChatSidebarTab(type) {
    chatSidebarTab = type;
    try {
        localStorage.setItem('chatSidebarTab', type);
    } catch (e) {}
    
    document.querySelectorAll('.sidebar-tab').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(type === 'completed' ? 'chat-sidebar-tab-completed' : 'chat-sidebar-tab-active');
    if (activeBtn) activeBtn.classList.add('active');
    
    if (type === 'completed') {
        await loadCompletedSessions();
    } else {
        if (!lastFetchedSessions) {
            try {
                const res = await fetch('/api/sessions');
                lastFetchedSessions = await res.json();
            } catch (e) {}
        }
        renderChatSidebar();
    }
}

async function loadCompletedSessions() {
    try {
        const res = await fetch('/api/sessions/completed');
        if (res.ok) {
            cachedCompletedSessions = await res.json();
        }
        renderChatSidebar();
    } catch (err) {
        console.error("Failed to load completed sessions:", err);
    }
}

async function loadChatSessions() {
    document.querySelectorAll('.sidebar-tab').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(chatSidebarTab === 'completed' ? 'chat-sidebar-tab-completed' : 'chat-sidebar-tab-active');
    if (activeBtn) activeBtn.classList.add('active');

    if (chatSidebarTab === 'completed') {
        await loadCompletedSessions();
    } else {
        if (!lastFetchedSessions) {
            try {
                const res = await fetch('/api/sessions');
                lastFetchedSessions = await res.json();
            } catch (e) {}
        }
        renderChatSidebar();
    }
}

function renderChatSidebar() {
    const container = document.getElementById('chat-sidebar-list-container');
    if (!container) return;
    
    const searchInput = document.getElementById('chat-search-input');
    const searchQuery = searchInput && searchInput.value ? searchInput.value.toLowerCase().trim() : '';
    const list = chatSidebarTab === 'completed' ? cachedCompletedSessions : lastFetchedSessions;
    
    document.querySelectorAll('.sidebar-tab').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(chatSidebarTab === 'completed' ? 'chat-sidebar-tab-completed' : 'chat-sidebar-tab-active');
    if (activeBtn) activeBtn.classList.add('active');

    if (list === null) {
        container.innerHTML = '<div style="padding:24px;text-align:center;color:rgba(255,255,255,0.4);font-size:0.85rem;">Завантаження...</div>';
        return;
    }

    if (!list || list.length === 0) {
        container.innerHTML = `<div style="padding:24px;text-align:center;color:rgba(255,255,255,0.35);font-size:0.85rem;">Немає ${chatSidebarTab === 'completed' ? 'архівних' : 'активних'} чатів</div>`;
        return;
    }
    
    container.innerHTML = '';
    
    const savedId = localStorage.getItem('selectedChatClientId');
    if (savedId && selectedChatClientId === null && list && list.length > 0) {
        const parsedSavedId = parseInt(savedId);
        if (list.some(s => s.client_id === parsedSavedId)) {
            setTimeout(() => {
                if (selectedChatClientId === null) {
                    selectChatClient(parsedSavedId, true);
                }
            }, 0);
        }
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
                if (session && window.renderClientInfoPanel) {
                    window.renderClientInfoPanel(session);
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

async function selectChatClient(clientId, isInitialLoad = false) {
    if (window.resetViewportScale) window.resetViewportScale();
    if (!isInitialLoad && selectedChatClientId !== null && selectedChatClientId !== clientId) {
        window._justSwitchedChatClient = true;
    }
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
        <div id="chat-floating-date-badge" class="chat-floating-date-badge"></div>
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
                    <button class="btn-attach-photo" onclick="triggerPhotoFileInput()" title="Прикріпити фото">
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>
                        </svg>
                    </button>
                    <input type="file" id="chat-file-input" accept="image/*" style="display: none;" onchange="handlePhotoFileSelected(this)">
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
    
    initChatTheme();
    
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
    
    await refreshChatPageMessages(clientId, true);
    
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


function formatChatLogDate(utcDateStr) {
    if (!utcDateStr) return '';
    let date = parseUtcToLocal(utcDateStr);
    if (!date) {
        try {
            date = new Date(utcDateStr.replace(' ', 'T') + 'Z');
        } catch(e) {
            date = new Date(utcDateStr);
        }
    }
    if (!date || isNaN(date.getTime())) return '';
    
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    const targetDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    
    if (targetDate.getTime() === today.getTime()) {
        return 'Сьогодні';
    } else if (targetDate.getTime() === yesterday.getTime()) {
        return 'Вчора';
    } else {
        const months = ['січня', 'лютого', 'березня', 'квітня', 'травня', 'червня', 'липня', 'серпня', 'вересня', 'жовтня', 'листопада', 'грудня'];
        const day = date.getDate();
        const month = months[date.getMonth()];
        const year = date.getFullYear();
        if (year === now.getFullYear()) {
            return `${day} ${month}`;
        }
        return `${day} ${month} ${year}`;
    }
}

function renderChatLogsFromArray(container, logs) {
    window._isRenderingChatLogs = true;
    container.innerHTML = '';
    if (!logs || logs.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,0.2);padding:40px;">Історія повідомлень порожня</div>';
        window._isRenderingChatLogs = false;
        return;
    }
    
    const getSenderGroup = (sender) => {
        if (sender === 'client') return 'client';
        if (sender === 'bot') return 'bot';
        return 'support'; // admin or operator
    };

    let lastDateStr = '';
    const groupedLogs = groupPhotoLogs(logs);
    groupedLogs.forEach((log, index) => {
        if (log.created_at) {
            const rawDate = log.created_at.split(' ')[0];
            if (rawDate && rawDate !== lastDateStr) {
                lastDateStr = rawDate;
                const formattedDate = formatChatLogDate(log.created_at);
                if (formattedDate) {
                    const dividerDiv = document.createElement('div');
                    dividerDiv.className = 'chat-date-divider';
                    dividerDiv.setAttribute('data-date-label', formattedDate);
                    dividerDiv.innerHTML = `<span class="chat-date-divider-pill">— ${formattedDate} —</span>`;
                    container.appendChild(dividerDiv);
                }
            }
        }
        const nextLog = groupedLogs[index + 1];
        const hideAvatar = nextLog && getSenderGroup(nextLog.sender) === getSenderGroup(log.sender);
        renderSingleChatMessage(container, log, hideAvatar, true);
    });
    
    setupFloatingDateScrollListener();

    const scrollContainer = document.getElementById('chat-window-body-container');
    let savedScrollPos = null;
    try {
        savedScrollPos = sessionStorage.getItem('chat_scroll_' + selectedChatClientId);
    } catch(e) {}

    const targetScroll = (savedScrollPos !== null) ? parseInt(savedScrollPos, 10) : null;
    const shouldRestoreScroll = targetScroll !== null && !isNaN(targetScroll) && !window._justSwitchedChatClient;

    if (shouldRestoreScroll) {
        let restorationActive = true;
        let restorationApplyCount = 0;
        let pendingImages = 0;
        let imagesDone = false;
        const timeoutIds = [];
        let fallbackEndTimeoutId = null;

        function endRestoration() {
            if (!restorationActive) return;
            restorationActive = false;
            window._isRenderingChatLogs = false;
            if (scrollContainer) {
                scrollContainer.removeEventListener('scroll', cancelOnScroll);
            }
            if (fallbackEndTimeoutId !== null) clearTimeout(fallbackEndTimeoutId);
            timeoutIds.forEach(id => clearTimeout(id));
        }

        function applyChatScroll() {
            if (!restorationActive || !scrollContainer) return;
            restorationApplyCount++;
            const maxScroll = scrollContainer.scrollHeight - scrollContainer.clientHeight;
            scrollContainer.scrollTop = Math.min(targetScroll, maxScroll);
            setTimeout(() => { restorationApplyCount--; }, 50);
        }

        function cancelOnScroll() {
            if (restorationApplyCount > 0) return;
            endRestoration();
        }

        function maybeEndRestoration() {
            if (imagesDone) {
                // Wait a brief moment for any layout reflow, then end.
                setTimeout(endRestoration, 50);
            }
        }

        if (scrollContainer) {
            scrollContainer.addEventListener('scroll', cancelOnScroll, { passive: true });
        }

        applyChatScroll();
        requestAnimationFrame(applyChatScroll);
        timeoutIds.push(setTimeout(applyChatScroll, 50));
        timeoutIds.push(setTimeout(applyChatScroll, 150));
        timeoutIds.push(setTimeout(applyChatScroll, 400));
        timeoutIds.push(setTimeout(applyChatScroll, 800));

        // Re-apply the saved position as each historical image loads, so late-loading
        // photos do not push the viewport to the bottom. Stop as soon as the user scrolls.
        if (scrollContainer) {
            const images = scrollContainer.querySelectorAll('img');
            pendingImages = images.length;
            if (pendingImages === 0) {
                imagesDone = true;
                maybeEndRestoration();
            } else {
                images.forEach(img => {
                    const onImgDone = () => {
                        applyChatScroll();
                        pendingImages--;
                        if (pendingImages <= 0) {
                            imagesDone = true;
                            maybeEndRestoration();
                        }
                    };
                    if (img.complete) {
                        onImgDone();
                    } else {
                        img.addEventListener('load', onImgDone, { once: true });
                        img.addEventListener('error', onImgDone, { once: true });
                    }
                });
            }
        }

        // Fallback: end restoration after a reasonable timeout if images hang.
        fallbackEndTimeoutId = setTimeout(() => {
            imagesDone = true;
            maybeEndRestoration();
        }, 2500);
    } else {
        scrollToBottom('chat-window-body-container', true);
        window._justSwitchedChatClient = false;
        setTimeout(() => {
            window._isRenderingChatLogs = false;
        }, 500);
    }
}

let dateBadgeTimeout = null;
let lastChatScrollTop = 0;

function setupFloatingDateScrollListener() {
    const container = document.getElementById('chat-window-body-container');
    if (!container || container._hasFloatingDateListener) return;
    container._hasFloatingDateListener = true;
    lastChatScrollTop = container.scrollTop;
    
    let badge = document.getElementById('chat-floating-date-badge');
    if (!badge) {
        badge = document.createElement('div');
        badge.id = 'chat-floating-date-badge';
        badge.className = 'chat-floating-date-badge';
        const chatWindow = document.getElementById('chat-window-container');
        if (chatWindow) {
            chatWindow.appendChild(badge);
        } else {
            container.parentNode.appendChild(badge);
        }
    }
    
    container.addEventListener('scroll', function() {
        if (selectedChatClientId && !window._isRenderingChatLogs) {
            try {
                sessionStorage.setItem('chat_scroll_' + selectedChatClientId, container.scrollTop);
            } catch(e) {}
        }
        const badge = document.getElementById('chat-floating-date-badge');
        if (!badge) return;

        const currentScrollTop = container.scrollTop;

        // При скролі до самого верху (scrollTop <= 35px) ховаємо плаваючий бейдж, щоб не дублювати статичний дівідер дати
        if (currentScrollTop <= 35) {
            badge.classList.remove('active');
            if (dateBadgeTimeout) clearTimeout(dateBadgeTimeout);
            return;
        }

        const delta = currentScrollTop - lastChatScrollTop;
        lastChatScrollTop = currentScrollTop;

        // Якщо скролять явно донизу (delta > 10px) — відразу ховаємо
        if (delta > 10) {
            badge.classList.remove('active');
            if (dateBadgeTimeout) clearTimeout(dateBadgeTimeout);
            return;
        }

        // Якщо скролять вгору (delta < -1px)
        if (delta < -1) {
            const dividers = container.querySelectorAll('.chat-date-divider, [data-date-label]');
            let currentLabel = '';

            const containerTop = container.getBoundingClientRect().top;
            dividers.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.top - containerTop <= 90) {
                    const label = el.getAttribute('data-date-label');
                    if (label) {
                        currentLabel = label;
                    }
                }
            });

            if (currentLabel) {
                badge.textContent = currentLabel;
                badge.classList.add('active');

                if (dateBadgeTimeout) {
                    clearTimeout(dateBadgeTimeout);
                }
                dateBadgeTimeout = setTimeout(() => {
                    badge.classList.remove('active');
                }, 1500);
            }
        }
    }, { passive: true });
}

async function refreshChatPageMessages(clientId, force = false) {
    try {
        const res = await fetch(`/api/sessions/${clientId}/chat`);
        const logs = await res.json();
        
        const bodyContainer = document.getElementById('chat-window-body-container');
        if (!bodyContainer || selectedChatClientId !== clientId) return;
        
        const prevLogsStr = chatLogsCache[clientId] ? JSON.stringify(chatLogsCache[clientId]) : '';
        const newLogsStr = JSON.stringify(logs);
        
        chatLogsCache[clientId] = logs;
        
        if (force || prevLogsStr !== newLogsStr || !bodyContainer.firstElementChild || bodyContainer.innerHTML.includes('Завантаження повідомлень...')) {
            renderChatLogsFromArray(bodyContainer, logs);
        }
    } catch (err) {
        console.error("Failed to load messages:", err);
    }
}

function renderSingleChatMessage(container, log, hideAvatar = false, isHistoryRender = false) {
    const allSessions = [...(lastFetchedSessions || []), ...(cachedCompletedSessions || [])];
    const session = allSessions.find(s => s.client_id === selectedChatClientId);
    const displayName = session ? extractDisplayName(session.client_data, session.username) : 'Клієнт';

    const containerDiv = document.createElement('div');
    const hasText = Boolean(log.message_text && String(log.message_text).trim().length > 0);
    const hasPhoto = log.photo_id || (log.photo_ids && log.photo_ids.length > 0);
    const isPhotoOnly = hasPhoto && !hasText;
    containerDiv.className = `chat-msg-container ${log.sender}${isPhotoOnly ? ' photo-only-msg' : ''}`;
    if (hideAvatar) {
        containerDiv.classList.add('same-sender-next');
    }

    if (log.created_at) {
        const formattedDate = formatChatLogDate(log.created_at);
        if (formattedDate) {
            containerDiv.setAttribute('data-date-label', formattedDate);
        }
    }

    const targetMsgId = log.message_id || log.id;
    if (targetMsgId) {
        containerDiv.id = `chat-msg-log-${targetMsgId}`;
        containerDiv.setAttribute('data-msg-id', String(log.message_id || ''));
        containerDiv.setAttribute('data-log-id', String(log.id || ''));
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
                const timePart = log.created_at.split(' ')[1];
                timeStr = timePart ? timePart.substring(0, 5) : '';
            } catch (e) {}
        }
    }

    let contentHtml = '';
    if (log.reply_to_message_id && chatLogsCache[selectedChatClientId]) {
        const targetReplyId = String(log.reply_to_message_id);
        const repliedLog = chatLogsCache[selectedChatClientId].find(l => (l.message_id != null && String(l.message_id) === targetReplyId) || (l.id != null && String(l.id) === targetReplyId));
        if (repliedLog) {
            const rSender = repliedLog.sender === 'client' ? 'Клієнт' : (repliedLog.sender === 'bot' ? '🤖 AI-агент' : '👤 Оператор');
            const accentColor = repliedLog.sender === 'client' ? '#3b82f6' : (repliedLog.sender === 'bot' ? '#06b6d4' : '#a855f7');
            
            const photoId = repliedLog.photo_id || (repliedLog.photo_ids && repliedLog.photo_ids.length > 0 ? repliedLog.photo_ids[0] : null);
            const photoClientParam = selectedChatClientId ? `?client_id=${selectedChatClientId}` : '';
            let quoteThumbHtml = '';
            let rText = '';
            if (photoId) {
                quoteThumbHtml = `<img class="chat-msg-quote-thumb" src="/api/photos/${photoId}${photoClientParam}" alt="Photo" style="width: 36px !important; height: 36px !important; min-width: 36px !important; min-height: 36px !important; max-width: 36px !important; max-height: 36px !important; object-fit: cover !important; border-radius: 6px !important; flex-shrink: 0 !important; display: inline-block !important; margin: 0 8px 0 0 !important;">`;
                const captionText = repliedLog.message_text ? `: ${stripMessageQuotes(repliedLog.message_text)}` : '';
                rText = `Фото${captionText}`;
            } else {
                rText = stripMessageQuotes(repliedLog.message_text) || '[Повідомлення]';
            }
            rText = rText.substring(0, 75);

            contentHtml += `
                <div class="chat-msg-quote-box ${photoId ? 'has-thumb' : ''}" style="--quote-accent-color: ${accentColor};" onclick="scrollToQuotedMessage('${targetReplyId}', event)">
                    ${quoteThumbHtml}
                    <div class="chat-msg-quote-content">
                        <div class="chat-msg-quote-sender-name" style="color: ${accentColor};">${rSender}</div>
                        <div class="chat-msg-quote-text">${escapeHtml(rText)}</div>
                    </div>
                </div>
            `;
        }
    }

    let bubbleClass = 'chat-msg-bubble';
    const isGallery = log.photo_ids && log.photo_ids.length > 1;
    if (hasPhoto) {
        bubbleClass += ' has-photo';
        if (isGallery) {
            bubbleClass += ' has-gallery';
        }
        if (!hasText) {
            bubbleClass += ' photo-only';
        }
    }

    const singlePhotoId = log.photo_id || (log.photo_ids && log.photo_ids.length > 0 ? log.photo_ids[0] : null);

    if (log.photo_ids && log.photo_ids.length > 1) {
        const allPhotoIds = log.photo_ids;
        const overflowCount = allPhotoIds.length > 10 ? allPhotoIds.length - 9 : 0;
        const visiblePhotoIds = overflowCount > 0 ? allPhotoIds.slice(0, 9) : allPhotoIds;
        const albumClass = overflowCount > 0 ? 'album-count-many' : `album-count-${allPhotoIds.length}`;
        const pidClientParam = selectedChatClientId ? `?client_id=${selectedChatClientId}` : '';
        const galleryHtml = `<div class="chat-msg-gallery ${albumClass}">` +
            visiblePhotoIds.map((pid, vIdx) => {
                const scrollOnLoad = isHistoryRender ? '' : ' scrollToBottom(\'chat-window-body-container\')';
                const imgTag = `<img class="chat-msg-gallery-img" src="/api/photos/${pid}${pidClientParam}" onerror="handlePhotoError(this)" onload="checkGalleryImgLayout(this);${scrollOnLoad}">`;
                if (overflowCount > 0 && vIdx === visiblePhotoIds.length - 1) {
                    return `<div class="chat-msg-gallery-more-cell">${imgTag}<span class="chat-msg-gallery-more">+${overflowCount}</span></div>`;
                }
                return imgTag;
            }).join('') +
            (overflowCount > 0 ? allPhotoIds.slice(9).map(pid => {
                return `<img class="chat-msg-gallery-img chat-msg-gallery-img-hidden" src="/api/photos/${pid}${pidClientParam}" style="display:none;" onerror="handlePhotoError(this)">`;
            }).join('') : '') +
            `</div>`;
        if (hasText) {
            contentHtml += galleryHtml;
            let rawText = stripMessageQuotes(log.message_text);
            let escapedText = escapeHtml(rawText);
            escapedText = escapedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            contentHtml += `<div class="chat-msg-caption-box">
                <span class="chat-msg-text">${escapedText.replace(/\n/g, '<br>')}</span>
                <span class="chat-msg-time-inline">${timeStr}</span>
            </div>`;
        } else {
            contentHtml += `
                <div class="chat-msg-media-wrapper">
                    ${galleryHtml}
                    <span class="chat-msg-time-inline photo-time">${timeStr}</span>
                </div>
            `;
        }
    } else if (singlePhotoId && !hasText) {
        const scrollOnLoad = isHistoryRender ? '' : 'onload="scrollToBottom(\'chat-window-body-container\')"';
        contentHtml += `
            <div class="chat-msg-media-wrapper">
                <div class="chat-msg-photo-wrapper">
                    <div class="chat-msg-photo-blur-bg" style="background-image: url('/api/photos/${singlePhotoId}?client_id=${selectedChatClientId || ''}');"></div>
                    <img class="chat-msg-img" data-msg-id="${log.message_id || ''}" src="/api/photos/${singlePhotoId}?client_id=${selectedChatClientId || ''}" onerror="handlePhotoError(this)" ${scrollOnLoad}>
                </div>
                <span class="chat-msg-time-inline photo-time">${timeStr}</span>
            </div>
        `;
    } else {
        if (singlePhotoId) {
            const scrollOnLoad = isHistoryRender ? '' : 'onload="scrollToBottom(\'chat-window-body-container\')"';
            contentHtml += `
                <div class="chat-msg-photo-wrapper">
                    <div class="chat-msg-photo-blur-bg" style="background-image: url('/api/photos/${singlePhotoId}?client_id=${selectedChatClientId || ''}');"></div>
                    <img class="chat-msg-img" data-msg-id="${log.message_id || ''}" src="/api/photos/${singlePhotoId}?client_id=${selectedChatClientId || ''}" onerror="handlePhotoError(this)" ${scrollOnLoad}>
                </div>
            `;
        }
        if (hasText) {
            let rawText = stripMessageQuotes(log.message_text);
            let escapedText = escapeHtml(rawText);
            escapedText = escapedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            if (singlePhotoId) {
                contentHtml += `<div class="chat-msg-caption-box">
                    <span class="chat-msg-text">${escapedText.replace(/\n/g, '<br>')}</span>
                    <span class="chat-msg-time-inline">${timeStr}</span>
                </div>`;
            } else {
                contentHtml += `<span class="chat-msg-text">${escapedText.replace(/\n/g, '<br>')}</span>`;
                contentHtml += `<span class="chat-msg-time-inline">${timeStr}</span>`;
            }
        } else if (!singlePhotoId) {
            contentHtml += `<span class="chat-msg-time-inline">${timeStr}</span>`;
        }
    }
    
    let avatarLetter = 'К';
    
    if (log.sender === 'client') {
        avatarLetter = displayName.replace(/^@/, '').substring(0, 1).toUpperCase() || 'К';
    } else if (log.sender === 'bot') {
        avatarLetter = '🤖';
    } else {
        avatarLetter = '👤';
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
        <div class="chat-msg-body-row" style="position: relative;">
            ${avatarHtml}
            <div class="${bubbleClass}">
                ${contentHtml}
            </div>
        </div>
    `;
    containerDiv.ondblclick = function(e) {
        e.stopPropagation();
        setChatReplyTo(log);
    };
    containerDiv.oncontextmenu = function(e) {
        showTelegramContextMenu(e, log);
    };
    containerDiv._receivedAt = Date.now();
    container.appendChild(containerDiv);

    if (log.photo_ids && log.photo_ids.length > 1) {
        requestAnimationFrame(() => {
            const gallery = containerDiv.querySelector('.chat-msg-gallery');
            if (gallery) applyAlbumGridLayout(gallery);
            const firstImg = gallery && gallery.querySelector('.chat-msg-gallery-img');
            if (firstImg) checkGalleryImgLayout(firstImg);
        });
    }
}

// Global Custom Telegram Context Menu Handler
let activeContextMenu = null;

function removeContextMenu() {
    if (activeContextMenu) {
        activeContextMenu.remove();
        activeContextMenu = null;
    }
}

document.addEventListener('click', removeContextMenu);
document.addEventListener('scroll', removeContextMenu, true);

function showTelegramContextMenu(e, log) {
    e.preventDefault();
    e.stopPropagation();
    removeContextMenu();

    const menu = document.createElement('div');
    menu.className = 'chat-context-menu';

    menu.innerHTML = `
        <div class="chat-context-menu-item" id="ctx-item-reply">
            <svg viewBox="0 0 24 24"><polyline points="9 17 4 12 9 7"></polyline><path d="M20 18v-2a4 4 0 0 0-4-4H4"></path></svg>
            <span>Відповісти</span>
        </div>
        ${log.message_text ? `
        <div class="chat-context-menu-item" id="ctx-item-copy">
            <svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            <span>Скопіювати текст</span>
        </div>
        ` : ''}
    `;

    document.body.appendChild(menu);

    let x = e.clientX;
    let y = e.clientY;
    const menuRect = menu.getBoundingClientRect();

    if (x + menuRect.width > window.innerWidth) {
        x = window.innerWidth - menuRect.width - 10;
    }
    if (y + menuRect.height > window.innerHeight) {
        y = window.innerHeight - menuRect.height - 10;
    }

    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;

    const replyBtn = menu.querySelector('#ctx-item-reply');
    if (replyBtn) {
        replyBtn.onclick = function(ev) {
            ev.stopPropagation();
            removeContextMenu();
            setChatReplyTo(log);
        };
    }

    const copyBtn = menu.querySelector('#ctx-item-copy');
    if (copyBtn) {
        copyBtn.onclick = function(ev) {
            ev.stopPropagation();
            removeContextMenu();
            if (navigator.clipboard && log.message_text) {
                navigator.clipboard.writeText(log.message_text);
                if (typeof showToast === 'function') {
                    showToast('Текст скопійовано', 'success');
                }
            }
        };
    }

    activeContextMenu = menu;
}

function scrollToBottom(containerId, force = false) {
    // Prevent auto-scroll from interfering while historical messages are still being rendered.
    if (window._isRenderingChatLogs && !force) return;
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

let activeChatReplyLog = null;

function setChatReplyTo(log) {
    activeChatReplyLog = log;
    let previewBar = document.getElementById('chat-reply-preview-bar');
    if (!previewBar) {
        const footer = document.querySelector('.chat-window-footer');
        if (footer) {
            previewBar = document.createElement('div');
            previewBar.id = 'chat-reply-preview-bar';
            footer.insertBefore(previewBar, footer.firstChild);
        }
    }
    if (previewBar) {
        const senderName = log.sender === 'client' ? 'Клієнта' : (log.sender === 'bot' ? 'Бота' : 'Оператора');
        const photoId = log.photo_id || (log.photo_ids && log.photo_ids.length > 0 ? log.photo_ids[0] : null);
        const replyClientParam = selectedChatClientId ? `?client_id=${selectedChatClientId}` : '';

        let replyThumbHtml = '';
        let textSnippet = '';
        if (photoId) {
            replyThumbHtml = `<img class="chat-reply-thumb" src="/api/photos/${photoId}${replyClientParam}" alt="Photo">`;
            const captionText = log.message_text ? `: ${stripMessageQuotes(log.message_text)}` : '';
            textSnippet = `Фото${captionText}`;
        } else {
            textSnippet = stripMessageQuotes(log.message_text) || '[Повідомлення]';
        }
        textSnippet = textSnippet.substring(0, 60);

        previewBar.className = 'chat-reply-preview-bar';
        previewBar.innerHTML = `
            <div class="chat-reply-preview-content">
                <span class="chat-reply-icon">↳</span>
                ${replyThumbHtml}
                <div class="chat-reply-text-wrapper">
                    <span class="chat-reply-sender">Відповідь для ${senderName}</span>
                    <span class="chat-reply-snippet">${escapeHtml(stripMessageQuotes(textSnippet))}</span>
                </div>
            </div>
            <button class="chat-reply-close-btn" onclick="cancelChatReply()" title="Скасувати відповідь">✕</button>
        `;
        previewBar.onclick = function(event) {
            if (event && event.target.closest('.chat-reply-close-btn')) return;
            const input = document.getElementById('chat-msg-input');
            if (input) input.focus();
        };
        const replyColumn = document.querySelector('.chat-window-column');
        if (replyColumn) replyColumn.classList.add('has-reply-preview');
        requestAnimationFrame(() => {
            previewBar.classList.add('active');
            smoothScrollSync(320);
        });
    }
    const input = document.getElementById('chat-msg-input');
    if (input) input.focus();
}

window.scrollToQuotedMessage = function(targetId, event) {
    if (event) {
        event.stopPropagation();
    }
    if (!targetId) return;

    const bodyContainer = document.getElementById('chat-window-body-container');
    if (!bodyContainer) return;

    let el = document.getElementById(`chat-msg-log-${targetId}`);
    if (!el) {
        el = bodyContainer.querySelector(`[data-msg-id="${targetId}"], [data-log-id="${targetId}"]`);
    }

    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        el.classList.remove('quote-highlight-target');
        void el.offsetWidth; // Trigger reflow for animation restart
        el.classList.add('quote-highlight-target');
        
        setTimeout(() => {
            el.classList.remove('quote-highlight-target');
        }, 4000);
    }
};

function smoothScrollSync(duration = 300) {
    const container = document.getElementById('chat-window-body-container');
    if (!container) return;
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 300;
    if (!isNearBottom) return;

    const startTime = performance.now();
    function step(currentTime) {
        container.scrollTop = container.scrollHeight;
        if (currentTime - startTime < duration) {
            requestAnimationFrame(step);
        }
    }
    requestAnimationFrame(step);
}

function cancelChatReply() {
    activeChatReplyLog = null;
    const previewBar = document.getElementById('chat-reply-preview-bar');
    if (previewBar) {
        previewBar.classList.remove('active');
        smoothScrollSync(320);
    }
    const replyColumn = document.querySelector('.chat-window-column');
    if (replyColumn) replyColumn.classList.remove('has-reply-preview');
}

async function sendChatPageMessage() {
    const clientId = selectedChatClientId;
    if (!clientId) return;
    
    const textarea = document.getElementById('chat-msg-input');
    if (!textarea) return;
    
    const message = textarea.value.trim();
    if (!message) return;
    
    const payload = { message };
    if (activeChatReplyLog && activeChatReplyLog.message_id) {
        payload.reply_to_message_id = activeChatReplyLog.message_id;
    }
    
    try {
        const res = await fetch(`/api/sessions/${clientId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            textarea.value = '';
            cancelChatReply();
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
        if (typeof pollData === 'function') {
            pollData();
        }
        const bodyContainer = document.getElementById('chat-window-body-container');
        if (bodyContainer) {
            const isNearBottom = bodyContainer.scrollHeight - bodyContainer.scrollTop - bodyContainer.clientHeight < 100;
            const isChatActiveAndVisible = (typeof currentTab !== 'undefined' && currentTab === 'chat');
            // Maintain chat cache in Telegram order.
            const logObj = {
                sender: data.sender,
                message_text: data.message_text,
                photo_id: data.photo_id,
                message_id: data.message_id,
                reply_to_message_id: data.reply_to_message_id,
                created_at: data.created_at
            };
            if (!chatLogsCache[data.client_id]) {
                chatLogsCache[data.client_id] = [];
            }
            chatLogsCache[data.client_id].push(logObj);
            chatLogsCache[data.client_id].sort((a, b) => {
                const at = a.created_at || '';
                const bt = b.created_at || '';
                if (at !== bt) return at.localeCompare(bt);
                const am = a.message_id != null ? Number(a.message_id) : (a.id != null ? Number(a.id) : 0);
                const bm = b.message_id != null ? Number(b.message_id) : (b.id != null ? Number(b.id) : 0);
                return am - bm;
            });

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

            // Attempt to merge photos in real-time if received within 180 seconds (3 minutes)
            if (data.photo_id && lastMsgContainer && lastMsgContainer._receivedAt && (Date.now() - lastMsgContainer._receivedAt < 180000)) {
                if (getLastMsgSenderGroup(lastMsgContainer) === getSenderGroup(data.sender)) {
                    const lastBubble = lastMsgContainer.querySelector('.chat-msg-bubble');
                    if (lastBubble) {
                        const singleImg = lastBubble.querySelector('.chat-msg-img');
                        if (singleImg) {
                            // Convert single image to gallery
                            const gallery = document.createElement('div');
                            gallery.className = 'chat-msg-gallery album-count-2';
                            
                            const img1 = singleImg.cloneNode();
                            img1.removeAttribute('width');
                            img1.removeAttribute('height');
                            img1.removeAttribute('style');
                            img1.className = 'chat-msg-gallery-img';
                            img1.dataset.msgId = singleImg.dataset.msgId || lastMsgContainer.getAttribute('data-msg-id') || '';
                            img1.onload = function() { checkGalleryImgLayout(img1); };

                            const img2 = document.createElement('img');
                            img2.removeAttribute('width');
                            img2.removeAttribute('height');
                            img2.removeAttribute('style');
                            img2.className = 'chat-msg-gallery-img';
                            img2.dataset.msgId = data.message_id || '';
                            img2.onerror = function() { handlePhotoError(img2); };
                            const photoParam2 = selectedChatClientId ? `?client_id=${selectedChatClientId}` : '';
                            img2.src = `/api/photos/${data.photo_id}${photoParam2}`;
                            img2.onload = function() { checkGalleryImgLayout(img2); checkGalleryImgLayout(img1); scrollToBottom('chat-window-body-container'); };

                            gallery.appendChild(img1);
                            gallery.appendChild(img2);
                            sortGalleryImages(gallery);

                            // Replace the whole photo wrapper so the gallery sits inside .chat-msg-media-wrapper
                            // instead of inside the constrained .chat-msg-photo-wrapper (max-width 480px / max-height 520px).
                            const photoWrapper = singleImg.closest('.chat-msg-photo-wrapper');
                            if (photoWrapper) {
                                photoWrapper.replaceWith(gallery);
                            } else {
                                singleImg.replaceWith(gallery);
                            }
                            applyAlbumGridLayout(gallery);

                            lastBubble.classList.add('has-photo', 'has-gallery');
                            const hadTextBefore = !!lastBubble.querySelector('.chat-msg-text');
                            const willHaveText = hadTextBefore || Boolean(data.message_text);

                            if (willHaveText) {
                                lastBubble.classList.remove('photo-only');
                                lastMsgContainer.classList.remove('photo-only-msg');
                            } else {
                                lastBubble.classList.add('photo-only');
                            }

                            // If the incoming message has text and the bubble doesn't, add it
                            if (data.message_text && !hadTextBefore) {
                                let rawText = stripMessageQuotes(data.message_text);
                                let escapedText = escapeHtml(rawText);
                                escapedText = escapedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
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
                            img.removeAttribute('width');
                            img.removeAttribute('height');
                            img.removeAttribute('style');
                            img.className = 'chat-msg-gallery-img';
                            img.dataset.msgId = data.message_id || '';
                            img.onerror = function() { handlePhotoError(img); };
                            const photoParam = selectedChatClientId ? `?client_id=${selectedChatClientId}` : '';
                            img.src = `/api/photos/${data.photo_id}${photoParam}`;
                            img.onload = function() { checkGalleryImgLayout(img); scrollToBottom('chat-window-body-container'); };

                            existingGallery.appendChild(img);
                            sortGalleryImages(existingGallery);

                            // Update grid layout class based on new photo count
                            const newCount = existingGallery.querySelectorAll('.chat-msg-gallery-img:not(.chat-msg-gallery-img-hidden)').length;
                            const newAlbumClass = newCount > 9 ? 'album-count-many' : `album-count-${newCount}`;
                            existingGallery.className = `chat-msg-gallery ${newAlbumClass}`;

                            // If an older gallery is still inside the constrained photo wrapper, move it into the media wrapper.
                            const photoWrapper = existingGallery.closest('.chat-msg-photo-wrapper');
                            const mediaWrapper = existingGallery.closest('.chat-msg-media-wrapper');
                            if (photoWrapper && mediaWrapper) {
                                mediaWrapper.insertBefore(existingGallery, photoWrapper);
                                photoWrapper.remove();
                            }

                            applyAlbumGridLayout(existingGallery);

                            lastBubble.classList.add('has-gallery');
                            const hadTextBefore = !!lastBubble.querySelector('.chat-msg-text');
                            const willHaveText = hadTextBefore || Boolean(data.message_text);

                            if (willHaveText) {
                                lastBubble.classList.remove('photo-only');
                                lastMsgContainer.classList.remove('photo-only-msg');
                            } else if (!lastBubble.classList.contains('photo-only')) {
                                lastBubble.classList.add('photo-only');
                            }

                            // If the incoming message has text and the bubble doesn't, add it
                            if (data.message_text && !hadTextBefore) {
                                let rawText = stripMessageQuotes(data.message_text);
                                let escapedText = escapeHtml(rawText);
                                escapedText = escapedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
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
    
    const clipboard = e.clipboardData || window.clipboardData;
    const items = clipboard ? clipboard.items : null;
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
});

window.triggerPhotoFileInput = function() {
    const fileInput = document.getElementById('chat-file-input');
    if (fileInput) {
        fileInput.value = '';
        fileInput.click();
    }
};

window.handlePhotoFileSelected = function(input) {
    if (input.files && input.files[0]) {
        const file = input.files[0];
        if (file.type.startsWith('image/')) {
            showPhotoUploadModal(file);
        } else {
            alert('Будь ласка, оберіть файл зображення (PNG, JPG, WEBP, тощо)');
        }
    }
};

// Drag & Drop Photo Files into Chat Window
document.addEventListener('dragover', function(e) {
    if (!selectedChatClientId) return;
    if (e.dataTransfer && e.dataTransfer.types && Array.from(e.dataTransfer.types).includes('Files')) {
        e.preventDefault();
    }
});

document.addEventListener('drop', function(e) {
    if (!selectedChatClientId) return;
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const file = e.dataTransfer.files[0];
        if (file.type.startsWith('image/')) {
            e.preventDefault();
            e.stopPropagation();
            showPhotoUploadModal(file);
        }
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
                if (diffMs > 180000) { // 3 minutes threshold for grouping photos into album
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
    const username = session.username ? `@${session.username.replace(/^@/, '')}` : '—';
    const isCompleted = session.status === 'completed';
    
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
    const hasPhone = cdata.phone && cdata.phone.trim() !== '' && cdata.phone.trim() !== '—';

    let phoneItemHTML = '';
    if (cdata.phone && cdata.phone.trim() !== '' && cdata.phone.trim() !== '—') {
        phoneItemHTML = `
                <!-- Phone -->
                <div class="tg-info-item">
                    <svg class="tg-info-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path>
                    </svg>
                    <div class="tg-info-content">
                        <div class="tg-info-val tg-info-phone">${cdata.phone}</div>
                        <div class="tg-info-label">Номер телефону</div>
                    </div>
                </div>
        `;
    }

    let selectedBanksHTML = '';
    if (allSessionBanks.length > 0) {
        let pendingPills = [];
        let completedPills = [];
        let releasedPills = [];
        let failedPills = [];

        allSessionBanks.forEach(bKey => {
            const historyKey = Object.keys(bankStatuses).find(x => x.toLowerCase() === bKey.toLowerCase());
            const status = historyKey ? bankStatuses[historyKey] : (bKey.toLowerCase() === (session.bank || '').toLowerCase() ? 'active' : 'pending');
            const bName = getBankNameHelper(bKey);

            if (status === 'success' || status === 'completed') {
                completedPills.push(`<span class="tg-bank-pill completed"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg> ${bName}</span>`);
            } else if (status === 'release' || status === 'released') {
                releasedPills.push(`<span class="tg-bank-pill released"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg> ${bName}</span>`);
            } else if (status === 'banned' || status === 'failure' || status === 'failed') {
                failedPills.push(`<span class="tg-bank-pill failed"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> ${bName}</span>`);
            } else {
                pendingPills.push(`<span class="tg-bank-pill pending"><span class="tg-pill-pulse-dot"></span> ${bName}</span>`);
            }
        });

        let sectionsHTML = '';

        if (pendingPills.length > 0) {
            sectionsHTML += `
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <div class="tg-banks-section-title">
                        <span class="tg-banks-dot pending"></span>
                        Обрані / В процесі
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">${pendingPills.join('')}</div>
                </div>
            `;
        }

        if (completedPills.length > 0) {
            const needsBorder = pendingPills.length > 0;
            sectionsHTML += `
                <div style="display: flex; flex-direction: column; gap: 8px; ${needsBorder ? 'margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.08);' : ''}">
                    <div class="tg-banks-section-title completed">
                        <span class="tg-banks-dot completed"></span>
                        Пройдені банки
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">${completedPills.join('')}</div>
                </div>
            `;
        }

        if (releasedPills.length > 0) {
            const needsBorder = pendingPills.length > 0 || completedPills.length > 0;
            sectionsHTML += `
                <div style="display: flex; flex-direction: column; gap: 8px; ${needsBorder ? 'margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.08);' : ''}">
                    <div class="tg-banks-section-title released">
                        <span class="tg-banks-dot released"></span>
                        В поверненні
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">${releasedPills.join('')}</div>
                </div>
            `;
        }

        if (failedPills.length > 0) {
            const needsBorder = pendingPills.length > 0 || completedPills.length > 0 || releasedPills.length > 0;
            sectionsHTML += `
                <div style="display: flex; flex-direction: column; gap: 8px; ${needsBorder ? 'margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.08);' : ''}">
                    <div class="tg-banks-section-title failed">
                        <span class="tg-banks-dot failed"></span>
                        Непройдені / Збій
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">${failedPills.join('')}</div>
                </div>
            `;
        }

        selectedBanksHTML = `
            <div class="tg-banks-card">
                ${sectionsHTML}
            </div>
        `;
    }

    panel.innerHTML = `
        <div class="client-panel-header">
            <div class="client-panel-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #a78bfa;">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                </svg>
                <span>Інформація про клієнта</span>
            </div>
            <button class="client-panel-close-btn" onclick="toggleClientInfoPanel(false)" title="Сховати панель">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>
        
        <div class="client-panel-body" style="padding: 20px 16px;">
            <!-- Hero Section (Avatar + Name + Subtitle) -->
            <div class="client-hero-section" style="display: flex; flex-direction: column; align-items: center; text-align: center; margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.06);">
                <div style="width: 68px; height: 68px; border-radius: 50%; background: linear-gradient(135deg, #3b82f6 0%, #2563eb 50%, #1d4ed8 100%); display: flex; align-items: center; justify-content: center; overflow: hidden; margin-bottom: 12px; font-size: 1.7rem; font-weight: 700; color: #fff; position: relative;">
                    <span id="panel-avatar-placeholder-${session.client_id}" style="display: none;">${displayName.replace(/^@/, '').substring(0, 1).toUpperCase() || 'К'}</span>
                    <img src="/api/avatar/${session.client_id}" style="width:100%; height:100%; object-fit:cover; position:absolute; top:0; left:0;" onerror="this.remove(); const el = document.getElementById('panel-avatar-placeholder-${session.client_id}'); if(el) el.style.display='inline-flex';">
                </div>
                <div class="client-panel-user-name">${displayName}</div>
                <div class="client-panel-status-pill">
                    <span class="${isCompleted ? 'archived' : (session.is_paused ? 'paused' : 'active')}">${isCompleted ? 'Архів' : (session.is_paused ? 'Ручний режим' : 'ШІ Активний')}</span>
                </div>
                
                <button class="btn-open-control-card" onclick="openClientControlCard(${session.client_id})">
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
                <!-- Username -->
                <div class="tg-info-item">
                    <svg class="tg-info-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"></path>
                    </svg>
                    <div class="tg-info-content">
                        <div class="tg-info-val tg-info-username">${username}</div>
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
                        <div class="tg-info-val tg-info-pib">${pib}</div>
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
                        <div class="tg-info-val tg-info-dob">${dob}</div>
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
                        <div class="tg-info-val tg-info-ipn">${ipn}</div>
                        <div class="tg-info-label">ІПН / РНОКПП</div>
                    </div>
                </div>

                ${phoneItemHTML}
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
    
    // Enable manual toggle transitions after initial render
    setTimeout(() => {
        panel.classList.remove('no-transition');
    }, 150);
};

// --- CHAT THEME SELECTOR LOGIC ---
const AVAILABLE_THEMES = [
    { id: 'default', name: 'Cosmic Dark', bg: 'linear-gradient(135deg, #03050c 0%, #8b5cf6 100%)' },
    { id: 'telegram-midnight', name: 'Telegram Midnight', bg: 'linear-gradient(135deg, #0e1621 0%, #2b5278 100%)' },
    { id: 'emerald', name: 'Emerald Mint', bg: 'linear-gradient(135deg, #04140e 0%, #10b981 100%)' },
    { id: 'pitch-black', name: 'OLED Black', bg: 'linear-gradient(135deg, #000000 0%, #a855f7 100%)' }
];

window.initChatTheme = function() {
    document.body.removeAttribute('data-theme');
    const savedTheme = localStorage.getItem('crm_chat_theme') || 'default';
    const chatLayout = document.getElementById('chat-page-layout-container');
    if (chatLayout) {
        if (savedTheme === 'default') {
            chatLayout.removeAttribute('data-theme');
        } else {
            chatLayout.setAttribute('data-theme', savedTheme);
        }
    }
    if (typeof window.updateSettingsThemeCardsActiveState === 'function') {
        window.updateSettingsThemeCardsActiveState(savedTheme);
    }
    if (typeof window.applyChatFont === 'function') {
        window.applyChatFont();
    }
    if (typeof window.initCustomBubbleColors === 'function') {
        window.initCustomBubbleColors();
    }
};

window.setChatTheme = function(themeId) {
    document.body.removeAttribute('data-theme');
    localStorage.setItem('crm_chat_theme', themeId);
    
    const chatLayout = document.getElementById('chat-page-layout-container');
    if (chatLayout) {
        if (themeId === 'default') {
            chatLayout.removeAttribute('data-theme');
        } else {
            chatLayout.setAttribute('data-theme', themeId);
        }
    }
    
    const backdrop = document.getElementById('chat-theme-modal-backdrop');
    if (backdrop) {
        const buttons = backdrop.querySelectorAll('.chat-theme-option-btn');
        buttons.forEach(btn => {
            if (btn.dataset.themeId === themeId) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    if (typeof window.updateSettingsThemeCardsActiveState === 'function') {
        window.updateSettingsThemeCardsActiveState(themeId);
    }
    if (typeof window.applyChatFont === 'function') {
        window.applyChatFont();
    }
};

window.selectThemeFromSettings = function(themeId) {
    window.setChatTheme(themeId);
    if (typeof showToast === 'function') {
        showToast("Тему чату успішно застосовано", "success");
    }
};

window.updateSettingsThemeCardsActiveState = function(currentTheme) {
    const theme = currentTheme || localStorage.getItem('crm_chat_theme') || 'default';
    document.querySelectorAll('.settings-theme-card').forEach(card => {
        if (card.dataset.settingsTheme === theme) {
            card.classList.add('active');
        } else {
            card.classList.remove('active');
        }
    });
};

window.switchThemeInnerSubtab = function(tabName) {
    try {
        localStorage.setItem('active_theme_inner_tab', tabName);
        const btnPresets = document.getElementById('btn-theme-tab-presets');
        const btnCustom = document.getElementById('btn-theme-tab-custom');
        const panePresets = document.getElementById('theme-subpane-presets');
        const paneCustom = document.getElementById('theme-subpane-custom');

        if (tabName === 'presets') {
            if (btnPresets) btnPresets.classList.add('active');
            if (btnCustom) btnCustom.classList.remove('active');
            if (panePresets) {
                panePresets.style.setProperty('display', 'block', 'important');
                panePresets.classList.add('active');
            }
            if (paneCustom) {
                paneCustom.style.setProperty('display', 'none', 'important');
                paneCustom.classList.remove('active');
            }
        } else {
            if (btnCustom) btnCustom.classList.add('active');
            if (btnPresets) btnPresets.classList.remove('active');
            if (paneCustom) {
                paneCustom.style.setProperty('display', 'flex', 'important');
                paneCustom.classList.add('active');
            }
            if (panePresets) {
                panePresets.style.setProperty('display', 'none', 'important');
                panePresets.classList.remove('active');
            }
            if (typeof window.updateLiveBubblePreview === 'function') {
                window.updateLiveBubblePreview();
            }
        }
    } catch(e) {
        console.error("switchThemeInnerSubtab error:", e);
    }
};

window.openThemeSelectorModal = function() {
    let backdrop = document.getElementById('chat-theme-modal-backdrop');
    const currentTheme = localStorage.getItem('crm_chat_theme') || 'default';

    if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.id = 'chat-theme-modal-backdrop';
        backdrop.className = 'chat-theme-modal-backdrop';
        
        let gridHtml = '';
        AVAILABLE_THEMES.forEach(t => {
            const isActive = t.id === currentTheme ? 'active' : '';
            gridHtml += `
                <button class="chat-theme-option-btn ${isActive}" data-theme-id="${t.id}" onclick="setChatTheme('${t.id}')">
                    <div class="chat-theme-circle" style="background: ${t.bg};"></div>
                    <span class="chat-theme-label">${t.name}</span>
                </button>
            `;
        });

        backdrop.innerHTML = `
            <div class="chat-theme-modal" onclick="event.stopPropagation()">
                <div class="chat-theme-modal-header">
                    <span class="chat-theme-modal-title">🎨 Тема чату</span>
                    <button class="chat-theme-modal-close" onclick="closeThemeSelectorModal()">✕</button>
                </div>
                <div class="chat-theme-options-grid">
                    ${gridHtml}
                </div>
            </div>
        `;
        backdrop.onclick = function() {
            closeThemeSelectorModal();
        };
        document.body.appendChild(backdrop);
    } else {
        const buttons = backdrop.querySelectorAll('.chat-theme-option-btn');
        buttons.forEach(btn => {
            if (btn.dataset.themeId === currentTheme) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    requestAnimationFrame(() => {
        backdrop.classList.add('active');
    });

    const dropdown = document.getElementById('chat-actions-dropdown');
    if (dropdown) dropdown.classList.remove('active');
};

window.closeThemeSelectorModal = function() {
    const backdrop = document.getElementById('chat-theme-modal-backdrop');
    if (backdrop) {
        backdrop.classList.remove('active');
    }
};

document.addEventListener('DOMContentLoaded', () => {
    window.initChatTheme();
});
window.initChatTheme();



