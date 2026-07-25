# План доведення візуала чату CRM

## 1. Короткий аналіз

- Стек: FastAPI + Jinja2 (`web/templates/index.html`) + vanilla JS (`web/static/js/chat.js`, `control.js`, `main.js`) + один CSS (`web/static/css/style.css`).
- Чат розташований у вкладці **Чати** (`#tab-content-chat`) і має 3 колонки: бічна панель (`chat-sidebar`), вікно чату (`chat-window`) та інформаційна панель клієнта (`chat-client-info-panel`).
- Логіка чату — у `web/static/js/chat.js`, стилі — у `web/static/css/style.css`, розмітка — у `web/templates/index.html`.
- Бекенд: `GET/POST/DELETE /api/sessions/{client_id}/...`, WebSocket `/ws/chat`.

## 2. Що вже працює (не чіпати без причини)

- Завантаження активних/архівних чатів, пошук, прев'ю останнього повідомлення, лічильники непрочитаних.
- Рендеринг повідомлень, одиночних фото, галерей, цитат, відповідей, автоскрол вниз, floating date badge.
- WebSocket для нових повідомлень, очищення, видалення сесії, банів, перемикання AI.
- Відправка тексту/фото, автодоповнення шаблонів (`/...`), перемикання AI, панель інформації про клієнта, селектор тем.

## 3. Головні візуальні розбіжності, які треба виправити

1. **Два паралельні набори стилів повідомлень.** У CSS є `.chat-message` (з `.message-text`, `.message-time`) і окремо `.chat-msg-container`/`.chat-msg-bubble`/`.chat-msg-text`/`.chat-msg-time-inline`. JS реально генерує лише другий набір. Перший — мертвий код.
2. **Повідомлення не вирівнюються праворуч для bot/operator/admin.** У `renderSingleChatMessage` `.chat-msg-body-row` має інлайн `justify-content: flex-start !important; flex-direction: row !important;`, тому всі бабли ліві.
3. **Хвостики баблів однакові.** Для client, bot, operator, admin задано border-radius `18px 18px 18px 6px`. Outgoing має бути дзеркальним: `18px 18px 6px 18px`.
4. **Розбіжності імен класів:**
   - HTML/JS використовують `chat-client-info-panel`, а частина CSS/медіа-запитів — `chat-details-sidebar`.
   - JS генерує `.chat-date-divider-pill`, CSS стилізує `.chat-date-pill`.
   - JS генерує `.chat-msg-time-inline`, теми CSS посилаються на `.chat-msg-time`.
5. **Заголовки повідомлень приховані.** JS створює `.chat-msg-header` з `.badge-ai`/`.badge-operator`, але CSS має `.chat-msg-container .chat-msg-header { display: none !important; }`.
6. **Мобільні стилі не співпадають.** Медіа-запити посилаються на `.msg-client`/`.msg-admin`/`.msg-bot` — класів, яких JS не створює.
7. **Теми посилаються на неіснуючі класи.** У CSS тем є `.chat-msg-author`, `.chat-msg-quote-author`, `.client-panel-user-name`, `.client-panel-status-pill`, `.btn-open-control-card`, `.tg-banks-*` — цих класів у DOM немає.
8. **Модальне вікно `#chat-modal` мертве.** Воно є в HTML/CSS, але `openChatModal` у `control.js` просто перемикає на вкладку `chat`, а `closeChatModal`/`sendModalChatMessage`/`onModalMessageInput` не визначені.
9. **`.chat-logs-container` стилі не використовуються у активному чаті.** Вони залишилися від попередньої/модальної реалізації.
10. **Права інформаційна панель не стикується з layout-ом.** Медіа-запити для 3-колонкового layout використовують не той клас і не враховують mobile-перемикання.

## 4. Покроковий план

### Крок 1. Прибрати мертвий код
- У `web/static/css/style.css` видалити/закоментувати правила `.chat-message`, `.msg-client`, `.msg-admin`, `.msg-bot`, `.chat-logs-container` (якщо не планується окрема модалка), `.chat-modal-*` (якщо не планується модалка).
- У `web/templates/index.html` видалити блок `#chat-modal`, якщо не планується його використання; інакше реалізувати `openChatModal`, `closeChatModal`, `sendModalChatMessage`, `onModalMessageInput` у `web/static/js/chat.js`.

### Крок 2. Уніфікувати імена класів
- `.chat-date-pill` -> `.chat-date-divider-pill` у CSS (або навпаки в JS).
- `.chat-msg-time` -> `.chat-msg-time-inline` у CSS (особливо у темах).
- `.chat-details-sidebar` -> `.chat-client-info-panel` у всіх CSS-правилах та медіа-запитах.
- Перевірити, що JS не створює `.chat-message`.

