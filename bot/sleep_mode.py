import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bot.config import get_cached_setting, get_admin_id

logger = logging.getLogger(__name__)

# Статичні зміщення для відомих часових поясів, якщо ZoneInfo не зміг знайти tzdata
_FALLBACK_OFFSETS = {
    "Europe/Kyiv": 2,   # EET (UTC+2) — без урахування DST
    "Europe/Berlin": 1, # CET (UTC+1) — без урахування DST
}


def get_sleep_settings():
    """Повертає поточні налаштування режиму сну з кешу."""
    enabled = get_cached_setting("sleep_mode_enabled", "0") == "1"
    start = get_cached_setting("sleep_mode_start", "22:00")
    end = get_cached_setting("sleep_mode_end", "08:00")
    tz_name = get_cached_setting("sleep_mode_timezone", "Europe/Kyiv")
    return enabled, start, end, tz_name


def _parse_time(time_str):
    """Парсить час у форматі HH:MM або HH:MM:SS."""
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Invalid time format: {time_str}")


def is_in_sleep_mode() -> bool:
    """Перевіряє, чи зараз активний режим сну за вказаним часовим поясом."""
    enabled, start_str, end_str, tz_name = get_sleep_settings()
    if not enabled:
        return False

    try:
        tz = ZoneInfo(tz_name)
    except Exception as e:
        logger.warning("Invalid sleep timezone %s: %s. Using fixed offset fallback.", tz_name, e)
        offset = _FALLBACK_OFFSETS.get(tz_name, 0)
        tz = timezone(timedelta(hours=offset))

    now = datetime.now(tz)
    try:
        start_time = _parse_time(start_str)
        end_time = _parse_time(end_str)
    except Exception as e:
        logger.warning("Invalid sleep time format (%s / %s): %s. Sleep mode disabled.", start_str, end_str, e)
        return False

    now_time = now.time()
    if start_time <= end_time:
        return start_time <= now_time < end_time
    else:
        # Інтервал переходить через північ (напр. 23:00 - 08:00)
        return now_time >= start_time or now_time < end_time


def is_client_chat(chat_id) -> bool:
    """Перевіряє, що chat_id належить клієнту (особистий чат, не група і не адмін)."""
    try:
        chat_id = int(chat_id)
    except (ValueError, TypeError):
        return False
    return chat_id > 0 and chat_id != get_admin_id()


def silence_method_if_sleeping(method):
    """Встановлює disable_notification=True для методів, що надсилаються клієнту під час сну."""
    if not is_in_sleep_mode():
        return
    if not hasattr(method, "chat_id") or not hasattr(method, "disable_notification"):
        return
    if is_client_chat(method.chat_id):
        method.disable_notification = True
