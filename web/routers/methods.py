import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from typing import List

import bot.database as db
from web.models import VerificationMethodCreate, VerificationMethodUpdate, SessionMethodUpdate


router = APIRouter()


@router.get("/methods", response_class=HTMLResponse)
async def get_methods_page():
    """Сторінка керування методами верифікації"""
    template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "methods.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="HTML template file not found")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


@router.get("/api/methods")
async def get_methods():
    """Отримання всіх методів верифікації"""
    methods = await db.get_all_verification_methods()
    return {"methods": methods}


@router.get("/api/methods/{key}")
async def get_method(key: str):
    """Отримання методу за ключем"""
    method = await db.get_verification_method(key)
    if not method:
        raise HTTPException(status_code=404, detail="Method not found")
    return method


@router.post("/api/methods")
async def create_method(body: VerificationMethodCreate):
    """Створення нового методу верифікації"""
    await db.save_verification_method(
        key=body.key,
        display_name=body.display_name,
        required_client_fields=body.required_client_fields,
        required_screenshots=body.required_screenshots,
        screenshot_instructions=body.screenshot_instructions,
        initial_message=body.initial_message,
        report_template=body.report_template,
        ai_rules=body.ai_rules,
        allowed_banks=body.allowed_banks,
        ask_relink_at_start=body.ask_relink_at_start,
        is_active=body.is_active
    )
    method = await db.get_verification_method(body.key)
    return {"status": "success", "method": method}


@router.put("/api/methods/{key}")
async def update_method(key: str, body: VerificationMethodUpdate):
    """Оновлення методу верифікації"""
    existing = await db.get_verification_method(key)
    if not existing:
        raise HTTPException(status_code=404, detail="Method not found")
    
    await db.save_verification_method(
        key=key,
        display_name=body.display_name,
        required_client_fields=body.required_client_fields,
        required_screenshots=body.required_screenshots,
        screenshot_instructions=body.screenshot_instructions,
        initial_message=body.initial_message,
        report_template=body.report_template,
        ai_rules=body.ai_rules,
        allowed_banks=body.allowed_banks,
        ask_relink_at_start=body.ask_relink_at_start,
        is_active=body.is_active
    )
    method = await db.get_verification_method(key)
    return {"status": "success", "method": method}


@router.delete("/api/methods/{key}")
async def delete_method(key: str):
    """Видалення методу верифікації"""
    existing = await db.get_verification_method(key)
    if not existing:
        raise HTTPException(status_code=404, detail="Method not found")
    
    await db.delete_verification_method(key)
    return {"status": "success"}


@router.post("/api/sessions/{client_id}/method")
async def set_session_method(client_id: int, body: SessionMethodUpdate):
    """Призначення методу верифікації для сесії через адмін-панель"""
    session = await db.get_session(client_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    method = await db.get_verification_method(body.method_key)
    if not method:
        raise HTTPException(status_code=404, detail="Method not found")
    
    await db.update_session_method(client_id, body.method_key)
    return {"status": "success", "method_key": body.method_key}
