import aiosqlite
import logging
import bot.database as db_mod
from typing import Optional, List

logger = logging.getLogger(__name__)


def _norm_key(key: str) -> str:
    return (key or "").strip().lower()


def _norm_username(username: str) -> str:
    return (username or "").lstrip("@").strip().lower()


async def save_bank_profile(
    profile_key: str,
    name: str,
    selected_banks: list = None,
    bot_username: Optional[str] = None,
    bot_token: Optional[str] = None,
    avatar_data_url: Optional[str] = None,
    is_active: int = 1,
    sort_order: int = 0,
):
    """Збереження або оновлення профілю банків."""
    selected_banks = selected_banks or []
    selected_banks_str = ",".join(str(b).strip() for b in selected_banks if str(b).strip())

    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO bank_profiles (profile_key, name, selected_banks, bot_username, bot_token, avatar_data_url, is_active, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_key) DO UPDATE SET
                name = excluded.name,
                selected_banks = excluded.selected_banks,
                bot_username = excluded.bot_username,
                bot_token = excluded.bot_token,
                avatar_data_url = excluded.avatar_data_url,
                is_active = excluded.is_active,
                sort_order = excluded.sort_order
            """,
            (profile_key.strip(), name or profile_key, selected_banks_str, bot_username or None, bot_token or None, avatar_data_url or None, is_active, sort_order)
        )
        await db.commit()


async def get_all_bank_profiles() -> dict:
    """Отримання всіх профілів банків."""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bank_profiles ORDER BY sort_order, profile_key") as cursor:
            rows = await cursor.fetchall()
            result = {}
            for row in rows:
                key = row["profile_key"]
                selected_banks_str = row["selected_banks"] or ""
                result[key] = {
                    "profile_key": key,
                    "name": row["name"],
                    "selected_banks": [b.strip() for b in selected_banks_str.split(",") if b.strip()],
                    "bot_username": row["bot_username"],
                    "bot_token": row["bot_token"],
                    "avatar_data_url": row["avatar_data_url"],
                    "is_active": row["is_active"],
                    "sort_order": row["sort_order"],
                }
            return result


async def get_active_bank_profiles() -> List[dict]:
    """Отримання лише активних профілів."""
    profiles = await get_all_bank_profiles()
    return [p for p in profiles.values() if p.get("is_active")]


async def get_bank_profile_by_key(profile_key: str) -> Optional[dict]:
    """Отримання профілю за ключем."""
    profiles = await get_all_bank_profiles()
    return profiles.get(_norm_key(profile_key))


async def get_bank_profile_by_bot_username(bot_username: str) -> Optional[dict]:
    """Отримання профілю за username Telegram-бота."""
    profiles = await get_all_bank_profiles()
    target = _norm_username(bot_username)
    for p in profiles.values():
        if _norm_username(p.get("bot_username")) == target:
            return p
    return None


async def delete_bank_profile(profile_key: str):
    """Видалення профілю."""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("DELETE FROM bank_profiles WHERE profile_key = ?", (profile_key.strip(),))
        await db.commit()


async def update_bank_profiles_order(ordered_keys: List[str]):
    """Оновлення sort_order відповідно до заданого порядку."""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        for idx, key in enumerate(ordered_keys):
            await db.execute(
                "UPDATE bank_profiles SET sort_order = ? WHERE profile_key = ?",
                (idx, str(key).strip())
            )
        await db.commit()
