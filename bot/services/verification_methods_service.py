import aiosqlite
import json
import logging
import bot.database as db_mod

logger = logging.getLogger(__name__)


async def get_all_verification_methods() -> dict:
    """Отримання всіх методів верифікації"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM verification_methods") as cursor:
            rows = await cursor.fetchall()
            return {
                row['key']: _row_to_dict(row) for row in rows
            }


async def get_active_verification_methods() -> dict:
    """Отримання активних методів верифікації"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM verification_methods WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            return {
                row['key']: _row_to_dict(row) for row in rows
            }


async def get_verification_method(key: str) -> dict | None:
    """Отримання методу за ключем"""
    if not key:
        return None
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM verification_methods WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return _row_to_dict(row) if row else None


async def save_verification_method(
    key: str,
    display_name: str,
    required_client_fields: list | None = None,
    required_screenshots: int = 0,
    screenshot_instructions: str = None,
    initial_message: str = None,
    report_template: str = None,
    ai_rules: str = None,
    allowed_banks: list | None = None,
    ask_relink_at_start: int = 0,
    is_active: int = 1
):
    """Збереження або оновлення методу верифікації"""
    if required_client_fields is None:
        required_client_fields = []
    if allowed_banks is None:
        allowed_banks = []
    fields_json = json.dumps(required_client_fields)
    banks_json = json.dumps(allowed_banks)

    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("""
            INSERT INTO verification_methods (key, display_name, required_client_fields, required_screenshots, screenshot_instructions, initial_message, report_template, ai_rules, allowed_banks, ask_relink_at_start, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                display_name = excluded.display_name,
                required_client_fields = excluded.required_client_fields,
                required_screenshots = excluded.required_screenshots,
                screenshot_instructions = excluded.screenshot_instructions,
                initial_message = excluded.initial_message,
                report_template = excluded.report_template,
                ai_rules = excluded.ai_rules,
                allowed_banks = excluded.allowed_banks,
                ask_relink_at_start = excluded.ask_relink_at_start,
                is_active = excluded.is_active
        """, (key, display_name, fields_json, required_screenshots, screenshot_instructions, initial_message, report_template, ai_rules, banks_json, ask_relink_at_start, is_active))
        await db.commit()


async def delete_verification_method(key: str):
    """Видалення методу верифікації"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("DELETE FROM verification_methods WHERE key = ?", (key,))
        await db.commit()


async def get_method_required_fields(key: str) -> list:
    """Повертає список обов'язкових текстових полів для методу"""
    method = await get_verification_method(key)
    if not method:
        return []
    fields = method.get('required_client_fields')
    if isinstance(fields, str):
        try:
            return json.loads(fields)
        except json.JSONDecodeError:
            return []
    return fields or []


def _row_to_dict(row):
    result = dict(row)
    try:
        result['required_client_fields'] = json.loads(result.get('required_client_fields') or '[]')
    except (json.JSONDecodeError, TypeError):
        result['required_client_fields'] = []
    try:
        result['allowed_banks'] = json.loads(result.get('allowed_banks') or '[]')
    except (json.JSONDecodeError, TypeError):
        result['allowed_banks'] = []
    result['ask_relink_at_start'] = result.get('ask_relink_at_start') or 0
    return result
