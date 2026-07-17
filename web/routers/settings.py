
import os
import shutil
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, File, UploadFile, Form

logger = logging.getLogger(__name__)

import bot.database as db
from bot.config import set_cached_setting
from web.models import *

router = APIRouter()

UPLOAD_LOGOS_DIR = os.path.join("web", "static", "images", "uploaded", "logos")
UPLOAD_INSTRUCTIONS_DIR = os.path.join("web", "static", "images", "uploaded", "instructions")

os.makedirs(UPLOAD_LOGOS_DIR, exist_ok=True)
os.makedirs(UPLOAD_INSTRUCTIONS_DIR, exist_ok=True)

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
async def update_template_endpoint(
    key: str = Form(...),
    command: str = Form(...),
    text: str = Form(...),
    code_length: int = Form(4),
    ai_rules: str = Form(""),
    report_template: str = Form(""),
    required_screenshots: int = Form(1),
    description: str = Form(""),
    display_name: str = Form(None),
    is_active: int = Form(1),
    logo_file: Optional[UploadFile] = File(None),
    screenshot_files: List[UploadFile] = File(default=[]),
    download_screenshot_file: Optional[UploadFile] = File(None),
    success_screenshot_file: Optional[UploadFile] = File(None),
    logo_removed: bool = Form(False),
    screenshots_removed: bool = Form(False),
    download_screenshot_removed: bool = Form(False),
    success_screenshot_removed: bool = Form(False)
):
    """Оновлення або додавання шаблону банку з файлами"""
    try:
        logger.info(f"update_template_endpoint key={key} logo_removed={logo_removed} screenshots_removed={screenshots_removed} download_screenshot_removed={download_screenshot_removed} success_screenshot_removed={success_screenshot_removed}")
        # Load existing template first to delete old files if they are being replaced or removed
        existing_template = await db.get_bank_template_db(key)
        
        def safe_delete_file(relative_path: str):
            if not relative_path:
                return
            try:
                abs_path = os.path.join("web", relative_path.lstrip("/"))
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except Exception as file_err:
                logger.error(f"Failed to delete file {relative_path}: {file_err}")

        # Handle removals
        clear_logo = False
        if logo_removed and existing_template:
            safe_delete_file(existing_template.get('logo_path'))
            clear_logo = True
            
        clear_screenshots = False
        if screenshots_removed and existing_template:
            old_paths_str = existing_template.get('screenshot_path')
            if old_paths_str:
                for p in old_paths_str.split(','):
                    safe_delete_file(p.strip())
            clear_screenshots = True
            
        clear_download_screenshot = False
        if download_screenshot_removed and existing_template:
            safe_delete_file(existing_template.get('download_screenshot_path'))
            clear_download_screenshot = True
            
        clear_success_screenshot = False
        if success_screenshot_removed and existing_template:
            safe_delete_file(existing_template.get('success_screenshot_path'))
            clear_success_screenshot = True

        logo_path = None
        if logo_file and logo_file.filename:
            # If replacing logo, delete old one first
            if existing_template and existing_template.get('logo_path'):
                safe_delete_file(existing_template.get('logo_path'))
            ext = os.path.splitext(logo_file.filename)[1] or ".png"
            filename = f"{key}{ext}"
            file_path = os.path.join(UPLOAD_LOGOS_DIR, filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(logo_file.file, buffer)
            logo_path = f"/static/images/uploaded/logos/{filename}"
            clear_logo = False
            
        screenshot_path = None
        # Handle multiple uploaded files
        valid_screenshot_files = [f for f in screenshot_files if f and f.filename]
        if valid_screenshot_files:
            # If replacing screenshots, delete old ones first
            if existing_template and existing_template.get('screenshot_path'):
                old_paths_str = existing_template.get('screenshot_path')
                if old_paths_str:
                    for p in old_paths_str.split(','):
                        safe_delete_file(p.strip())
            paths = []
            for i, f in enumerate(valid_screenshot_files):
                ext = os.path.splitext(f.filename)[1] or ".jpg"
                filename = f"{key}_step{i+1}{ext}"
                file_path = os.path.join(UPLOAD_INSTRUCTIONS_DIR, filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(f.file, buffer)
                paths.append(f"/static/images/uploaded/instructions/{filename}")
            screenshot_path = ",".join(paths)
            clear_screenshots = False

        download_screenshot_path = None
        if download_screenshot_file and download_screenshot_file.filename:
            # If replacing, delete old one first
            if existing_template and existing_template.get('download_screenshot_path'):
                safe_delete_file(existing_template.get('download_screenshot_path'))
            ext = os.path.splitext(download_screenshot_file.filename)[1] or ".jpg"
            filename = f"{key}_download{ext}"
            file_path = os.path.join(UPLOAD_INSTRUCTIONS_DIR, filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(download_screenshot_file.file, buffer)
            download_screenshot_path = f"/static/images/uploaded/instructions/{filename}"
            clear_download_screenshot = False

        success_screenshot_path = None
        if success_screenshot_file and success_screenshot_file.filename:
            # If replacing, delete old one first
            if existing_template and existing_template.get('success_screenshot_path'):
                safe_delete_file(existing_template.get('success_screenshot_path'))
            ext = os.path.splitext(success_screenshot_file.filename)[1] or ".jpg"
            filename = f"{key}_success{ext}"
            file_path = os.path.join(UPLOAD_INSTRUCTIONS_DIR, filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(success_screenshot_file.file, buffer)
            success_screenshot_path = f"/static/images/uploaded/instructions/{filename}"
            clear_success_screenshot = False
            
        await db.save_bank_template(
            key=key,
            command=command,
            text=text,
            code_length=code_length,
            logo_path=logo_path,
            screenshot_path=screenshot_path,
            download_screenshot_path=download_screenshot_path,
            success_screenshot_path=success_screenshot_path,
            report_template=report_template,
            ai_rules=ai_rules,
            required_screenshots=required_screenshots,
            description=description,
            display_name=display_name,
            is_active=is_active,
            clear_download_screenshot=clear_download_screenshot,
            clear_success_screenshot=clear_success_screenshot,
            clear_screenshots=clear_screenshots,
            clear_logo=clear_logo
        )
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

