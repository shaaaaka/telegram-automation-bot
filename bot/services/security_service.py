import re
import logging

logger = logging.getLogger(__name__)

# Регулярні вирази для виявлення спроб Prompt Injection / Jailbreak
INJECTION_PATTERNS = [
    # Фрази для скасування інструкцій
    r'(забудь|ігноруй|скасуй|знехтуй|forget|ignore|override)\b.*?(інструкц|правил|промпт|prompt|rules|system)',
    r'\b(you are now|system prompt|act as|pretend to be|say that i passed)\b',
    # Спроби змусити видати маркери успіху чи спеціальні команди
    r'(скажи|напиши|поверни|постав).*(пройшов|верифіковано|увага|\[SUCCESS_VERIFICATION\]|\[REFUSED_PHONE\])',
    r'\[(SUCCESS_VERIFICATION|REFUSED_PHONE|OFFER_AMOBANK_INSTRUCTIONS|OFFER_LVIV_SUCCESS_SCREEN)\]',
    # Системні модифікатори ролей
    r'</?user_message>',
    r'</?system>',
    r'</?assistant>'
]

def sanitize_user_input(text: str) -> tuple[bool, str]:
    """
    Перевіряє вхідний текст користувача на наявність спроб Prompt Injection чи маніпуляції промптом.
    Повертає (is_safe: bool, sanitized_text_or_reason: str).
    """
    if not text:
        return True, text

    cleaned_text = text.strip()

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, cleaned_text, re.IGNORECASE):
            logger.warning(f"Detected Prompt Injection attempt: '{cleaned_text[:50]}...' matching pattern '{pattern}'")
            return False, "Виявлено спробу нестандартного запиту. Повідомлення передано на перевірку адміністратору."

    return True, cleaned_text

def anonymize_pii_data(text: str) -> str:
    """
    Маскує персональні дані (PII) у тексті перед відправкою до зовнішніх AI API:
    - 16-значні номери банківських карток -> [КАРТКА_****_1234]
    - 10-значні ІПН (РНОКПП) -> [ІПН_ПРИХОВАНО]
    - Номери телефонів (міжнародний та локальний формат) -> [ТЕЛЕФОН_ПРИХОВАНО]
    """
    if not text:
        return text

    sanitized = text

    # 1. Маскування 16-значних номерів карток (з пробілами або дефісами)
    def card_replacer(match):
        digits = re.sub(r'\D', '', match.group(0))
        if len(digits) == 16:
            return f"[КАРТКА_****_{digits[-4:]}]"
        return match.group(0)

    sanitized = re.sub(r'\b(?:\d[ -]*?){16}\b', card_replacer, sanitized)

    # 2. Маскування номерів телефонів (формат +380... або 0...)
    sanitized = re.sub(r'\b(?:\+?380|0)\d{9}\b', '[ТЕЛЕФОН_ПРИХОВАНО]', sanitized)

    # 3. Маскування 10-значних ІПН (РНОКПП) у полях анкетних даних
    # Маскуємо тільки 10 підряд цифр (щоб не зачепити дати чи короткі ID)
    def ipn_replacer(match):
        digits = match.group(0)
        # Перевіряємо, чи це не частина більшого числа
        return '[ІПН_ПРИХОВАНО]'

    sanitized = re.sub(r'\b\d{10}\b', ipn_replacer, sanitized)

    return sanitized
