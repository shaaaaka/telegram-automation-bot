import logging

from aiogram import Bot
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import bot.database as db

logger = logging.getLogger(__name__)


async def send_completion_client_messages(
    client_id: int,
    bank_name: str,
    result: str,
    remaining: bool,
    bot: Bot,
    session: dict | None,
    is_admin_mode: bool = True,
) -> None:
    """Надсилає клієнту повідомлення після успішної верифікації або відмови банку."""
    if session and session.get("client_message_id"):
        try:
            await bot.edit_message_reply_markup(
                chat_id=client_id,
                message_id=session["client_message_id"],
                reply_markup=None,
            )
        except Exception as e:
            logger.error("Помилка видалення кнопки у клієнта: %s", e)

    if not remaining:
        if is_admin_mode:
            text = "Роботу завершили, дякуємо за співпрацю."
            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="🔄 Розпочати знову")]],
                resize_keyboard=True,
                one_time_keyboard=False,
                is_persistent=True,
            )
        else:
            text = (
                f"Верифікацію для банку {bank_name} завершено. "
                "Всі обрані банки пройдено, очікуйте на рішення адміністратора."
            )
            keyboard = ReplyKeyboardRemove()
    else:
        if result == "failure":
            text = (
                f"На жаль, виникла помилка з цим номером (відмова банку {bank_name}). "
                "Будь ласка, зачекайте, ми призначимо вам новий номер для цього банку."
            )
        else:
            text = (
                f"Верифікацію для банку {bank_name} завершено. "
                "Очікуйте наступний номер."
            )

        if is_admin_mode:
            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="⏳ Очікування номера...")]],
                resize_keyboard=True,
                one_time_keyboard=False,
                is_persistent=True,
            )
        else:
            keyboard = ReplyKeyboardRemove()

    try:
        await bot.send_message(
            chat_id=client_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error("Не вдалося надіслати клієнту повідомлення: %s", e)
