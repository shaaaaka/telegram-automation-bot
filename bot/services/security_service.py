import re
import logging

logger = logging.getLogger(__name__)

# Регулярні вирази для виявлення спроб Prompt Injection / Jailbreak
INJECTION_PATTERNS = [
    # Фрази для скасування інструкцій
    r'\b(забудь|ігноруй|скасуй|знехтуй|forget|ignore|override)\b.*?(інструкц|правил|промпт|prompt|rules|system)',
    r'\b(you are now|system prompt|act as|pretend to be)\b',
    # Спроби змусити видати маркери успіху або імперативно змусити вважати верифікацію пройденою
    r'(?:напиши|поверни)\s+(?:маркер\s+)?\[?SUCCESS_VERIFICATION\]?',
    r'(?:скажи|напиши|поверни)\s+(?:що|ніби|будто)?\s*(?:я|користувач)?\s*(?:успішно\s+)?пройшов\s+верифікацію\b',
    r'\[(SUCCESS_VERIFICATION|REFUSED_PHONE|OFFER_AMOBANK_INSTRUCTIONS|OFFER_LVIV_SUCCESS_SCREEN)\]',
    # Системні модифікатори ролей та XML-теги
    r'</?(user_message|system|assistant)>'
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
    - Номери телефонів у різних форматах (+380..., 093..., +38 (093) 123-45-67) -> [ТЕЛЕФОН_ПРИХОВАНО]
    - 10-значні ІПН (РНОКПП) -> [ІПН_ПРИХОВАНО]
    """
    if not text:
        return text

    sanitized = text

    # 1. Маскування номерів банківських карток (4 групи по 4 цифри з розделителями чи разом)
    def card_replacer(match):
        raw = match.group(0)
        digits = re.sub(r'\D', '', raw)
        if len(digits) == 16:
            return f"[КАРТКА_****_{digits[-4:]}]"
        return raw

    sanitized = re.sub(r'\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b', card_replacer, sanitized)

    # 2. Маскування номерів телефонів у різних форматах
    # Наприклад: +380931234567, 0931234567, +38 (093) 123-45-67, 093 123 45 67, 093-123-4567
    phone_pattern = r'(?:\+?38)?\s*\(?0\d{2}\)?[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b'
    sanitized = re.sub(phone_pattern, '[ТЕЛЕФОН_ПРИХОВАНО]', sanitized)

    # 3. Маскування 10-значних ІПН (РНОКПП)
    # Маскуємо 10 підряд цифр, перевіряючи відсутність крапок чи слешів навколо (щоб не пошкодити дати/URL)
    ipn_pattern = r'(?<![.\/\d])\b\d{10}\b(?![.\/\d])'
    sanitized = re.sub(ipn_pattern, '[ІПН_ПРИХОВАНО]', sanitized)

    return sanitized

def redact_prompt_injections(text: str) -> str:
    """
    Замінює будь-які виявлені фрази prompt injection у тексті на [REDACTED_INJECTION].
    """
    if not text:
        return text

    sanitized = text
    for pattern in INJECTION_PATTERNS:
        sanitized = re.sub(pattern, '[REDACTED_INJECTION]', sanitized, flags=re.IGNORECASE)
    return sanitized
