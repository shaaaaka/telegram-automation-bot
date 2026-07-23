import pytest
import bot.database as db
from bot.services.chat_log_service import (
    log_chat_message,
    get_chat_logs,
    clear_chat_logs,
    log_verification_start,
    log_verification_end,
    get_client_verification_history,
    get_statistics,
)

@pytest.mark.asyncio
async def test_chat_logs_flow(test_db):
    client_id = 777666555

    # Log messages
    await log_chat_message(client_id, "client", "Привіт, відправляю ПІБ")
    await log_chat_message(client_id, "bot", "Дякую, чекаю")

    logs = await get_chat_logs(client_id)
    assert len(logs) == 2
    assert logs[0]["sender"] == "client"
    assert logs[0]["message_text"] == "Привіт, відправляю ПІБ"
    assert logs[1]["sender"] == "bot"

    # Clear logs
    await clear_chat_logs(client_id)
    cleared_logs = await get_chat_logs(client_id)
    assert len(cleared_logs) == 0


@pytest.mark.asyncio
async def test_verification_logs_and_stats(test_db):
    client_id = 555444333

    await log_verification_start(client_id, "test_user", "IziBank", "+380991112233")
    await log_verification_end(client_id, "IziBank", "success")

    history = await get_client_verification_history(client_id)
    assert len(history) == 1
    assert history[0]["bank"] == "IziBank"
    assert history[0]["status"] == "success"

    stats = await get_statistics()
    assert "totals" in stats
    assert "today" in stats
    assert "banks" in stats


@pytest.mark.asyncio
async def test_chat_logs_database_reexport_compatibility(test_db):
    client_id = 333222111

    # Verify re-export compatibility via bot.database
    await db.log_chat_message(client_id, "client", "Тест сумісності")
    logs = await db.get_chat_logs(client_id)
    assert len(logs) == 1
    assert logs[0]["message_text"] == "Тест сумісності"

    await db.clear_chat_logs(client_id)
