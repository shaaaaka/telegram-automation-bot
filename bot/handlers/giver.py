import re
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import get_giver_chat_id, get_admin_id
import bot.database as db

router = Router()

async def giver_chat_filter(message: Message) -> bool:
    if message.chat.id != get_giver_chat_id():
        return False
    from bot.handlers.verifier import is_verifier_action
    if await is_verifier_action(message):
        return False
    return True

@router.message(giver_chat_filter)
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
            expected_len = await get_expected_code_length(line_info['bank'])
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
        
        button_text = f"+{line_info['phone_number']} ({bank_name})" if line_info else f"Клієнт {s['client_id']} ({bank_name})"
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

    from aiogram.types import ReplyKeyboardRemove
    # Відправляємо клієнту
    await db.increment_session_sent_codes_count(client_id)
    await bot.send_message(
        chat_id=client_id,
        text=f"`{code}`",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

    # Оновлюємо статус сесії назад на 'number_assigned' (щоб клієнт міг зробити запит знову)
    await db.set_session_status(client_id, 'number_assigned')

    # Перевіряємо чи це перший надісланий код
    import asyncio
    updated_session = await db.get_session(client_id)
    if updated_session and updated_session.get('sent_codes_count') == 1:
        asyncio.create_task(send_first_code_helper_delayed(bot, client_id, line_id, bank_name))

    # Звітуємо адміну
    phone_str = f" (+{line_info['phone_number']})" if line_info else ""
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"Код {code} автоматично переслано користувачу @{username}{phone_str} ({bank_name}).\n"
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

    from aiogram.types import ReplyKeyboardRemove
    # Відправляємо клієнту
    await bot.send_message(
        chat_id=client_id,
        text="Немає коду, запросіть новий код в додатку банка",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

    # Оновлюємо статус сесії назад на 'number_assigned'
    await db.set_session_status(client_id, 'number_assigned')

    # Звітуємо адміну
    phone_str = f" (+{line_info['phone_number']})" if line_info else ""
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"Гівер надіслав відмову (`-`) для користувача @{username}{phone_str} ({bank_name}).\n"
            f"Статус сесії скинуто на 'Номер видано'."
        ),
        parse_mode="Markdown"
    )

async def send_first_code_helper_delayed(bot: Bot, client_id: int, line_id: int, bank_name: str):
    """Надсилає допоміжне повідомлення та шаблони через 1 хвилину після відправки першого коду"""
    import asyncio
    await asyncio.sleep(60)
    try:
        # Перевіряємо чи сесія все ще активна та не була змінена
        session = await db.get_session(client_id)
        if not session or session.get('status') == 'completed' or session.get('line_id') != line_id:
            return
            
        is_amobank = bank_name.lower().strip() == "amobank"
        is_bank_kd = bank_name and "bank.kd" in bank_name.lower()

        if is_bank_kd:
            import os
            from aiogram.types import FSInputFile
            cards_photo_path = os.path.join(os.path.dirname(__file__), "..", "resources", "images", "bank.kd_cards_instruction.png")
            if os.path.exists(cards_photo_path):
                try:
                    await bot.send_photo(
                        chat_id=client_id,
                        photo=FSInputFile(cards_photo_path),
                        caption='В кінці при виборі картки, обирайте "Мультивалютна"'
                    )
                except Exception as e:
                    import logging
                    logging.error(f"Error sending bank.kd card choice instruction photo: {e}")
            return

        text = "Реєструйте як наче під себе робите"
        if is_amobank:
            text += ", або якщо що, то ось готовий шаблон реєстрації:"
            
        # Надсилаємо текст клієнту
        await bot.send_message(chat_id=client_id, text=text)
        
        # Якщо це AmoBank, надсилаємо 4 скріншоти
        if is_amobank:
            from aiogram.types import InputMediaPhoto, FSInputFile
            import os
            
            images_dir = os.path.join(os.path.dirname(__file__), "..", "resources", "images")
            media = []
            for i in range(1, 5):
                img_path = os.path.join(images_dir, f"amobank_step{i}.png")
                if os.path.exists(img_path):
                    media.append(InputMediaPhoto(media=FSInputFile(img_path)))
            
            if media:
                sent_messages = await bot.send_media_group(chat_id=client_id, media=media)
                for i, msg in enumerate(sent_messages):
                    photo_id = msg.photo[-1].file_id if msg.photo else None
                    # Логуємо фотографії в чат-історію
                    await db.log_chat_message(client_id, 'bot', None, photo_id)
                    
    except Exception as e:
        import logging
        logging.error(f"Error in send_first_code_helper_delayed: {e}")
