import asyncio
import logging
import sys
import uvicorn

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message
from aiogram.methods import SendMessage, SendPhoto
from bot.config import BOT_TOKEN
from bot.database import init_db
from bot.handlers import client, admin, giver
from bot.scheduler import auto_reminder_loop
from web.app import app as web_app, set_bot

class CustomBot(Bot):
    async def __call__(self, method, request_timeout=None):
        res = await super().__call__(method, request_timeout)
        try:
            if isinstance(method, SendMessage):
                if isinstance(method.chat_id, int) and method.chat_id > 0:
                    from bot.database import log_chat_message, current_sender
                    sender = current_sender.get()
                    await log_chat_message(method.chat_id, sender, method.text)
            elif isinstance(method, SendPhoto):
                if isinstance(method.chat_id, int) and method.chat_id > 0:
                    from bot.database import log_chat_message, current_sender
                    sender = current_sender.get()
                    photo_id = method.photo if isinstance(method.photo, str) else None
                    if res and getattr(res, 'photo', None):
                        photo_id = res.photo[-1].file_id
                    caption = method.caption or "[Фото]"
                    await log_chat_message(method.chat_id, sender, caption, photo_id)
        except Exception as e:
            logging.error(f"Error logging outgoing message: {e}")
        return res

class IncomingLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data):
        if isinstance(event, Message) and event.chat.type == "private":
            try:
                from bot.database import log_chat_message
                text = event.text or event.caption
                photo_id = event.photo[-1].file_id if event.photo else None
                if text or photo_id:
                    await log_chat_message(event.from_user.id, 'client', text, photo_id)
            except Exception as e:
                logging.error(f"Error logging incoming message: {e}")
        return await handler(event, data)

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout
)

async def main():
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN не задано! Будь ласка, створить файл .env та вкажіть його.")
        return

    # Ініціалізація бази даних
    logging.info("Ініціалізація бази даних...")
    await init_db()

    # Ініціалізація бота та диспетчера
    bot = CustomBot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.message.outer_middleware(IncomingLoggingMiddleware())

    # Реєстрація роутерів (черговість важлива: спочатку адмін та гівер, потім загальні)
    dp.include_router(admin.router)
    dp.include_router(giver.router)
    dp.include_router(client.router)

    # Передаємо об'єкт бота у FastAPI додаток
    set_bot(bot)

    # Налаштування конфігурації Uvicorn
    config = uvicorn.Config(web_app, host="0.0.0.0", port=8000, loop="asyncio")
    server = uvicorn.Server(config)

    logging.info("Запуск бота та веб-панелі...")
    try:
        # Очищуємо накопичені повідомлення перед запуском (щоб не відповідати на старі)
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Скидаємо кастомну кнопку меню (якщо вона була встановлена як WebApp) до дефолтної
        from aiogram.types import MenuButtonDefault
        try:
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            logging.info("Кнопку меню бота успішно скинуто до стандартної.")
        except Exception as e:
            logging.warning(f"Не вдалося скинути кнопку меню бота: {e}")
        
        # Запускаємо і бота, і веб-сервер, і планувальник нагадувань паралельно
        await asyncio.gather(
            dp.start_polling(bot),
            server.serve(),
            auto_reminder_loop(bot)
        )
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
