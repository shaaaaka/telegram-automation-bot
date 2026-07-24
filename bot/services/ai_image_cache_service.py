import cv2
import numpy as np
import logging
import json
from datetime import date
import aiosqlite

from bot.config import DB_FILE

logger = logging.getLogger(__name__)

def _compute_phash(image_bytes: bytes) -> str | None:
    """
    Обчислення 64-бітного pHash (Perceptual Hash) для зображення з використанням чистих cv2 + numpy.
    Зображення зменшується до 32x32 у відтінках сірого, до нього застосовується дискретне косинусне перетворення (DCT),
    після чого витягується матриця 8x8 низьких частот для генерації хешу.
    """
    if not image_bytes:
        return None

    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None

        # Зменшуємо до 32x32
        img_resized = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
        img_float = np.float32(img_resized)

        # Дискретне косинусне перетворення (DCT)
        dct = cv2.dct(img_float)

        # Беріть низькочастотні коефіцієнти 8x8 (пропускаємо DC коефіцієнт [0,0] чи включаємо від медіани)
        dct_low = dct[:8, :8]
        median = np.median(dct_low)

        # Бінарна матриця відносно медіани
        bits = (dct_low >= median).astype(int).flatten()

        # Конвертуємо 64 біти в 16-значний Hex рядок
        bit_string = "".join(str(b) for b in bits)
        return hex(int(bit_string, 2))[2:].zfill(16)
    except Exception as e:
        logger.warning(f"Error computing pHash: {e}")
        return None

def _hamming_distance(hash1: str, hash2: str) -> int:
    """
    Обчислення хеммінгової відстані між двома 16-значними hex-хешами.
    Повертає кількість відмінних бітів (від 0 до 64).
    """
    try:
        val1 = int(hash1, 16)
        val2 = int(hash2, 16)
        return bin(val1 ^ val2).count('1')
    except Exception:
        return 64

async def get_cached_verdict(
    image_bytes: bytes,
    bank_name: str | None,
    task: str,
    prompt_version: str | None = None,
    threshold: int | None = None
) -> dict | None:
    """
    Шукає вердикт у кеші ai_image_cache за допомогою pHash та threshold (Хеммінгової відстані).
    Якщо значення prompt_version або threshold не передано — вони читаються з налаштувань app_settings у БД.
    """
    if not image_bytes:
        return None

    # Перевіряємо прапорець увімкнення кешу та читаємо налаштування з БД
    eff_threshold = threshold
    eff_prompt_ver = prompt_version
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT key, value FROM app_settings WHERE key IN ('ai_image_cache_enabled', 'ai_image_cache_threshold', 'ai_image_cache_prompt_version')") as cursor:
                settings_rows = await cursor.fetchall()
                s_dict = {row[0]: row[1] for row in settings_rows}
                if s_dict.get('ai_image_cache_enabled') == '0':
                    return None
                if eff_threshold is None:
                    try:
                        eff_threshold = int(s_dict.get('ai_image_cache_threshold', '4'))
                    except ValueError:
                        eff_threshold = 4
                if eff_prompt_ver is None:
                    eff_prompt_ver = s_dict.get('ai_image_cache_prompt_version', '1')
    except Exception:
        if eff_threshold is None:
            eff_threshold = 4
        if eff_prompt_ver is None:
            eff_prompt_ver = '1'

    img_hash = _compute_phash(image_bytes)
    if not img_hash:
        return None

    norm_bank = bank_name.strip().lower() if bank_name else None

    try:
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row

            # 1. Спроба exact match
            query_exact = """
                SELECT id, result_text, is_valid, reason, extracted_data, image_hash
                FROM ai_image_cache
                WHERE task = ? AND prompt_version = ? AND image_hash = ?
            """
            params_exact = [task, eff_prompt_ver, img_hash]
            if norm_bank:
                query_exact += " AND LOWER(bank_name) = ?"
                params_exact.append(norm_bank)
            else:
                query_exact += " AND bank_name IS NULL"

            async with db.execute(query_exact, params_exact) as cursor:
                row = await cursor.fetchone()
                if row:
                    await bump_hit_count(row['id'])
                    extracted = json.loads(row['extracted_data']) if row['extracted_data'] else {}
                    return {
                        'id': row['id'],
                        'result_text': row['result_text'],
                        'is_valid': bool(row['is_valid']) if row['is_valid'] is not None else None,
                        'reason': row['reason'],
                        'extracted_data': extracted,
                        'distance': 0
                    }

            # 2. Fuzzy match за всіма хешами поточного таску та банку
            query_fuzzy = """
                SELECT id, result_text, is_valid, reason, extracted_data, image_hash
                FROM ai_image_cache
                WHERE task = ? AND prompt_version = ?
            """
            params_fuzzy = [task, eff_prompt_ver]
            if norm_bank:
                query_fuzzy += " AND LOWER(bank_name) = ?"
                params_fuzzy.append(norm_bank)
            else:
                query_fuzzy += " AND bank_name IS NULL"

            async with db.execute(query_fuzzy, params_fuzzy) as cursor:
                rows = await cursor.fetchall()
                best_match = None
                min_dist = 65

                for r in rows:
                    dist = _hamming_distance(img_hash, r['image_hash'])
                    if dist <= eff_threshold and dist < min_dist:
                        min_dist = dist
                        best_match = r

                if best_match:
                    await bump_hit_count(best_match['id'])
                    extracted = json.loads(best_match['extracted_data']) if best_match['extracted_data'] else {}
                    return {
                        'id': best_match['id'],
                        'result_text': best_match['result_text'],
                        'is_valid': bool(best_match['is_valid']) if best_match['is_valid'] is not None else None,
                        'reason': best_match['reason'],
                        'extracted_data': extracted,
                        'distance': min_dist
                    }
    except Exception as e:
        logger.error(f"Error checking ai_image_cache: {e}")

    return None

