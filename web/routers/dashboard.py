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

@router.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Повертає головну сторінку адмін-панелі"""
    template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "index.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="HTML template file not found")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@router.get("/api/status")
async def get_status():
    """Отримання статусу підключення"""
    from bot.config import BOT_TOKEN
    return {
        "status": "online",
        "bot_configured": BOT_TOKEN is not None
    }

