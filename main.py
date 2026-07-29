import asyncio
import logging
import socket
import sys
import uvicorn

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message
from aiogram.methods import SendMessage, SendPhoto, SendMediaGroup
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods.base import TelegramMethod, Response, TelegramType
from bot.config import BOT_TOKEN, LOG_BOT_TOKEN, set_cached_setting
from bot.database import init_db
from bot.handlers import client, admin, giver, verifier
from bot.scheduler import auto_reminder_loop
from bot.sleep_mode import silence_method_if_sleeping
from bot.bot_registry import init_bots, get_all_bots, get_bot, close_all_bots
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
                    msg_id = getattr(res, 'message_id', None)
                    reply_to_id = getattr(method, 'reply_to_message_id', None)
                    if not reply_to_id and getattr(method, 'reply_parameters', None):
                        reply_to_id = getattr(method.reply_parameters, 'message_id', None)
                    if not reply_to_id and res and getattr(res, 'reply_to_message', None):
                        reply_to_id = getattr(res.reply_to_message, 'message_id', None)
                    await log_chat_message(method.chat_id, sender, method.text, message_id=msg_id, reply_to_message_id=reply_to_id)
                    
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
                    caption = getattr(method, 'caption', None) or ""
                    photo_id = method.photo if isinstance(method.photo, str) else None
                    if res and getattr(res, 'photo', None):
                        photo_id = res.photo[-1].file_id
                    msg_id = getattr(res, 'message_id', None)
                    reply_to_id = getattr(method, 'reply_to_message_id', None)
                    if not reply_to_id and getattr(method, 'reply_parameters', None):
                        reply_to_id = getattr(method.reply_parameters, 'message_id', None)
                    if not reply_to_id and res and getattr(res, 'reply_to_message', None):
                        reply_to_id = getattr(res.reply_to_message, 'message_id', None)
                    await log_chat_message(method.chat_id, sender, caption, photo_id, message_id=msg_id, reply_to_message_id=reply_to_id)
                    
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
            elif isinstance(method, SendMediaGroup):
                if isinstance(method.chat_id, int) and method.chat_id > 0:
                    from bot.database import log_chat_message, current_sender
                    sender = current_sender.get()
                    reply_to_id = getattr(method, 'reply_to_message_id', None)
                    if not reply_to_id and getattr(method, 'reply_parameters', None):
                        reply_to_id = getattr(method.reply_parameters, 'message_id', None)
                    
                    if res and isinstance(res, list):
                        for item in res:
                            item_photo_id = item.photo[-1].file_id if getattr(item, 'photo', None) else None
                            item_caption = getattr(item, 'caption', None) or ""
                            item_msg_id = getattr(item, 'message_id', None)
                            if item_photo_id:
                                await log_chat_message(method.chat_id, sender, item_caption, item_photo_id, message_id=item_msg_id, reply_to_message_id=reply_to_id)
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
                reply_to_id = getattr(event.reply_to_message, 'message_id', None) if event.reply_to_message else None
                if text or photo_id:
                    await log_chat_message(event.from_user.id, 'client', text, photo_id, message_id=event.message_id, reply_to_message_id=reply_to_id)
                
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

# Додаємо FileHandler до кореневого логера, бо basicConfig вже сконфігурований у bot.config
root_logger = logging.getLogger()
file_handler = logging.FileHandler("bot.log", encoding="utf-8")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
)
root_logger.addHandler(file_handler)
# Піднімаємо рівень aiogram API debug, щоб не засмічував лог
logging.getLogger("aiogram").setLevel(logging.INFO)

async def main():
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

    # Ініціалізація бота (головного + профільних) через реєстр
    await init_bots(BOT_TOKEN)

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
    default_bot = get_bot()
    for b in get_all_bots():
        b.session.middleware(OutgoingLoggingMiddleware(log_bot=log_bot))
    set_bot(default_bot)
    set_dp(dp)

    # Налаштування конфігурації Uvicorn
    import os

    def find_free_port(start_port, end_port=8010):
        for port in range(start_port, end_port + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("0.0.0.0", port))
                    return port
                except OSError:
                    pass
        return start_port

    base_port = int(os.getenv("PORT", 8000))
    web_port = find_free_port(base_port)
    if web_port != base_port:
        logging.warning(f"Порт {base_port} зайнятий, використовую {web_port}")
    config = uvicorn.Config(web_app, host="0.0.0.0", port=web_port, loop="asyncio")
    server = uvicorn.Server(config)

    logging.info("Запуск бота та веб-панелі...")
    try:
        bots = get_all_bots()
        if not bots:
            logging.error("Не знайдено жодного Telegram-бота для запуску (BOT_TOKEN або токени в профілях).")
            return

        # Очищуємо накопичені повідомлення перед запуском (щоб не відповідати на старі)
        for b in bots:
            try:
                await b.delete_webhook(drop_pending_updates=True)
            except Exception as e:
                logging.warning(f"Не вдалося скинути webhook для бота: {e}")

        # Скидаємо кастомну кнопку меню (якщо вона була встановлена як WebApp) до дефолтної
        from aiogram.types import MenuButtonDefault
        for b in bots:
            try:
                await b.set_chat_menu_button(menu_button=MenuButtonDefault())
                logging.info("Кнопку меню бота успішно скинуто до стандартної.")
            except Exception as e:
                logging.warning(f"Не вдалося скинути кнопку меню бота: {e}")

        # Отримуємо всі типи оновлень, які використовує бот
        allowed_updates = dp.resolve_used_update_types()
        if "message_reaction" not in allowed_updates:
            allowed_updates.append("message_reaction")
        logging.info(f"Allowed updates for polling: {allowed_updates}")

        # Запускаємо polling для всіх ботів, веб-сервер та планувальник паралельно
        # Dispatcher.start_polling приймає *bots та обробляє всіх одночасно.
        await asyncio.gather(
            dp.start_polling(*bots, allowed_updates=allowed_updates),
            server.serve(),
            auto_reminder_loop(default_bot)
        )
    finally:
        await close_all_bots()
        if log_bot:
            await log_bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
