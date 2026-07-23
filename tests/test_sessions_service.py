import pytest
import bot.database as db
from bot.services.sessions_service import (
    create_registering_session,
    create_or_update_session,
    get_session,
    update_session_banks,
    set_session_status,
    assign_line_to_session,
    complete_current_bank,
    unassign_line_from_session,
    delete_session_completely,
    add_notified_bank,
)
from bot.services.lines_service import add_or_update_line, clear_all_lines

@pytest.mark.asyncio
async def test_sessions_lifecycle_and_line_assignment(test_db):
    client_id = 888777666
    username = "test_session_user"

    # Register session
    await create_registering_session(client_id, username)
    session = await get_session(client_id)
    assert session["status"] == "registering"

    # Fill data
    await create_or_update_session(client_id, username, "📝 ПІБ: Тестов Тест Тестович\n📞 Телефон: +380998887766")
    session = await get_session(client_id)
    assert session["status"] == "registered"

    # Set banks
    await update_session_banks(client_id, "IziBank,Alliance", "IziBank,Alliance")

    # Add line and assign
    await add_or_update_line(50, "+380509998877", "IziBank")
    lines = await db.get_all_lines()
    line_50 = next(l for l in lines if l["line_id"] == 50)

    await assign_line_to_session(client_id, line_50["id"])
    session = await get_session(client_id)
    assert session["line_id"] == line_50["id"]
    assert session["status"] == "number_assigned"

    # Add notified bank
    await add_notified_bank(client_id, "IziBank")
    session = await get_session(client_id)
    assert "IziBank" in session["notified_banks"]

    # Complete bank
    res = await complete_current_bank(client_id, "success")
    assert res is not None
    assert res["log_status"] == "success"

    # Delete session
    await delete_session_completely(client_id)
    assert await get_session(client_id) is None


@pytest.mark.asyncio
async def test_sessions_database_reexport_compatibility(test_db):
    client_id = 444333222

    await db.create_or_update_session(client_id, "compat_user", "data")
    s = await db.get_session(client_id)
    assert s is not None
    assert s["username"] == "compat_user"

    await db.delete_session_completely(client_id)
