# TelegaV1.0

Telegram-бот для обробки анкет з веб-панеллю на FastAPI.

## Швидкий старт

1. **Перевір, що встановлено Python 3.11+.**
2. **Налаштуй середовище:**
   ```cmd
   scripts\setup_env.bat
   ```
3. **Заповни `.env`** своїми токенами та ID.
4. **Запускай бота:**
   - Подвійний клік на `start.bat`
   - Або в PowerShell: `.\scripts\start.ps1`

## Структура

- `main.py` — точка входу (бот + веб-сервер)
- `bot/` — логіка Telegram-бота
- `web/` — FastAPI веб-панель
- `tests/` — тести
- `scripts/` — допоміжні скрипти (`setup_env`, `clear_db`, `diagnose_bots`, `kill_port_8000`)
- `data/` — база даних SQLite

## Корисні скрипти

```cmd
scripts\setup_env.bat        # створити .venv і встановити залежності
scripts\clear_db.py          # очистити сесії в базі
scripts\diagnose_bots.py     # перевірити ініціалізацію ботів
scripts\kill_port_8000.py    # прибити процеси на 8000 порті
```
