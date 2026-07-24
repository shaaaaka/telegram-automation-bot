import base64
import logging
import re
from openai import AsyncOpenAI
from bot.config import OPENROUTER_API_KEY, OPENROUTER_MODEL

logger = logging.getLogger(__name__)

# Ініціалізуємо AsyncOpenAI клієнт для OpenRouter
client = None
if OPENROUTER_API_KEY:
    client = AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )
else:
    logger.warning("OPENROUTER_API_KEY не знайдено в конфігурації. ШІ-підтримка буде неактивною.")

# Реекспорт сервісу генерації системних інструкцій
from bot.services.prompt_service import (
    BASE_MANNER_OF_SPEECH,
    compile_system_instruction,
)

# Реекспорт сервісу Vision аналізу скріншотів
import bot.services.vision_service as vision_mod

async def analyze_proceedings_screenshot(image_bytes: bytes) -> str:
    return await vision_mod.analyze_proceedings_screenshot(client, image_bytes)

async def verify_deletion_proof(media_bytes: bytes, media_type: str, bank_name: str = None) -> tuple[bool, str]:
    return await vision_mod.verify_deletion_proof(client, media_bytes, media_type, bank_name)

async def verify_relink_initial_screenshot(media_bytes: bytes, bank_name: str = None) -> tuple[bool, str]:
    return await vision_mod.verify_relink_initial_screenshot(client, media_bytes, bank_name)


from bot.services.ai_economy_service import (
    resize_and_compress_image,
    get_cached_template_base64,
    match_fallback_rule,
    record_ai_usage,
    check_daily_limit_exceeded,
)
from bot.services.security_service import (
    sanitize_user_input,
    anonymize_pii_data,
)

async def get_support_response(user_text: str = None, image_bytes: bytes = None, client_data: str = None, current_bank_name: str = None, chat_history: list = None, sent_codes_count: int = 0) -> str:
    """Отримання відповіді від моделі OpenRouter (Gemini)"""
    if not client:
        return "Дякуємо за звернення. Адміністратор відповість вам найближчим часом."

    # 0. Захист від Prompt Injection / Маніпуляцій промптом
    safe_user_text = user_text
    if user_text:
        is_safe, check_res = sanitize_user_input(user_text)
        if not is_safe:
            logger.warning(f"Prompt Injection blocked for input: '{user_text[:40]}...'")
            return check_res
        safe_user_text = check_res

    # 1. Перевірка детермінованих fallback-правил (без виклику AI)
    if safe_user_text:
        fallback_resp = await match_fallback_rule(safe_user_text, current_bank_name)
        if fallback_resp:
            logger.info(f"Fallback regex matched for text '{safe_user_text[:30]}...': responding without AI.")
            return fallback_resp

    # 2. Перевірка денного ліміту токенів
    if await check_daily_limit_exceeded():
        logger.warning("AI daily token limit exceeded. Returning fallback support response.")
        return "Дякуємо за звернення. Наразі підключається менеджер для допомоги."

    # Збираємо системний промпт динамічно
    system_instruction = await compile_system_instruction(current_bank_name, sent_codes_count)

    messages = [
        {"role": "system", "content": system_instruction}
    ]

    # Додаємо few-shot приклади з бази
    from bot import database as db
    try:
        examples = await db.get_active_ai_examples()
        for ex in examples:
            messages.append({"role": "user", "content": [{"type": "text", "text": f"<user_message>{ex['client_message']}</user_message>"}]})
            messages.append({"role": "assistant", "content": ex['bot_response']})
    except Exception as ex_err:
        logger.error(f"Помилка завантаження few-shot прикладів: {ex_err}")

    # Додаємо контекст клієнта, якщо він є (маскуючи PII)
    context_parts = []
    if client_data:
        anon_client_data = anonymize_pii_data(client_data)
        context_parts.append(f"Анкетні дані клієнта:\n{anon_client_data}")
        dob_match = re.search(r'(?:ДР|Дата народження|Дата|Дар):\s*([^\n]+)', client_data, re.IGNORECASE)
        if dob_match:
            dob_str = dob_match.group(1).strip()
            try:
                date_parts = re.findall(r'\d+', dob_str)
                if len(date_parts) == 3:
                    day = int(date_parts[0])
                    month = int(date_parts[1])
                    year = int(date_parts[2])
                    if year < 100:
                        year += 1900 if year > 30 else 2000
                    
                    from datetime import date
                    born = date(year, month, day)
                    today = date.today()
                    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
                    context_parts.append(f"Розрахований вік клієнта: {age} років (це важливо для вибору зайнятості та доходів)")
            except Exception as age_err:
                logger.error(f"Error calculating client age from DOB '{dob_str}': {age_err}")
    if current_bank_name:
        context_parts.append(f"Поточний банк, який проходить клієнт: {current_bank_name}")
        
    if context_parts:
        messages.append({
            "role": "system",
            "content": "КОНТЕКСТ ПОТОЧНОГО КЛІЄНТА:\n" + "\n\n".join(context_parts)
        })

    # Додаємо історію чату, якщо вона передана
    if chat_history:
        messages.extend(chat_history)

    # Завантажуємо зразок успішної реєстрації з БД (використовуючи in-memory кеш)
    success_b64_images = []
    if current_bank_name and image_bytes:
        try:
            bank_template = await db.get_bank_template_db(current_bank_name)
            if bank_template and bank_template.get('success_screenshot_path'):
                import os
                paths_str = bank_template['success_screenshot_path']
                paths = [p.strip() for p in paths_str.split(',') if p.strip()]
                for p in paths:
                    rel_path = p.lstrip('/')
                    local_path = os.path.join("web", rel_path)
                    b64_data = get_cached_template_base64(local_path)
                    if b64_data:
                        success_b64_images.append(b64_data)
        except Exception as e:
            logger.error(f"Error loading success screenshot templates: {e}")

    content = []
    if safe_user_text:
        content.append({"type": "text", "text": f"<user_message>{safe_user_text}</user_message>"})

    if image_bytes:
        if success_b64_images:
            content.append({"type": "text", "text": "КЛІЄНТСЬКИЙ СКРІНШОТ (надісланий користувачем для перевірки):"})
        # 3. Стискаємо зображення клієнта до 1024px
        compressed_bytes = resize_and_compress_image(image_bytes, max_side=1024, quality=80)
        base64_image = base64.b64encode(compressed_bytes).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
            }
        })

    if success_b64_images:
        content.append({"type": "text", "text": "ЕТАЛОННІ ЗРАЗКИ УСПІШНОЇ РЕЄСТРАЦІЇ (як має виглядати правильний фінальний екран для цього банку):"})
        for b64_img in success_b64_images:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_img}"
                }
            })

    if not content:
        return "Будь ласка, напишіть ваше запитання або надішліть скріншот помилки."

    messages.append({
        "role": "user",
        "content": content
    })

    try:
        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            max_tokens=250,
            extra_headers={
                "HTTP-Referer": "https://github.com/shaaaaka/telegram-automation-bot",
                "X-Title": "Verification Support Bot"
            }
        )
        if hasattr(response, 'usage') and response.usage:
            await record_ai_usage(response.usage.prompt_tokens, response.usage.completion_tokens)

        raw_response = response.choices[0].message.content.strip()
        return raw_response
    except Exception as e:
        logger.error(f"Помилка при запиті до OpenRouter: {e}")
        return "Виникла помилка при обробці запиту ШІ. Будь ласка, зачекайте на відповідь адміністратора."

