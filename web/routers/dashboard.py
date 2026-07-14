import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse



router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Повертає головну сторінку адмін-панелі"""
    template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "index.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="HTML template file not found")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@router.get("/api/status")
async def get_status():
    """Отримання статусу підключення"""
    from bot.config import BOT_TOKEN
    return {
        "status": "online",
        "bot_configured": BOT_TOKEN is not None
    }

