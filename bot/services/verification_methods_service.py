import json
import aiosqlite
import logging
import bot.database as db_mod

logger = logging.getLogger(__name__)


def _parse_json_list(value) -> list:
    """Десеріалізує JSON-рядок у список; повертає [] у разі помилки."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return [v.strip() for v in str(value).split(",") if v.strip()]


def _serialize_json_list(value) -> str:
    """Серіалізує список (або рядок) у JSON-рядок."""
    if value is None:
        return json.dumps([])
    if isinstance(value, list):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps([v.strip() for v in value.split(",") if v.strip()])
    return json.dumps([])


def _norm_linked_bots(linked_bots) -> list:
    """Чистить список юзернеймів ботів: без @, lower-case."""
    bots = _parse_json_list(linked_bots)
    return [b.lstrip("@").strip().lower() for b in bots if b.strip()]


def _row_to_dict(row) -> dict | None:
    """Перетворює рядок таблиці verification_methods у dict із десеріалізованими JSON-полями."""
    if not row:
        return None
    result = dict(row)
    result["allowed_banks"] = _parse_json_list(result.get("allowed_banks"))
    result["linked_bots"] = _parse_json_list(result.get("linked_bots"))
    result["required_client_fields"] = _parse_json_list(result.get("required_client_fields"))
    result["is_active"] = bool(result.get("is_active", 1))
    return result


async def save_verification_method(
    key: str,
    display_name: str | None = None,
    allowed_banks: list | str | None = None,
    linked_bots: list | str | None = None,
    avatar_path: str | None = None,
    required_client_fields: list | str | None = None,
    initial_message: str | None = None,
    is_active: int | None = 1,
    sort_order: int | None = 0,
):
    """Зберігає або оновлює метод верифікації.

    JSON-поля серіалізуються перед записом. При оновленні поля, що не передані
    (None), зберігають попереднє значення.
    """
    key = (key or "").strip()
    if not key:
        raise ValueError("Method key is required")

    existing = await get_verification_method(key)

    if existing:
        # Мердж: якщо параметр не передано, беремо існуюче
        display_name = display_name if display_name is not None else existing.get("display_name")
        allowed_banks = allowed_banks if allowed_banks is not None else existing.get("allowed_banks")
        linked_bots = linked_bots if linked_bots is not None else existing.get("linked_bots")
        avatar_path = avatar_path if avatar_path is not None else existing.get("avatar_path")
        required_client_fields = required_client_fields if required_client_fields is not None else existing.get("required_client_fields")
        initial_message = initial_message if initial_message is not None else existing.get("initial_message")
        is_active = is_active if is_active is not None else int(existing.get("is_active", 1))
        sort_order = sort_order if sort_order is not None else existing.get("sort_order", 0)

    allowed_banks_str = _serialize_json_list(allowed_banks)
    linked_bots_str = _serialize_json_list(_norm_linked_bots(linked_bots))
    required_client_fields_str = _serialize_json_list(required_client_fields)

    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO verification_methods (
                key, display_name, allowed_banks, linked_bots, avatar_path,
                required_client_fields, initial_message, is_active, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                display_name = excluded.display_name,
                allowed_banks = excluded.allowed_banks,
                linked_bots = excluded.linked_bots,
                avatar_path = excluded.avatar_path,
                required_client_fields = excluded.required_client_fields,
                initial_message = excluded.initial_message,
                is_active = excluded.is_active,
                sort_order = excluded.sort_order,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                key,
                display_name,
                allowed_banks_str,
                linked_bots_str,
                avatar_path,
                required_client_fields_str,
                initial_message,
                is_active,
                sort_order,
            ),
        )
        await db.commit()


async def get_verification_method(key: str) -> dict | None:
    """Повертає метод верифікації за ключем."""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM verification_methods WHERE key = ?", (key.strip(),)) as cursor:
            row = await cursor.fetchone()
            return _row_to_dict(row)


async def get_verification_methods(active_only: bool = False) -> list[dict]:
    """Повертає список усіх методів верифікації."""
    query = "SELECT * FROM verification_methods"
    params = ()
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY sort_order, display_name, key"

    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_dict(row) for row in rows]


async def get_verification_method_by_bot_username(bot_username: str) -> dict | None:
    """Знаходить перший активний метод, прив'язаний до username бота."""
    target = (bot_username or "").lstrip("@").strip().lower()
    if not target:
        return None
    methods = await get_verification_methods(active_only=True)
    for method in methods:
        if target in [b.lstrip("@").strip().lower() for b in method.get("linked_bots", [])]:
            return method
    return None


async def delete_verification_method(key: str):
    """Видаляє метод верифікації за ключем."""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("DELETE FROM verification_methods WHERE key = ?", (key.strip(),))
        await db.commit()
