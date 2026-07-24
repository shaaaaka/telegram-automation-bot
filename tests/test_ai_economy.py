import pytest
import cv2
import numpy as np
import os
import tempfile
import aiofiles
from unittest.mock import patch, AsyncMock

from bot.services.ai_economy_service import (
    resize_and_compress_image,
    get_cached_template_base64,
    invalidate_template_base64_cache,
    match_fallback_rule,
    record_ai_usage,
    check_daily_limit_exceeded,
    _TEMPLATE_BASE64_CACHE
)

def test_resize_and_compress_image():
    # Створюємо синтетичне велике зображення 2000x1500
    large_img = np.zeros((1500, 2000, 3), dtype=np.uint8)
    cv2.putText(large_img, "Test Image", (100, 500), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 5)
    _, original_bytes = cv2.imencode('.png', large_img)
    original_bytes = original_bytes.tobytes()

    compressed_bytes = resize_and_compress_image(original_bytes, max_side=1024, quality=80)
    assert compressed_bytes is not None
    assert len(compressed_bytes) > 0

    # Перевіряємо, що розміри зменшено
    nparr = np.frombuffer(compressed_bytes, np.uint8)
    res_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    assert res_img is not None
    h, w = res_img.shape[:2]
    assert max(h, w) <= 1024

def test_template_base64_cache():
    invalidate_template_base64_cache()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(b"fake_image_bytes_for_testing")
        tmp_path = tmp.name

    try:
        b64_1 = get_cached_template_base64(tmp_path)
        assert b64_1 is not None
        assert tmp_path in _TEMPLATE_BASE64_CACHE

        # Другий виклик має повертати значення з кешу
        b64_2 = get_cached_template_base64(tmp_path)
        assert b64_1 == b64_2

        # Скидаємо кеш
        invalidate_template_base64_cache(tmp_path)
        assert tmp_path not in _TEMPLATE_BASE64_CACHE
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@pytest.mark.asyncio
async def test_match_fallback_rules():
    # Тест стандартних регулярних виразів фолбеку
    ans_pin = await match_fallback_rule("який пін мені вводити?")
    assert ans_pin is not None
    assert "пін-код" in ans_pin.lower()

    ans_pincode = await match_fallback_rule("який пін-код вказувати?")
    assert ans_pincode is not None
    assert "пін-код" in ans_pincode.lower()

    ans_pin_en = await match_fallback_rule("який pin ставити?")
    assert ans_pin_en is not None

    ans_ipn = await match_fallback_rule("де взяти іпн для реєстрації?")
    assert ans_ipn is not None
    assert "податковий" in ans_ipn.lower()

    ans_code = await match_fallback_rule("код підійшов, все ок")
    assert ans_code is not None
    assert "чудово" in ans_code.lower()

    ans_unknown = await match_fallback_rule("що робити якщо з'явилась помилка 500 в банку?")
    assert ans_unknown is None

@pytest.mark.asyncio
async def test_ai_usage_and_daily_limit(tmp_path):
    # Мокаємо DB_FILE для тесту
    test_db = str(tmp_path / "test_bot.db")
    with patch("bot.services.ai_economy_service.DB_FILE", test_db):
        import aiosqlite
        async with aiosqlite.connect(test_db) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ai_usage (
                    date TEXT PRIMARY KEY,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    requests INTEGER DEFAULT 0
                )
            """)
            await db.commit()

        # Початково ліміт не перевищено
        exceeded = await check_daily_limit_exceeded(max_daily_tokens=1000)
        assert exceeded is False

        # Записуємо 600 токенів
        await record_ai_usage(prompt_tokens=400, completion_tokens=200)
        exceeded = await check_daily_limit_exceeded(max_daily_tokens=1000)
        assert exceeded is False

        # Записуємо ще 500 токенів (всього 1100)
        await record_ai_usage(prompt_tokens=300, completion_tokens=200)
        exceeded = await check_daily_limit_exceeded(max_daily_tokens=1000)
        assert exceeded is True
