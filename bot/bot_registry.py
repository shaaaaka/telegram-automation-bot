import json
import os
from typing import Optional, Union
import logging
from aiogram import Bot

logger = logging.getLogger(__name__)

_bots_by_username: dict[str, Bot] = {}
_default_bot: Optional[Bot] = None


def _norm_username(username: Optional[str]) -> str:
    return (username or "").lstrip("@").strip().lower()


def set_bot(username: Optional[str], bot: Bot):
    """Реєструє бота за його username (без @, lower-case).

    Якщо username is None — реєструє бота як дефолтного.
    """
    global _default_bot
    normalized = _norm_username(username)
    if not normalized:
        _default_bot = bot
        logger.info("Default bot set")
        return
    _bots_by_username[normalized] = bot
    logger.info(f"Registered bot @{normalized}")


def get_bot(username: Optional[str] = None) -> Optional[Bot]:
    """Повертає дефолтного або конкретного бота за username."""
    if not username:
        return _default_bot
    normalized = _norm_username(username)
    bot = _bots_by_username.get(normalized)
    if bot:
        return bot
    return _default_bot


def get_bot_strict(username: Optional[str] = None) -> Optional[Bot]:
    """Повертає бота за username, без fallback на дефолтного."""
    if not username:
        return None
    return _bots_by_username.get(_norm_username(username))


def get_all_bots() -> list[Bot]:
    """Повертає унікальний список усіх зареєстрованих Bot-інстансів (за токеном)."""
    seen_tokens = set()
    result = []
    for bot in list(_bots_by_username.values()):
        token = getattr(bot, "token", None)
        if token and token in seen_tokens:
            continue
        if token:
            seen_tokens.add(token)
        result.append(bot)
    if _default_bot:
        token = getattr(_default_bot, "token", None)
        if not token or token not in seen_tokens:
            if token:
                seen_tokens.add(token)
            result.append(_default_bot)
    return result


async def get_bot_for_session(session: Union[dict, int, None] = None) -> Optional[Bot]:
    """Повертає бот, яким спілкується клієнт, за полем session['bot_username'].

    Приймає dict (session), client_id (int) або None.
    """
    if isinstance(session, int):
        import bot.database as db
        session = await db.get_session(session)
    if not session:
        return _default_bot
    return get_bot(session.get("bot_username"))


async def init_bots(default_token: Optional[str]):
    """Ініціалізує дефолтного бота та профільних ботів із BOTS env / профілів."""
    global _default_bot

    seen_tokens = set()

    async def _init_bot(token: str, source: str) -> Optional[Bot]:
        if not token or token in seen_tokens:
            return None
        seen_tokens.add(token)
        b = Bot(token=token)
        try:
            me = await b.get_me()
            if not me.username:
                logger.warning(f"Bot from {source} has no username")
                return None
            set_bot(me.username, b)
            logger.info(f"Bot initialized from {source}: @{me.username}")
            return b
        except Exception as e:
            logger.error(f"Failed to initialize bot from {source}: {e}")
            try:
                await b.session.close()
            except Exception:
                pass
            return None

    # Дефолтний бот
    if default_token:
        default_bot = await _init_bot(default_token, "BOT_TOKEN")
        if default_bot:
            _default_bot = default_bot

    # Боти з BOTS env
    bots_json = os.getenv("BOTS")
    if bots_json:
        try:
            bots_list = json.loads(bots_json)
            if not isinstance(bots_list, list):
                bots_list = []
        except Exception as e:
            logger.error(f"Failed to parse BOTS env: {e}")
            bots_list = []
        for bot_info in bots_list:
            if not isinstance(bot_info, dict):
                continue
            token = bot_info.get("token")
            source = bot_info.get("username") or "BOTS env"
            await _init_bot(token, source)

    # Боти з банк-профілів для зворотної сумісності
    try:
        from bot.services.bank_profiles_service import get_all_bank_profiles

        profiles = await get_all_bank_profiles()
        for p in profiles.values():
            token = p.get("bot_token")
            if not token:
                continue
            await _init_bot(token, f"bank profile {p.get('profile_key')}")
    except Exception as e:
        logger.error(f"Failed to load profile bots: {e}")

    # Якщо дефолтного бота не задано — беремо першого зареєстрованого
    if _default_bot is None and _bots_by_username:
        first = next(iter(_bots_by_username.values()))
        _default_bot = first
        logger.info(f"Default bot set to first registered: @{first}")


async def close_all_bots():
    """Закриває сесії всіх унікальних ботів."""
    for bot in get_all_bots():
        try:
            await bot.session.close()
        except Exception as e:
            logger.error(f"Error closing bot session: {e}")


# --- Зворотна сумісність ---

def set_default_bot(bot: Bot):
    """Псевдонім для set_bot(None, bot)."""
    set_bot(None, bot)


def register_bot(username: str, bot: Bot):
    """Псевдонім для set_bot(username, bot)."""
    set_bot(username, bot)
