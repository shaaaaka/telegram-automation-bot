import asyncio
import logging
import sys
import os

from dotenv import load_dotenv

# Завантажуємо тестовий .env ПЕРЕД імпортом config.py
load_dotenv(".env.test", override=True)

from main import main

if __name__ == "__main__":
    asyncio.run(main())
