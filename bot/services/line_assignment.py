import asyncio
import logging
from aiogram import Bot
from aiogram.types import FSInputFile, ReplyKeyboardRemove, InlineKeyboardButton

import bot.database as db
from bot.config import get_template_photo, DEFAULT_BANK_ORDER, normalize_bank_name

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
    """Повертає об'єднаний та відсортований список активних банків."""
    unique_banks_db = await db.get_unique_banks()
    combined_banks = list(dict.fromkeys(DEFAULT_BANK_ORDER + unique_banks_db))

    # Фільтруємо неактивні банки
    templates = await db.get_all_bank_templates()
    active_banks = []
    for bank in combined_banks:
        is_active = True
        name_norm = normalize_bank_name(bank)
        for key, val in templates.items():
            key_norm = normalize_bank_name(key)
            if key_norm == name_norm or key_norm in name_norm or name_norm in key_norm:
                if val.get('is_active') == 0:
                    is_active = False
                break
        if is_active:
            active_banks.append(bank)

    return active_banks


async def send_line_assignment_messages(client_id: int, line_id: int, bot: Bot, delay_before_phone: float = 0.0, state = None) -> dict | None:
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
        key, template = await db.get_bank_template_with_key_db(bank_name)
        allow_relink = template.get('allow_relink') if template else 0

        # Якщо дозволено перев'яз і банк ще не сповіщений, пропонуємо вибір
        if allow_relink == 1 and not is_already_notified:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🆕 Нова реєстрація", callback_data=f"relink_choice_fresh_{line_id}_{key}"),
                    InlineKeyboardButton(text="🔄 Перев'яз акаунту", callback_data=f"relink_choice_relink_{line_id}_{key}")
                ]
            ])
            
            display_name = template.get('display_name') or bank_name
            choice_msg = await bot.send_message(
                chat_id=client_id,
                text=f"Ви будете проходити нову реєстрацію чи перев'яз існуючого акаунту для банку {display_name}?",
                reply_markup=markup
            )
            
            if state:
                from bot.handlers.client_helpers import RegistrationStates
                await state.update_data(relink_choice_msg_id=choice_msg.message_id, bank_name=key, assign_line_id=line_id)
                await state.set_state(RegistrationStates.waiting_relink_choice)
                
            return {
                "session": session,
                "line_info": line_info,
                "client_msg_id": choice_msg.message_id,
            }

        # Інакше йдемо за стандартним флоу надсилання телефону
        client_msg_id = await send_assigned_phone_to_client(client_id, line_id, bot, delay_before_phone=delay_before_phone)
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
        "client_msg_id": client_msg_id,
    }

async def send_assigned_phone_to_client(client_id: int, line_id: int, bot: Bot, delay_before_phone: float = 0.0, is_relink: bool = False) -> int:
    line_info = await db.get_line(line_id)
    if not line_info:
        raise ValueError("Line info not found")
    session = await db.get_session(client_id)
    if not session:
        raise ValueError("Session not found")

    bank_name = line_info['bank']
    phone_number = line_info['phone_number'].lstrip('+')

    if is_relink:
        key, template = await db.get_bank_template_with_key_db(bank_name)
        display_name = template.get('display_name') or bank_name
        relink_text = (template.get('relink_instruction_text') if template else None) or f"Зайдіть у налаштування профілю додатка {display_name}, натисніть «Змінити номер» та введіть цей номер:"
        await bot.send_message(chat_id=client_id, text=relink_text)
    else:
        # Перевіряємо чи банк вже був сповіщений
        notified_banks_str = session.get('notified_banks') or ''
        notified_list = [b.strip() for b in notified_banks_str.split(",") if b.strip()]
        is_already_notified = bank_name in notified_list

        import os
        key, template = await db.get_bank_template_with_key_db(bank_name)

        if not is_already_notified:
            if template:
                # Send download screenshots if present, otherwise send download text
                download_paths_str = template.get('download_screenshot_path')
                download_paths = [p.strip() for p in download_paths_str.split(",") if p.strip()] if download_paths_str else []
                
                valid_local_paths = []
                for p in download_paths:
                    rel_path = p.lstrip('/')
                    local_path = os.path.join("web", rel_path)
                    if os.path.exists(local_path):
                        valid_local_paths.append(local_path)
                
                if valid_local_paths:
                    download_text = template.get('text') or "Спершу завантажте цей додаток:"
                    if len(valid_local_paths) == 1:
                        try:
                            await bot.send_photo(
                                chat_id=client_id,
                                photo=FSInputFile(valid_local_paths[0]),
                                caption=download_text
                            )
                        except Exception as e:
                            logger.error("Помилка надсилання фото додатку для завантаження: %s", e)
                    else:
                        try:
                            from aiogram.types import InputMediaPhoto
                            media = []
                            for idx, p in enumerate(valid_local_paths):
                                caption = download_text if idx == 0 else None
                                media.append(InputMediaPhoto(media=FSInputFile(p), caption=caption))
                            await bot.send_media_group(chat_id=client_id, media=media)
                        except Exception as e:
                            logger.error("Помилка надсилання групи фото додатку для завантаження: %s", e)
                else:
                    if template.get('text'):
                        try:
                            await bot.send_message(chat_id=client_id, text=template['text'])
                        except Exception as e:
                            logger.error("Помилка надсилання тексту додатку для завантаження: %s", e)

            await bot.send_message(
                chat_id=client_id,
                text="Реєстрація робиться за моїм номером телефону, скажете коли потрібен буде СМС код"
            )
            await db.add_notified_bank(client_id, bank_name)
        else:
            await bot.send_message(
                chat_id=client_id,
                text="Ось новий номер телефону по якому робити реєстрацію:"
            )

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
    return client_msg.message_id
