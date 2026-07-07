import os
import asyncio
import mimetypes
mimetypes.init()
mimetypes.add_type("text/css", ".css", True)
mimetypes.add_type("application/javascript", ".js", True)

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Depends, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import io
from pydantic import BaseModel
from typing import List, Optional
import aiosqlite
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, ReplyKeyboardRemove
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from contextlib import asynccontextmanager

from bot.config import DB_FILE, ADMIN_ID, get_bank_template, get_bank_template_with_key, get_template_photo
import bot.database as db
from bot.database import current_sender, chat_message_callbacks

security = HTTPBasic(auto_error=False)

async def check_admin_auth(request: Request = None, websocket: WebSocket = None):
    username_env = os.getenv("WEB_USERNAME")
    password_env = os.getenv("WEB_PASSWORD")
    if not username_env or not password_env:
        return True

    if websocket is not None or (request and request.scope.get("type") == "websocket"):
        return True

    if request is not None:
        credentials = await security(request)
        if credentials:
            is_username_correct = secrets.compare_digest(credentials.username, username_env)
            is_password_correct = secrets.compare_digest(credentials.password, password_env)
            if is_username_correct and is_password_correct:
                return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Basic"},
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ініціалізація бази даних при запуску веб-сервера
    try:
        from bot.database import init_db
        await init_db()
    except Exception as e:
        import logging
        logging.error(f"Помилка ініціалізації бази даних на веб-сервері: {e}")
    yield

