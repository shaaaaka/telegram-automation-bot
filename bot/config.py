import os
import logging
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Завантажуємо змінні з файлу .env, якщо він існує
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_BOT_TOKEN = os.getenv("LOG_BOT_TOKEN")
DB_FILE = os.getenv("DB_FILE", "bot.db")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-flash-1.5")

# Зчитуємо та перетворюємо ID адміна та чату гівера
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

try:
    GIVER_CHAT_ID = int(os.getenv("GIVER_CHAT_ID", "0"))
except ValueError:
    GIVER_CHAT_ID = 0

try:
    ANKETA_CHAT_ID = int(os.getenv("ANKETA_CHAT_ID", "0"))
except ValueError:
    ANKETA_CHAT_ID = 0

try:
    ARCHIVE_GROUP_ID = int(os.getenv("ARCHIVE_GROUP_ID", "0"))
except ValueError:
    ARCHIVE_GROUP_ID = 0

# Валідація основних параметрів
if not BOT_TOKEN:
    logger.warning("BOT_TOKEN is not set in environment or .env file!")
if not ADMIN_ID:
    logger.warning("ADMIN_ID is not set or invalid!")
if not GIVER_CHAT_ID:
    logger.warning("GIVER_CHAT_ID is not set or invalid!")

# Шаблони інструкцій завантаження для банків
BANK_TEMPLATES = {
    "izibank": {
        "command": "/ЗАВАНТАЖізі",
        "text": "Завантажуйте будь ласка додаток \"izi bank\"",
        "code_length": 4
    },
    "amobank": {
        "command": "/ЗАВАНТАЖамо",
        "text": "Завантажуйте будь ласка додаток \"amobank\"",
        "code_length": 4
    },
    "lvivbank": {
        "command": "/ЗАВАНТАЖльвів",
        "text": "Завантажуйте будь ласка додаток \"Bank Lviv\"",
        "code_length": 6
    },
    "bank.kd": {
        "command": "/ЗАВАНТАЖкд",
        "text": "Завантажуйте будь ласка додаток \"bank.kd\"",
        "code_length": 6
    },
    "alliance": {
        "command": "/ЗАВАНТАЖальянс",
        "text": "Завантажуйте будь ласка додаток \"Alliance\"",
        "code_length": 4
    }
}

# Порядок відображення банків за замовчуванням
DEFAULT_BANK_ORDER = ["bank.kd", "IziBank", "Alliance", "LvivBank", "AmoBank"]

def get_bank_template(bank_name: str):
    if not bank_name:
        return None
    name_norm = bank_name.lower().replace(" ", "").replace("-", "")
    for key, val in BANK_TEMPLATES.items():
        if key in name_norm or name_norm in key:
            return val
    return None

def get_bank_template_with_key(bank_name: str):
    if not bank_name:
        return None, None
    name_norm = bank_name.lower().replace(" ", "").replace("-", "")
    for key, val in BANK_TEMPLATES.items():
        if key in name_norm or name_norm in key:
            return key, val
    return None, None

def get_template_photo(key: str):
    if not key:
        return None
    # Нормалізуємо ключ: переводимо в нижній регістр та прибираємо слеші
    normalised = key.strip().lower().replace("/", "")
    images_dir = os.path.join(os.path.dirname(__file__), "resources", "images")
    if not os.path.exists(images_dir):
        return None
    for ext in [".png", ".jpg", ".jpeg", ".gif"]:
        file_path = os.path.join(images_dir, f"{normalised}{ext}")
        if os.path.exists(file_path):
            return file_path
    return None


async def get_expected_code_length(bank_name: str) -> int | None:
    if not bank_name:
        return None
    name_norm = bank_name.lower().replace(" ", "").replace("-", "").replace(".", "")
    
    try:
        from bot import database as db
        templates = await db.get_all_bank_templates()
        for key, val in templates.items():
            key_norm = key.lower().replace(" ", "").replace("-", "").replace(".", "")
            if key_norm in name_norm or name_norm in key_norm:
                if 'code_length' in val and val['code_length'] is not None:
                    return int(val['code_length'])
    except Exception:
        pass

    norm_lengths = {
        "bankkd": 5,
        "izibank": 4,
        "alliance": 4,
        "lvivbank": 4,
        "amobank": 6
    }
    for key, length in norm_lengths.items():
        if key in name_norm or name_norm in key:
            return length
    return None

# Кеш налаштувань у пам'яті (для гарячого оновлення ID чатів без перезапуску)
_settings_cache = {}

_INT_SETTINGS = {"anketa_chat_id", "giver_chat_id", "archive_group_id", "admin_id"}

def get_cached_setting(key: str, default=None):
    """Повертає будь-яке налаштування з кешу, якщо воно там є."""
    return _settings_cache.get(key, default)

def get_anketa_chat_id() -> int:
    return _settings_cache.get("anketa_chat_id", ANKETA_CHAT_ID)

def get_giver_chat_id() -> int:
    return _settings_cache.get("giver_chat_id", GIVER_CHAT_ID)

def get_archive_group_id() -> int:
    return _settings_cache.get("archive_group_id", ARCHIVE_GROUP_ID)

def get_admin_id() -> int:
    return _settings_cache.get("admin_id", ADMIN_ID)

def set_cached_setting(key: str, value: str):
    """Зберігає значення в кеш. ID чатів конвертує в int, інше — зберігає як рядок."""
    if key in _INT_SETTINGS:
        try:
            _settings_cache[key] = int(value)
        except (ValueError, TypeError):
            pass
    else:
        _settings_cache[key] = value

