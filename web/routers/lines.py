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

@router.get("/api/lines")
async def get_lines():
    """Отримання списку всіх телефонних ліній та їхніх статусів"""
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM lines ORDER BY line_id, bank") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

@router.post("/api/lines")
async def add_line(body: LineAdd):
    """Додавання нової лінії вручну"""
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            if body.line_id is not None and body.line_id > 0:
                line_id = body.line_id
            else:
                async with conn.execute("SELECT line_id FROM lines WHERE phone_number = ? LIMIT 1", (body.phone_number,)) as cursor:
                    existing = await cursor.fetchone()
                    if existing:
                        line_id = existing["line_id"]
                    else:
                        async with conn.execute("SELECT MAX(line_id) as max_id FROM lines") as max_cursor:
                            row = await max_cursor.fetchone()
                            max_id = row["max_id"] if row and row["max_id"] is not None else 0
                            line_id = max_id + 1
        
        await db.add_or_update_line(line_id, body.phone_number, body.bank)
        return {"status": "success"}
    except Exception as e:
        import sys
        sys.stderr.write(f"ERROR add_line: {e}\n")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/lines/clear")
async def clear_lines():
    """Очищення всіх ліній"""
    await db.clear_all_lines()
    return {"status": "success"}

@router.delete("/api/lines/{line_id}")
async def delete_line_endpoint(line_id: int):
    """Видалення лінії з бази даних"""
    await db.delete_line(line_id)
    return {"status": "success"}

