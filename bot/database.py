import aiosqlite
from bot.config import DB_FILE

async def init_db():
    """Ініціалізація бази даних та створення таблиць"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Таблиця для збереження телефонних ліній
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lines (
                id INTEGER PRIMARY KEY,
                phone_number TEXT NOT NULL,
                bank TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'available'
            )
        """)
        
        # Таблиця для збереження активних сесій верифікації
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                client_id INTEGER PRIMARY KEY,
                username TEXT,
                client_data TEXT NOT NULL,
                line_id INTEGER REFERENCES lines(id),
                client_message_id INTEGER,
                selected_banks TEXT,  -- Список обраних банків (через кому)
                remaining_banks TEXT, -- Список банків, які залишилося пройти (через кому)
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_at TIMESTAMP,
                last_reminder_sent_at TIMESTAMP
            )
        """)
        
        # Додаємо нові колонки, якщо вони ще не існують (для зворотної сумісності)
        try:
            await db.execute("ALTER TABLE sessions ADD COLUMN assigned_at TIMESTAMP")
        except aiosqlite.OperationalError:
            pass
            
        try:
            await db.execute("ALTER TABLE sessions ADD COLUMN last_reminder_sent_at TIMESTAMP")
        except aiosqlite.OperationalError:
            pass

        # Таблиця для логування статистики верифікацій
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bank_verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                username TEXT,
                bank TEXT,
                phone_number TEXT,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT, -- 'success', 'banned', 'released', 'pending'
                duration_seconds INTEGER
            )
        """)

        # Таблиця для загальних налаштувань
        await db.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Таблиця для шаблонів завантаження банків
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bank_templates (
                key TEXT PRIMARY KEY,
                command TEXT,
                text TEXT
            )
        """)
        
        # Заповнюємо налаштування за замовчуванням
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('reminder_delay_minutes', '5')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('reminder_text', 'Ви отримали номер телефону для реєстрації. Будь ласка, введіть його в додатку, щоб ми могли надіслати вам код. Якщо виникли труднощі — напишіть нам!')")

        # Ініціалізуємо стандартні шаблони банків, якщо таблиця порожня
        cursor = await db.execute("SELECT COUNT(*) FROM bank_templates")
        count = (await cursor.fetchone())[0]
        if count == 0:
            from bot.config import BANK_TEMPLATES
            for key, val in BANK_TEMPLATES.items():
                await db.execute(
                    "INSERT INTO bank_templates (key, command, text) VALUES (?, ?, ?)",
                    (key, val['command'], val['text'])
                )

        await db.commit()

# --- Робота з лініями (Lines) ---

async def add_or_update_line(line_id: int, phone_number: str, bank: str):
    """Додавання нової або оновлення існуючої лінії"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO lines (id, phone_number, bank, status)
            VALUES (?, ?, ?, 'available')
            ON CONFLICT(id) DO UPDATE SET
                phone_number = excluded.phone_number,
                bank = excluded.bank,
                status = 'available'
        """, (line_id, phone_number, bank))
        await db.commit()

async def get_available_lines():
    """Отримання всіх вільних ліній"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM lines WHERE status = 'available'") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_line(line_id: int):
    """Отримання інформації про конкретну лінію"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM lines WHERE id = ?", (line_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def set_line_status(line_id: int, status: str):
    """Зміна статусу лінії ('available', 'busy')"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE lines SET status = ? WHERE id = ?", (status, line_id))
        await db.commit()

async def get_unique_banks():
    """Отримання списку всіх унікальних назв банків, що є в базі ліній"""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT DISTINCT bank FROM lines") as cursor:
            rows = await cursor.fetchall()
            banks = [row[0] for row in rows]
            
            # Сортування за послідовністю користувача
            custom_order = ["PUMB", "bank.kd", "IziBank", "EcoBank", "Alliance", "LvivBank", "AmoBank"]
            def get_sort_key(bank):
                try:
                    return custom_order.index(bank)
                except ValueError:
                    # Регістронезалежне співпадіння
                    for i, item in enumerate(custom_order):
                        if item.lower() == bank.lower():
                            return i
                    return len(custom_order)  # Всі інші в кінець
            
            return sorted(banks, key=get_sort_key)

async def clear_all_lines():
    """Видалення всіх ліній із бази даних"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM lines")
        await db.commit()

async def delete_line(line_id: int):
    """Видалення лінії за її ID"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM lines WHERE id = ?", (line_id,))
        await db.commit()


# --- Робота з сесіями клієнтів (Sessions) ---

async def create_or_update_session(client_id: int, username: str, client_data: str):
    """Створення нової сесії для клієнта (коли він надсилає свої дані)"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO sessions (client_id, username, client_data, status, client_message_id, selected_banks, remaining_banks)
            VALUES (?, ?, ?, 'registered', NULL, NULL, NULL)
            ON CONFLICT(client_id) DO UPDATE SET
                username = excluded.username,
                client_data = excluded.client_data,
                line_id = NULL,
                client_message_id = NULL,
                selected_banks = NULL,
                remaining_banks = NULL,
                status = 'registered',
                created_at = CURRENT_TIMESTAMP
        """, (client_id, username, client_data))
        await db.commit()

