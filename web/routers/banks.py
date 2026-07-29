
from fastapi import APIRouter

import bot.database as db
from bot.config import normalize_bank_name


router = APIRouter()

@router.get("/api/banks")
async def get_banks():
    """Отримання списку унікальних банків з ліній та шаблонів налаштувань"""
    lines_banks = await db.get_unique_banks()
    templates = await db.get_all_bank_templates()
    template_keys = list(templates.keys())
    
    # Об'єднуємо обидва списки, зберігаючи унікальність за нормалізованою назвою
    merged_banks = []
    seen_norm = set()
    for bank in lines_banks + template_keys:
        name_norm = normalize_bank_name(bank)
        if name_norm and name_norm not in seen_norm:
            seen_norm.add(name_norm)
            # Prefer the template key if available, otherwise keep the first seen name
            canonical_key = bank
            for key in template_keys:
                if normalize_bank_name(key) == name_norm:
                    canonical_key = key
                    break
            merged_banks.append(canonical_key)
    
    # Фільтруємо неактивні банки
    active_banks = []
    for bank in merged_banks:
        is_active = True
        name_norm = normalize_bank_name(bank)
        for key, val in templates.items():
            key_norm = normalize_bank_name(key)
            if key_norm == name_norm or key_norm in name_norm or name_norm in key_norm:
                if val.get('is_active') == 0:
                    is_active = False
                break
        if is_active:
            active_banks.append(bank)
            
    return {"banks": active_banks}

