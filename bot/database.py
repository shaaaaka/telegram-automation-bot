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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
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
