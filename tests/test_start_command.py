import pytest
import bot.database as db
from bot.services.verification_methods_service import save_verification_method


@pytest.fixture
async def test_start_db(tmp_path):
    """Тимчасова БД з тестовим методом."""
    import os
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".db", dir=str(tmp_path))
    os.close(fd)
    original_db_file = db.DB_FILE
    db.DB_FILE = path
    try:
        await db.init_db()
        await db.add_or_update_line(1, "+380111111111", "IziBank")
        yield db
    finally:
        db.DB_FILE = original_db_file
        try:
            os.remove(path)
        except Exception:
            pass


async def test_method_fields_not_overwritten(test_start_db):
    """При оновленні методу непередані поля не перезаписуються."""
    await save_verification_method(
        key="pumb",
        display_name="ПУМБ",
        allowed_banks=["pumb"],
        linked_bots=["pumbverifbot"],
        initial_message="Ласкаво просимо",
    )

    await save_verification_method(
        key="pumb",
        initial_message=None,
    )

    method = await db.get_verification_method("pumb")
    assert method["display_name"] == "ПУМБ"
    assert method["linked_bots"] == ["pumbverifbot"]


async def test_initial_message_can_be_empty(test_start_db):
    """Початкова інструкція методу може бути пустою."""
    await save_verification_method(
        key="volf",
        display_name="Вольф",
        allowed_banks=["volf"],
        linked_bots=["rummyverifbot"],
        initial_message=None,
    )

    method = await db.get_verification_method("volf")
    assert method["initial_message"] is None
    assert method["allowed_banks"] == ["volf"]
