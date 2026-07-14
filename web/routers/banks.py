
from fastapi import APIRouter

import bot.database as db


router = APIRouter()

@router.get("/api/banks")
async def get_banks():
    """Отримання списку унікальних банків з ліній"""
    banks = await db.get_unique_banks()
    return {"banks": banks}

