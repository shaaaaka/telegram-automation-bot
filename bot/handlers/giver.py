import re
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import GIVER_CHAT_ID, ADMIN_ID
import bot.database as db

router = Router()

@router.message(F.chat.id == GIVER_CHAT_ID)
async def handle_giver_message(message: Message, bot: Bot):
    """Обробник повідомлень від постачальника кодів"""
    text = message.text
    if not text:
        return

    # Перевіряємо, чи це відмова (мінус або слова про відсутність коду)
    from bot.handlers.client import is_no_code_text, REFUSAL_KEYWORDS
    is_refusal = (re.search(r'(?:^|\s)-(?:\s|$)', text) is not None) or is_no_code_text(text)

    code = None
    if not is_refusal:
        # Шукаємо код у повідомленні (тільки 4 або 6 цифр, 5 цифр ігноруємо)
        match = re.search(r'\b(\d{4}|\d{6})\b', text)
        if not match:
            return  # Якщо це не мінус/відмова і немає коду, ігноруємо повідомлення
        code = match.group(0)

    # Отримуємо всі сесії, які зараз чекають на код
    waiting_sessions = await db.get_all_waiting_sessions()
    if not waiting_sessions:
        # Немає клієнтів, які чекають на код
        return

    # --- Сценарій: обробка відмови від гівера (мінус або слова-відмови) ---
    if is_refusal:
        matched_session = None
        
        # Спробуємо знайти відповідність за текстом (номер лінії або назва банку)
        search_text = text.replace("-", "").strip()
        keywords_to_remove = REFUSAL_KEYWORDS
        search_lower = search_text.lower()
        for kw in keywords_to_remove:
            search_lower = search_lower.replace(kw, "")
        search_text = search_lower.strip()

        if search_text:
            for session in waiting_sessions:
                line_id = session['line_id']
                line_info = await db.get_line(line_id) if line_id else None
                
                if line_info:
                    line_pattern = rf"\b{line_id}\b"
                    bank_name = line_info['bank'].lower()
                    if re.search(line_pattern, search_text) or bank_name in search_text.lower():
                        matched_session = (session, line_info)
                        break

        # Якщо не знайдено за текстом, але очікує лише один клієнт
        if not matched_session and len(waiting_sessions) == 1:
            session = waiting_sessions[0]
            line_info = await db.get_line(session['line_id']) if session['line_id'] else None
            matched_session = (session, line_info)

        if matched_session:
            session, line_info = matched_session
            await handle_giver_refusal(bot, session, line_info)
        else:
            # Декілька сесій і не вдалося розпізнати автоматично, повідомляємо адміна
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"Отримано відмову від гівера (`{text}`), але в черзі очікування декілька клієнтів і лінію не розпізнано.\n"
                    f"Будь ласка, скасуйте очікування коду вручну."
                )
            )
        return

    # Фільтруємо сесії за очікуваною довжиною коду
    from bot.config import get_expected_code_length
    
    valid_sessions = []
    for s in waiting_sessions:
        line_id = s['line_id']
        line_info = await db.get_line(line_id) if line_id else None
        if line_info:
            expected_len = get_expected_code_length(line_info['bank'])
            if expected_len is not None and len(code) != expected_len:
                continue
        valid_sessions.append(s)

    if not valid_sessions:
        return

    # --- Сценарій 2: Автоматичний пошук відповідності за текстом для коду ---
    search_text = text.replace(code, "").strip()
    
    matched_session = None
    for session in valid_sessions:
        line_id = session['line_id']
        line_info = await db.get_line(line_id) if line_id else None
        
        if line_info:
            line_pattern = rf"\b{line_id}\b"
            bank_name = line_info['bank'].lower()
            
            if re.search(line_pattern, search_text) or bank_name in search_text.lower():
                matched_session = (session, line_info)
                break

    if matched_session:
        session, line_info = matched_session
        await send_code_to_client(bot, session, line_info, code)
        return

    # --- Сценарій 1: Тільки один активний запит у черзі з відповідною довжиною ---
    if len(valid_sessions) == 1:
        session = valid_sessions[0]
        line_info = await db.get_line(session['line_id']) if session['line_id'] else None
        await send_code_to_client(bot, session, line_info, code)
        return

    # --- Сценарій 3: Декілька активних запитів і немає явного співпадіння в тексті ---
    try:
        import datetime
        from web.app import unrouted_codes
        if not any(c['code'] == code for c in unrouted_codes):
            unrouted_codes.append({
                "code": code,
                "received_at": datetime.datetime.now().strftime("%H:%M:%S")
            })
    except Exception as e:
        print(f"Помилка додавання коду до веб-панелі: {e}")

    keyboard_buttons = []
    for s in valid_sessions:
        line_info = await db.get_line(s['line_id']) if s['line_id'] else None
        bank_name = line_info['bank'] if line_info else "Невідомий банк"
        line_id = s['line_id']
        
        button_text = f"Line {line_id} ({bank_name})"
        callback_data = f"route_{s['client_id']}_{code}"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"Отримано новий код від гівера: `{code}`\n\n"
            f"У черзі очікування декілька клієнтів з відповідною довжиною коду. Будь ласка, оберіть лінію для пересилання:"
        ),
        reply_markup=markup,
        parse_mode="Markdown"
    )

async def send_code_to_client(bot: Bot, session: dict, line_info: dict, code: str):
    """Допоміжна функція для відправки коду клієнту (сесія залишається активною)"""
    client_id = session['client_id']
    username = session['username']
    line_id = session['line_id']
    bank_name = line_info['bank'] if line_info else "Банк"

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    client_kbd = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Запросити SMS-код")]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )

    # Відправляємо клієнту
    await bot.send_message(
        chat_id=client_id,
        text=f"Ваш SMS-код для банку {bank_name}:\n\n`{code}`",
        reply_markup=client_kbd,
        parse_mode="Markdown"
    )

    # Оновлюємо статус сесії назад на 'number_assigned' (щоб клієнт міг зробити запит знову)
    await db.set_session_status(client_id, 'number_assigned')

    # Звітуємо адміну
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"Код {code} автоматично переслано користувачу @{username} (Line {line_id} - {bank_name}).\n"
            f"Сесія залишається активною для наступних запитів."
        ),
        parse_mode="Markdown"
    )

async def handle_giver_refusal(bot: Bot, session: dict, line_info: dict):
    """Обробник відмови від гівера (скидає статус сесії на 'number_assigned' та інформує клієнта/адміна)"""
    client_id = session['client_id']
    username = session['username']
    line_id = session['line_id']
    bank_name = line_info['bank'] if line_info else "Банк"

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    client_kbd = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Запросити SMS-код")]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )

    # Відправляємо клієнту
    await bot.send_message(
        chat_id=client_id,
        text="Немає коду, запросіть новий код в додатку банка",
        reply_markup=client_kbd,
        parse_mode="Markdown"
    )

    # Оновлюємо статус сесії назад на 'number_assigned'
    await db.set_session_status(client_id, 'number_assigned')

    # Звітуємо адміну
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"Гівер надіслав відмову (`-`) для користувача @{username} (Line {line_id} - {bank_name}).\n"
            f"Статус сесії скинуто на 'Номер видано'."
        ),
        parse_mode="Markdown"
    )
