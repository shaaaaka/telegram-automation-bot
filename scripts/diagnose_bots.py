"""Діагностика: перевіряє, які боти ініціалізуються з токенів/.env/профілів."""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout,
)


async def main():
    from bot.config import BOT_TOKEN
    from bot.database import init_db
    from bot.bot_registry import init_bots, get_all_bots, close_all_bots

    await init_db()
    await init_bots(BOT_TOKEN)

    bots = get_all_bots()
    print(f"\n{'='*60}")
    print(f"Усього зареєстровано ботів: {len(bots)}")
    for bot in bots:
        try:
            me = await bot.get_me()
            print(f"  @{me.username} ({me.first_name}) — token ends with ...{bot.token[-8:]}")
        except Exception as e:
            print(f"  НЕ ВДАЛОСЬ отримати get_me: {e}")
    print(f"{'='*60}\n")

    await close_all_bots()


if __name__ == "__main__":
    asyncio.run(main())
