import base64
import cv2
import logging
import numpy as np
import re
from datetime import date
import aiosqlite

from bot.config import DB_FILE

logger = logging.getLogger(__name__)

# Кеш для base64 еталонних зображень банків у пам'яті
# _TEMPLATE_BASE64_CACHE[file_path] = base64_str
_TEMPLATE_BASE64_CACHE = {}

def resize_and_compress_image(image_bytes: bytes, max_side: int = 1024, quality: int = 80) -> bytes:
    """
    Зменшує зображення до max_side по довшій стороні та стискає в JPEG (quality%).
    Якщо зображення не вдалося прочитати OpenCV, повертає вихідні байти.
    """
    if not image_bytes:
        return image_bytes

    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes

        h, w = img.shape[:2]
        if max(h, w) > max_side:
            scale = max_side / float(max(h, w))
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        success, encoded_img = cv2.imencode('.jpg', img, encode_param)
        if success:
            return encoded_img.tobytes()
    except Exception as e:
        logger.warning(f"Error compressing image with OpenCV: {e}")

    return image_bytes

def get_cached_template_base64(file_path: str) -> str | None:
    """
    Отримання base64-рядка еталонного скріншоту банку з in-memory кешу або з диска.
    """
    if not file_path:
        return None

    if file_path in _TEMPLATE_BASE64_CACHE:
        return _TEMPLATE_BASE64_CACHE[file_path]

    try:
        import os
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                _TEMPLATE_BASE64_CACHE[file_path] = b64
                return b64
    except Exception as e:
        logger.error(f"Error reading/encoding template image '{file_path}': {e}")

    return None

def invalidate_template_base64_cache(file_path: str = None):
    """
    Скидання кешу еталонних зображень банків.
    Якщо file_path=None, очищається весь кеш.
    """
    global _TEMPLATE_BASE64_CACHE
    if file_path:
        _TEMPLATE_BASE64_CACHE.pop(file_path, None)
    else:
        _TEMPLATE_BASE64_CACHE.clear()

async def match_fallback_rule(user_text: str, bank_name: str = None) -> str | None:
    """
    Перевіряє текст клієнта за правилами ai_fallback_rules у БД або базовим списком.
    Якщо є відповідність, повертає готовий текст відповіді без виклику AI.
    """
    if not user_text:
        return None

    cleaned_text = user_text.strip().lower()
    if not cleaned_text:
        return None

    # Читаємо з БД активні fallback-правила
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT pattern, bank_name, response_text FROM ai_fallback_rules WHERE is_active = 1 ORDER BY priority DESC"
            ) as cursor:
                rules = await cursor.fetchall()
                for rule in rules:
                    rule_bank = rule['bank_name']
                    if rule_bank and bank_name and rule_bank.lower() != bank_name.lower():
                        continue
                    pattern = rule['pattern']
                    try:
                        if re.search(pattern, cleaned_text, re.IGNORECASE):
                            return rule['response_text']
                    except Exception as reg_err:
                        logger.error(f"Invalid regex pattern in ai_fallback_rules '{pattern}': {reg_err}")
    except Exception as db_err:
        logger.warning(f"Could not read fallback rules from DB: {db_err}")

    # Статичний фолбек за замовчуванням (якщо БД недоступна або порожня)
    DEFAULT_PATTERNS = [
        (r'який (пін|пін[- ]?код|пароль|pin|pass|password)', "Вказуйте будь-який зручний пін-код, головне запам'ятати його."),
        (r'(що таке|де взяти) (іпн|рнокпп|податковий)', "ІПН (РНОКПП) — це ваш 10-значний податковий номер, його можна знайти в додатку Дія або на довідці."),
        (r'код (підійшов|ввів|є|прийшов)', "Чудово! Продовжуйте наступні кроки за інструкцією."),
        (r'не можу зробити скрін', "Якщо додаток блокує скріншот, зробіть фото екрана іншим телефоном."),
        (r'(навіщо|для чого) (телефон|номер)', "Номер телефону потрібен для реєстрації облікового запису в банку.")
    ]

    for pattern, resp in DEFAULT_PATTERNS:
        if re.search(pattern, cleaned_text, re.IGNORECASE):
            return resp

    return None

async def record_ai_usage(prompt_tokens: int = 0, completion_tokens: int = 0):
    """
    Записує кількість використаних токенів та запитів за поточний день у БД.
    """
    today_str = date.today().isoformat()
    total_input = prompt_tokens or 0
    total_output = completion_tokens or 0

    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                INSERT INTO ai_usage (date, input_tokens, output_tokens, requests)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    input_tokens = input_tokens + excluded.input_tokens,
                    output_tokens = output_tokens + excluded.output_tokens,
                    requests = requests + 1
            """, (today_str, total_input, total_output))
            await db.commit()
    except Exception as e:
        logger.error(f"Error recording AI usage: {e}")

async def check_daily_limit_exceeded(max_daily_tokens: int = 1000000) -> bool:
    """
    Перевіряє, чи не перевищено денний ліміт токенів.
    """
    today_str = date.today().isoformat()
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT input_tokens + output_tokens FROM ai_usage WHERE date = ?", (today_str,)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return row[0] >= max_daily_tokens
    except Exception as e:
        logger.error(f"Error checking AI daily limit: {e}")

    return False
