import asyncio
import logging
import sys
import uvicorn

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message
from aiogram.methods import SendMessage, SendPhoto
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods.base import TelegramMethod, Response, TelegramType
from bot.config import BOT_TOKEN, LOG_BOT_TOKEN, set_cached_setting
from bot.database import init_db
from bot.handlers import client, admin, giver, verifier
from bot.scheduler import auto_reminder_loop
from bot.sleep_mode import silence_method_if_sleeping
from web.app import app as web_app
from web.core import set_bot, set_dp

# Ініціалізація додаткового бота для логів, якщо вказаний токен
log_bot = None
if LOG_BOT_TOKEN:
    log_bot = Bot(token=LOG_BOT_TOKEN)

class OutgoingLoggingMiddleware(BaseRequestMiddleware):
    def __init__(self, log_bot: Bot = None):
        self.log_bot = log_bot

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> TelegramType:
        # Під час режиму сну відключаємо звук усіх повідомлень, що надсилаються клієнтам
        silence_method_if_sleeping(method)
        res = await make_request(bot, method)
        try:
            if isinstance(method, SendMessage):
                if isinstance(method.chat_id, int) and method.chat_id > 0:
                    from bot.database import log_chat_message, current_sender, active_subscriptions
                    sender = current_sender.get()
                    await log_chat_message(method.chat_id, sender, method.text)
                    
                    # Пересилаємо повідомлення адміну, якщо увімкнене стеження
                    send_bot = self.log_bot if self.log_bot else bot
                    for admin_id, sub_client_id in active_subscriptions.items():
                        if sub_client_id == method.chat_id and admin_id != method.chat_id:
                            try:
                                await send_bot.send_message(
                                    chat_id=admin_id,
                                    text=f"👁️ <b>[Стеження: ID {sub_client_id}]</b>\nБот: {method.text}",
                                    parse_mode="HTML"
                                )
                            except Exception as err:
                                logging.error(f"Error forwarding spy message via log_bot: {err}")
                                if self.log_bot:
                                    try:
                                        await bot.send_message(
                                            chat_id=admin_id,
                                            text=f"👁️ <b>[Стеження: ID {sub_client_id}]</b>\nБот: {method.text}",
                                            parse_mode="HTML"
                                        )
                                    except Exception:
                                        pass
            elif isinstance(method, SendPhoto):
                if isinstance(method.chat_id, int) and method.chat_id > 0:
                    from bot.database import log_chat_message, current_sender, active_subscriptions
                    sender = current_sender.get()
                    photo_id = method.photo if isinstance(method.photo, str) else None
                    if res and getattr(res, 'photo', None):
                        photo_id = res.photo[-1].file_id
                    caption = method.caption or "[Фото]"
                    await log_chat_message(method.chat_id, sender, caption, photo_id)
                    
                    # Пересилаємо фото адміну, якщо увімкнене стеження
                    send_bot = self.log_bot if self.log_bot else bot
                    for admin_id, sub_client_id in active_subscriptions.items():
                        if sub_client_id == method.chat_id and admin_id != method.chat_id:
                            msg_text = f"👁️ <b>[Стеження: ID {sub_client_id}]</b>\nБот: {caption}"
                            try:
                                if photo_id:
                                    await send_bot.send_photo(chat_id=admin_id, photo=photo_id, caption=msg_text, parse_mode="HTML")
                                else:
                                    await send_bot.send_message(chat_id=admin_id, text=msg_text, parse_mode="HTML")
                            except Exception as err:
                                logging.error(f"Error forwarding spy photo via log_bot: {err}")
                                if self.log_bot:
                                    try:
                                        if photo_id:
                                            await bot.send_photo(chat_id=admin_id, photo=photo_id, caption=msg_text, parse_mode="HTML")
                                        else:
                                            await bot.send_message(chat_id=admin_id, text=msg_text, parse_mode="HTML")
                                    except Exception:
                                        pass
        except Exception as e:
            logging.error(f"Error logging outgoing message: {e}")
        return res

class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user:
            from bot.database import is_user_banned
            if await is_user_banned(user.id):
                return
        return await handler(event, data)

class IncomingLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data):
        if isinstance(event, Message) and event.chat.type == "private":
            try:
                from bot.database import log_chat_message, active_subscriptions
                text = event.text or event.caption
                photo_id = event.photo[-1].file_id if event.photo else None
                if text or photo_id:
                    await log_chat_message(event.from_user.id, 'client', text, photo_id)
                
                # Копіюємо повідомлення адміну, якщо активоване стеження
                send_bot = log_bot if log_bot else event.bot
                for admin_id, sub_client_id in active_subscriptions.items():
                    if sub_client_id == event.from_user.id:
                        username = event.from_user.username or "Невідомий"
                        msg_text = f"👁️ <b>[Стеження: @{username}]</b>\nКлієнт: {text or '[Фото/Файл]'}"
                        
                        try:
                            if photo_id:
                                await send_bot.send_photo(chat_id=admin_id, photo=photo_id, caption=msg_text, parse_mode="HTML")
                            else:
                                await send_bot.send_message(chat_id=admin_id, text=msg_text, parse_mode="HTML")
                        except Exception as err:
                            logging.error(f"Error forwarding client message via log_bot: {err}")
                            if log_bot:
                                try:
                                    if photo_id:
                                        await event.bot.send_photo(chat_id=admin_id, photo=photo_id, caption=msg_text, parse_mode="HTML")
                                    else:
                                        await event.bot.send_message(chat_id=admin_id, text=msg_text, parse_mode="HTML")
                                except Exception:
                                    pass
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

    # Завантажуємо налаштування чатів з БД та кешуємо у конфіг
    from bot.database import get_setting
    for key in ["anketa_chat_id", "giver_chat_id", "archive_group_id", "admin_id"]:
        val = await get_setting(key)
        if val:
            set_cached_setting(key, val)

    # Завантажуємо налаштування режиму сну
    for key in ["sleep_mode_enabled", "sleep_mode_start", "sleep_mode_end", "sleep_mode_timezone"]:
        val = await get_setting(key)
        if val:
            set_cached_setting(key, val)

    # Ініціалізація бота та диспетчера та реєстрація middleware
    bot = Bot(token=BOT_TOKEN)
    bot.session.middleware(OutgoingLoggingMiddleware(log_bot=log_bot))
    dp = Dispatcher()
    dp.message.outer_middleware(BanMiddleware())
    dp.callback_query.outer_middleware(BanMiddleware())
    dp.message.outer_middleware(IncomingLoggingMiddleware())

    # Реєстрація роутерів (черговість важлива: спочатку адмін та гівер, потім загальні)
    dp.include_router(admin.router)
    dp.include_router(giver.router)
    dp.include_router(verifier.router)
    dp.include_router(client.router)

    # Передаємо об'єкт бота та диспетчера у FastAPI додаток
    set_bot(bot)
    set_dp(dp)

    # Налаштування конфігурації Uvicorn
    import os
    web_port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(web_app, host="0.0.0.0", port=web_port, loop="asyncio")
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
        
        # Отримуємо всі типи оновлень, які використовує бот
        allowed_updates = dp.resolve_used_update_types()
        if "message_reaction" not in allowed_updates:
            allowed_updates.append("message_reaction")
        logging.info(f"Allowed updates for polling: {allowed_updates}")
        
        # Запускаємо і бота, і веб-сервер, і планувальник нагадувань паралельно
        await asyncio.gather(
            dp.start_polling(bot, allowed_updates=allowed_updates),
            server.serve(),
            auto_reminder_loop(bot)
        )
    finally:
        await bot.session.close()
        if log_bot:
            await log_bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
