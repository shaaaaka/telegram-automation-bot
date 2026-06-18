import os
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import aiosqlite
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from bot.config import DB_FILE, ADMIN_ID, get_bank_template, get_bank_template_with_key, get_template_photo
import bot.database as db

app = FastAPI(title="Verification Bot Web Admin")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

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
    phone_number: str
    bank: str

@app.post("/api/lines")
async def add_line(body: LineAdd):
    """Додавання нової лінії вручну"""
    await db.add_or_update_line(body.id, body.phone_number, body.bank)
    return {"status": "success"}

@app.post("/api/lines/import")
async def import_lines():
    """Імпорт ліній з файлу lines.txt"""
    file_path = "lines.txt"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File lines.txt not found")
    
    import re
    imported_count = 0
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_str in f:
                line_str = line_str.strip()
                if not line_str or line_str.startswith("#"):
                    continue
                
                try:
                    match = re.match(r'(?:Line\s+)?(\d+)\s+Return:\s+(\d+)(?:\s+(.+))?', line_str, re.IGNORECASE)
                    if match:
                        line_id = int(match.group(1))
                        phone = match.group(2).strip()
                        bank = match.group(3).strip() if match.group(3) else "Невідомий"
                        await db.add_or_update_line(line_id, phone, bank)
                        imported_count += 1
                except Exception:
                    continue
        return {"status": "success", "imported_count": imported_count}
    except Exception as e:
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
                    for v_row in v_rows:
                        status = v_row['status']
                        if status == 'failure':
                            status = 'banned'
                        bank_statuses[v_row['bank']] = status
                    session_dict['bank_statuses'] = bank_statuses
                
                sessions_list.append(session_dict)
            return sessions_list

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
    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    remaining_str = session['remaining_banks']
    remaining = remaining_str.split(",") if remaining_str else []
    
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
            if photo_path:
                await bot.send_photo(
                    chat_id=client_id,
                    photo=FSInputFile(photo_path),
                    caption=caption_text
                )
            else:
                await bot.send_message(
                    chat_id=client_id,
                    text=caption_text
                )
            # Затримка 3 секунди перед надсиланням номера телефону
            await asyncio.sleep(3)

        # Потім надсилаємо картку з номером телефону та кнопкою
        client_msg = await bot.send_message(
            chat_id=client_id,
            text=message_text,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        # Зберігаємо ID повідомлення у клієнта
        await db.update_session_message_id(client_id, client_msg.message_id)
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
            from aiogram.types import ReplyKeyboardRemove
            await bot.send_message(
                chat_id=client_id,
                text="Роботу завершено. Дякуємо за співпрацю.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
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
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            return {"status": "line_rejected", "remaining_banks": new_remaining_str}
        else:
            try:
                await bot.send_message(
                    chat_id=client_id,
                    text=f"Верифікацію для банку {bank_name} завершено. Очікуйте наступний номер.",
                    parse_mode="Markdown"
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
        await bot.send_message(
            chat_id=client_id,
            text="Роботу завершено. Дякуємо за співпрацю.",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    # Закриваємо сесію та вивільняємо лінію
    await db.close_session(client_id)
    return {"status": "terminated"}

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
    bank_name = line_info['bank'] if line_info else "Банк"

    # 1. Відправляємо код клієнту
    await bot.send_message(
        chat_id=client_id,
        text=f"Ваш SMS-код для банку {bank_name}:\n\n`{body.code}`",
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
            text=f"Код {body.code} вручну переслано користувачу @{session['username']} (Line {line_id} - {bank_name}) через веб-панель."
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
    
    try:
        await bot.send_message(chat_id=client_id, text=body.message)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")

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