### Крок 3. Вирівняти бабли та аватари
- У `renderSingleChatMessage` прибрати з `.chat-msg-body-row` інлайн `flex-direction: row !important; justify-content: flex-start !important;`. Можна залишити `position: relative;` і `gap`.
- Додати у CSS:
  - `.chat-msg-container` — `display: flex; flex-direction: column;`.
  - `.chat-msg-container.client { align-items: flex-start; }`
  - `.chat-msg-container.bot, .chat-msg-container.operator, .chat-msg-container.admin { align-items: flex-end; }`
  - `.chat-msg-container.client .chat-msg-body-row { flex-direction: row; justify-content: flex-start; }`
  - `.chat-msg-container.bot .chat-msg-body-row, .chat-msg-container.operator .chat-msg-body-row, .chat-msg-container.admin .chat-msg-body-row { flex-direction: row-reverse; justify-content: flex-end; }`
- Border-radius:
  - client: `18px 18px 18px 6px;`
  - bot/operator/admin: `18px 18px 6px 18px;`
  - `.same-sender-next .chat-msg-bubble`: `border-radius: 18px;`
- Перевірити `.chat-msg-avatar` при `row-reverse`: аватар має залишатися на зовнішньому краю, бабло — біля краю вікна. Перевірити `.no-avatar` margins, щоб бабла не стрибали.

### Крок 4. Показати або прибрати заголовки повідомлень
- Варіант A: прибрати `.chat-msg-container .chat-msg-header { display: none !important; }` і стилізувати `.badge-ai`/`.badge-operator` (стилі вже є).
- Варіант B: видалити генерацію `headerHtml` у `renderSingleChatMessage` і прибрати CSS для `.chat-msg-header`/`.badge-*`.
- Головне — узгодженість між DOM і CSS.

### Крок 5. Правильний 3-колонковий layout
- `.chat-page-layout` — `display: flex; height: 100%; overflow: hidden;`.
- `.chat-client-info-panel` — `width: 320px; margin-right: -320px; opacity: 0; visibility: hidden; transition: ...;`.
- `.chat-client-info-panel.visible` — `margin-right: 0; opacity: 1; visibility: visible;`.
- Перевірити, що `.chat-window` займає flex-grow, а приховування панелі не викликає горизонтальний скрол.
- Медіа-запити (max-width: 768px/900px):
  - `.chat-page-layout:not(.chat-selected) .chat-sidebar` — показати; `.chat-window`, `.chat-client-info-panel` — сховати.
  - `.chat-page-layout.chat-selected .chat-sidebar`, `.chat-client-info-panel` — сховати; `.chat-window` — flex, width 100%.
  - `.chat-back-btn` показувати лише на mobile.
  - `body.hide-nav-bar .chat-page-layout` має займати весь viewport без зсувів.

### Крок 6. Теми
- `setChatTheme` вже пише `data-theme` на `.chat-page-layout` — залишити.
- Виправити CSS тем:
  - замінити `.chat-msg-time` на `.chat-msg-time-inline`;
  - або додати в JS класи `.chat-msg-author`/`.chat-msg-quote-author`, або видалити ці CSS-правила;
  - або додати в `renderClientInfoPanel` класи `.client-panel-user-name`, `.client-panel-status-pill`, `.btn-open-control-card`, `.tg-banks-*`, або видалити непотрібні правила тем.
- Забезпечити, щоб теми могли перекривати базові кольори баблів (можливо, зменшити кількість `!important` у базових стилях `.chat-msg-bubble`).
- Доповнити теми `telegram-midnight` та `emerald`, якщо потрібно.

### Крок 7. Фото, галереї, лайтбокс
- Перевірити `.chat-msg-gallery.album-count-*` layout (2, 3, 4, 5-6, 7-9, many).
- Перевірити `.album-stack-vertical` для двох широких фото.
- `.chat-msg-bubble.has-photo.photo-only` має мати border-radius, щоб фото не вилазило.
- Лайтбокс `#image-lightbox` вже є; перевірити `openLightbox`/`closeLightbox`.

### Крок 8. Полірування та тестування
- Підняти `?v=` cache-buster у `index.html` для `style.css` та `chat.js`.
- Протестувати на десктопі (Chrome, Firefox) та мобільному емуляторі (390–430 px, iPhone SE/14).
- Перевірити WebSocket: нове повідомлення з'являється, бабли групуються, аватар ховається для same-sender, скрол працює.
- Перевірити відправку фото, відповідь/цитата, перемикання AI, панель інформації, селектор тем.

## 5. API / WebSocket контракт

