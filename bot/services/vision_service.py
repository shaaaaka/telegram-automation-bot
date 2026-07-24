import base64
import logging
from bot.config import OPENROUTER_MODEL

logger = logging.getLogger(__name__)

async def analyze_proceedings_screenshot(client, image_bytes: bytes) -> str:
    """Аналіз скріншоту виконавчих проваджень на предмет наявності відкритих проваджень"""
    if not client:
        return "[UNKNOWN] OpenAI API key is not configured."
        
    from bot.services.ai_economy_service import (
        resize_and_compress_image,
        record_ai_usage,
        check_daily_limit_exceeded
    )
    from bot.services.ai_image_cache_service import get_cached_verdict, save_verdict

    # 1. Перевірка pHash кешу скріншотів
    cached = await get_cached_verdict(image_bytes, bank_name=None, task='proceedings')
    if cached and cached.get('result_text'):
        logger.info(f"AI Image Cache HIT for proceedings screenshot (distance: {cached['distance']})")
        return cached['result_text']

    if await check_daily_limit_exceeded():
        logger.warning("AI daily limit exceeded in analyze_proceedings_screenshot")
        return "[UNKNOWN] Передано на ручну перевірку (ліміт токенів вичерпано)."

    compressed_bytes = resize_and_compress_image(image_bytes, max_side=1024, quality=80)
    base64_image = base64.b64encode(compressed_bytes).decode('utf-8')
    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI assistant specialized in analyzing screenshots of 'Виконавчі провадження' "
                "(Executive Proceedings) from the Ukrainian state application 'Дія'.\n\n"
                "Your task is to determine whether the screenshot indicates that the user has any "
                "ACTIVE / OPEN (відкриті) proceedings, or if they are all CLOSED / FINISHED (закриті) or NONE exist.\n\n"
                "Guidance on what to look for:\n"
                "1. If the screenshot has the text 'У вас усе добре' or 'Відкритих проваджень немає' (or similar), "
                "or shows empty list under 'Відкриті' tab, classify as CLOSED.\n"
                "2. If the screenshot shows proceedings with the status 'Завершено' or 'Завершено без оплати' (or similar), "
                "classify as CLOSED.\n"
                "3. If the screenshot shows proceedings with the status 'Чекає на зарахування', 'Відкрите', or shows active "
                "sums of money that must be paid (often with black 'Детальніше' buttons under active headers), "
                "classify as OPEN.\n\n"
                "CRITICAL: Start your response with exactly either '[OPEN]' or '[CLOSED]', and then write a brief "
                "explanation in Ukrainian (1 sentence) describing what you see on the screenshot (e.g. '[CLOSED] Відкритих проваджень немає, усе добре')."
            )
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        }
    ]
    
    try:
        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            max_tokens=150,
            extra_headers={
                "HTTP-Referer": "https://github.com/shaaaaka/telegram-automation-bot",
                "X-Title": "Verification Support Bot"
            }
        )
        if hasattr(response, 'usage') and response.usage:
            await record_ai_usage(response.usage.prompt_tokens, response.usage.completion_tokens)

        res_text = response.choices[0].message.content.strip()
        await save_verdict(image_bytes, bank_name=None, task='proceedings', result_text=res_text, source_size=len(image_bytes))
        return res_text
    except Exception as e:
        logger.error(f"Помилка при запиті до OpenRouter для аналізу проваджень: {e}")
        return f"[UNKNOWN] Не вдалося проаналізувати скріншот через помилку: {e}"

