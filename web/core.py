import os
import secrets
from contextlib import asynccontextmanager
from typing import List, Optional

from aiogram import Bot, Dispatcher
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from bot import database as db
from bot.database import chat_message_callbacks


bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None

# Глобальний список нерозподілених кодів (Сценарій 3)
unrouted_codes = []


def set_bot(bot_instance: Bot):
    global bot
    bot = bot_instance


def set_dp(dp_instance: Dispatcher):
    global dp
    dp = dp_instance


security = HTTPBasic(auto_error=False)


async def check_admin_auth(request: Request = None, websocket: WebSocket = None):
    """Перевірка авторизації адміністратора"""
    username_env = os.getenv("WEB_USERNAME")
    password_env = os.getenv("WEB_PASSWORD")
    if not username_env or not password_env:
        return True

    auth_header = None
    if request is not None:
        auth_header = request.headers.get("authorization")
    elif websocket is not None:
        auth_header = websocket.headers.get("authorization")

    if auth_header:
        import base64
        try:
            if auth_header.startswith("Basic "):
                encoded = auth_header.split(" ", 1)[1]
                decoded = base64.b64decode(encoded).decode("utf-8")
                username, password = decoded.split(":", 1)
                is_username_correct = secrets.compare_digest(username, username_env)
                is_password_correct = secrets.compare_digest(password, password_env)
                if is_username_correct and is_password_correct:
                    return True
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Basic"},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Життєвий цикл веб-сервера"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Web lifespan starting")

    try:
        from bot.database import init_db
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Помилка ініціалізації бази даних на веб-сервері: {e}")

    # Initialize bot/dp from BOT_TOKEN if running uvicorn directly
    logger.info(f"Bot before init: {bot is not None}")
    if bot is None:
        from bot.config import BOT_TOKEN
        logger.info(f"BOT_TOKEN from config: {'SET' if BOT_TOKEN else 'NOT SET'}")
        if BOT_TOKEN:
            set_bot(Bot(token=BOT_TOKEN))
            logger.info(f"After set_bot, bot is {bot is not None}")
            if dp is None:
                set_dp(Dispatcher())
                logger.info(f"After set_dp, dp is {dp is not None}")
        else:
            logger.warning("BOT_TOKEN not set, bot remains None")

    logger.info(f"Bot after init: {bot is not None}")
    yield


# WebSocket Connection Manager for real-time CRM chat updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


async def on_new_chat_message(client_id: int, sender: str, message_text: str = None, photo_id: str = None):
    """Broadcast a new chat message to all connected WebSocket clients."""
    import datetime
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await manager.broadcast({
        "type": "new_message",
        "client_id": client_id,
        "sender": sender,
        "message_text": message_text,
        "photo_id": photo_id,
        "created_at": now_str
    })


# Register WebSocket broadcast callback
chat_message_callbacks.append(on_new_chat_message)


# Local file cache for Telegram static files (photos, avatars) to optimize loading speed
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
PHOTOS_CACHE_DIR = os.path.join(CACHE_DIR, "photos")
AVATARS_CACHE_DIR = os.path.join(CACHE_DIR, "avatars")

os.makedirs(PHOTOS_CACHE_DIR, exist_ok=True)
os.makedirs(AVATARS_CACHE_DIR, exist_ok=True)
