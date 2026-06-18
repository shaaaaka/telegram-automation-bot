import os
from dotenv import load_dotenv

# Завантажуємо змінні з файлу .env, якщо він існує
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
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

# Валідація основних параметрів
if not BOT_TOKEN:
    print("WARNING: BOT_TOKEN is not set in environment or .env file!")
if not ADMIN_ID:
    print("WARNING: ADMIN_ID is not set or invalid!")
if not GIVER_CHAT_ID:
    print("WARNING: GIVER_CHAT_ID is not set or invalid!")

# Шаблони інструкцій завантаження для банків
BANK_TEMPLATES = {
    "izibank": {
        "command": "/ЗАВАНТАЖізі",
        "text": "Завантажуйте будь ласка додаток \"izi bank\""
    },
    "ecobank": {
        "command": "/ЗАВАНТАЖеко",
        "text": "Завантажуйте будь ласка додаток \"ЕкоБанк\""
    },
    "amobank": {
        "command": "/ЗАВАНТАЖамо",
        "text": "Завантажуйте будь ласка додаток \"amobank\""
    },
    "lvivbank": {
        "command": "/ЗАВАНТАЖльвів",
        "text": "Завантажуйте будь ласка додаток \"Bank Lviv\""
    },
    "bank.kd": {
        "command": "/ЗАВАНТАЖкд",
        "text": "Завантажуйте будь ласка додаток \"bank.kd\""
    },
    "pumb": {
        "command": "/ЗАВАНТАЖпумб",
        "text": "Завантажуйте будь ласка додаток \"ПУМБ\""
    },
    "alliance": {
        "command": "/ЗАВАНТАЖальянс",
        "text": "Завантажуйте будь ласка додаток \"Alliance\""
    }
}

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

