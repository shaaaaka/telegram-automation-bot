from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

import bot.database as db
from bot.database import current_sender
from web.models import *
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
        sent_msg = None
        if body.reply_to_message_id:
            try:
                sent_msg = await web.core.bot.send_message(
                    chat_id=client_id, 
                    text=body.message, 
                    reply_to_message_id=body.reply_to_message_id
                )
            except Exception as reply_err:
                import logging
                logging.warning(f"Failed to send with reply_to_message_id={body.reply_to_message_id}, falling back: {reply_err}")
                sent_msg = await web.core.bot.send_message(chat_id=client_id, text=body.message)
        else:
            sent_msg = await web.core.bot.send_message(chat_id=client_id, text=body.message)
        
        session = await db.get_session(client_id)
        if session and session['status'] == 'waiting_code':
            await db.set_session_status(client_id, 'number_assigned')
            
        return {"status": "success"}
    except Exception as e:
        import logging
        logging.error(f"Error in send_client_message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")
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

