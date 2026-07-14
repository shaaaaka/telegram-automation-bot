import os
import io
import time
import datetime
import logging
from typing import List, Optional

import aiosqlite
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from aiogram import Bot
from aiogram.types import (
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, BufferedInputFile, InputMediaPhoto
)

import bot.database as db
from bot.config import ADMIN_ID, DB_FILE, set_cached_setting
from bot.database import current_sender
from bot.services.line_assignment import send_line_assignment_messages
from bot.services.session_completion import send_completion_client_messages
from web.models import *
from web.core import dp, manager, unrouted_codes
import web.core


router = APIRouter()

@router.post("/api/users/{client_id}/ban")
async def ban_user_endpoint(client_id: int):
    """Блокування користувача"""
    username = "Невідомий"
    session = await db.get_session(client_id)
    if web.core.bot:
        try:
            chat = await web.core.bot.get_chat(client_id)
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
                await web.core.bot.edit_message_reply_markup(
                    chat_id=client_id,
                    message_id=session['client_message_id'],
                    reply_markup=None
                )
            except Exception:
                pass
        
        # Повідомляємо клієнта
        if web.core.bot:
            try:
                from aiogram.types import ReplyKeyboardRemove
                await web.core.bot.send_message(
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

