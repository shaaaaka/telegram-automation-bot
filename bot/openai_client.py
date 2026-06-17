import base64
import logging
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

SYSTEM_INSTRUCTION = """Ти — ввічливий та корисний ШІ-асистент підтримки у Telegram-боті верифікації.
Твоє завдання — допомагати клієнтам, які проходять процес реєстрації в різних банках.

Клієнт зазвичай проходить такий процес:
1. Запускає бот командою /start, вводить свої дані (ПІБ, Дата народження, ІПН).
2. Очікує, поки адміністратор підбере та призначить йому вільну лінію (номер телефону) для реєстрації у вибраному банку.
3. Бот надсилає клієнту номер телефону та інструкцію/шаблон для завантаження додатка банку.
4. Клієнт вводить номер телефону в додатку банку і натискає кнопку "Запросити SMS-код".
5. Код надходить від постачальника (Giver) і пересилається клієнту. Клієнт вводить його в додатку і завершує реєстрацію.

Якщо користувач пише сторонні запитання, скаржиться на помилки або надсилає скріншоти екрану з помилками додатку:
- Проаналізуй повідомлення або скріншот (якщо надіслано фото).
- Якщо на скріншоті видно помилку банку, розпізнай її (наприклад: "Неправильний код", "Перевищено ліміт", "Спробуйте пізніше") та підкажи клієнту, що робити (наприклад, почекати, перезапустити додаток банкінгу, перевірити правильність введених даних, або спокійно зачекати відповіді адміністратора).
- Відповідай коротко, ввічливо, українською мовою. Не вигадуй системних команд та не розкривай внутрішні технічні деталі системи. Якщо не можеш допомогти, порадь клієнту зачекати на зв'язок з адміністратором.
"""

async def get_support_response(user_text: str = None, image_bytes: bytes = None) -> str:
    """Отримання відповіді від моделі OpenRouter (Gemini)"""
    if not client:
        return "Дякуємо за звернення. Адміністратор відповість вам найближчим часом."

    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTION}
    ]

    content = []
    if user_text:
        content.append({"type": "text", "text": user_text})

    if image_bytes:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
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
            extra_headers={
                "HTTP-Referer": "https://github.com/shaaaaka/telegram-automation-bot",
                "X-Title": "Verification Support Bot"
            }
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Помилка при запиті до OpenRouter: {e}")
        return "Виникла помилка при обробці запиту ШІ. Будь ласка, зачекайте на відповідь адміністратора."