async def verify_deletion_proof(client, media_bytes: bytes, media_type: str, bank_name: str = None) -> tuple[bool, str]:
    """
    Аналіз медіа-файлу (фото чи відео) за допомогою Gemini/OpenAI для перевірки видалення додатку.
    Повертає (is_valid: bool, reason: str).
    """
    if not client:
        return True, "ШІ-клієнт не ініціалізований (пропускаємо авто-перевірку)"

    from bot.services.ai_economy_service import (
        resize_and_compress_image,
        record_ai_usage,
        check_daily_limit_exceeded
    )
    from bot.services.ai_image_cache_service import get_cached_verdict, save_verdict

    cache_image_bytes = media_bytes
    if media_type == 'video':
        try:
            import cv2
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                tmp.write(media_bytes)
                tmp_path = tmp.name
            cap = cv2.VideoCapture(tmp_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 0:
                mid_idx = int(total_frames * 0.4)
                cap.set(cv2.CAP_PROP_POS_FRAMES, mid_idx)
                ret, frame = cap.read()
                if ret:
                    frame_resized = cv2.resize(frame, (480, 640))
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
                    _, buffer = cv2.imencode('.jpg', frame_resized, encode_param)
                    cache_image_bytes = buffer.tobytes()
            cap.release()
            os.remove(tmp_path)
        except Exception as vid_cache_err:
            logger.warning(f"Error extracting video cache frame: {vid_cache_err}")

    # 1. Перевірка pHash кешу для доказу видалення
    cached = await get_cached_verdict(cache_image_bytes, bank_name=bank_name, task='deletion_proof')
    if cached and cached.get('is_valid') is not None:
        logger.info(f"AI Image Cache HIT for deletion proof (distance: {cached['distance']})")
        return cached['is_valid'], cached['reason'] or "Оцінено з кешу"

    if await check_daily_limit_exceeded():
        logger.warning("AI daily limit exceeded in verify_deletion_proof")
        return False, "Не вдалося перевірити автоматично (ліміт токенів вичерпано), буде ручна перевірка"

    try:
        frames_base64 = []
        if media_type == 'video':
            try:
                import cv2
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                    tmp.write(media_bytes)
                    tmp_path = tmp.name
                
                cap = cv2.VideoCapture(tmp_path)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames > 0:
                    indices = [int(total_frames * r) for r in [0.1, 0.4, 0.7, 0.95]]
                    for idx in indices:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                        ret, frame = cap.read()
                        if ret:
                            frame_resized = cv2.resize(frame, (480, 640))
                            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
                            _, buffer = cv2.imencode('.jpg', frame_resized, encode_param)
                            b64 = base64.b64encode(buffer).decode('utf-8')
                            frames_base64.append(b64)
                cap.release()
                os.remove(tmp_path)
            except Exception as vid_err:
                logger.error(f"Error extracting frames from video: {vid_err}")
                return False, f"Помилка обробки відео-файлу: {vid_err}"
        else:
            compressed_bytes = resize_and_compress_image(media_bytes, max_side=1024, quality=80)
            b64 = base64.b64encode(compressed_bytes).decode('utf-8')
            frames_base64.append(b64)

        if not frames_base64:
            return False, "Не вдалося отримати кадри з надісланого медіа-файлу"

        target_app = f"додатку «{bank_name}»" if bank_name else "мобільного додатку"
        exact_bank = f"саме «{bank_name}»" if bank_name else "потрібного банку"

        content = [
            {
                "type": "text", 
                "text": (
                    f"Проаналізуй надані зображення/кадри відео. Це доказ видалення {target_app} клієнтом з телефону. "
                    f"Доказ має бути скріншотом або відео з офіційного магазину додатків: App Store (iOS) або Google Play Market (Android), "
                    f"або процес видалення з екрана смартфона, на якому чітко видно видалення {exact_bank}.\n\n"
                    f"ПРАВИЛА ОЦІНКИ (КРИТИЧНО СУВОРІ):\n"
                    f"1. На зображенні/відео має бути видалення {exact_bank}. Якщо надіслано скріншот/відео ДРУГОГО або ІНШОГО банку/додатка "
                    f"(наприклад, надіслано Alliance, Monobank, Privat24, Кредит Дніпро замість потрібного {bank_name or 'банку'}) — це ПОМИЛКА! Поверни НІ та вкажи причину: «Надіслано скріншот/відео іншого додатку, а не {bank_name or 'потрібного банку'}.»\n"
                    f"2. Якщо на екрані App Store або Play Market видно саме {exact_bank} із кнопкою для встановлення («Завантажити», «Встановити», «Get», кнопка хмарки зі стрілкою тощо, а не кнопкою «Відкрити»), або на відео видно затискання та успішне видалення додатку {bank_name or ''} з екрана — то видалення підтверджено. Поверни ТАК.\n"
                    f"3. Якщо надіслано скріншот робочого столу, де просто немає іконки — це НЕ вважається надійним доказом. Поверни НІ та вкажи причину: «Будь ласка, надішліть скріншот саме з App Store або Play Market, де видно кнопку встановлення додатку, або відео видалення.»\n"
                    f"4. Якщо додаток все ще встановлено (видно кнопку «Відкрити», «Оновити» або додаток запущено) — поверни НІ та вкажи причину: «Додаток все ще встановлено на телефоні.»\n"
                    f"5. В інших випадках, коли видалення не видно або надіслано сторонній скріншот — поверни НІ та вкажи коротку причину.\n\n"
                    f"Дай відповідь у наступному форматі:\n"
                    f"Рядок 1: Тільки одне слово ТАК або НІ (чи підтверджено видалення додатку)\n"
                    f"Рядок 2: Коротке пояснення причини українською мовою для клієнта."
                )
            }
        ]
        
        for b64_frame in frames_base64:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_frame}"
                }
            })

        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "user", "content": content}
            ],
            max_tokens=150,
            extra_headers={
                "HTTP-Referer": "https://github.com/shaaaaka/telegram-automation-bot",
                "X-Title": "Verification Support Bot"
            }
        )
        if hasattr(response, 'usage') and response.usage:
            await record_ai_usage(response.usage.prompt_tokens, response.usage.completion_tokens)
        
        res_text = response.choices[0].message.content.strip()
        lines = [line.strip() for line in res_text.split('\n') if line.strip()]
        
        if not lines:
            return False, "ШІ не повернув відповіді"
            
        decision = lines[0].upper()
        reason = lines[1] if len(lines) > 1 else "Оцінено ШІ"
        
        is_valid = "ТАК" in decision or "YES" in decision
        await save_verdict(cache_image_bytes, bank_name=bank_name, task='deletion_proof', is_valid=is_valid, reason=reason, source_size=len(media_bytes))
        return is_valid, reason

    except Exception as e:
        logger.error(f"Error in verify_deletion_proof: {e}")
        return True, f"Помилка ШІ-верифікації: {e} (пропущено)"

