
from fastapi import APIRouter

import bot.database as db
from web.core import manager
import web.core
from bot.bot_registry import get_bot_for_session, get_bot


router = APIRouter()

@router.post("/api/users/{client_id}/ban")
async def ban_user_endpoint(client_id: int):
    """Блокування користувача"""
    username = "Невідомий"
    session = await db.get_session(client_id)
    bot = await get_bot_for_session(client_id) or get_bot() or web.core.bot
    if bot:
        try:
            chat = await bot.get_chat(client_id)
            if chat.username:
                username = chat.username
            elif chat.first_name:
                username = chat.first_name
        except Exception:
            pass
    
    # Додаємо в бан-лист
    await db.ban_user(client_id, username)
    
    # Якщо є активна сесія, примусово закриваємо її
    if session:
        # Прибираємо кнопку у клієнта, якщо вона є
        if session['client_message_id'] and bot:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=client_id,
                    message_id=session['client_message_id'],
                    reply_markup=None
                )
            except Exception:
                pass
        
        # Повідомляємо клієнта
        if bot:
            try:
                from aiogram.types import ReplyKeyboardRemove
                await bot.send_message(
                    chat_id=client_id,
                    text="Ваш доступ до бота обмежено.",
                    reply_markup=ReplyKeyboardRemove()
                )
            except Exception:
                pass
        
        await db.close_session(client_id)
    
    # Сповіщаємо всі веб-панелі
    await manager.broadcast({
        "type": "user_banned",
        "client_id": client_id
    })
    
    return {"status": "banned"}

@router.post("/api/users/{client_id}/unban")
async def unban_user_endpoint(client_id: int):
    """Розблокування користувача"""
    await db.unban_user(client_id)
    # Сповіщаємо всі веб-панелі
    await manager.broadcast({
        "type": "user_unbanned",
        "client_id": client_id
    })
    return {"status": "unbanned"}

@router.get("/api/banned-users")
async def get_banned_users_endpoint():
    """Отримання списку заблокованих користувачів"""
    users = await db.get_banned_users()
    return users

