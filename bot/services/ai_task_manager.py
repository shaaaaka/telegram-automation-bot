import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Словник для відстеження активних задач ШІ: client_id -> asyncio.Task
_active_ai_tasks: Dict[int, asyncio.Task] = {}


def register_ai_task(client_id: int, task: asyncio.Task) -> None:
    """Реєстрація активної асинхронної задачі ШІ для клієнта."""
    # Якщо вже є запущена задача для цього клієнта — скасовуємо попередню
    cancel_ai_task(client_id)
    _active_ai_tasks[client_id] = task


def cancel_ai_task(client_id: int) -> bool:
    """Миттєве скасування активної задачі ШІ для клієнта."""
    task = _active_ai_tasks.pop(client_id, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"🛑 [AI Task Manager] Скасовано активну задачу ШІ для клієнта {client_id}")
        return True
    return False


def unregister_ai_task(client_id: int, task: Optional[asyncio.Task] = None) -> None:
    """Видалення задачі зі словника після завершення."""
    current_task = _active_ai_tasks.get(client_id)
    if current_task is task or task is None:
        _active_ai_tasks.pop(client_id, None)


async def is_session_ai_paused(client_id: int) -> bool:
    """Перевірка стану is_paused для клієнта в БД."""
    try:
        from bot.database import get_session
        session = await get_session(client_id)
        if session and session.get("is_paused"):
            return True
    except Exception as e:
        logger.error(f"Помилка перевірки is_paused для client {client_id}: {e}")
    return False
