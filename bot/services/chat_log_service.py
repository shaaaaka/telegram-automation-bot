import aiosqlite
import contextvars
import asyncio
import logging
import bot.database as db_mod

current_sender = contextvars.ContextVar("current_sender", default="bot")
chat_message_callbacks = []
active_subscriptions = {}

async def log_verification_start(client_id: int, username: str, bank: str, phone_number: str):
    """Логування початку верифікації для лінії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("""
            UPDATE sessions
            SET assigned_at = CURRENT_TIMESTAMP, last_reminder_sent_at = NULL
            WHERE client_id = ?
        """, (client_id,))
        
        await db.execute("""
            INSERT INTO bank_verifications (client_id, username, bank, phone_number, assigned_at, status)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'pending')
        """, (client_id, username or 'Невідомий', bank, phone_number))
        await db.commit()

async def log_verification_end(client_id: int, bank: str, status: str):
    """Логування завершення верифікації (успіх/відмова/випуск)"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT id, assigned_at FROM bank_verifications
            WHERE client_id = ? AND bank = ? AND status = 'pending'
            ORDER BY id DESC LIMIT 1
        """, (client_id, bank)) as cursor:
            row = await cursor.fetchone()
            if row:
                await db.execute("""
                    UPDATE bank_verifications
                    SET completed_at = CURRENT_TIMESTAMP,
                        status = ?,
                        duration_seconds = CAST((strftime('%s', CURRENT_TIMESTAMP) - strftime('%s', assigned_at)) AS INTEGER)
                    WHERE id = ?
                """, (status, row['id']))
                await db.commit()

async def get_client_verification_history(client_id: int):
    """Отримання історії верифікацій клієнта"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT bank, status, assigned_at, completed_at, phone_number, duration_seconds
            FROM bank_verifications
            WHERE client_id = ?
            ORDER BY assigned_at DESC
            LIMIT 50
        """, (client_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_statistics() -> dict:
    """Отримання агрегованої статистики для веб-панелі"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        
        async with db.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' OR status = 'released' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'banned' THEN 1 ELSE 0 END) as failure_count
            FROM bank_verifications
            WHERE status != 'pending'
        """) as cursor:
            totals = dict(await cursor.fetchone())
            
        async with db.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' OR status = 'released' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'banned' THEN 1 ELSE 0 END) as failure_count
            FROM bank_verifications
            WHERE status != 'pending' AND date(assigned_at) = date('now')
        """) as cursor:
            today = dict(await cursor.fetchone())
            
        async with db.execute("""
            SELECT 
                bank,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' OR status = 'released' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'banned' THEN 1 ELSE 0 END) as failure,
                ROUND(AVG(duration_seconds)) as avg_duration
            FROM bank_verifications
            WHERE status != 'pending' AND duration_seconds IS NOT NULL
            GROUP BY bank
            ORDER BY total DESC
        """) as cursor:
            banks_stats = [dict(row) for row in await cursor.fetchall()]
            
        return {
            "totals": totals,
            "today": today,
            "banks": banks_stats
        }

async def clear_statistics():
    """Видалення всієї статистики верифікацій"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("DELETE FROM bank_verifications")
        await db.commit()

async def log_chat_message(client_id: int, sender: str, message_text: str = None, photo_id: str = None, message_id: int = None, reply_to_message_id: int = None):
    """Збереження повідомлення в історію чату"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        try:
            await db.execute("""
                INSERT INTO chat_logs (client_id, sender, message_text, photo_id, message_id, reply_to_message_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (client_id, sender, message_text, photo_id, message_id, reply_to_message_id))
        except Exception:
            try:
                await db.execute("""
                    INSERT INTO chat_logs (client_id, sender, message_text, photo_id, message_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (client_id, sender, message_text, photo_id, message_id))
            except Exception:
                await db.execute("""
                    INSERT INTO chat_logs (client_id, sender, message_text, photo_id)
                    VALUES (?, ?, ?, ?)
                """, (client_id, sender, message_text, photo_id))
        await db.commit()
    
    for cb in chat_message_callbacks:
        try:
            asyncio.create_task(cb(client_id, sender, message_text, photo_id, message_id, reply_to_message_id))
        except Exception as e:
            logging.error(f"Error in chat_message_callback: {e}")

async def get_chat_logs(client_id: int):
    """Отримання всієї історії чату для конкретного клієнта"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM chat_logs WHERE client_id = ? ORDER BY created_at ASC, COALESCE(message_id, id) ASC
        """, (client_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def clear_chat_logs(client_id: int):
    """Видалення всієї історії чату для конкретного клієнта"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("DELETE FROM chat_logs WHERE client_id = ?", (client_id,))
        await db.commit()
