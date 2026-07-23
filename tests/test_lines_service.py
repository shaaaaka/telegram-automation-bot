import pytest
import bot.database as db
from bot.services.lines_service import (
    add_or_update_line,
    get_all_lines,
    get_available_lines,
    get_line,
    set_line_status,
    get_unique_banks,
    clear_all_lines,
    delete_line,
    get_max_line_id,
)

@pytest.mark.asyncio
async def test_lines_crud_operations(test_db):
    await clear_all_lines()
    assert len(await get_all_lines()) == 0

    # Add lines
    await add_or_update_line(1, "+380501112233", "IziBank")
    await add_or_update_line(2, "+380502223344", "AmoBank")

    all_lines = await get_all_lines()
    assert len(all_lines) == 2

    avail = await get_available_lines()
    assert len(avail) == 2

    # Get line
    line_1 = all_lines[0]
    line_data = await get_line(line_1["id"])
    assert line_data["phone_number"] == "+380501112233"

    # Set line status
    await set_line_status(line_1["id"], "busy")
    avail_after_busy = await get_available_lines()
    assert len(avail_after_busy) == 1

    # Unique banks
    banks = await get_unique_banks()
    assert "IziBank" in banks
    assert "AmoBank" in banks

    # Max line id
    max_id = await get_max_line_id()
    assert max_id == 2

    # Delete line
    await delete_line(line_1["id"])
    lines_after_del = await get_all_lines()
    assert len(lines_after_del) == 1


@pytest.mark.asyncio
async def test_lines_database_reexport_compatibility(test_db):
    await db.clear_all_lines()
    await db.add_or_update_line(99, "+380998887766", "Alliance")

    lines = await db.get_all_lines()
    assert len(lines) == 1
    assert lines[0]["bank"] == "Alliance"

    max_id = await db.get_max_line_id()
    assert max_id == 99
