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

@router.post("/api/sessions/{client_id}/message")
async def send_client_message(client_id: int, body: ClientMessage):
    """Надсилання повідомлення клієнту в Telegram від імені бота"""
    if not web.core.bot:
        raise HTTPException(status_code=500, detail="Telegram bot is not initialized")
    
    # Встановлюємо sender як 'admin' для цього асинхронного контексту
    token = current_sender.set("admin")
    try:
        await web.core.bot.send_message(chat_id=client_id, text=body.message)
        
        # Якщо сесія була в статусі waiting_code, а адмін написав клієнту повідомлення,
        # то автоматично скасовуємо статус очікування коду і повертаємо до number_assigned.
        session = await db.get_session(client_id)
        if session and session['status'] == 'waiting_code':
            await db.set_session_status(client_id, 'number_assigned')
            
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")
    finally:
        current_sender.reset(token)

@router.post("/api/sessions/{client_id}/photo")
async def send_client_photo(client_id: int, file: UploadFile = File(...), caption: Optional[str] = Form(None)):
    """Надсилання фото клієнту в Telegram від імені бота"""
    if not web.core.bot:
        raise HTTPException(status_code=500, detail="Telegram bot is not initialized")
    
    token = current_sender.set("admin")
    try:
        from aiogram.types import BufferedInputFile
        file_bytes = await file.read()
        input_file = BufferedInputFile(file_bytes, filename=file.filename)
        
        await web.core.bot.send_photo(chat_id=client_id, photo=input_file, caption=caption)
        
        # Якщо сесія була в статусі waiting_code, а адмін написав клієнту повідомлення,
        # то автоматично скасовуємо статус очікування коду і повертаємо до number_assigned.
        session = await db.get_session(client_id)
        if session and session['status'] == 'waiting_code':
            await db.set_session_status(client_id, 'number_assigned')
            
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send photo: {str(e)}")
    finally:
        current_sender.reset(token)

