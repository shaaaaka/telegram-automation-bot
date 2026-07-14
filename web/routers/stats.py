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

@router.get("/api/stats")
async def get_stats_endpoint():
    """Отримання статистики верифікацій"""
    try:
        stats = await db.get_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

@router.post("/api/stats/clear")
async def clear_stats_endpoint():
    """Очищення всієї статистики"""
    try:
        await db.clear_statistics()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear stats: {str(e)}")

