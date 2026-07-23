import pytest
import bot.database as db
from bot.services.ban_service import ban_user, unban_user, is_user_banned, get_banned_users

@pytest.mark.asyncio
async def test_ban_user_flow(test_db):
    client_id = 999888777
    username = "banned_test_user"

    # Initially not banned
    assert await is_user_banned(client_id) is False

    # Ban user
    await ban_user(client_id, username)
    assert await is_user_banned(client_id) is True

    banned_list = await get_banned_users()
    assert any(u["client_id"] == client_id for u in banned_list)

    # Unban user
    await unban_user(client_id)
    assert await is_user_banned(client_id) is False


@pytest.mark.asyncio
async def test_ban_user_database_compatibility(test_db):
    client_id = 111222333

    # Test compatibility via bot.database re-export
    await db.ban_user(client_id, "compat_user")
    assert await db.is_user_banned(client_id) is True

    banned = await db.get_banned_users()
    assert any(u["client_id"] == client_id for u in banned)

    await db.unban_user(client_id)
    assert await db.is_user_banned(client_id) is False
