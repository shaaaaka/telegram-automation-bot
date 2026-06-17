import asyncio
import logging
import sys
import uvicorn

from aiogram import Bot, Dispatcher
from bot.config import BOT_TOKEN
from bot.database import init_db
from bot.handlers import client, admin, giver
from bot.scheduler import auto_reminder_loop
from web.app import app as web_app, set_bot

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
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Реєстрація роутерів (черговість важлива: спочатку адмін та гівер, потім загальні)
    dp.include_router(admin.router)
    dp.include_router(giver.router)
    dp.include_router(client.router)

    # Передаємо об'єкт бота у FastAPI додаток
    set_bot(bot)

    # Налаштування конфігурації Uvicorn
    config = uvicorn.Config(web_app, host="127.0.0.1", port=8000, loop="asyncio")
    server = uvicorn.Server(config)

    logging.info("Запуск бота та веб-панелі...")
    try:
        # Очищуємо накопичені повідомлення перед запуском (щоб не відповідати на старі)
        await bot.delete_webhook(drop_pending_updates=True)
        
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
