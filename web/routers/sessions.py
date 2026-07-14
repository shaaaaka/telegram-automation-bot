import logging

import aiosqlite
from fastapi import APIRouter, HTTPException, BackgroundTasks
from aiogram.types import (
    ReplyKeyboardRemove
)

import bot.database as db
from bot.config import DB_FILE
from bot.services.line_assignment import send_line_assignment_messages
from bot.services.session_completion import send_completion_client_messages
from web.models import *
from web.core import dp, manager
import web.core


router = APIRouter()

async def _prepare_session_data(row, conn) -> dict:
    session_dict = dict(row)
    client_id = session_dict['client_id']
    
    # Заповнення назви банку з lines, якщо колонка порожня (для старих сесій)
    if not session_dict.get('bank') and session_dict.get('line_id'):
        async with conn.execute("SELECT bank FROM lines WHERE id = ?", (session_dict['line_id'],)) as l_cursor:
            l_row = await l_cursor.fetchone()
            if l_row:
                session_dict['bank'] = l_row['bank']
    
    # Запит на отримання останніх завершених спроб верифікації
    async with conn.execute("""
        SELECT bank, status, assigned_at FROM bank_verifications 
        WHERE client_id = ? AND status != 'pending'
        ORDER BY id ASC
    """, (client_id,)) as v_cursor:
        v_rows = await v_cursor.fetchall()
        bank_statuses = {}
        created_at = session_dict.get('created_at')
        for v_row in v_rows:
            status = v_row['status']
            assigned_at = v_row['assigned_at']
            if status == 'failure':
                status = 'banned'
            # Якщо банк був повернутий у минулій сесії, ігноруємо його
            if status in ('release', 'released') and created_at and assigned_at and assigned_at < created_at:
                continue
            bank_statuses[v_row['bank']] = status
        session_dict['bank_statuses'] = bank_statuses
    
    # Запит на отримання останнього повідомлення чату
    async with conn.execute("""
        SELECT message_text, photo_id, sender, created_at FROM chat_logs 
        WHERE client_id = ? 
        ORDER BY id DESC LIMIT 1
    """, (client_id,)) as msg_cursor:
        msg_row = await msg_cursor.fetchone()
        if msg_row:
            session_dict['last_message'] = {
                'text': msg_row['message_text'],
                'photo': bool(msg_row['photo_id']),
                'sender': msg_row['sender'],
                'created_at': msg_row['created_at']
            }
        else:
            session_dict['last_message'] = None
            
    return session_dict

@router.get("/api/sessions")
async def get_sessions():
    """Отримання списку всіх активних сесій клієнтів"""
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM sessions WHERE status != 'completed' ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            
            sessions_list = []
            for row in rows:
                session_dict = await _prepare_session_data(row, conn)
                sessions_list.append(session_dict)
            
            # Сортуємо сесії за часом останнього повідомлення (або за часом створення, якщо повідомлень немає)
            sessions_list.sort(
                key=lambda s: s['last_message']['created_at'] if (s.get('last_message') and s['last_message'].get('created_at')) else s['created_at'],
                reverse=True
            )
            return sessions_list

@router.get("/api/sessions/{client_id}/chat")
async def get_session_chat(client_id: int):
    """Отримання історії чату для конкретної сесії"""
    try:
        logs = await db.get_chat_logs(client_id)
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/sessions/{client_id}/send_template")
async def send_session_template(client_id: int, body: TemplateSendRequest):
    """Надсилання готового шаблону (наприклад, фото AmoBank) через бота"""
    if not web.core.bot:
        raise HTTPException(status_code=500, detail="Bot is not configured")
    try:
        session = await db.get_session(client_id)
        if not session:
            raise HTTPException(status_code=404, detail="Сесію не знайдено")
            
        if body.template_key == "amobank_steps":
            from aiogram.types import InputMediaPhoto, FSInputFile
            import os
            
            # Шлях до зображень
            images_dir = os.path.join(os.path.dirname(__file__), "..", "..", "bot", "resources", "images")
            media = []
            for i in range(1, 5):
                img_path = os.path.join(images_dir, f"amobank_step{i}.png")
                if os.path.exists(img_path):
                    # Для першого фото додаємо підпис
                    caption = "Ось детальний шаблон заповнення анкети для AmoBank:" if len(media) == 0 else None
                    media.append(InputMediaPhoto(media=FSInputFile(img_path), caption=caption))
            
            if media:
                sent_messages = await web.core.bot.send_media_group(chat_id=client_id, media=media)
                # Логуємо кожне надіслане повідомлення
                for i, msg in enumerate(sent_messages):
                    photo_id = msg.photo[-1].file_id if msg.photo else None
                    # Додаємо підпис тільки до першого логу
                    txt = "Ось детальний шаблон заповнення анкети для AmoBank:" if i == 0 else None
                    await db.log_chat_message(client_id, 'operator', txt, photo_id)
                return {"status": "success", "message": "Шаблон AmoBank надіслано успішно"}
            else:
                raise HTTPException(status_code=404, detail="Файли шаблонів не знайдено")
        else:
            raise HTTPException(status_code=400, detail=f"Невідомий ключ шаблону: {body.template_key}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/sessions/{client_id}/history")
