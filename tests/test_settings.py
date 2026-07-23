import pytest
import bot.database as db
from bot.services.settings_service import get_setting, set_setting, get_all_settings

@pytest.mark.asyncio
async def test_settings_default(test_db):
    val = await get_setting("non_existent_test_key", default="default_val")
    assert val == "default_val"

@pytest.mark.asyncio
async def test_settings_set_and_get(test_db):
    await set_setting("test_key_1", "value_1")
    val = await get_setting("test_key_1")
    assert val == "value_1"

@pytest.mark.asyncio
async def test_settings_update(test_db):
    await set_setting("test_key_2", "initial")
    assert await get_setting("test_key_2") == "initial"

    await set_setting("test_key_2", "updated")
    assert await get_setting("test_key_2") == "updated"

@pytest.mark.asyncio
async def test_settings_get_all(test_db):
    await set_setting("setting_a", "alpha")
    await set_setting("setting_b", "beta")

    all_settings = await get_all_settings()
    assert isinstance(all_settings, dict)
    assert all_settings.get("setting_a") == "alpha"
    assert all_settings.get("setting_b") == "beta"

@pytest.mark.asyncio
async def test_database_reexport_compatibility(test_db):
    # Verify backward compatibility when importing from bot.database
    await db.set_setting("reexport_key", "reexport_val")
    val = await db.get_setting("reexport_key")
    assert val == "reexport_val"

    all_sets = await db.get_all_settings()
    assert all_sets.get("reexport_key") == "reexport_val"