async def save_verdict(
    image_bytes: bytes,
    bank_name: str | None,
    task: str,
    result_text: str | None = None,
    is_valid: bool | None = None,
    reason: str | None = None,
    extracted_data: dict | None = None,
    prompt_version: str | None = None,
    source_size: int = 0
) -> bool:
    """
    Зберігає новий ШІ-вердикт для зображення в ai_image_cache.
    Якщо prompt_version не вказано — читається з налаштувань app_settings.
    """
    eff_prompt_ver = prompt_version
    if eff_prompt_ver is None:
        try:
            async with aiosqlite.connect(DB_FILE) as db:
                async with db.execute("SELECT value FROM app_settings WHERE key = 'ai_image_cache_prompt_version'") as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        eff_prompt_ver = row[0]
                    else:
                        eff_prompt_ver = "1"
        except Exception:
            eff_prompt_ver = "1"

    img_hash = _compute_phash(image_bytes)
    if not img_hash:
        return False

    norm_bank = bank_name.strip() if bank_name else None
    valid_int = 1 if is_valid is True else (0 if is_valid is False else None)
    ext_json = json.dumps(extracted_data) if extracted_data else None

    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                INSERT INTO ai_image_cache (
                    image_hash, bank_name, task, result_text, is_valid, reason,
                    extracted_data, prompt_version, source_size, hit_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(image_hash, bank_name, task, prompt_version) DO UPDATE SET
                    result_text = excluded.result_text,
                    is_valid = excluded.is_valid,
                    reason = excluded.reason,
                    extracted_data = excluded.extracted_data,
                    last_hit_at = CURRENT_TIMESTAMP
            """, (img_hash, norm_bank, task, result_text, valid_int, reason, ext_json, eff_prompt_ver, source_size))
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Error saving verdict to ai_image_cache: {e}")

    return False

async def bump_hit_count(cache_id: int):
    """
    Оновлює лічильник hit_count та час останнього попадання у кеш.
    """
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                UPDATE ai_image_cache
                SET hit_count = hit_count + 1, last_hit_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (cache_id,))
            await db.commit()
    except Exception as e:
        logger.error(f"Error bumping cache hit_count for id {cache_id}: {e}")

async def cleanup_old_cache(days: int = 30, unactive_days: int = 90):
    """
    Видаляє записи з ai_image_cache:
    1. Жодного разу не використані (hit_count = 0) і створені більше `days` днів тому.
    2. Жодного разу не запитувані більше ніж `unactive_days` (за last_hit_at).
    """
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                DELETE FROM ai_image_cache
                WHERE (hit_count = 0 AND created_at < datetime('now', '-' || ? || ' days'))
                   OR (last_hit_at < datetime('now', '-' || ? || ' days'))
            """, (days, unactive_days))
            await db.commit()
            logger.info(f"Cleaned up ai_image_cache: unhit > {days}d or inactive > {unactive_days}d.")
    except Exception as e:
        logger.error(f"Error cleaning up old ai_image_cache: {e}")
