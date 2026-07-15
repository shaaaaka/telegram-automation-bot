
from fastapi import APIRouter

import bot.database as db


router = APIRouter()

@router.get("/api/banks")
async def get_banks():
    """Отримання списку унікальних банків з ліній та шаблонів налаштувань"""
    lines_banks = await db.get_unique_banks()
    templates = await db.get_all_bank_templates()
    template_keys = list(templates.keys())
    
    # Об'єднуємо обидва списки, зберігаючи унікальність та регістр
    merged_banks = list(dict.fromkeys(lines_banks + template_keys))
    return {"banks": merged_banks}

