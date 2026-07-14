import os
import tempfile
import pytest
import bot.database as db


@pytest.fixture
async def test_db(tmp_path):
    """Створює тимчасову БД для тестів."""
    fd, path = tempfile.mkstemp(suffix=".db", dir=str(tmp_path))
    os.close(fd)
    original_db_file = db.DB_FILE
    db.DB_FILE = path
    try:
        await db.init_db()
        await db.add_or_update_line(1, "+380111111111", "IziBank")
        await db.create_or_update_session(12345, "testuser", "data")
        await db.update_session_banks(12345, "IziBank,Alliance", "IziBank,Alliance")
        yield db
    finally:
        db.DB_FILE = original_db_file
        try:
            os.remove(path)
        except Exception:
            pass
