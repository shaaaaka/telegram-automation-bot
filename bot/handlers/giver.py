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

    # Шукаємо код у повідомленні (послідовність від 4 до 8 цифр)
    match = re.search(r'\b\d{4,8}\b', text)
    if not match:
        return  # Якщо коду немає в повідомленні, ігноруємо його

    code = match.group(0)

    # Отримуємо всі сесії, які зараз чекають на код
    waiting_sessions = await db.get_all_waiting_sessions()
    if not waiting_sessions:
        # Немає клієнтів, які чекають на код. Можливо, це повідомлення не для бота
        return

    # --- Сценарій 2: Автоматичний пошук відповідності за текстом ---
    # Очищаємо текст повідомлення від самого коду, щоб уникнути помилкового співпадіння
    # (наприклад, якщо код 4325 містить у собі число 32, це не має вважатися вибором Line 32)
    search_text = text.replace(code, "").strip()
    
    matched_session = None
    for session in waiting_sessions:
        line_id = session['line_id']
        line_info = await db.get_line(line_id) if line_id else None
        
        if line_info:
            # Перевіряємо чи є номер лінії як окреме число або назва банку в залишку тексту
            line_pattern = rf"\b{line_id}\b"
            bank_name = line_info['bank'].lower()
            
            if re.search(line_pattern, search_text) or bank_name in search_text.lower():
                matched_session = (session, line_info)
                break

    if matched_session:
        session, line_info = matched_session
        await send_code_to_client(bot, session, line_info, code)
        return

    # --- Сценарій 1: Тільки один активний запит у черзі ---
    if len(waiting_sessions) == 1:
        session = waiting_sessions[0]
        line_info = await db.get_line(session['line_id']) if session['line_id'] else None
        await send_code_to_client(bot, session, line_info, code)
        return

    # --- Сценарій 3: Декілька активних запитів і немає явного співпадіння в тексті ---
    # Додаємо у список нерозподілених кодів для веб-панелі
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

    # Надсилаємо запит Адміну з вибором лінії
    keyboard_buttons = []
    for s in waiting_sessions:
        line_info = await db.get_line(s['line_id']) if s['line_id'] else None
        bank_name = line_info['bank'] if line_info else "Невідомий банк"
        line_id = s['line_id']
        
        button_text = f"Line {line_id} ({bank_name})"
        # callback_data: route_{client_id}_{code}
        callback_data = f"route_{s['client_id']}_{code}"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"Отримано новий код від гівера: `{code}`\n\n"
            f"У черзі очікування декілька клієнтів. Будь ласка, оберіть лінію для пересилання:"
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

    # Відправляємо клієнту
    await bot.send_message(
        chat_id=client_id,
        text=f"Ваш SMS-код для банку {bank_name}:\n\n`{code}`",
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
