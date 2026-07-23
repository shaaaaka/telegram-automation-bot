import aiosqlite
import bot.database as db_mod

async def get_setting(key: str, default: str = None) -> str:
    """Отримання значення налаштування з БД"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        async with db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key: str, value: str):
    """Збереження значення налаштування в БД"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("""
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()

async def get_all_settings() -> dict:
    """Отримання всіх налаштувань"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        async with db.execute("SELECT key, value FROM app_settings") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}