- `GET /api/sessions/{client_id}/chat` — JSON-масив логів з полями: `id`, `client_id`, `sender` (`client`/`bot`/`admin`/`operator`), `message_text`, `photo_id`, `photo_ids` (групування в `groupPhotoLogs`), `message_id`, `reply_to_message_id`, `created_at`.
- `POST /api/sessions/{client_id}/message` — `{message, reply_to_message_id?}`.
- `POST /api/sessions/{client_id}/photo` — multipart `file`, опціонально `caption`.
- `POST /api/sessions/{client_id}/toggle-ai` — повертає `{is_paused: bool}`.
- `POST /api/sessions/{client_id}/clear-chat`.
- `DELETE /api/sessions/{client_id}`.
- `GET /api/sessions/completed` — архівні сесії.
- `WS /ws/chat` — події:
  - `new_message`: `{type, client_id, sender, message_text, photo_id, message_id, reply_to_message_id, created_at}`
  - `chat_cleared`, `session_deleted`, `user_banned`, `user_unbanned`, `ai_toggled`
- Медіа: `/api/photos/{photo_id}`, `/api/avatar/{client_id}`.

## 6. Обмеження / не чіпати

- Не змінювати структуру таблиці `chat_logs` та основну логіку логування.
- Не змінювати ендпоінти FastAPI без узгодження.
- Не додавати JS-фреймворки; залишити vanilla JS/CSS.
- Використовувати існуючі CSS-змінні: `--accent-primary`, `--accent-success`, `--accent-danger`, `--text-main`, `--text-muted`, `--panel-bg`, `--panel-border`, `--card-bg`, `--card-border`.
- Зберігати українську мову інтерфейсу.

## 7. Критерії прийняття

- [ ] Відкриття вкладки **Чати**: sidebar + window + info panel відображаються без зсувів; панель відкривається/закривається по кнопці.
- [ ] Вибір клієнта: повідомлення `client` ліворуч, `bot`/`operator`/`admin` праворуч; аватар показується для першого повідомлення в групі, ховається для наступних.
- [ ] Бабли мають правильні кольори та напрямні "хвостики".
- [ ] Фото, галереї, цитати, відповіді, час повідомлення відображаються коректно.
- [ ] Мобільна версія: перемикання між списком і чатом, back button працює, input не втрачається за клавіатурою.
- [ ] Теми змінюють кольори всіх трьох панелей та баблів.
- [ ] WebSocket доставляє нові повідомлення без миготіння/дублювання.
- [ ] Немає 404/500 при завантаженні чату, фото, аватарів.

---

## Prompt для іншої AI (EN, copy-paste ready)

```
You are a frontend developer working on a FastAPI + vanilla JS admin panel.
Fix and finish the visual layer of the CRM chat (tab "Чати" / #tab-content-chat).

Files to edit:
- web/templates/index.html
- web/static/css/style.css
- web/static/js/chat.js
- optionally control.js if you remove the dead chat modal

Existing logic already works: loading active/archived chat list, message rendering, photos/galleries, quotes/replies, WebSocket updates, sending text/photo, AI toggle, client info panel, theme selector.

Your job is only to make the visual layer consistent and correct:
1. Remove dead CSS: .chat-message, .msg-client, .msg-admin, .msg-bot, .chat-logs-container (if not used by real modal), .chat-modal-* (if not used). Remove the dead #chat-modal HTML or implement its JS.
2. Unify class names: .chat-client-info-panel (not .chat-details-sidebar), .chat-date-divider-pill (not .chat-date-pill), .chat-msg-time-inline (not .chat-msg-time).
3. Fix bubble alignment: client messages left-aligned, bot/operator/admin right-aligned. Use flex-direction row-reverse for outgoing. Fix bubble tails (border-radius mirrored: client 18px 18px 18px 6px, outgoing 18px 18px 6px 18px, same-sender-next all rounded).
4. Remove inline `!important` flex styles from .chat-msg-body-row in renderSingleChatMessage; control layout via CSS classes.
5. Decide what to do with message headers (.chat-msg-header / .badge-ai / .badge-operator): either show and style them, or remove generation and CSS. Do not leave hidden generated DOM.
6. Fix right info panel layout (chat-client-info-panel) for desktop and mobile; update all media queries.
7. Update theme CSS: replace .chat-msg-time with .chat-msg-time-inline, and either add missing classes (.chat-msg-author, .chat-msg-quote-author, .client-panel-user-name, .client-panel-status-pill, .btn-open-control-card, .tg-banks-*) to the JS-rendered HTML or remove those unused theme rules.
8. Polish photos/galleries/lightbox and mobile safe-area behavior.
9. Bump ?v= cache-busters in index.html for style.css and chat.js.
10. Verify on desktop and mobile emulators, and via WebSocket new-message flow.

Keep the Ukrainian UI text. Do not change backend endpoints or DB schema. Do not add frameworks. Use existing CSS variables.

Acceptance criteria are in CHAT_UI_PLAN.md section 7.
```