async def analyze_chat_and_propose_rule(chat_history_text: str) -> str:
    """Аналіз історії діалогу з клієнтом за допомогою Gemini для генерації пропозиції нового правила."""
    if not client:
        return ""
        
    prompt = f"""Ти — аналітик ШІ-підтримки для верифікації мобільних банків.
Нижче наведено лог реального діалогу між Клієнтом (Client), ШІ-ботом (Bot) та Адміністратором/Менеджером (Admin), який підключився вручну для вирішення проблеми, оскільки бот не зміг упоратися або дав неправильну відповідь.

ДІАЛОГ ДЛЯ АНАЛІЗУ:
{chat_history_text}

ЗАВДАННЯ:
1. Проаналізуй цей діалог і знайди, на якому етапі виникло непорозуміння, помилка додатку чи складність для клієнта.
2. Сформулюй ОДНЕ чітке, конкретне і коротке правило або інструкцію для ШІ-бота українською мовою.
3. Правило має вчити бот, як правильно вирішувати саме цю проблему в майбутньому (наприклад: порадити вимкнути VPN, дати інструкцію щодо фотографування, або повідомити щось конкретне).
4. Правило має бути написане в 1-2 коротких реченнях, у наказовому або рекомендаційному тоні для ШІ (наприклад: "Якщо клієнт отримує помилку ліміту, скажіть...").
5. Не пиши жодного зайвого тексту, вступів, пояснень чи аналітики. Поверни СТРОГО тільки текст самого правила. Якщо нове правило не потрібне (діалог звичайний), поверни порожній рядок.
"""
    try:
        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": "Ти — корисний аналітик діалогів підтримки. Повертаєш тільки сформульоване правило без додаткового тексту."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250,
            extra_headers={
                "HTTP-Referer": "https://github.com/shaaaaka/telegram-automation-bot",
                "X-Title": "Verification Support Analyzer"
            }
        )
        if hasattr(response, 'usage') and response.usage:
            await record_ai_usage(response.usage.prompt_tokens, response.usage.completion_tokens)

        rule_text = response.choices[0].message.content.strip()
        if rule_text.startswith('"') and rule_text.endswith('"'):
            rule_text = rule_text[1:-1].strip()
        if rule_text.lower().startswith("правило:"):
            rule_text = rule_text[len("правило:"):].strip()
        return rule_text
    except Exception as e:
        logger.error(f"Помилка при аналізі чату: {e}")
        return ""
