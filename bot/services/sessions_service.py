import aiosqlite
import logging
import re
import bot.database as db_mod
from bot.services.lines_service import get_line, set_line_status
from bot.services.chat_log_service import log_verification_end, active_subscriptions

async def increment_session_sent_codes_count(client_id: int):
    """Збільшує лічильник відправлених кодів для сесії клієнта на 1"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("""
            UPDATE sessions 
            SET sent_codes_count = COALESCE(sent_codes_count, 0) + 1 
            WHERE client_id = ?
        """, (client_id,))
        await db.commit()

async def create_registering_session(client_id: int, username: str, bot_username: str = None):
    """Створення сесії в статусі заповнення анкети (для відображення на сайті)"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("""
            INSERT INTO sessions (client_id, username, client_data, status, client_message_id, selected_banks, remaining_banks, success_photo_id, card_first4, card_last4, card_photo_id, sent_codes_count, bot_username)
            VALUES (?, ?, '📝 Заповнює реєстраційні дані...', 'registering', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                username = excluded.username,
                client_data = excluded.client_data,
                line_id = NULL,
                client_message_id = NULL,
                selected_banks = NULL,
                remaining_banks = NULL,
                status = 'registering',
                created_at = CURRENT_TIMESTAMP,
                success_photo_id = NULL,
                card_first4 = NULL,
                card_last4 = NULL,
                card_photo_id = NULL,
                pumb_rebind_collected = NULL,
                sent_codes_count = 0,
                is_verified = 0,
                verifier_message_id = NULL,
                notified_banks = '',
                bot_username = COALESCE(excluded.bot_username, sessions.bot_username)
        """, (client_id, username, bot_username))
        await db.commit()

async def create_or_update_session(client_id: int, username: str, client_data: str, bot_username: str = None):
    """Створення нової сесії для клієнта (коли він надсилає свої дані)"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("""
            INSERT INTO sessions (client_id, username, client_data, status, client_message_id, selected_banks, remaining_banks, success_photo_id, card_first4, card_last4, card_photo_id, sent_codes_count, bot_username)
            VALUES (?, ?, ?, 'registered', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                username = excluded.username,
                client_data = excluded.client_data,
                line_id = NULL,
                client_message_id = NULL,
                selected_banks = NULL,
                remaining_banks = NULL,
                status = 'registered',
                created_at = CURRENT_TIMESTAMP,
                success_photo_id = NULL,
                card_first4 = NULL,
                card_last4 = NULL,
                card_photo_id = NULL,
                pumb_rebind_collected = NULL,
                sent_codes_count = 0,
                is_verified = 0,
                verifier_message_id = NULL,
                notified_banks = '',
                bot_username = COALESCE(excluded.bot_username, sessions.bot_username)
        """, (client_id, username, client_data, bot_username))
        await db.commit()

async def update_session_pumb_rebind_collected(client_id: int, collected_json: str | None):
    """Зберігає JSON-стан pumb_rebind_collected у БД."""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute(
            "UPDATE sessions SET pumb_rebind_collected = ? WHERE client_id = ?",
            (collected_json, client_id)
        )
        await db.commit()

async def update_session_verification_data(client_id: int, success_photo_id: str = None, card_first4: str = None, card_last4: str = None, card_photo_id: str = None):
    """Оновлення фото та маски картки верифікації в сесії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("""
            UPDATE sessions 
            SET success_photo_id = COALESCE(?, success_photo_id),
                card_first4 = COALESCE(?, card_first4),
                card_last4 = COALESCE(?, card_last4),
                card_photo_id = COALESCE(?, card_photo_id)
            WHERE client_id = ?
        """, (success_photo_id, card_first4, card_last4, card_photo_id, client_id))
        await db.commit()

async def get_session(client_id: int):
    """Отримання активної сесії клієнта"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_session_verifier_message_id(client_id: int, message_id: int):
    """Оновлення ID повідомлення верифікатора в сесії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE sessions SET verifier_message_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def set_session_verified(client_id: int, is_verified: int = 1):
    """Встановлення прапорця верифікації для сесії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE sessions SET is_verified = ? WHERE client_id = ?", (is_verified, client_id))
        await db.commit()

async def get_session_by_verifier_message_id(message_id: int):
    """Отримання сесії за ID повідомлення верифікатора"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE verifier_message_id = ?", (message_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_session_by_proceedings_question_message_id(message_id: int):
    """Отримання сесії за ID повідомлення запитання про провадження"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE proceedings_question_msg_id = ?", (message_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def set_session_waiting_proceedings(client_id: int, waiting: int):
    """Встановлення прапорця очікування проваджень для сесії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE sessions SET waiting_proceedings = ? WHERE client_id = ?", (waiting, client_id))
        await db.commit()

async def set_session_proceedings_question_msg_id(client_id: int, message_id: int):
    """Встановлення ID повідомлення запитання про провадження"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE sessions SET proceedings_question_msg_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def get_latest_waiting_verification_session():
    """Отримання останньої сесії, яка чекає перевірки"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE status = 'waiting_verification' ORDER BY created_at DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_active_session_by_line(line_id: int):
    """Пошук активної сесії за номером лінії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE line_id = ? AND status != 'completed'", (line_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_all_waiting_sessions():
    """Отримання всіх сесій, які зараз чекають на код"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE status = 'waiting_code'") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def assign_line_to_session(client_id: int, line_id: int, bot_username: str = None):
    """Призначення лінії для клієнта.

    Записує line_id, bank, status='number_assigned', bot_username.
    Якщо у клієнта вже була line іншого банку — звільняє її.
    Керує notified_banks, щоб при повторному призначенні того самого банку
    не дублювати intro.
    """
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")

        old_bank = None
        notified_banks_str = ""
        old_bot_username = None
        old_is_relink = 0
        async with db.execute("SELECT line_id, bank, notified_banks, bot_username, is_relink FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                old_bank = row['bank']
                notified_banks_str = row['notified_banks'] or ""
                old_bot_username = row['bot_username']
                old_is_relink = row['is_relink'] or 0
                if row['line_id'] and row['line_id'] != line_id:
                    await db.execute("UPDATE lines SET status = 'available' WHERE id = ?", (row['line_id'],))

        bank_name = None
        async with db.execute("SELECT bank FROM lines WHERE id = ?", (line_id,)) as cursor:
            l_row = await cursor.fetchone()
            if l_row:
                bank_name = l_row['bank']

        # Якщо банк той самий — зберігаємо is_relink і notified_banks; інакше скидаємо
        if bank_name and old_bank == bank_name:
            new_notified_banks = notified_banks_str
            new_is_relink = old_is_relink
        else:
            notified_list = [b.strip() for b in notified_banks_str.split(",") if b.strip()]
            if bank_name in notified_list:
                notified_list.remove(bank_name)
            new_notified_banks = ",".join(notified_list)
            new_is_relink = None  # дозволити вибір relink/fresh, якщо шаблон дозволяє

        bot_username_to_set = bot_username or old_bot_username

        await db.execute("""
            UPDATE sessions
            SET line_id = ?, status = 'number_assigned',
                bank = ?,
                success_photo_id = NULL,
                card_photo_id = NULL,
                card_first4 = NULL,
                card_last4 = NULL,
                sent_codes_count = 0,
                notified_banks = ?,
                bot_username = ?,
                is_relink = ?
            WHERE client_id = ?
        """, (line_id, bank_name, new_notified_banks, bot_username_to_set, new_is_relink, client_id))
        await db.execute("UPDATE lines SET status = 'busy' WHERE id = ?", (line_id,))
        await db.commit()

async def update_session_message_id(client_id: int, message_id: int):
    """Оновлення ID повідомлення з кнопкою у клієнта"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE sessions SET client_message_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def update_session_waiting_message_id(client_id: int, message_id: int):
    """Оновлення ID повідомлення про очікування номера у клієнта"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE sessions SET waiting_message_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def update_session_instruction_message_id(client_id: int, message_id: int):
    """Оновлення ID повідомлення з інструкцією банку у клієнта"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE sessions SET instruction_message_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def update_session_client_phone(client_id: int, phone: str):
    """Збереження номера телефону клієнта"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE sessions SET client_phone = ? WHERE client_id = ?", (phone, client_id))
        await db.commit()

async def update_session_banks(client_id: int, selected_banks: str, remaining_banks: str):
    """Оновлення списків обраних та залишкових банків для сесії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("""
            UPDATE sessions 
            SET selected_banks = ?, remaining_banks = ? 
            WHERE client_id = ?
        """, (selected_banks, remaining_banks, client_id))
        await db.commit()

async def set_session_status(client_id: int, status: str):
    """Зміна статусу сесії ('registered', 'number_assigned', 'waiting_code', 'completed')"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE sessions SET status = ? WHERE client_id = ?", (status, client_id))
        await db.commit()

async def set_session_is_relink(client_id: int, is_relink: int):
    """Встановлення прапорця перев'язу для сесії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE sessions SET is_relink = ? WHERE client_id = ?", (is_relink, client_id))
        await db.commit()

async def update_session_client_data(client_id: int, client_data: str, status: str = None):
    """Оновлення client_data сесії з можливістю зміни статусу без скидання банків/ліній"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        if status:
            await db.execute(
                "UPDATE sessions SET client_data = ?, status = ? WHERE client_id = ?",
                (client_data, status, client_id)
            )
        else:
            await db.execute(
                "UPDATE sessions SET client_data = ? WHERE client_id = ?",
                (client_data, client_id)
            )
        await db.commit()

async def complete_current_bank(client_id: int, result: str) -> dict | None:
    """Завершення верифікації поточного банку: звільняє лінію, логує, оновлює сесію."""
    session = await get_session(client_id)
    if not session or not session.get('line_id'):
        return None

    line_id = session['line_id']
    line_info = await get_line(line_id)
    bank_name = line_info['bank'] if line_info else "Банк"

    if result in ('success', 'release'):
        line_status = 'success' if result == 'success' else 'available'
        log_status = 'success' if result == 'success' else 'released'
    else:
        line_status = 'banned'
        log_status = 'banned'

    await set_line_status(line_id, line_status)
    await log_verification_end(client_id, bank_name, log_status)

    async with aiosqlite.connect(db_mod.DB_FILE) as db_conn:
        await db_conn.execute("""
            UPDATE sessions
            SET line_id = NULL, client_message_id = NULL, status = 'registered', sent_codes_count = 0
            WHERE client_id = ?
        """, (client_id,))
        await db_conn.commit()

    remaining = session['remaining_banks'].split(",") if session.get('remaining_banks') else []
    if bank_name in remaining:
        remaining.remove(bank_name)
    new_remaining = ",".join(remaining)
    await update_session_banks(client_id, session.get('selected_banks', ''), new_remaining)

    session['remaining_banks'] = new_remaining
    return {
        "session": session,
        "line_id": line_id,
        "bank_name": bank_name,
        "line_status": line_status,
        "log_status": log_status,
        "remaining": remaining,
        "remaining_banks": new_remaining,
        "selected_banks": session.get('selected_banks', ''),
    }

async def send_archive_report(client_id: int, bot):
    """Генерує текстовий звіт про сесію та надсилає його в архівну групу"""
    try:
        from bot.config import get_archive_group_id, LOG_BOT_TOKEN
        archive_group_id = get_archive_group_id()
        if not archive_group_id:
            return
            
        from aiogram import Bot
        
        session = await get_session(client_id)
        if not session:
            return
            
        username = session['username'] or "Невідомий"
        client_data = session['client_data'] or ""
        
        phone_match = re.search(r'(?:Телефон|Тлф|Номер):\s*([^\n]+)', client_data, re.IGNORECASE)
        phone = phone_match.group(1).strip() if phone_match else "Не вказано"
        
        card_first4 = session.get('card_first4') or ""
        card_last4 = session.get('card_last4') or ""
        card_info = f"{card_first4}...{card_last4}" if (card_first4 and card_last4) else "Не розпізнано"
        
        passed_banks = []
        async with aiosqlite.connect(db_mod.DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("""
                SELECT bank, status FROM bank_verifications 
                WHERE client_id = ? AND status = 'success'
            """, (client_id,)) as cursor:
                rows = await cursor.fetchall()
                passed_banks = [r['bank'] for r in rows]
        
        banks_str = ", ".join(passed_banks) if passed_banks else "Немає успішних реєстрацій"
        
        report_lines = [
            "✅ <b>СЕСІЮ ЗАВЕРШЕНО</b>",
            f"👤 <b>Клієнт:</b> @{username} (ID: <code>{client_id}</code>)",
            f"📞 <b>Телефон:</b> <code>{phone}</code>",
            f"🏦 <b>Пройдені банки:</b> {banks_str}",
            f"💳 <b>Картка:</b> <code>{card_info}</code>",
        ]
        
        pib_match = re.search(r'(?:ПІБ|ФИО|Ім\'я):\s*([^\n]+)', client_data, re.IGNORECASE)
        dob_match = re.search(r'(?:ДР|Дата народження|Дата|Дар):\s*([^\n]+)', client_data, re.IGNORECASE)
        if pib_match:
            report_lines.insert(2, f"📝 <b>ПІБ:</b> {pib_match.group(1).strip()}")
        if dob_match:
            report_lines.insert(3, f"📅 <b>ДР:</b> {dob_match.group(1).strip()}")
            
        report_text = "\n".join(report_lines)
        
        send_bot = bot
        close_send_bot = False
        if LOG_BOT_TOKEN:
            try:
                send_bot = Bot(token=LOG_BOT_TOKEN)
                close_send_bot = True
            except Exception as e:
                logging.error(f"Помилка створення log_bot з LOG_BOT_TOKEN: {e}. Використовуємо дефолтного бота.")
                send_bot = bot

        try:
            await send_bot.send_message(
                chat_id=archive_group_id,
                text=report_text,
                parse_mode="HTML"
            )
        finally:
            if close_send_bot:
                try:
                    await send_bot.session.close()
                except Exception as e:
                    logging.error(f"Помилка закриття сесії log_bot: {e}")
                
    except Exception as e:
        logging.error(f"Помилка надсилання архівного звіту: {e}")

async def close_session(client_id: int):
    """Завершення сесії: звільняємо лінію та видаляємо/архівуємо сесію"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT line_id FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['line_id']:
                await db.execute("UPDATE lines SET status = 'available' WHERE id = ?", (row['line_id'],))
        
        await db.execute("UPDATE sessions SET status = 'completed' WHERE client_id = ?", (client_id,))
        await db.commit()

    for admin_id, sub_client_id in list(active_subscriptions.items()):
        if sub_client_id == client_id:
            active_subscriptions.pop(admin_id, None)

    try:
        import web.core
        from bot.bot_registry import get_bot
        bot = web.core.bot or get_bot()
        if bot:
            await send_archive_report(client_id, bot)
    except Exception as e:
        logging.error(f"Помилка відправки архівного звіту: {e}")

async def unassign_line_from_session(client_id: int):
    """Звільнення лінії від сесії клієнта (повернення в доступні)"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT line_id FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['line_id']:
                await db.execute("UPDATE lines SET status = 'available' WHERE id = ?", (row['line_id'],))
        
        await db.execute("""
            UPDATE sessions 
            SET line_id = NULL, 
                status = 'registered',
                success_photo_id = NULL,
                card_photo_id = NULL,
                card_first4 = NULL,
                card_last4 = NULL
            WHERE client_id = ?
        """, (client_id,))
        await db.commit()

async def delete_session_completely(client_id: int):
    """Повне видалення сесії, логів та верифікацій клієнта з вивільненням лінії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT line_id FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['line_id']:
                await db.execute("UPDATE lines SET status = 'available' WHERE id = ?", (row['line_id'],))
        
        await db.execute("DELETE FROM bank_verifications WHERE client_id = ?", (client_id,))
        await db.execute("DELETE FROM chat_logs WHERE client_id = ?", (client_id,))
        await db.execute("DELETE FROM sessions WHERE client_id = ?", (client_id,))
        await db.commit()

async def add_notified_bank(client_id: int, bank_name: str):
    """Додає назву банку до списку сповіщених банків у сесії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT notified_banks FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                current = row['notified_banks'] or ''
                banks = [b.strip() for b in current.split(",") if b.strip()]
                if bank_name not in banks:
                    banks.append(bank_name)
                    new_val = ",".join(banks)
                    await db.execute("UPDATE sessions SET notified_banks = ? WHERE client_id = ?", (new_val, client_id))
                    await db.commit()
