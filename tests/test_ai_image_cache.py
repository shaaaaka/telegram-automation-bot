import pytest
import cv2
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

from bot.services.ai_image_cache_service import (
    _compute_phash,
    _hamming_distance,
    get_cached_verdict,
    save_verdict,
    bump_hit_count,
    cleanup_old_cache
)

def create_synthetic_image(text: str, color=(255, 255, 255), width=800, height=600):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(img, text, (50, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 2, color, 3)
    _, encoded = cv2.imencode('.png', img)
    return encoded.tobytes()

def test_phash_same_image_returns_same_hash():
    img_bytes = create_synthetic_image("Test Image 1")
    hash1 = _compute_phash(img_bytes)
    hash2 = _compute_phash(img_bytes)
    assert hash1 is not None
    assert hash1 == hash2

def test_phash_resized_image_similar():
    img_bytes1 = create_synthetic_image("Test Image 1", width=800, height=600)
    # Змінюємо роздільну здатність і якість
    nparr = np.frombuffer(img_bytes1, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    img_resized = cv2.resize(img, (400, 300))
    _, img_bytes2 = cv2.imencode('.jpg', img_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
    img_bytes2 = img_bytes2.tobytes()

    hash1 = _compute_phash(img_bytes1)
    hash2 = _compute_phash(img_bytes2)

    dist = _hamming_distance(hash1, hash2)
    assert dist <= 4

def test_phash_different_image_different_hash():
    img_bytes1 = create_synthetic_image("AAAAA BBBBB CCCCC")
    img_bytes2 = create_synthetic_image("12345 67890 XYZWW")

    hash1 = _compute_phash(img_bytes1)
    hash2 = _compute_phash(img_bytes2)

    assert hash1 != hash2

@pytest.mark.asyncio
async def test_cache_hit_and_miss_proceedings(tmp_path):
    test_db = str(tmp_path / "test_cache.db")
    with patch("bot.services.ai_image_cache_service.DB_FILE", test_db), \
         patch("bot.database.DB_FILE", test_db), \
         patch("bot.services.ai_economy_service.DB_FILE", test_db):
        
        from bot.database import init_db
        await init_db()

        img_bytes = create_synthetic_image("Proceedings Screenshot")

        # 1. Початково у кеші немає
        cached1 = await get_cached_verdict(img_bytes, bank_name=None, task="proceedings")
        assert cached1 is None

        # 2. Зберігаємо вердикт
        saved = await save_verdict(img_bytes, bank_name=None, task="proceedings", result_text="[CLOSED] Все добре", source_size=len(img_bytes))
        assert saved is True

        # 3. Повторний запит повертає значення з кешу
        cached2 = await get_cached_verdict(img_bytes, bank_name=None, task="proceedings")
        assert cached2 is not None
        assert cached2['result_text'] == "[CLOSED] Все добре"
        assert cached2['distance'] == 0

@pytest.mark.asyncio
async def test_cache_hit_and_miss_deletion_proof(tmp_path):
    test_db = str(tmp_path / "test_cache_del.db")
    with patch("bot.services.ai_image_cache_service.DB_FILE", test_db), \
         patch("bot.database.DB_FILE", test_db), \
         patch("bot.services.ai_economy_service.DB_FILE", test_db):

        from bot.database import init_db
        await init_db()

        img_bytes = create_synthetic_image("App Store Deletion Screen")

        # 1. Зберігаємо вердикт для AmoBank
        await save_verdict(img_bytes, bank_name="AmoBank", task="deletion_proof", is_valid=True, reason="Видалення підтверджено", source_size=len(img_bytes))

        # 2. Перевіряємо hit для того самого банку
        cached = await get_cached_verdict(img_bytes, bank_name="AmoBank", task="deletion_proof")
        assert cached is not None
        assert cached['is_valid'] is True
        assert cached['reason'] == "Видалення підтверджено"

        # 3. Перевіряємо miss для іншого банку
        cached_other = await get_cached_verdict(img_bytes, bank_name="Monobank", task="deletion_proof")
        assert cached_other is None

@pytest.mark.asyncio
async def test_prompt_version_invalidation(tmp_path):
    test_db = str(tmp_path / "test_cache_ver.db")
    with patch("bot.services.ai_image_cache_service.DB_FILE", test_db), \
         patch("bot.database.DB_FILE", test_db), \
         patch("bot.services.ai_economy_service.DB_FILE", test_db):

        from bot.database import init_db
        await init_db()

        img_bytes = create_synthetic_image("Relink Screenshot")

        # Зберігаємо під версією промпту '1'
        await save_verdict(img_bytes, bank_name="bank.kd", task="relink_initial", is_valid=True, reason="Картка діюча", prompt_version="1")

        # Перевірка з версією промпту '1' -> HIT
        cached_v1 = await get_cached_verdict(img_bytes, bank_name="bank.kd", task="relink_initial", prompt_version="1")
        assert cached_v1 is not None

        # Перевірка з новою версією промпту '2' -> MISS (інвалідація)
        cached_v2 = await get_cached_verdict(img_bytes, bank_name="bank.kd", task="relink_initial", prompt_version="2")
        assert cached_v2 is None

@pytest.mark.asyncio
async def test_vision_service_cache_integration(tmp_path):
    test_db = str(tmp_path / "test_vision_cache.db")
    with patch("bot.services.ai_image_cache_service.DB_FILE", test_db), \
         patch("bot.services.ai_economy_service.DB_FILE", test_db), \
         patch("bot.database.DB_FILE", test_db):

        from bot.database import init_db
        await init_db()

        from bot.services.vision_service import analyze_proceedings_screenshot

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="[CLOSED] Відкритих проваджень немає"))]
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=20)
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        img_bytes = create_synthetic_image("Proceedings Screen Test Integration")

        # Перший виклик -> іде в OpenRouter
        res1 = await analyze_proceedings_screenshot(mock_client, img_bytes)
        assert res1 == "[CLOSED] Відкритих проваджень немає"
        assert mock_client.chat.completions.create.call_count == 1

        # Другий виклик -> бере з кешу, OpenRouter більше не викликається!
        res2 = await analyze_proceedings_screenshot(mock_client, img_bytes)
        assert res2 == "[CLOSED] Відкритих проваджень немає"
        assert mock_client.chat.completions.create.call_count == 1

