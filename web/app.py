import os
import mimetypes

from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles

from web.core import check_admin_auth, lifespan
from web.routers import (
    dashboard, lines, sessions, media, banks, codes, messages, users, settings, stats, websocket
)

mimetypes.init()
mimetypes.add_type("text/css", ".css", True)
mimetypes.add_type("application/javascript", ".js", True)

app = FastAPI(title="Verification Bot Web Admin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

admin_dependency = Depends(check_admin_auth)
app.include_router(dashboard.router, dependencies=[admin_dependency])
app.include_router(lines.router, dependencies=[admin_dependency])
app.include_router(sessions.router, dependencies=[admin_dependency])
app.include_router(media.router, dependencies=[admin_dependency])
app.include_router(banks.router, dependencies=[admin_dependency])
app.include_router(codes.router, dependencies=[admin_dependency])
app.include_router(messages.router, dependencies=[admin_dependency])
app.include_router(users.router, dependencies=[admin_dependency])
app.include_router(settings.router, dependencies=[admin_dependency])
app.include_router(stats.router, dependencies=[admin_dependency])
app.include_router(websocket.router)