async def get_session(client_id: int):
    """Отримання активної сесії клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_active_session_by_line(line_id: int):
    """Пошук активної сесії за номером лінії"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE line_id = ? AND status != 'completed'", (line_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_all_waiting_sessions():
    """Отримання всіх сесій, які зараз чекають на код"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE status = 'waiting_code'") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def assign_line_to_session(client_id: int, line_id: int):
    """Призначення лінії для клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Встановлюємо статус сесії
        await db.execute("""
            UPDATE sessions
            SET line_id = ?, status = 'number_assigned'
            WHERE client_id = ?
        """, (line_id, client_id))
        # Маркуємо лінію як зайняту
        await db.execute("UPDATE lines SET status = 'busy' WHERE id = ?", (line_id,))
        await db.commit()

async def update_session_message_id(client_id: int, message_id: int):
    """Оновлення ID повідомлення з кнопкою у клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET client_message_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def update_session_banks(client_id: int, selected_banks: str, remaining_banks: str):
    """Оновлення списків обраних та залишкових банків для сесії"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            UPDATE sessions 
            SET selected_banks = ?, remaining_banks = ? 
            WHERE client_id = ?
        """, (selected_banks, remaining_banks, client_id))
        await db.commit()

async def set_session_status(client_id: int, status: str):
    """Зміна статусу сесії ('registered', 'number_assigned', 'waiting_code', 'completed')"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET status = ? WHERE client_id = ?", (status, client_id))
        await db.commit()

async def close_session(client_id: int):
    """Завершення сесії: звільняємо лінію та видаляємо/архівуємо сесію"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Отримуємо інформацію про лінію перед видаленням сесії
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT line_id FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['line_id']:
                # Звільняємо лінію
                await db.execute("UPDATE lines SET status = 'available' WHERE id = ?", (row['line_id'],))
        
        # Переводимо сесію в статус завершеної
        await db.execute("UPDATE sessions SET status = 'completed' WHERE client_id = ?", (client_id,))
        await db.commit()

# --- Статистика, Налаштування та Шаблони (Stats, Settings & Templates) ---

async def get_setting(key: str, default: str = None) -> str:
    """Отримання значення налаштування з БД"""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key: str, value: str):
    """Збереження значення налаштування в БД"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()

async def get_all_settings() -> dict:
    """Отримання всіх налаштувань"""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT key, value FROM app_settings") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

async def get_all_bank_templates() -> dict:
    """Отримання всіх шаблонів банків"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bank_templates") as cursor:
            rows = await cursor.fetchall()
            return {row['key']: {'command': row['command'], 'text': row['text']} for row in rows}

async def save_bank_template(key: str, command: str, text: str):
    """Збереження або оновлення шаблону банку"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO bank_templates (key, command, text)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                command = excluded.command,
                text = excluded.text
        """, (key, command, text))
        await db.commit()

async def delete_bank_template(key: str):
    """Видалення шаблону банку"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM bank_templates WHERE key = ?", (key,))
        await db.commit()

async def get_bank_template_db(bank_name: str):
    """Отримання шаблону за назвою банку (async версія)"""
    if not bank_name:
        return None
    templates = await get_all_bank_templates()
    name_norm = bank_name.lower().replace(" ", "").replace("-", "")
    for key, val in templates.items():
        if key in name_norm or name_norm in key:
            return val
    return None

async def get_bank_template_with_key_db(bank_name: str):
    """Отримання шаблону та ключа за назвою банку (async версія)"""
    if not bank_name:
        return None, None
    templates = await get_all_bank_templates()
    name_norm = bank_name.lower().replace(" ", "").replace("-", "")
    for key, val in templates.items():
        if key in name_norm or name_norm in key:
            return key, val
    return None, None

async def log_verification_start(client_id: int, username: str, bank: str, phone_number: str):
    """Логування початку верифікації для лінії"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Оновлюємо час призначення та скидаємо статус нагадування в сесії
        await db.execute("""
            UPDATE sessions
            SET assigned_at = CURRENT_TIMESTAMP, last_reminder_sent_at = NULL
            WHERE client_id = ?
        """, (client_id,))
        
        # Створюємо запис у таблиці статистики
        await db.execute("""
            INSERT INTO bank_verifications (client_id, username, bank, phone_number, assigned_at, status)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'pending')
        """, (client_id, username or 'Невідомий', bank, phone_number))
        await db.commit()

async def log_verification_end(client_id: int, bank: str, status: str):
    """Логування завершення верифікації (успіх/відмова/випуск)"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Шукаємо останню незавершену верифікацію для цього клієнта та банку
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT id, assigned_at FROM bank_verifications
            WHERE client_id = ? AND bank = ? AND status = 'pending'
            ORDER BY id DESC LIMIT 1
        """, (client_id, bank)) as cursor:
            row = await cursor.fetchone()
            if row:
                # Вираховуємо тривалість у секундах
                await db.execute("""
                    UPDATE bank_verifications
                    SET completed_at = CURRENT_TIMESTAMP,
                        status = ?,
                        duration_seconds = CAST((strftime('%s', CURRENT_TIMESTAMP) - strftime('%s', assigned_at)) AS INTEGER)
                    WHERE id = ?
                """, (status, row['id']))
                await db.commit()

async def get_statistics() -> dict:
    """Отримання агрегованої статистики для веб-панелі"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        
        # Загальні показники
        async with db.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' OR status = 'released' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'banned' THEN 1 ELSE 0 END) as failure_count
            FROM bank_verifications
            WHERE status != 'pending'
        """) as cursor:
            totals = dict(await cursor.fetchone())
            
        # Показники за сьогодні
        async with db.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' OR status = 'released' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'banned' THEN 1 ELSE 0 END) as failure_count
            FROM bank_verifications
            WHERE status != 'pending' AND date(assigned_at) = date('now')
        """) as cursor:
            today = dict(await cursor.fetchone())
            
        # Середня тривалість по банках
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