async def get_client_history(client_id: int):
    """Отримання історії верифікацій клієнта"""
    try:
        history = await db.get_client_verification_history(client_id)
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/sessions/{client_id}/banks")
async def save_client_banks(client_id: int, body: BanksSelection):
    """Збереження списку банків, які має пройти клієнт"""
    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    new_selected = body.selected_banks
    
    current_remaining_str = session.get('remaining_banks', '')
    current_remaining = current_remaining_str.split(",") if current_remaining_str else []
    
    current_selected_str = session.get('selected_banks', '')
    current_selected = current_selected_str.split(",") if current_selected_str else []
    
    new_remaining = []
    for bank in new_selected:
        if bank in current_remaining:
            new_remaining.append(bank)
        elif bank not in current_selected:
            # Це новий банк, якого раніше не було в списку обраних взагалі
            new_remaining.append(bank)
            
    selected_str = ",".join(new_selected)
    remaining_str = ",".join(new_remaining)
    
    await db.update_session_banks(client_id, selected_str, remaining_str)
    return {"status": "success", "selected_banks": new_selected}

@router.post("/api/sessions/{client_id}/send-to-verifier")
async def send_to_verifier_endpoint(client_id: int):
    """Надсилання анкети клієнта верифікатору з веб-панелі"""
    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    await db.set_session_status(client_id, 'waiting_verification')
    
    from bot.handlers.client import send_anketa_to_verifier
    if web.core.bot:
        await send_anketa_to_verifier(client_id, web.core.bot)
        
    return {"status": "success"}

@router.post("/api/sessions/{client_id}/verify-manually")
async def verify_manually_endpoint(client_id: int):
    """Ручне схвалення анкети дропа (без перевірки верифікатором)"""
    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    await db.set_session_verified(client_id, 1)
    await db.set_session_status(client_id, 'registered')
            
    return {"status": "success"}

@router.post("/api/sessions/{client_id}/banks/readd")
async def readd_session_bank(client_id: int, bank: str):
    """Додавання банку назад до списку залишкових (remaining_banks)"""
    import sys
    sys.stderr.write(f"DEBUG readd: client_id={client_id}, bank={bank}\n")
    
    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    remaining_str = session['remaining_banks']
    remaining = remaining_str.split(",") if remaining_str else []
    selected_str = session['selected_banks']
    selected = selected_str.split(",") if selected_str else []
    
    sys.stderr.write(f"DEBUG readd: before - remaining={remaining}, selected={selected}\n")
    
    if bank not in remaining:
        remaining.append(bank)
    if bank not in selected:
        selected.append(bank)
        
    # Зберігаємо оновлений список
    new_remaining_str = ",".join(remaining)
    new_selected_str = ",".join(selected)
    await db.update_session_banks(client_id, new_selected_str, new_remaining_str)
    return {"status": "success", "remaining_banks": new_remaining_str, "selected_banks": new_selected_str}

@router.post("/api/sessions/{client_id}/assign")
async def assign_line(client_id: int, body: LineAssignment, background_tasks: BackgroundTasks):
    """Призначення телефонної лінії для клієнта через веб-інтерфейс"""
    if not web.core.bot:
        raise HTTPException(status_code=500, detail="Telegram web.core.bot is not initialized")

    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    line_info = await db.get_line(body.line_id)
    if not line_info or line_info['status'] != 'available':
        raise HTTPException(status_code=400, detail="Line is busy or does not exist")

    # 1. Записуємо призначення у БД та логуємо у статистику
    await db.assign_line_to_session(client_id, body.line_id)
    await db.log_verification_start(client_id, session['username'], line_info['bank'], line_info['phone_number'])

    # 2. Додаємо завдання відправки повідомлень у фоновий потік, щоб не блокувати сайт
    background_tasks.add_task(send_line_assignment_messages, client_id, body.line_id, web.core.bot)

    return {"status": "success", "line_id": body.line_id}

