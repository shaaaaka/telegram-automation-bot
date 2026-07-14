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
from web.core import dp, manager, unrouted_codes, PHOTOS_CACHE_DIR, AVATARS_CACHE_DIR
import web.core


router = APIRouter()

@router.get("/api/photos/{file_id}")
async def get_telegram_photo(file_id: str):
    """Стрімінг фотографії з Telegram по її file_id з локальним кешуванням на диску"""
    if not web.core.bot:
        raise HTTPException(status_code=500, detail="Bot is not configured")
    
    import re
    if not file_id or not re.match(r'^[\w-]+$', file_id):
        raise HTTPException(status_code=400, detail="Invalid file_id format")

    cache_path = os.path.join(PHOTOS_CACHE_DIR, file_id)
    if os.path.exists(cache_path):
        return FileResponse(
            cache_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )
        
    try:
        file_info = await web.core.bot.get_file(file_id)
        photo_bytes = io.BytesIO()
        await web.core.bot.download_file(file_info.file_path, photo_bytes)
        photo_bytes.seek(0)
        
        # Save to disk cache
        with open(cache_path, "wb") as f:
            f.write(photo_bytes.getbuffer())
            
        return FileResponse(
            cache_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch photo from Telegram: {e}")

@router.get("/api/avatar/{client_id}")
async def get_client_avatar(client_id: int):
    """Повертає аватарку користувача з Telegram або 404, якщо її немає. Кешує на 24 години."""
    if not web.core.bot:
        raise HTTPException(status_code=500, detail="Bot is not configured")
    
    import time
    
    # 1. Check if we cached a 404 (no avatar) recently
    no_avatar_path = os.path.join(AVATARS_CACHE_DIR, f"{client_id}.no_avatar")
    if os.path.exists(no_avatar_path) and (time.time() - os.path.getmtime(no_avatar_path) < 86400):
        raise HTTPException(status_code=404, detail="No profile photos found (cached)")
        
    # 2. Check if we have a cached avatar on disk and it is fresh (< 24 hours)
    cache_path = os.path.join(AVATARS_CACHE_DIR, f"{client_id}.jpg")
    if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path) < 86400):
        return FileResponse(
            cache_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"}
        )
        
    try:
        photos = await web.core.bot.get_user_profile_photos(user_id=client_id, limit=1)
        if photos and photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            file_info = await web.core.bot.get_file(file_id)
            photo_bytes = io.BytesIO()
            await web.core.bot.download_file(file_info.file_path, photo_bytes)
            photo_bytes.seek(0)
            
            # Save to disk cache
            with open(cache_path, "wb") as f:
                f.write(photo_bytes.getbuffer())
                
            return FileResponse(
                cache_path,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=86400"}
            )
        else:
            # Cache the fact that user has no avatar (negative cache)
            with open(no_avatar_path, "w") as f:
                f.write("")
            raise HTTPException(status_code=404, detail="No profile photos found")
    except Exception as e:
        # Cache the failed avatar fetch to avoid constant API hammering
        if not os.path.exists(no_avatar_path):
            try:
                with open(no_avatar_path, "w") as f:
                    f.write("")
            except Exception:
                pass
        raise HTTPException(status_code=404, detail=f"Failed to fetch avatar: {e}")

