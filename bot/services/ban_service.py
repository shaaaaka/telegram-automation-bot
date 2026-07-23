import aiosqlite
import bot.database as db_mod

async def ban_user(client_id: int, username: str = None):
    """Додавання користувача до чорного списку"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO banned_users (client_id, username) VALUES (?, ?)", (client_id, username))
        await db.commit()

async def unban_user(client_id: int):
    """Видалення користувача з чорного списку"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("DELETE FROM banned_users WHERE client_id = ?", (client_id,))
        await db.commit()

async def is_user_banned(client_id: int) -> bool:
    """Перевірка чи користувач заблокований"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        async with db.execute("SELECT 1 FROM banned_users WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def get_banned_users() -> list:
    """Отримання списку всіх заблокованих користувачів"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT client_id, username, banned_at FROM banned_users ORDER BY banned_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
