import aiosqlite
from bot.config import DB_FILE

async def get_all_ai_rules():
    """Отримання всіх правил ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ai_rules ORDER BY category, id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_active_ai_rules(category: str = None):
    """Отримання списку активних правил ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        if category:
            query = "SELECT * FROM ai_rules WHERE is_active = 1 AND category = ? ORDER BY id ASC"
            params = (category,)
        else:
            query = "SELECT * FROM ai_rules WHERE is_active = 1 ORDER BY category, id ASC"
            params = ()
            
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def add_ai_rule(rule_text: str, category: str = 'general', is_active: int = 1) -> int:
    """Додавання нового правила ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            INSERT INTO ai_rules (rule_text, category, is_active)
            VALUES (?, ?, ?)
        """, (rule_text, category, is_active))
        await db.commit()
        return cursor.lastrowid

async def toggle_ai_rule(rule_id: int, is_active: int = None) -> bool:
    """Увімкнення/вимкнення правила ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        if is_active is None:
            await db.execute("""
                UPDATE ai_rules 
                SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END
                WHERE id = ?
            """, (rule_id,))
        else:
            await db.execute("""
                UPDATE ai_rules 
                SET is_active = ?
                WHERE id = ?
            """, (is_active, rule_id))
        await db.commit()
        return True

async def delete_ai_rule(rule_id: int) -> bool:
    """Видалення правила ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM ai_rules WHERE id = ?", (rule_id,))
        await db.commit()
        return True

async def update_ai_rule(rule_id: int, rule_text: str, category: str, is_active: int) -> bool:
    """Оновлення тексту, категорії та статусу правила ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            UPDATE ai_rules 
            SET rule_text = ?, category = ?, is_active = ?
            WHERE id = ?
        """, (rule_text, category, is_active, rule_id))
        await db.commit()
        return True

async def get_all_ai_examples():
    """Отримання всіх few-shot прикладів діалогу ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ai_examples ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_active_ai_examples():
    """Отримання активних few-shot прикладів діалогу ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ai_examples WHERE is_active = 1 ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def add_ai_example(client_message: str, bot_response: str, is_active: int = 1) -> int:
    """Додавання прикладу діалогу для ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            INSERT INTO ai_examples (client_message, bot_response, is_active)
            VALUES (?, ?, ?)
        """, (client_message, bot_response, is_active))
        await db.commit()
        return cursor.lastrowid

async def delete_ai_example(example_id: int) -> bool:
    """Видалення прикладу діалогу"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM ai_examples WHERE id = ?", (example_id,))
        await db.commit()
        return True

async def update_ai_example(example_id: int, client_message: str, bot_response: str, is_active: int) -> bool:
    """Оновлення прикладу діалогу ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            UPDATE ai_examples
            SET client_message = ?, bot_response = ?, is_active = ?
            WHERE id = ?
        """, (client_message, bot_response, is_active, example_id))
        await db.commit()
        return True

async def toggle_ai_example(example_id: int, is_active: int = None) -> bool:
    """Увімкнення/вимкнення прикладу діалогу ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        if is_active is None:
            await db.execute("""
                UPDATE ai_examples 
                SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END
                WHERE id = ?
            """, (example_id,))
        else:
            await db.execute("""
                UPDATE ai_examples 
                SET is_active = ?
                WHERE id = ?
            """, (is_active, example_id))
        await db.commit()
        return True
