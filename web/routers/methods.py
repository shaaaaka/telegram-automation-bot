import os
import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, File, UploadFile, HTTPException

import bot.database as db
from bot.services.verification_methods_service import (
    save_verification_method,
    get_verification_method,
    get_verification_methods,
    delete_verification_method,
    _norm_linked_bots,
    _parse_json_list,
)

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "methods"


def _allowed_file_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return ext if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"} else ""


def _avatar_db_path(key: str, ext: str) -> str:
    return f"/uploads/methods/{key}/avatar{ext}"


def _parse_optional_json_list(value: Optional[str]) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(v).strip() for v in parsed if str(v).strip()]
    except Exception:
        pass
    return [v.strip() for v in value.split(",") if v.strip()]


@router.get("/api/methods")
async def list_methods():
    """Список методів верифікації."""
    return await get_verification_methods()


@router.get("/api/methods/{key}")
async def read_method(key: str):
    """Один метод верифікації."""
    method = await get_verification_method(key)
    if not method:
        raise HTTPException(status_code=404, detail="Method not found")
    return method


@router.post("/api/methods")
async def create_method(
    key: str = Form(...),
    display_name: Optional[str] = Form(None),
    allowed_banks: Optional[str] = Form(None),
    linked_bots: Optional[str] = Form(None),
    required_client_fields: Optional[str] = Form(None),
    initial_message: Optional[str] = Form(None),
    is_active: int = Form(1),
    sort_order: int = Form(0),
    avatar: Optional[UploadFile] = File(None),
):
    """Створення методу верифікації."""
    if await get_verification_method(key):
        raise HTTPException(status_code=409, detail="Method with this key already exists")

    allowed_banks_list = _parse_optional_json_list(allowed_banks)
    linked_bots_list = _norm_linked_bots(linked_bots)
    required_fields_list = _parse_optional_json_list(required_client_fields)

    avatar_path = None
    if avatar and avatar.filename:
        ext = _allowed_file_ext(avatar.filename)
        if not ext:
            raise HTTPException(status_code=400, detail="Invalid avatar file type")
        method_dir = UPLOADS_DIR / key
        method_dir.mkdir(parents=True, exist_ok=True)
        dest_path = method_dir / f"avatar{ext}"
        with dest_path.open("wb") as f:
            shutil.copyfileobj(avatar.file, f)
        avatar_path = _avatar_db_path(key, ext)

    await save_verification_method(
        key=key,
        display_name=display_name,
        allowed_banks=allowed_banks_list,
        linked_bots=linked_bots_list,
        avatar_path=avatar_path,
        required_client_fields=required_fields_list,
        initial_message=initial_message,
        is_active=is_active,
        sort_order=sort_order,
    )

    return await get_verification_method(key)


@router.put("/api/methods/{key}")
async def update_method(
    key: str,
    display_name: Optional[str] = Form(None),
    allowed_banks: Optional[str] = Form(None),
    linked_bots: Optional[str] = Form(None),
    required_client_fields: Optional[str] = Form(None),
    initial_message: Optional[str] = Form(None),
    is_active: Optional[int] = Form(None),
    sort_order: Optional[int] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    removed: Optional[int] = Form(0),
):
    """Оновлення методу верифікації."""
    existing = await get_verification_method(key)
    if not existing:
        raise HTTPException(status_code=404, detail="Method not found")

    # Мерджимо поля
    new_display_name = display_name if display_name is not None else existing.get("display_name")
    new_allowed_banks = _parse_optional_json_list(allowed_banks) if allowed_banks is not None else existing.get("allowed_banks")
    new_linked_bots = _norm_linked_bots(linked_bots) if linked_bots is not None else existing.get("linked_bots")
    new_required_fields = _parse_optional_json_list(required_client_fields) if required_client_fields is not None else existing.get("required_client_fields")
    new_initial_message = initial_message if initial_message is not None else existing.get("initial_message")
    new_is_active = is_active if is_active is not None else int(existing.get("is_active", 1))
    new_sort_order = sort_order if sort_order is not None else existing.get("sort_order", 0)

    new_avatar_path = existing.get("avatar_path")
    if removed == 1:
        # Видаляємо старий аватар
        if new_avatar_path:
            old_abs = (UPLOADS_DIR / key / f"avatar{Path(new_avatar_path).suffix}").resolve()
            if old_abs.exists():
                try:
                    old_abs.unlink()
                except Exception as e:
                    logger.warning(f"Failed to remove old avatar: {e}")
        new_avatar_path = None
    elif avatar and avatar.filename:
        ext = _allowed_file_ext(avatar.filename)
        if not ext:
            raise HTTPException(status_code=400, detail="Invalid avatar file type")
        method_dir = UPLOADS_DIR / key
        method_dir.mkdir(parents=True, exist_ok=True)
        # Видаляємо старі аватари
        for f in method_dir.glob("avatar.*"):
            try:
                f.unlink()
            except Exception:
                pass
        dest_path = method_dir / f"avatar{ext}"
        with dest_path.open("wb") as f:
            shutil.copyfileobj(avatar.file, f)
        new_avatar_path = _avatar_db_path(key, ext)

    await save_verification_method(
        key=key,
        display_name=new_display_name,
        allowed_banks=new_allowed_banks,
        linked_bots=new_linked_bots,
        avatar_path=new_avatar_path,
        required_client_fields=new_required_fields,
        initial_message=new_initial_message,
        is_active=new_is_active,
        sort_order=new_sort_order,
    )

    return await get_verification_method(key)


@router.delete("/api/methods/{key}")
async def delete_method(key: str):
    """Видалення методу верифікації."""
    existing = await get_verification_method(key)
    if not existing:
        raise HTTPException(status_code=404, detail="Method not found")

    # Видаляємо аватар
    if existing.get("avatar_path"):
        old_abs = (UPLOADS_DIR / key).resolve()
        if old_abs.exists():
            try:
                shutil.rmtree(old_abs)
            except Exception as e:
                logger.warning(f"Failed to remove method avatar dir: {e}")

    await delete_verification_method(key)
    return {"status": "deleted"}
