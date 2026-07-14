
from fastapi import APIRouter, HTTPException

import bot.database as db
from bot.config import ADMIN_ID
from web.models import *
from web.core import unrouted_codes
import web.core


router = APIRouter()

@router.get("/api/unrouted-codes")

async def get_unrouted_codes():
    """Отримання списку нерозподілених кодів"""
    return {"codes": unrouted_codes}

@router.post("/api/sessions/{client_id}/route-code")
async def route_code(client_id: int, body: CodeRouting):
    """Ручний розподіл коду клієнту через веб-адмінку"""
    if not web.core.bot:
        raise HTTPException(status_code=500, detail="Telegram bot is not initialized")

    session = await db.get_session(client_id)
    if not session or session['status'] != 'waiting_code':
        raise HTTPException(status_code=400, detail="Client is not waiting for a code")

    line_id = session['line_id']
    line_info = await db.get_line(line_id) if line_id else None
    line_num = line_info['line_id'] if line_info else line_id
    bank_name = line_info['bank'] if line_info else "Банк"

    # 1. Відправляємо код клієнту
    from aiogram.types import ReplyKeyboardRemove
    await db.increment_session_sent_codes_count(client_id)
    await web.core.bot.send_message(
        chat_id=client_id,
        text=f"`{body.code}`",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

    # 2. Повертаємо сесію в робочий статус
    await db.set_session_status(client_id, 'number_assigned')

    # 3. Видаляємо код зі списку нерозподілених
    
    unrouted_codes[:] = [c for c in unrouted_codes if c['code'] != body.code]

    # 4. Повідомляємо адміна в Telegram
    try:
        await web.core.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Код {body.code} вручну переслано користувачу @{session['username']} (Line {line_num} - {bank_name}) через веб-панель."
        )
    except Exception:
        pass

    return {"status": "success"}

