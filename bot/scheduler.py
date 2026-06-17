import asyncio
import logging
import aiosqlite
from aiogram import Bot
from bot.config import DB_FILE
import bot.database as db

logger = logging.getLogger(__name__)

async def auto_reminder_loop(bot: Bot):
    """Фонова задача для автоматичного нагадування клієнтам про верифікацію"""
    logger.info("Запуск фонового планувальника нагадувань...")
    while True:
        try:
            # Перевіряємо, чи ввімкнені нагадування взагалі
            enabled_str = await db.get_setting("reminders_enabled", "1")
            if enabled_str != "1":
                await asyncio.sleep(60)
                continue

            # Отримуємо налаштування з БД
            delay_str = await db.get_setting("reminder_delay_minutes", "5")
            try:
                reminder_delay_minutes = int(delay_str)
            except ValueError:
                reminder_delay_minutes = 5
                
            reminder_text = await db.get_setting(
                "reminder_text", 
                "Ви отримали номер телефону для реєстрації. Будь ласка, введіть його в додатку, щоб ми могли надіслати вам код. Якщо виникли труднощі — напишіть нам!"
            )
            
            async with aiosqlite.connect(DB_FILE) as conn:
                conn.row_factory = aiosqlite.Row
                # Шукаємо сесії, які:
                # 1. Знаходяться в статусах 'number_assigned' або 'waiting_code'
                # 2. Не отримували нагадування (last_reminder_sent_at IS NULL)
                # 3. Призначені більше ніж `reminder_delay_minutes` хвилин тому
                query = """
                    SELECT s.client_id, s.username, l.bank
                    FROM sessions s
                    LEFT JOIN lines l ON s.line_id = l.id
                    WHERE s.status IN ('number_assigned', 'waiting_code')
                      AND s.last_reminder_sent_at IS NULL
                      AND s.assigned_at IS NOT NULL
                      AND CAST((strftime('%s', CURRENT_TIMESTAMP) - strftime('%s', s.assigned_at)) AS INTEGER) >= ? * 60
                """
                async with conn.execute(query, (reminder_delay_minutes,)) as cursor:
                    rows = await cursor.fetchall()
            
            for row in rows:
                client_id = row['client_id']
                username = row['username']
                bank = row['bank'] or 'банку'
                
                # Формуємо текст нагадування
                msg = f"🔔 *Нагадування щодо верифікації {bank}*\n\n{reminder_text}"
                
                try:
                    logger.info(f"Надсилаємо нагадування клієнту @{username} (ID: {client_id})")
                    await bot.send_message(chat_id=client_id, text=msg, parse_mode="Markdown")
                    
                    # Оновлюємо статус у БД
                    async with aiosqlite.connect(DB_FILE) as conn:
                        await conn.execute(
                            "UPDATE sessions SET last_reminder_sent_at = CURRENT_TIMESTAMP WHERE client_id = ?",
                            (client_id,)
                        )
                        await conn.commit()
                except Exception as e:
                    logger.error(f"Помилка відправки нагадування клієнту {client_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Помилка у фоновому циклі планувальника: {e}")
            
        # Затримка 60 секунд перед наступною перевіркою
        await asyncio.sleep(60)
