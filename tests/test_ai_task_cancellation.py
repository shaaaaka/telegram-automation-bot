import asyncio
import pytest
from bot.services.ai_task_manager import (
    register_ai_task,
    cancel_ai_task,
    unregister_ai_task,
    is_session_ai_paused,
)
from bot.handlers.client_helpers import simulate_typing


@pytest.mark.asyncio
async def test_ai_task_manager_cancellation():
    client_id = 99999
    was_cancelled = False

    async def dummy_ai_work():
        nonlocal was_cancelled
        try:
            await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            was_cancelled = True
            raise

    task = asyncio.create_task(dummy_ai_work())
    register_ai_task(client_id, task)

    await asyncio.sleep(0.05)
    assert cancel_ai_task(client_id) is True
    
    with pytest.raises(asyncio.CancelledError):
        await task

    assert was_cancelled is True


@pytest.mark.asyncio
async def test_is_session_ai_paused(test_db):
    client_id = 12345
    # Default is_paused is 0
    assert await is_session_ai_paused(client_id) is False

    # Toggle to 1 in DB
    await test_db.toggle_session_ai(client_id) if hasattr(test_db, 'toggle_session_ai') else None
    
    import aiosqlite
    async with aiosqlite.connect(test_db.DB_FILE) as conn:
        await conn.execute("UPDATE sessions SET is_paused = 1 WHERE client_id = ?", (client_id,))
        await conn.commit()

    assert await is_session_ai_paused(client_id) is True


@pytest.mark.asyncio
async def test_simulate_typing_cancels_on_paused(test_db):
    client_id = 12345
    
    import aiosqlite
    async with aiosqlite.connect(test_db.DB_FILE) as conn:
        await conn.execute("UPDATE sessions SET is_paused = 1 WHERE client_id = ?", (client_id,))
        await conn.commit()

    class DummyBot:
        async def send_chat_action(self, chat_id, action):
            pass

    bot = DummyBot()
    with pytest.raises(asyncio.CancelledError):
        await simulate_typing(bot, client_id, 10.0)
