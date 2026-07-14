import asyncio
import logging
from aiogram import Bot
from aiogram.types import FSInputFile, ReplyKeyboardRemove, InlineKeyboardButton

import bot.database as db
from bot.config import get_template_photo, DEFAULT_BANK_ORDER

logger = logging.getLogger(__name__)


def build_bank_selection_rows(
    all_banks: list,
    client_id: int,
    selected: list | set | None = None,
    passed_banks: list | set | None = None,
    banned_banks: list | set | None = None,
    per_row: int = 2
) -> list:
    """Формує рядки Inline-кнопок для вибору банків."""
    selected = set(selected or [])
    passed_banks = set(passed_banks or [])
    banned_banks = set(banned_banks or [])

    keyboard_buttons = []
    row = []
    for bank in all_banks:
        suffix = ""
        if bank in passed_banks:
            suffix = " (✅ Пройдено)"
        elif bank in banned_banks:
            suffix = " (❌ Бан)"
        checkbox = "[x]" if bank in selected else "[ ]"
        button_text = f"{checkbox} {bank}{suffix}"
        callback_data = f"toggle_{client_id}_{bank}"
        row.append(InlineKeyboardButton(text=button_text, callback_data=callback_data))
        if len(row) == per_row:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)

    return keyboard_buttons


async def get_all_banks_for_selection() -> list:
    """Повертає об'єднаний та відсортований список банків за замовчуванням + з бази."""
    unique_banks_db = await db.get_unique_banks()
    return list(dict.fromkeys(DEFAULT_BANK_ORDER + unique_banks_db))


async def send_line_assignment_messages(client_id: int, line_id: int, bot: Bot, delay_before_phone: float = 0.0) -> dict | None:
    """Відправляє клієнту інструкцію банку та номер телефону після призначення лінії.

    Повертає {'session': ..., 'line_info': ..., 'client_msg_id': ...} або None у разі помилки.
    При помилці відкочує призначення лінії.
    """
    line_info = await db.get_line(line_id)
    if not line_info:
        return None

    session = await db.get_session(client_id)
    if not session or session.get('line_id') != line_id:
        return None

    bank_name = line_info['bank']
    phone_number = line_info['phone_number'].lstrip('+')

    # Видаляємо повідомлення очікування номера
    if session.get('waiting_message_id'):
        try:
            await bot.delete_message(chat_id=client_id, message_id=session['waiting_message_id'])
        except Exception:
            pass

    # Перевіряємо чи банк вже був сповіщений
    notified_banks_str = session.get('notified_banks') or ''
    notified_list = [b.strip() for b in notified_banks_str.split(",") if b.strip()]
    is_already_notified = bank_name in notified_list

    try:
        if is_already_notified:
            await bot.send_message(
                chat_id=client_id,
                text="Ось новий номер телефону по якому робити реєстрацію:"
            )
        else:
            import os
            key, template = await db.get_bank_template_with_key_db(bank_name)
            if template:
                photo_path = None
                if template.get('screenshot_path'):
                    # Convert web URL path (e.g. /static/...) to local filesystem path (e.g. web/static/...)
                    rel_path = template['screenshot_path'].lstrip('/')
                    photo_path = os.path.join("web", rel_path)
                
                if not photo_path or not os.path.exists(photo_path):
                    photo_path = get_template_photo(key) if key else None
                    
                caption_text = template['text']
                instruction_msg = None
                if photo_path and os.path.exists(photo_path):
                    try:
                        instruction_msg = await bot.send_photo(
                            chat_id=client_id,
                            photo=FSInputFile(photo_path),
                            caption=caption_text
                        )
                    except Exception as e:
                        logger.error("Помилка надсилання фото шаблону банку: %s", e)
                        try:
                            instruction_msg = await bot.send_message(chat_id=client_id, text=caption_text)
                        except Exception:
                            pass
                else:
                    try:
                        instruction_msg = await bot.send_message(chat_id=client_id, text=caption_text)
                    except Exception as e:
                        logger.error("Помилка надсилання тексту шаблону банку: %s", e)

                if instruction_msg:
                    try:
                        await db.update_session_instruction_message_id(client_id, instruction_msg.message_id)
                    except Exception as e:
                        logger.error("Помилка оновлення instruction_message_id в БД: %s", e)

            await bot.send_message(
                chat_id=client_id,
                text="Реєстрація робиться за моїм номером телефону, скажете коли потрібен буде СМС код"
            )
            await db.add_notified_bank(client_id, bank_name)

        # Невелика затримка перед надсиланням номера (якщо потрібно)
        if delay_before_phone > 0:
            await asyncio.sleep(delay_before_phone)

        client_msg = await bot.send_message(
            chat_id=client_id,
            text=f"`+{phone_number}`",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        await db.update_session_message_id(client_id, client_msg.message_id)
    except Exception as e:
        logger.error("Помилка надсилання повідомлення клієнту: %s", e)
        # Відкочуємо призначення, щоб не лишити лінію "зайнятою" без повідомлення
        await db.set_line_status(line_id, 'available')
        import aiosqlite
        async with aiosqlite.connect(db.DB_FILE) as db_conn:
            await db_conn.execute(
                "UPDATE sessions SET line_id = NULL, status = 'registered' WHERE client_id = ?",
                (client_id,)
            )
            await db_conn.commit()
        return None

    return {
        "session": session,
        "line_info": line_info,
        "client_msg_id": client_msg.message_id,
    }
