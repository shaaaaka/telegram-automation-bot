
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
    deletion_requirement: str = Form("none"),
    logo_file: Optional[UploadFile] = File(None),
    screenshot_files: List[UploadFile] = File(default=[]),
    download_screenshot_files: List[UploadFile] = File(default=[]),
    success_screenshot_files: List[UploadFile] = File(default=[]),
    deletion_screenshot_files: List[UploadFile] = File(default=[]),
    download_screenshot_file: Optional[UploadFile] = File(None),
    success_screenshot_file: Optional[UploadFile] = File(None),
    deletion_screenshot_file: Optional[UploadFile] = File(None),
    logo_removed: str = Form("false"),
    screenshots_removed: str = Form("false"),
    download_screenshot_removed: str = Form("false"),
    success_screenshot_removed: str = Form("false"),
    deletion_screenshot_removed: str = Form("false"),
    instruction_text: Optional[str] = Form(None),
    success_text: Optional[str] = Form(None),
    deletion_text: Optional[str] = Form(None)
):
    """Оновлення або додавання шаблону банку з файлами"""
    try:
        # Convert to boolean manually to be 100% robust
        def is_removed(val) -> bool:
            if isinstance(val, bool):
                return val
            if not val:
                return False
            val_str = str(val).lower().strip()
            return val_str in ("true", "1", "yes")

        is_logo_removed = is_removed(logo_removed)
        is_screenshots_removed = is_removed(screenshots_removed)
        is_download_screenshot_removed = is_removed(download_screenshot_removed)
        is_success_screenshot_removed = is_removed(success_screenshot_removed)
        is_deletion_screenshot_removed = is_removed(deletion_screenshot_removed)

        # Write debug log
        try:
            debug_path = "debug_api.txt"
            with open(debug_path, "a", encoding="utf-8") as debug_file:
                debug_file.write(f"key={key}\n")
                debug_file.write(f"logo_removed={logo_removed} (parsed={is_logo_removed})\n")
                debug_file.write(f"screenshots_removed={screenshots_removed} (parsed={is_screenshots_removed})\n")
                debug_file.write(f"download_screenshot_removed={download_screenshot_removed} (parsed={is_download_screenshot_removed})\n")
                debug_file.write(f"success_screenshot_removed={success_screenshot_removed} (parsed={is_success_screenshot_removed})\n")
                debug_file.write(f"deletion_screenshot_removed={deletion_screenshot_removed} (parsed={is_deletion_screenshot_removed})\n")
                debug_file.write(f"download_screenshot_files count={len(download_screenshot_files)}\n")
                debug_file.write(f"success_screenshot_files count={len(success_screenshot_files)}\n")
                debug_file.write(f"screenshot_files count={len(screenshot_files)}\n")
                debug_file.write(f"deletion_screenshot_files count={len(deletion_screenshot_files)}\n")
                debug_file.write("-" * 40 + "\n")
        except Exception as debug_err:
            pass

        logger.info(f"update_template_endpoint key={key} logo_removed={is_logo_removed} screenshots_removed={is_screenshots_removed} download_screenshot_removed={is_download_screenshot_removed} success_screenshot_removed={is_success_screenshot_removed}")
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
        if is_logo_removed and existing_template:
            safe_delete_file(existing_template.get('logo_path'))
            clear_logo = True
            
        clear_screenshots = False
        if is_screenshots_removed and existing_template:
            old_paths_str = existing_template.get('screenshot_path')
            if old_paths_str:
                for p in old_paths_str.split(','):
                    safe_delete_file(p.strip())
            clear_screenshots = True
            
        clear_download_screenshot = False
        if is_download_screenshot_removed and existing_template:
            old_paths_str = existing_template.get('download_screenshot_path')
            if old_paths_str:
                for p in old_paths_str.split(','):
                    safe_delete_file(p.strip())
            clear_download_screenshot = True
            
        clear_success_screenshot = False
        if is_success_screenshot_removed and existing_template:
            old_paths_str = existing_template.get('success_screenshot_path')
            if old_paths_str:
                for p in old_paths_str.split(','):
                    safe_delete_file(p.strip())
            clear_success_screenshot = True

        clear_deletion_screenshot = False
        if is_deletion_screenshot_removed and existing_template:
            old_paths_str = existing_template.get('deletion_screenshot_path')
            if old_paths_str:
                for p in old_paths_str.split(','):
                    safe_delete_file(p.strip())
            clear_deletion_screenshot = True

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

        # Collect download files
        valid_download_files = [f for f in download_screenshot_files if f and f.filename]
        if download_screenshot_file and download_screenshot_file.filename:
            valid_download_files.append(download_screenshot_file)
            
        download_screenshot_path = None
        if valid_download_files:
            if existing_template and existing_template.get('download_screenshot_path'):
                old_paths_str = existing_template.get('download_screenshot_path')
                if old_paths_str:
                    for p in old_paths_str.split(','):
                        safe_delete_file(p.strip())
            paths = []
            for i, f in enumerate(valid_download_files):
                ext = os.path.splitext(f.filename)[1] or ".jpg"
                filename = f"{key}_download{i+1}{ext}"
                file_path = os.path.join(UPLOAD_INSTRUCTIONS_DIR, filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(f.file, buffer)
                paths.append(f"/static/images/uploaded/instructions/{filename}")
            download_screenshot_path = ",".join(paths)
            clear_download_screenshot = False

        # Collect success files
        valid_success_files = [f for f in success_screenshot_files if f and f.filename]
        if success_screenshot_file and success_screenshot_file.filename:
            valid_success_files.append(success_screenshot_file)
            
        success_screenshot_path = None
        if valid_success_files:
            if existing_template and existing_template.get('success_screenshot_path'):
                old_paths_str = existing_template.get('success_screenshot_path')
                if old_paths_str:
                    for p in old_paths_str.split(','):
                        safe_delete_file(p.strip())
            paths = []
            for i, f in enumerate(valid_success_files):
                ext = os.path.splitext(f.filename)[1] or ".jpg"
                filename = f"{key}_success{i+1}{ext}"
                file_path = os.path.join(UPLOAD_INSTRUCTIONS_DIR, filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(f.file, buffer)
                paths.append(f"/static/images/uploaded/instructions/{filename}")
            success_screenshot_path = ",".join(paths)
            clear_success_screenshot = False
            
        # Collect deletion files
        valid_deletion_files = [f for f in deletion_screenshot_files if f and f.filename]
        if deletion_screenshot_file and deletion_screenshot_file.filename:
            valid_deletion_files.append(deletion_screenshot_file)
            
        deletion_screenshot_path = None
        if valid_deletion_files:
            if existing_template and existing_template.get('deletion_screenshot_path'):
                old_paths_str = existing_template.get('deletion_screenshot_path')
                if old_paths_str:
                    for p in old_paths_str.split(','):
                        safe_delete_file(p.strip())
            paths = []
            for i, f in enumerate(valid_deletion_files):
                ext = os.path.splitext(f.filename)[1] or ".jpg"
                filename = f"{key}_deletion{i+1}{ext}"
                file_path = os.path.join(UPLOAD_INSTRUCTIONS_DIR, filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(f.file, buffer)
                paths.append(f"/static/images/uploaded/instructions/{filename}")
            deletion_screenshot_path = ",".join(paths)
            clear_deletion_screenshot = False
            
        await db.save_bank_template(
            key=key,
            command=command,
            text=text,
            code_length=code_length,
            logo_path=logo_path,
            screenshot_path=screenshot_path,
            download_screenshot_path=download_screenshot_path,
            success_screenshot_path=success_screenshot_path,
            deletion_requirement=deletion_requirement,
            deletion_screenshot_path=deletion_screenshot_path,
            report_template=report_template,
            ai_rules=ai_rules,
            required_screenshots=required_screenshots,
            description=description,
            display_name=display_name,
            is_active=is_active,
            clear_download_screenshot=clear_download_screenshot,
            clear_success_screenshot=clear_success_screenshot,
            clear_screenshots=clear_screenshots,
            clear_logo=clear_logo,
            clear_deletion_screenshot=clear_deletion_screenshot,
            instruction_text=instruction_text,
            success_text=success_text,
            deletion_text=deletion_text
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

@router.get("/api/settings/ai")
async def get_ai_settings():
    """Отримання налаштувань ШІ, списку правил та прикладів діалогу"""
    try:
        # Отримуємо базові ліміти
        income = await db.get_setting("ai_income_limit", "25000")
        turnover = await db.get_setting("ai_turnover_limit", "30000")
        pwd_kd = await db.get_setting("ai_password_kd", "12345")
        pwd_other = await db.get_setting("ai_password_other", "1111, 1234 або 1232")
        
        # Отримуємо правила та приклади
        rules = await db.get_all_ai_rules()
        examples = await db.get_all_ai_examples()
        
        return {
            "ai_income_limit": income,
            "ai_turnover_limit": turnover,
            "ai_password_kd": pwd_kd,
            "ai_password_other": pwd_other,
            "rules": rules,
            "examples": examples
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get AI settings: {str(e)}")

@router.post("/api/settings/ai")
async def save_ai_settings_endpoint(body: AISettingsUpdate):
    """Збереження базових лімітів та паролів ШІ"""
    try:
        await db.set_setting("ai_income_limit", body.ai_income_limit)
        await db.set_setting("ai_turnover_limit", body.ai_turnover_limit)
        await db.set_setting("ai_password_kd", body.ai_password_kd)
        await db.set_setting("ai_password_other", body.ai_password_other)
        
        # Оновимо кеш налаштувань
        set_cached_setting("ai_income_limit", body.ai_income_limit)
        set_cached_setting("ai_turnover_limit", body.ai_turnover_limit)
        set_cached_setting("ai_password_kd", body.ai_password_kd)
        set_cached_setting("ai_password_other", body.ai_password_other)
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save AI settings: {str(e)}")

@router.post("/api/settings/ai/rules")
async def create_ai_rule(body: AIRuleCreate):
    """Додавання нового правила ШІ"""
    try:
        rule_id = await db.add_ai_rule(body.rule_text, body.category, body.is_active)
        return {"status": "success", "id": rule_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add AI rule: {str(e)}")

@router.put("/api/settings/ai/rules/{rule_id}")
async def update_ai_rule_endpoint(rule_id: int, body: AIRuleCreate):
    """Оновлення існуючого правила ШІ"""
    try:
        await db.update_ai_rule(rule_id, body.rule_text, body.category, body.is_active)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update AI rule: {str(e)}")

@router.post("/api/settings/ai/rules/{rule_id}/toggle")
async def toggle_ai_rule_endpoint(rule_id: int, is_active: Optional[int] = None):
    """Перемикання активності правила ШІ"""
    try:
        await db.toggle_ai_rule(rule_id, is_active)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle AI rule: {str(e)}")

@router.delete("/api/settings/ai/rules/{rule_id}")
async def delete_ai_rule_endpoint(rule_id: int):
    """Видалення правила ШІ"""
    try:
        await db.delete_ai_rule(rule_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete AI rule: {str(e)}")

@router.post("/api/settings/ai/examples")
async def create_ai_example(body: AIExampleCreate):
    """Додавання нового прикладу діалогу ШІ"""
    try:
        example_id = await db.add_ai_example(body.client_message, body.bot_response, body.is_active)
        return {"status": "success", "id": example_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add AI example: {str(e)}")

@router.put("/api/settings/ai/examples/{example_id}")
async def update_ai_example_endpoint(example_id: int, body: AIExampleCreate):
    """Оновлення існуючого прикладу діалогу ШІ"""
    try:
        await db.update_ai_example(example_id, body.client_message, body.bot_response, body.is_active)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update AI example: {str(e)}")

@router.post("/api/settings/ai/examples/{example_id}/toggle")
async def toggle_ai_example_endpoint(example_id: int, is_active: Optional[int] = None):
    """Перемикання активності прикладу діалогу ШІ"""
    try:
        await db.toggle_ai_example(example_id, is_active)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle AI example: {str(e)}")

@router.delete("/api/settings/ai/examples/{example_id}")
async def delete_ai_example_endpoint(example_id: int):
    """Видалення прикладу діалогу ШІ"""
    try:
        await db.delete_ai_example(example_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete AI example: {str(e)}")

