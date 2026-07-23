import aiosqlite
import bot.database as db_mod
from bot.config import DEFAULT_BANK_ORDER

async def add_or_update_line(line_id: int, phone_number: str, bank: str):
    """Додавання нової або оновлення існуючої лінії"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("""
            INSERT INTO lines (line_id, phone_number, bank, status)
            VALUES (?, ?, ?, 'available')
            ON CONFLICT(line_id, bank) DO UPDATE SET
                phone_number = excluded.phone_number,
                status = 'available'
        """, (line_id, phone_number, bank))
        await db.commit()

async def get_all_lines():
    """Отримання всіх ліній із бази даних"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM lines ORDER BY line_id, bank") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_available_lines():
    """Отримання всіх вільних ліній"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM lines WHERE status = 'available'") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_line(line_id: int):
    """Отримання інформації про конкретну лінію"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM lines WHERE id = ?", (line_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def set_line_status(line_id: int, status: str):
    """Зміна статусу лінії ('available', 'busy')"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("UPDATE lines SET status = ? WHERE id = ?", (status, line_id))
        await db.commit()

async def get_unique_banks():
    """Отримання списку всіх унікальних назв банків, що є в базі ліній"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        async with db.execute("SELECT DISTINCT bank FROM lines") as cursor:
            rows = await cursor.fetchall()
            banks = [row[0] for row in rows if row[0] and row[0].lower() not in ('ecobank', 'pumb')]
            
            def get_sort_key(bank):
                try:
                    return DEFAULT_BANK_ORDER.index(bank)
                except ValueError:
                    for i, item in enumerate(DEFAULT_BANK_ORDER):
                        if item.lower() == bank.lower():
                            return i
                    return len(DEFAULT_BANK_ORDER)
            
            return sorted(banks, key=get_sort_key)

async def clear_all_lines():
    """Видалення всіх ліній із бази даних"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("DELETE FROM lines")
        await db.commit()

async def delete_line(line_id: int):
    """Видалення лінії за її ID"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("DELETE FROM lines WHERE id = ?", (line_id,))
        await db.commit()

async def get_max_line_id() -> int:
    """Отримання максимального ID лінії в базі даних"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        async with db.execute("SELECT MAX(line_id) FROM lines") as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0
