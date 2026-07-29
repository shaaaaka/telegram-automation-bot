import os
import io
import logging
import time

from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from aiogram.exceptions import TelegramBadRequest
from web.core import PHOTOS_CACHE_DIR, AVATARS_CACHE_DIR
import web.core
from bot.bot_registry import get_bot_for_session, get_bot, get_all_bots

logger = logging.getLogger(__name__)


router = APIRouter()

@router.get("/api/photos/{file_id}")
async def get_telegram_photo(file_id: str, client_id: Optional[int] = None):
    """Стрімінг фотографії з Telegram по її file_id з локальним кешуванням на диску"""
    default_bot = get_bot() or web.core.bot
    if not default_bot:
        raise HTTPException(status_code=500, detail="Bot is not configured")

    import re
    if not file_id or not re.match(r'^[\w-]+=?$', file_id):
        logger.debug(f"Invalid file_id requested: {file_id!r}")
        raise HTTPException(status_code=400, detail="Invalid file_id format")

    cache_path = os.path.join(PHOTOS_CACHE_DIR, file_id)
    no_photo_path = cache_path + ".no_photo"

    # Negative cache: don't hammer Telegram API for known-bad file_ids
    if os.path.exists(no_photo_path) and (time.time() - os.path.getmtime(no_photo_path) < 86400):
        raise HTTPException(status_code=404, detail="Photo not found or unavailable")

    if os.path.exists(cache_path):
        return FileResponse(
            cache_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )

    # Спробуємо бота сесії (якщо client_id відомий), інакше — дефолтного та всіх зареєстрованих
    bots_to_try = []
    seen_ids = set()
    def add_bot(b):
        if b and id(b) not in seen_ids:
            seen_ids.add(id(b))
            bots_to_try.append(b)
    if client_id:
        session_bot = await get_bot_for_session(client_id)
        add_bot(session_bot)
    add_bot(default_bot)
    if not client_id:
        for b in get_all_bots():
            add_bot(b)

    last_error = None
    for bot in bots_to_try:
        try:
            file_info = await bot.get_file(file_id)
            photo_bytes = io.BytesIO()
            await bot.download_file(file_info.file_path, photo_bytes)
            photo_bytes.seek(0)

            # Save to disk cache
            with open(cache_path, "wb") as f:
                f.write(photo_bytes.getbuffer())

            return FileResponse(
                cache_path,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=31536000, immutable"}
            )
        except TelegramBadRequest as e:
            logger.debug(f"Photo {file_id!r} not available on Telegram with {bot.id}: {e}")
            last_error = e
        except Exception as e:
            logger.exception(f"Failed to fetch photo {file_id!r} from Telegram with {bot.id}: {e}")
            last_error = e

    # Mark missing photo for negative caching
    try:
        with open(no_photo_path, "w") as f:
            f.write("")
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Photo not found or unavailable")

@router.get("/api/avatar/{client_id}")
async def get_client_avatar(client_id: int):
    """Повертає аватарку користувача з Telegram або 404, якщо її немає. Кешує на 24 години."""
    bot = await get_bot_for_session(client_id) or get_bot() or web.core.bot
    if not bot:
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
        photos = await bot.get_user_profile_photos(user_id=client_id, limit=1)
        if photos and photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            file_info = await bot.get_file(file_id)
            photo_bytes = io.BytesIO()
            await bot.download_file(file_info.file_path, photo_bytes)
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