@router.post("/api/sessions/{client_id}/complete")
async def complete_bank(client_id: int, result: str = "success"):
    """Завершення або відмова верифікації для поточного банку клієнта"""
    if not web.core.bot:
        raise HTTPException(status_code=500, detail="Telegram web.core.bot is not initialized")

    session = await db.get_session(client_id)
    if not session or not session['line_id']:
        raise HTTPException(status_code=400, detail="No active line for this session")

    line_id = session['line_id']
    line_info = await db.get_line(line_id)
    bank_name = line_info['bank'] if line_info else "Банк"

    completed = await db.complete_current_bank(client_id, result)
    if not completed:
        raise HTTPException(status_code=500, detail="Failed to complete bank")

    remaining = completed['remaining']
    new_remaining_str = completed['remaining_banks']
    bank_name = completed['bank_name']

    await send_completion_client_messages(
        client_id=client_id,
        bank_name=bank_name,
        result=result,
        remaining=bool(remaining),
        bot=web.core.bot,
        session=session,
        is_admin_mode=False,
    )

    if not remaining:
        return {"status": "completed_bank", "remaining_banks": ""}
    else:
        if result == "failure":
            return {"status": "line_rejected", "remaining_banks": new_remaining_str}
        else:
            return {"status": "completed_bank", "remaining_banks": new_remaining_str}

@router.post("/api/sessions/{client_id}/terminate")
async def terminate_session(client_id: int):
    """Остаточне закриття сесії клієнта вручну (або скасування реєстрації)"""
    if not web.core.bot:
        raise HTTPException(status_code=500, detail="Telegram web.core.bot is not initialized")

    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Якщо сесія у статусі заповнення анкети
    if session['status'] == 'registering':
        # Скидаємо FSM стан бота
        if dp:
            try:
                from aiogram.fsm.storage.base import StorageKey
                key = StorageKey(bot_id=web.core.bot.id, chat_id=client_id, user_id=client_id)
                await dp.storage.set_state(key, None)
                await dp.storage.set_data(key, {})
            except Exception as e:
                logging.error(f"Помилка при скиданні FSM стану для {client_id}: {e}")

        # Повідомляємо клієнта
        try:
            await web.core.bot.send_message(
                chat_id=client_id,
                text="Введення даних скасовано адміністратором. Напишіть /start, щоб почати спочатку.",
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception:
            pass

        # Закриваємо сесію
        await db.close_session(client_id)
        return {"status": "terminated"}

    # Прибираємо кнопку у клієнта, якщо вона є
    if session['client_message_id']:
        try:
            await web.core.bot.edit_message_reply_markup(
                chat_id=client_id,
                message_id=session['client_message_id'],
                reply_markup=None
            )
        except Exception:
            pass

    # Повідомляємо клієнта
    try:
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        kbd = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔄 Розпочати знову")]
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )
        await web.core.bot.send_message(
            chat_id=client_id,
            text="Роботу завершили, дякуємо за співпрацю.",
            parse_mode="Markdown",
            reply_markup=kbd
        )
    except Exception:
        pass

    # Закриваємо сесію та вивільняємо лінію
    await db.close_session(client_id)
    return {"status": "terminated"}

@router.post("/api/sessions/{client_id}/clear-chat")
async def clear_chat_endpoint(client_id: int):
    """Очищення історії чату клієнта"""
    try:
        await db.clear_chat_logs(client_id)
        # Broadcast via websocket to synchronize all panels
        await manager.broadcast({
            "type": "chat_cleared",
            "client_id": client_id
        })
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear chat history: {str(e)}")

@router.post("/api/sessions/{client_id}/toggle-ai")
async def toggle_session_ai(client_id: int):
    """Перемикання паузи ШІ-бота для сесії"""
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT is_paused FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Session not found")
                
                new_state = 0 if row['is_paused'] else 1
                await conn.execute("UPDATE sessions SET is_paused = ? WHERE client_id = ?", (new_state, client_id))
                await conn.commit()
                
                # Broadcast via websocket to synchronize all panels
                await manager.broadcast({
                    "type": "ai_toggled",
                    "client_id": client_id,
                    "is_paused": bool(new_state)
                })
                
                return {"status": "success", "is_paused": bool(new_state)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle AI: {str(e)}")

@router.delete("/api/sessions/{client_id}")
async def delete_session_endpoint(client_id: int):
    """Повне видалення сесії та чату клієнта"""
    try:
        await db.delete_session_completely(client_id)
        # Broadcast via websocket to synchronize all panels
        await manager.broadcast({
            "type": "session_deleted",
            "client_id": client_id
        })
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")

@router.get("/api/sessions/completed")
async def get_completed_sessions():
    """Отримання списку завершених сесій клієнтів (ліміт 50)"""
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM sessions WHERE status = 'completed' ORDER BY created_at DESC LIMIT 50") as cursor:
            rows = await cursor.fetchall()
            
            sessions_list = []
            for row in rows:
                session_dict = await _prepare_session_data(row, conn)
                sessions_list.append(session_dict)
            
            # Сортуємо сесії за часом останнього повідомлення (або за часом створення, якщо повідомлень немає)
            sessions_list.sort(
                key=lambda s: s['last_message']['created_at'] if (s.get('last_message') and s['last_message'].get('created_at')) else s['created_at'],
                reverse=True
            )
            return sessions_list