async def verify_relink_initial_screenshot(client, media_bytes: bytes, bank_name: str = None) -> tuple[bool, str]:
    """
    Первинна ШІ-перевірка скріншота екрана банку перед процедурою перев'язу.
    Перевіряє, чи належить екран банку та чи не заблокована картка/акаунт.
    Повертає (is_valid: bool, reason: str).
    """
    if not client:
        return True, "ШІ-клієнт не ініціалізований (пропускаємо авто-перевірку)"

    from bot.services.ai_economy_service import (
        resize_and_compress_image,
        record_ai_usage,
        check_daily_limit_exceeded
    )
    from bot.services.ai_image_cache_service import get_cached_verdict, save_verdict

    # 1. Перевірка pHash кешу для первинного скріншота перев'язу
    cached = await get_cached_verdict(media_bytes, bank_name=bank_name, task='relink_initial')
    if cached and cached.get('is_valid') is not None:
        logger.info(f"AI Image Cache HIT for relink initial screenshot (distance: {cached['distance']})")
        return cached['is_valid'], cached['reason'] or "Оцінено з кешу"

    if await check_daily_limit_exceeded():
        logger.warning("AI daily limit exceeded in verify_relink_initial_screenshot")
        return False, "Перевищено денний ліміт ШІ, буде проведена ручна перевірка."

    try:
        compressed_bytes = resize_and_compress_image(media_bytes, max_side=1024, quality=80)
        b64 = base64.b64encode(compressed_bytes).decode('utf-8')

        target_app = f"додатку «{bank_name}»" if bank_name else "мобільного додатку банку"

        content = [
            {
                "type": "text",
                "text": (
                    f"Проаналізуй надане зображення (скріншот екрана). Це первинна перевірка акаунту перед процедурою перев'язу "
                    f"(зміни номера телефону) для {target_app}.\n\n"
                    f"ПРАВИЛА ОЦІНКИ (КРИТИЧНО СУВОРІ):\n"
                    f"1. На скріншоті має бути зображено екран додатку {target_app}. Якщо це чужий банк або стороннє зображення — "
                    f"поверни НІ та вкажи причину: «Надіслано скріншот іншого додатку, а не {bank_name or 'потрібного банку'}.»\n"
                    f"2. Перевір стан акаунту та картки:\n"
                    f"   - Акаунт/картка повинні бути діючими та не заблокованими.\n"
                    f"   - Якщо видно червоні написи про заблокування, арешт коштів, обмеження чи закриття картки — "
                    f"поверни НІ та вкажи причину: «Акаунт або картка заблокована банком, перев'яз неможливий.»\n"
                    f"3. Якщо скріншот відповідає {target_app} і акаунт/картка в нормальному робочому стані — поверни ТАК.\n\n"
                    f"Дай відповідь у наступному форматі:\n"
                    f"Рядок 1: Тільки одне слово ТАК або НІ\n"
                    f"Рядок 2: Коротке пояснення причини українською мовою."
                )
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}"
                }
            }
        ]

        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "user", "content": content}
            ],
            max_tokens=150,
            extra_headers={
                "HTTP-Referer": "https://github.com/shaaaaka/telegram-automation-bot",
                "X-Title": "Verification Support Bot"
            }
        )
        if hasattr(response, 'usage') and response.usage:
            await record_ai_usage(response.usage.prompt_tokens, response.usage.completion_tokens)

        res_text = response.choices[0].message.content.strip()
        lines = [line.strip() for line in res_text.split('\n') if line.strip()]

        if not lines:
            return False, "ШІ не повернув відповіді"

        decision = lines[0].upper()
        reason = lines[1] if len(lines) > 1 else "Оцінено ШІ"

        is_valid = "ТАК" in decision or "YES" in decision
        await save_verdict(media_bytes, bank_name=bank_name, task='relink_initial', is_valid=is_valid, reason=reason, source_size=len(media_bytes))
        return is_valid, reason

    except Exception as e:
        logger.error(f"Error in verify_relink_initial_screenshot: {e}")
        return True, f"Помилка ШІ-верифікації: {e} (пропущено)"
