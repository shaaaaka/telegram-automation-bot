
from fastapi import APIRouter, HTTPException

import bot.database as db


router = APIRouter()

@router.get("/api/stats")
async def get_stats_endpoint():
    """Отримання статистики верифікацій"""
    try:
        stats = await db.get_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

@router.post("/api/stats/clear")
async def clear_stats_endpoint():
    """Очищення всієї статистики"""
    try:
        await db.clear_statistics()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear stats: {str(e)}")