@pytest.mark.asyncio
async def test_cleanup_old_cache_purging(tmp_path):
    test_db = str(tmp_path / "test_cleanup.db")
    with patch("bot.services.ai_image_cache_service.DB_FILE", test_db), \
         patch("bot.database.DB_FILE", test_db):

        from bot.database import init_db
        await init_db()

        import aiosqlite
        async with aiosqlite.connect(test_db) as db:
            # 1. Запис > 30 днів без hit
            await db.execute("""
                INSERT INTO ai_image_cache (image_hash, bank_name, task, result_text, is_valid, prompt_version, hit_count, created_at, last_hit_at)
                VALUES ('hash1', 'BankA', 'test', 'res1', 1, '1', 0, datetime('now', '-35 days'), datetime('now', '-35 days'))
            """)
            # 2. Запис > 90 днів неактивний
            await db.execute("""
                INSERT INTO ai_image_cache (image_hash, bank_name, task, result_text, is_valid, prompt_version, hit_count, created_at, last_hit_at)
                VALUES ('hash2', 'BankB', 'test', 'res2', 1, '1', 5, datetime('now', '-100 days'), datetime('now', '-95 days'))
            """)
            # 3. Свіжий запис
            await db.execute("""
                INSERT INTO ai_image_cache (image_hash, bank_name, task, result_text, is_valid, prompt_version, hit_count, created_at, last_hit_at)
                VALUES ('hash3', 'BankC', 'test', 'res3', 1, '1', 2, datetime('now', '-2 days'), datetime('now', '-1 days'))
            """)
            await db.commit()

        await cleanup_old_cache(days=30, unactive_days=90)

        async with aiosqlite.connect(test_db) as db:
            async with db.execute("SELECT image_hash FROM ai_image_cache") as cursor:
                rows = await cursor.fetchall()
                remaining_hashes = [r[0] for r in rows]
                assert "hash1" not in remaining_hashes
                assert "hash2" not in remaining_hashes
                assert "hash3" in remaining_hashes