app = FastAPI(title="Verification Bot Web Admin", dependencies=[Depends(check_admin_auth)], lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
# WebSocket Connection Manager for real-time CRM chat updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Maintain connection, wait for client close
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

async def on_new_chat_message(client_id: int, sender: str, message_text: str = None, photo_id: str = None):
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await manager.broadcast({
        "type": "new_message",
        "client_id": client_id,
        "sender": sender,
        "message_text": message_text,
        "photo_id": photo_id,
        "created_at": now_str
    })

# Register WebSocket broadcast callback
chat_message_callbacks.append(on_new_chat_message)


# Глобальне посилання на бота Telegram
bot: Optional[Bot] = None

# Глобальний список нерозподілених кодів (Сценарій 3)
unrouted_codes = []

def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance

class BanksSelection(BaseModel):
    selected_banks: List[str]

class LineAssignment(BaseModel):
    line_id: int

class CodeRouting(BaseModel):
    code: str

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Повертає головну сторінку адмін-панелі"""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="HTML template file not found")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/status")
async def get_status():
    """Отримання статусу підключення"""
    return {
        "status": "online",
        "bot_configured": bot is not None
    }

@app.get("/api/lines")
async def get_lines():
    """Отримання списку всіх телефонних ліній та їхніх статусів"""
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM lines ORDER BY id") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

class LineAdd(BaseModel):
    id: int
    line_id: int | None = None
    phone_number: str
    bank: str

@app.post("/api/lines")
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



@app.post("/api/lines/clear")
async def clear_lines():
    """Очищення всіх ліній"""
    await db.clear_all_lines()
    return {"status": "success"}

@app.delete("/api/lines/{line_id}")
async def delete_line_endpoint(line_id: int):
    """Видалення лінії з бази даних"""
    await db.delete_line(line_id)
    return {"status": "success"}


@app.get("/api/sessions")
async def get_sessions():
    """Отримання списку всіх активних сесій клієнтів"""
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM sessions WHERE status != 'completed' ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            
            sessions_list = []
            for row in rows:
                session_dict = dict(row)
                client_id = session_dict['client_id']
                
                # Запит на отримання останніх завершених спроб верифікації
                async with conn.execute("""
                    SELECT bank, status FROM bank_verifications 
                    WHERE client_id = ? AND status != 'pending'
                    ORDER BY id ASC
                """, (client_id,)) as v_cursor:
                    v_rows = await v_cursor.fetchall()
                    bank_statuses = {}
                    # Тимчасово закоментовано для зручності тестування:
                    # for v_row in v_rows:
                    #     status = v_row['status']
                    #     if status == 'failure':
                    #         status = 'banned'
                    #     bank_statuses[v_row['bank']] = status
                    session_dict['bank_statuses'] = bank_statuses
                
                sessions_list.append(session_dict)
            return sessions_list

@app.get("/api/sessions/{client_id}/chat")
async def get_session_chat(client_id: int):
    """Отримання історії чату для конкретної сесії"""
    try:
        logs = await db.get_chat_logs(client_id)
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{client_id}/history")
async def get_client_history(client_id: int):
    """Отримання історії верифікацій клієнта"""
    try:
        history = await db.get_client_verification_history(client_id)
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/photos/{file_id}")
async def get_telegram_photo(file_id: str):
    """Стрімінг фотографії з Telegram по її file_id"""
    if not bot:
        raise HTTPException(status_code=500, detail="Bot is not configured")
    try:
        file_info = await bot.get_file(file_id)
        photo_bytes = io.BytesIO()
        await bot.download_file(file_info.file_path, photo_bytes)
        photo_bytes.seek(0)
        return StreamingResponse(photo_bytes, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch photo from Telegram: {e}")

@app.get("/api/avatar/{client_id}")
async def get_client_avatar(client_id: int):
    """Повертає аватарку користувача з Telegram або 404, якщо її немає"""
    if not bot:
        raise HTTPException(status_code=500, detail="Bot is not configured")
    try:
        photos = await bot.get_user_profile_photos(user_id=client_id, limit=1)
        if photos and photos.total_count > 0:
            # photos.photos is List[List[PhotoSize]], where photos[0][0] is the first photo, smallest size
            file_id = photos.photos[0][0].file_id
            file_info = await bot.get_file(file_id)
            photo_bytes = io.BytesIO()
            await bot.download_file(file_info.file_path, photo_bytes)
            photo_bytes.seek(0)
            return StreamingResponse(photo_bytes, media_type="image/jpeg")
        else:
            raise HTTPException(status_code=404, detail="No profile photos found")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to fetch avatar: {e}")

@app.get("/api/banks")
async def get_banks():
    """Отримання списку унікальних банків з ліній"""
    banks = await db.get_unique_banks()
    return {"banks": banks}

@app.post("/api/sessions/{client_id}/banks")
async def save_client_banks(client_id: int, body: BanksSelection):
    """Збереження списку банків, які має пройти клієнт"""
    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Розраховуємо новий список залишкових банків (щоб не скидати пройдений статус інших банків)
    old_selected_str = session['selected_banks']
    old_selected = old_selected_str.split(",") if old_selected_str else []
    
    old_remaining_str = session['remaining_banks']
    old_remaining = old_remaining_str.split(",") if old_remaining_str else []
    
    new_selected = body.selected_banks
    
    # Автоматично зберігаємо вже завершені/пройдені банки в списку обраних.
    # Завершені банки - це ті, які були в old_selected, але відсутні в old_remaining.
    completed_banks = [bank for bank in old_selected if bank not in old_remaining]
    for bank in completed_banks:
        if bank not in new_selected:
            new_selected.append(bank)
            
    new_remaining = []
    
    for bank in new_selected:
        if bank in old_remaining:
            new_remaining.append(bank)
        elif bank not in old_selected:
            new_remaining.append(bank)
            
    selected_str = ",".join(new_selected)
    remaining_str = ",".join(new_remaining)
    
    await db.update_session_banks(client_id, selected_str, remaining_str)
    return {"status": "success", "selected_banks": new_selected}

@app.post("/api/sessions/{client_id}/banks/readd")
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
        
    # Зберігаємо оновлений список
    new_remaining_str = ",".join(remaining)
    await db.update_session_banks(client_id, session['selected_banks'], new_remaining_str)
    return {"status": "success", "remaining_banks": new_remaining_str}

@app.post("/api/sessions/{client_id}/assign")
async def assign_line(client_id: int, body: LineAssignment):
    """Призначення телефонної лінії для клієнта через веб-інтерфейс"""
    if not bot:
        raise HTTPException(status_code=500, detail="Telegram bot is not initialized")

    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    line_info = await db.get_line(body.line_id)
    if not line_info or line_info['status'] != 'available':
        raise HTTPException(status_code=400, detail="Line is busy or does not exist")

    # 1. Записуємо призначення у БД та логуємо у статистику
    await db.assign_line_to_session(client_id, body.line_id)
    await db.log_verification_start(client_id, session['username'], line_info['bank'], line_info['phone_number'])

    # Видаляємо повідомлення про очікування номера у клієнта
    if session.get('waiting_message_id'):
        try:
            await bot.delete_message(chat_id=client_id, message_id=session['waiting_message_id'])
        except Exception as e:
            print(f"Помилка видалення повідомлення очікування у клієнта: {e}")

    # 2. Відправляємо клієнту номер та кнопку в Telegram
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Запросити SMS-код", callback_data="request_code")]
    ])
    
    bank_name = line_info['bank']
    template = await db.get_bank_template_db(bank_name)
    
    client_assign_format = await db.get_setting("client_number_assigned_format", "Банк: *{bank_name}*\nНомер телефону:\n\n`+{phone_number}`\n\nКоли надішлете SMS і вам знадобиться код, тисніть кнопку нижче.")
    try:
        message_text = client_assign_format.format(bank_name=bank_name, phone_number=line_info['phone_number'])
    except Exception:
        message_text = (
            f"Банк: *{bank_name}*\n"
            f"Номер телефону:\n\n"
            f"`+{line_info['phone_number']}`\n\n"
            f"Коли надішлете SMS і вам знадобиться код, тисніть кнопку нижче."
        )
    
    try:
        # Спочатку надсилаємо шаблон (інструкцію/фото завантаження додатку), якщо він є
        if template:
            key, _ = await db.get_bank_template_with_key_db(bank_name)
            photo_path = get_template_photo(key) if key else None
            caption_text = template['text']  # Прибираємо команду /ЗАВАНТАЖ...
            instruction_msg = None
            if photo_path:
                instruction_msg = await bot.send_photo(
                    chat_id=client_id,
                    photo=FSInputFile(photo_path),
                    caption=caption_text
                )
            else:
                instruction_msg = await bot.send_message(
                    chat_id=client_id,
                    text=caption_text
                )
            if instruction_msg:
                try:
                    await db.update_session_instruction_message_id(client_id, instruction_msg.message_id)
                except Exception as e:
                    print(f"Помилка оновлення instruction_message_id в БД: {e}")
            # Затримка 3 секунди перед надсиланням номера телефону
            await asyncio.sleep(3)

        await bot.send_message(
            chat_id=client_id,
            text="Реєстрація робиться за моїм номером телефону, скажете коли потрібен буде СМС код"
        )

        # Потім надсилаємо картку з номером телефону
        client_msg = await bot.send_message(
            chat_id=client_id,
            text=f"`+{line_info['phone_number']}`",
            reply_markup=None,
            parse_mode="Markdown"
        )
        # Зберігаємо ID повідомлення у клієнта
        await db.update_session_message_id(client_id, client_msg.message_id)

        # Додаємо Reply Keyboard кнопку для зручності
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        reply_keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Запросити SMS-код")]],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )
        try:
            await bot.send_message(
                chat_id=client_id,
                text="З'явилася кнопка внизу для швидкого запиту коду 👇",
                reply_markup=reply_keyboard
            )
        except Exception:
            pass
    except Exception as e:
        # У разі помилки відкочуємо призначення
        await db.set_line_status(body.line_id, 'available')
        async with aiosqlite.connect(DB_FILE) as db_conn:
            await db_conn.execute("UPDATE sessions SET line_id = NULL, status = 'registered' WHERE client_id = ?", (client_id,))
            await db_conn.commit()
        raise HTTPException(status_code=500, detail=f"Failed to send Telegram message to client: {str(e)}")

    # 3. Надсилаємо адміну в Telegram сповіщення з кнопкою завершення
    complete_markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Зареєстрував", callback_data=f"complete_success_{client_id}"),
            InlineKeyboardButton(text="❌ Відмова", callback_data=f"complete_failure_{client_id}")
        ],
        [
            InlineKeyboardButton(text="🔄 Завершити реєстрацію банку", callback_data=f"complete_release_{client_id}")
        ]
    ])
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"Лінію {body.line_id} ({line_info['bank']}) призначено клієнту @{session['username']} через веб-панель!\n\n"
                f"Натисніть відповідну кнопку нижче, залежно від результату верифікації."
            ),
            reply_markup=complete_markup,
            parse_mode="Markdown"
        )
    except Exception:
        pass # Якщо адміну не надіслалось, веб-адмінка все одно працює

    return {"status": "success", "line_id": body.line_id}

@app.post("/api/sessions/{client_id}/complete")
async def complete_bank(client_id: int, result: str = "success"):
    """Завершення або відмова верифікації для поточного банку клієнта"""
    if not bot:
        raise HTTPException(status_code=500, detail="Telegram bot is not initialized")

    session = await db.get_session(client_id)
    if not session or not session['line_id']:
        raise HTTPException(status_code=400, detail="No active line for this session")

    line_id = session['line_id']
    line_info = await db.get_line(line_id)
    bank_name = line_info['bank'] if line_info else "Банк"

    # 1. Прибираємо кнопку запиту коду в Telegram
    if session['client_message_id']:
        try:
            await bot.edit_message_reply_markup(
                chat_id=client_id,
                message_id=session['client_message_id'],
                reply_markup=None
            )
        except Exception:
            pass

    # 2. Звільняємо лінію відповідно та логуємо
    if result in ("success", "release"):
        line_status = 'success' if result == 'success' else 'available'
        await db.set_line_status(line_id, line_status)
        await db.log_verification_end(client_id, bank_name, result)
    else:
        # Failure / Banned
        await db.set_line_status(line_id, 'banned')
        await db.log_verification_end(client_id, bank_name, 'banned')

    # Оновлюємо статус сесії на 'registered' та скидаємо line_id
    async with aiosqlite.connect(DB_FILE) as db_conn:
        await db_conn.execute("UPDATE sessions SET line_id = NULL, client_message_id = NULL, status = 'registered' WHERE client_id = ?", (client_id,))
        await db_conn.commit()

    # 3. Видаляємо пройдений/відкинутий банк з решти
    remaining_banks_str = session['remaining_banks']
    remaining = remaining_banks_str.split(",") if remaining_banks_str else []
    if bank_name in remaining:
        remaining.remove(bank_name)
    
    new_remaining_str = ",".join(remaining)
    await db.update_session_banks(client_id, session['selected_banks'], new_remaining_str)

    # 4. Перевіряємо чи це був останній банк
    if not remaining:
        # Завершуємо роботу повністю
        try:
            from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
            kbd = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🔄 Розпочати знову")],
                    [KeyboardButton(text="📋 Мої дані")]
                ],
                resize_keyboard=True,
                one_time_keyboard=False,
                is_persistent=True
            )
            await bot.send_message(
                chat_id=client_id,
                text="Роботу завершено. Дякуємо за співпрацю.\n\nНатисніть «🔄 Розпочати знову» нижче, щоб почати нову сесію верифікації.",
                parse_mode="Markdown",
                reply_markup=kbd
            )
        except Exception:
            pass
        await db.close_session(client_id)
        
        # Повідомляємо адміна в Telegram
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=f"Верифікацію для клієнта @{session['username']} успішно завершено по всіх банках через веб-панель!")
        except Exception:
            pass
        
        return {"status": "completed_all"}
    else:
        # Очікування наступного банку або заміна номера після відмови
        if result == "failure":
            try:
                await bot.send_message(
                    chat_id=client_id,
                    text=f"На жаль, виникла помилка з цим номером (відмова банку {bank_name}). Будь ласка, зачекайте, ми призначимо вам новий номер для цього банку.",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
            except Exception:
                pass
            return {"status": "line_rejected", "remaining_banks": new_remaining_str}
        else:
            try:
                await bot.send_message(
                    chat_id=client_id,
                    text=f"Верифікацію для банку {bank_name} завершено. Очікуйте наступний номер.",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
            except Exception:
                pass
            return {"status": "completed_bank", "remaining_banks": new_remaining_str}

@app.post("/api/sessions/{client_id}/terminate")
async def terminate_session(client_id: int):
    """Остаточне закриття сесії клієнта вручну"""
    if not bot:
        raise HTTPException(status_code=500, detail="Telegram bot is not initialized")

    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Прибираємо кнопку у клієнта, якщо вона є
    if session['client_message_id']:
        try:
            await bot.edit_message_reply_markup(
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
                [KeyboardButton(text="🔄 Розпочати знову")],
                [KeyboardButton(text="📋 Мої дані")]
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )
        await bot.send_message(
            chat_id=client_id,
            text="Роботу завершено. Дякуємо за співпрацю.\n\nНатисніть «🔄 Розпочати знову» нижче, щоб почати нову сесію верифікації.",
            parse_mode="Markdown",
            reply_markup=kbd
        )
    except Exception:
        pass

    # Закриваємо сесію та вивільняємо лінію
    await db.close_session(client_id)
    return {"status": "terminated"}

@app.post("/api/sessions/{client_id}/clear-chat")
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

@app.delete("/api/sessions/{client_id}")
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

@app.get("/api/unrouted-codes")

async def get_unrouted_codes():
    """Отримання списку нерозподілених кодів"""
    return {"codes": unrouted_codes}

@app.post("/api/sessions/{client_id}/route-code")
async def route_code(client_id: int, body: CodeRouting):
    """Ручний розподіл коду клієнту через веб-адмінку"""
    if not bot:
        raise HTTPException(status_code=500, detail="Telegram bot is not initialized")

    session = await db.get_session(client_id)
    if not session or session['status'] != 'waiting_code':
        raise HTTPException(status_code=400, detail="Client is not waiting for a code")

    line_id = session['line_id']
    line_info = await db.get_line(line_id) if line_id else None
    line_num = line_info['line_id'] if line_info else line_id
    bank_name = line_info['bank'] if line_info else "Банк"

    # 1. Відправляємо код клієнту
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    client_kbd = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Запросити SMS-код")]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )
    await bot.send_message(
        chat_id=client_id,
        text=f"Ваш SMS-код для банку {bank_name}:\n\n`{body.code}`",
        reply_markup=client_kbd,
        parse_mode="Markdown"
    )

    # 2. Повертаємо сесію в робочий статус
    await db.set_session_status(client_id, 'number_assigned')

    # 3. Видаляємо код зі списку нерозподілених
    global unrouted_codes
    unrouted_codes = [c for c in unrouted_codes if c['code'] != body.code]

    # 4. Повідомляємо адміна в Telegram
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Код {body.code} вручну переслано користувачу @{session['username']} (Line {line_num} - {bank_name}) через веб-панель."
        )
    except Exception:
        pass

    return {"status": "success"}

class ClientMessage(BaseModel):
    message: str

@app.post("/api/sessions/{client_id}/message")
async def send_client_message(client_id: int, body: ClientMessage):
    """Надсилання повідомлення клієнту в Telegram від імені бота"""
    if not bot:
        raise HTTPException(status_code=500, detail="Telegram bot is not initialized")
    
    # Встановлюємо sender як 'admin' для цього асинхронного контексту
    token = current_sender.set("admin")
    try:
        await bot.send_message(chat_id=client_id, text=body.message)
        
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

@app.get("/api/sessions/completed")
async def get_completed_sessions():
    """Отримання списку завершених сесій клієнтів (ліміт 50)"""
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM sessions WHERE status = 'completed' ORDER BY created_at DESC LIMIT 50") as cursor:
            rows = await cursor.fetchall()
            
            sessions_list = []
            for row in rows:
                session_dict = dict(row)
                client_id = session_dict['client_id']
                
                # Запит на отримання завершених спроб верифікації
                async with conn.execute("""
                    SELECT bank, status FROM bank_verifications 
                    WHERE client_id = ? AND status != 'pending'
                    ORDER BY id ASC
                """, (client_id,)) as v_cursor:
                    v_rows = await v_cursor.fetchall()
                    bank_statuses = {}
                    # Тимчасово закоментовано для зручності тестування:
                    # for v_row in v_rows:
                    #     status = v_row['status']
                    #     if status == 'failure':
                    #         status = 'banned'
                    #     bank_statuses[v_row['bank']] = status
                    session_dict['bank_statuses'] = bank_statuses
                
                sessions_list.append(session_dict)
            return sessions_list

class AppSettingsUpdate(BaseModel):
    reminder_delay_minutes: str
    reminder_text: str
    reminders_enabled: str
    giver_request_format: Optional[str] = None
    giver_request_retry_format: Optional[str] = None
    client_number_assigned_format: Optional[str] = None

class BankTemplateUpdate(BaseModel):
    key: str
    command: str
    text: str

@app.get("/api/stats")
async def get_stats_endpoint():
    """Отримання статистики верифікацій"""
    try:
        stats = await db.get_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

@app.post("/api/stats/clear")
async def clear_stats_endpoint():
    """Очищення всієї статистики"""
    try:
        await db.clear_statistics()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear stats: {str(e)}")

@app.get("/api/settings")
async def get_settings_endpoint():
    """Отримання налаштувань та шаблонів банків"""
    try:
        settings = await db.get_all_settings()
        templates = await db.get_all_bank_templates()
        return {
            "settings": settings,
            "templates": templates
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get settings: {str(e)}")

@app.post("/api/settings")
async def update_settings_endpoint(body: AppSettingsUpdate):
    """Оновлення загальних налаштувань"""
    try:
        await db.set_setting("reminder_delay_minutes", body.reminder_delay_minutes)
        await db.set_setting("reminder_text", body.reminder_text)
        await db.set_setting("reminders_enabled", body.reminders_enabled)
        if body.giver_request_format is not None:
            await db.set_setting("giver_request_format", body.giver_request_format)
        if body.giver_request_retry_format is not None:
            await db.set_setting("giver_request_retry_format", body.giver_request_retry_format)
        if body.client_number_assigned_format is not None:
            await db.set_setting("client_number_assigned_format", body.client_number_assigned_format)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")

@app.post("/api/settings/templates")
async def update_template_endpoint(body: BankTemplateUpdate):
    """Оновлення або додавання шаблону банку"""
    try:
        await db.save_bank_template(body.key, body.command, body.text)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save bank template: {str(e)}")

@app.delete("/api/settings/templates/{key}")
async def delete_template_endpoint(key: str):
    """Видалення шаблону банку"""
    try:
        await db.delete_bank_template(key)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete bank template: {str(e)}")


# --- Нові API ендпоінти для керування ШІ (AI Rules & Learning) ---

class AIRuleCreate(BaseModel):
    rule_text: str
    category: str = "general"

class AIExampleCreate(BaseModel):
    client_message: str
    bot_response: str

class AISettingsUpdate(BaseModel):
    ai_income_limit: str
    ai_turnover_limit: str
    ai_password_kd: str
    ai_password_other: str

@app.get("/api/ai/rules")
async def get_ai_rules():
    """Отримання всіх правил ШІ"""
    try:
        rules = await db.get_all_ai_rules()
        return rules
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch rules: {e}")

@app.post("/api/ai/rules")
async def create_ai_rule(body: AIRuleCreate):
    """Створення нового правила ШІ"""
    try:
        rule_id = await db.add_ai_rule(body.rule_text, body.category, is_active=1)
        return {"status": "success", "id": rule_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create rule: {e}")

@app.put("/api/ai/rules/{rule_id}/toggle")
async def toggle_ai_rule_endpoint(rule_id: int):
    """Перемикання активності правила ШІ"""
    try:
        await db.toggle_ai_rule(rule_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle rule: {e}")

@app.delete("/api/ai/rules/{rule_id}")
async def delete_ai_rule_endpoint(rule_id: int):
    """Видалення правила ШІ"""
    try:
        await db.delete_ai_rule(rule_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete rule: {e}")

@app.get("/api/ai/examples")
async def get_ai_examples():
    """Отримання всіх few-shot прикладів"""
    try:
        examples = await db.get_all_ai_examples()
        return examples
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch examples: {e}")

@app.post("/api/ai/examples")
async def create_ai_example(body: AIExampleCreate):
    """Створення нового few-shot прикладу"""
    try:
        example_id = await db.add_ai_example(body.client_message, body.bot_response, is_active=1)
        return {"status": "success", "id": example_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create example: {e}")

@app.delete("/api/ai/examples/{example_id}")
async def delete_ai_example_endpoint(example_id: int):
    """Видалення few-shot прикладу"""
    try:
        await db.delete_ai_example(example_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete example: {e}")

@app.get("/api/ai/settings")
async def get_ai_settings():
    """Отримання поточних лімітів та паролів для ШІ"""
    try:
        income = await db.get_setting("ai_income_limit", "25000")
        turnover = await db.get_setting("ai_turnover_limit", "30000")
        password_kd = await db.get_setting("ai_password_kd", "12345")
        password_other = await db.get_setting("ai_password_other", "1111, 1234 або 1232")
        return {
            "ai_income_limit": income,
            "ai_turnover_limit": turnover,
            "ai_password_kd": password_kd,
            "ai_password_other": password_other
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch AI settings: {e}")

@app.post("/api/ai/settings")
async def update_ai_settings(body: AISettingsUpdate):
    """Оновлення лімітів та паролів для ШІ"""
    try:
        await db.set_setting("ai_income_limit", body.ai_income_limit)
        await db.set_setting("ai_turnover_limit", body.ai_turnover_limit)
        await db.set_setting("ai_password_kd", body.ai_password_kd)
        await db.set_setting("ai_password_other", body.ai_password_other)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update AI settings: {e}")

class AILearnRequest(BaseModel):
    client_ids: list[int] = None

@app.get("/api/ai/learnable-chats")
async def get_learnable_chats():
    """Отримання списку сесій/клієнтів для вибору в інтерфейсі (і активні, і архівні)"""
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("""
                SELECT client_id, username, client_data, status
                FROM sessions
                ORDER BY created_at DESC
                LIMIT 50
            """) as cursor:
                rows = await cursor.fetchall()
                
        chats = []
        for row in rows:
            client_id = row["client_id"]
            username = row["username"] if row["username"] else f"ID: {client_id}"
            chats.append({
                "client_id": client_id,
                "username": username,
                "client_data": row["client_data"],
                "status": row["status"]
            })
        return chats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch learnable chats: {e}")

@app.post("/api/ai/learn")
async def trigger_ai_learn(body: AILearnRequest = None):
    """Аналіз останніх діалогів за участю адміна та автогенерація правил-чернеток"""
    from bot.openai_client import analyze_chat_and_propose_rule
    
    try:
        client_ids = []
        if body and body.client_ids:
            client_ids = body.client_ids
        else:
            # 1. Знаходимо клієнтів, у діалогах яких брав участь адмін (за замовчуванням останні 10)
            async with aiosqlite.connect(db.DB_FILE) as conn:
                async with conn.execute("""
                    SELECT DISTINCT client_id 
                    FROM chat_logs 
                    WHERE sender = 'admin' 
                    ORDER BY id DESC 
                    LIMIT 10
                """) as cursor:
                    client_ids = [row[0] for row in await cursor.fetchall()]
                
        if not client_ids:
            return {
                "status": "success", 
                "proposed_rules": [], 
                "message": "Не знайдено діалогів за участю адміністратора для аналізу."
            }
            
        proposed_rules = []
        
        # Отримуємо вже існуючі правила, щоб не створювати дублікати
        existing_rules_list = await db.get_all_ai_rules()
        existing_rules_texts = [r['rule_text'].lower().strip() for r in existing_rules_list]
        
        for c_id in client_ids:
            session = await db.get_session(c_id)
            username = session['username'] if session and session['username'] else f"Client {c_id}"
            
            logs = await db.get_chat_logs(c_id)
            if not logs:
                continue
                
            # Формуємо лог діалогу для аналізу
            chat_lines = []
            for log in logs:
                sender = log['sender'].capitalize()
                text = log['message_text'] or "[Скріншот/Фото]"
                chat_lines.append(f"{sender}: {text}")
                
            chat_history_text = "\n".join(chat_lines)
            
            # Запускаємо аналізатор
            proposed_rule_text = await analyze_chat_and_propose_rule(chat_history_text)
            
            if proposed_rule_text and proposed_rule_text.lower().strip() not in existing_rules_texts:
                if proposed_rule_text not in [r['rule_text'] for r in proposed_rules]:
                    # Зберігаємо в базу як вимкнену чернетку
                    rule_id = await db.add_ai_rule(
                        rule_text=proposed_rule_text, 
                        category='troubleshooting', 
                        is_active=0
                    )
                    proposed_rules.append({
                        "id": rule_id,
                        "rule_text": proposed_rule_text,
                        "category": "troubleshooting",
                        "is_active": 0,
                        "username": username
                    })
                    
        return {
            "status": "success",
            "proposed_rules": proposed_rules,
            "message": f"Проаналізовано {len(client_ids)} діалогів. Згенеровано {len(proposed_rules)} нових правил-чернеток."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run AI learning loop: {e}")
