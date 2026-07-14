
from fastapi import APIRouter, HTTPException

import bot.database as db
from bot.config import set_cached_setting
from web.models import *


router = APIRouter()

@router.get("/api/settings")
async def get_settings_endpoint():
    """Отримання налаштувань та шаблонів банків"""
    try:
        settings = await db.get_all_settings()

        # Load environment defaults if database values are missing or empty
        from bot.config import ADMIN_ID, ANKETA_CHAT_ID, GIVER_CHAT_ID, ARCHIVE_GROUP_ID
        
        for key in ["admin_id", "anketa_chat_id", "giver_chat_id", "archive_group_id"]:
            val = settings.get(key)
            if not val or val == "None" or val == "null":
                settings[key] = ""
                
        if not settings["admin_id"]:
            settings["admin_id"] = str(ADMIN_ID) if ADMIN_ID else ""
        if not settings["anketa_chat_id"]:
            settings["anketa_chat_id"] = str(ANKETA_CHAT_ID) if ANKETA_CHAT_ID else ""
        if not settings["giver_chat_id"]:
            settings["giver_chat_id"] = str(GIVER_CHAT_ID) if GIVER_CHAT_ID else ""
        if not settings["archive_group_id"]:
            settings["archive_group_id"] = str(ARCHIVE_GROUP_ID) if ARCHIVE_GROUP_ID else ""

        templates = await db.get_all_bank_templates()
        return {
            "settings": settings,
            "templates": templates
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get settings: {str(e)}")

@router.post("/api/settings")
async def update_settings_endpoint(body: AppSettingsUpdate):
    """Оновлення загальних налаштувань"""
    try:
        await db.set_setting("reminder_delay_minutes", body.reminder_delay_minutes)
        await db.set_setting("reminder_text", body.reminder_text)
        await db.set_setting("reminders_enabled", body.reminders_enabled)
        if body.giver_request_format is not None:
            await db.set_setting("giver_request_format", body.giver_request_format)
        if body.giver_request_retry_format is not None:
            await db.set_setting("giver_request_retry_format", body.giver_request_retry_format)
        if body.client_number_assigned_format is not None:
            await db.set_setting("client_number_assigned_format", body.client_number_assigned_format)
        
        if body.sms_cooldown_seconds is not None:
            await db.set_setting("sms_cooldown_seconds", body.sms_cooldown_seconds)
            set_cached_setting("sms_cooldown_seconds", body.sms_cooldown_seconds)

        if body.sleep_mode_enabled is not None:
            await db.set_setting("sleep_mode_enabled", body.sleep_mode_enabled)
            set_cached_setting("sleep_mode_enabled", body.sleep_mode_enabled)
        if body.sleep_mode_start is not None:
            await db.set_setting("sleep_mode_start", body.sleep_mode_start)
            set_cached_setting("sleep_mode_start", body.sleep_mode_start)
        if body.sleep_mode_end is not None:
            await db.set_setting("sleep_mode_end", body.sleep_mode_end)
            set_cached_setting("sleep_mode_end", body.sleep_mode_end)
        if body.sleep_mode_timezone is not None:
            await db.set_setting("sleep_mode_timezone", body.sleep_mode_timezone)
            set_cached_setting("sleep_mode_timezone", body.sleep_mode_timezone)
        if body.sleep_mode_reply is not None:
            await db.set_setting("sleep_mode_reply", body.sleep_mode_reply)
            set_cached_setting("sleep_mode_reply", body.sleep_mode_reply)

        if body.admin_id is not None:
            await db.set_setting("admin_id", body.admin_id)
            set_cached_setting("admin_id", body.admin_id)
        if body.anketa_chat_id is not None:
            await db.set_setting("anketa_chat_id", body.anketa_chat_id)
            set_cached_setting("anketa_chat_id", body.anketa_chat_id)
        if body.giver_chat_id is not None:
            await db.set_setting("giver_chat_id", body.giver_chat_id)
            set_cached_setting("giver_chat_id", body.giver_chat_id)
        if body.archive_group_id is not None:
            await db.set_setting("archive_group_id", body.archive_group_id)
            set_cached_setting("archive_group_id", body.archive_group_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")

@router.post("/api/settings/templates")
async def update_template_endpoint(body: BankTemplateUpdate):
    """Оновлення або додавання шаблону банку"""
    try:
        await db.save_bank_template(body.key, body.command, body.text, body.code_length or 4)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save bank template: {str(e)}")

@router.delete("/api/settings/templates/{key}")
async def delete_template_endpoint(key: str):
    """Видалення шаблону банку"""
    try:
        await db.delete_bank_template(key)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete bank template: {str(e)}")

