import bot.database as db
from bot.services.line_assignment import get_all_banks_for_selection


async def test_complete_current_bank_success(test_db):
    await db.assign_line_to_session(12345, 1)
    await db.log_verification_start(12345, "testuser", "IziBank", "+380111111111")
    result = await db.complete_current_bank(12345, "success")

    assert result is not None
    assert result["bank_name"] == "IziBank"
    assert result["remaining"] == ["Alliance"]
    assert result["line_status"] == "success"
    assert result["log_status"] == "success"

    session = await db.get_session(12345)
    assert session["line_id"] is None
    assert session["status"] == "registered"
    assert session["remaining_banks"] == "Alliance"

    line = await db.get_line(1)
    assert line["status"] == "success"


async def test_complete_current_bank_release(test_db):
    await db.assign_line_to_session(12345, 1)
    await db.log_verification_start(12345, "testuser", "IziBank", "+380111111111")
    result = await db.complete_current_bank(12345, "release")

    assert result is not None
    assert result["line_status"] == "available"
    assert result["log_status"] == "released"

    line = await db.get_line(1)
    assert line["status"] == "available"


async def test_complete_current_bank_banned(test_db):
    await db.assign_line_to_session(12345, 1)
    await db.log_verification_start(12345, "testuser", "IziBank", "+380111111111")
    result = await db.complete_current_bank(12345, "failure")

    assert result is not None
    assert result["line_status"] == "banned"
    assert result["log_status"] == "banned"

    line = await db.get_line(1)
    assert line["status"] == "banned"


async def test_get_all_banks_for_selection(test_db):
    all_banks = await get_all_banks_for_selection()
    assert all_banks == ["bank.kd", "IziBank", "Alliance", "LvivBank", "AmoBank"]
