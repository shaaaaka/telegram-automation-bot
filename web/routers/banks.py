
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
    
    # Об'єднуємо обидва списки, зберігаючи унікальність та регістр
    merged_banks = list(dict.fromkeys(lines_banks + template_keys))
    
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

