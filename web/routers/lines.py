
import aiosqlite
from fastapi import APIRouter, HTTPException

import bot.database as db
from bot.config import DB_FILE
from web.models import *


router = APIRouter()

@router.get("/api/lines")
async def get_lines():
    """Отримання списку всіх телефонних ліній та їхніх статусів"""
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM lines ORDER BY line_id, bank") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

@router.post("/api/lines")
async def add_line(body: LineAdd):
    """Додавання нової лінії вручну"""
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            if body.line_id is not None and body.line_id > 0:
                line_id = body.line_id
            else:
                async with conn.execute("SELECT line_id FROM lines WHERE phone_number = ? LIMIT 1", (body.phone_number,)) as cursor:
                    existing = await cursor.fetchone()
                    if existing:
                        line_id = existing["line_id"]
                    else:
                        async with conn.execute("SELECT MAX(line_id) as max_id FROM lines") as max_cursor:
                            row = await max_cursor.fetchone()
                            max_id = row["max_id"] if row and row["max_id"] is not None else 0
                            line_id = max_id + 1
        
        await db.add_or_update_line(line_id, body.phone_number, body.bank)
        return {"status": "success"}
    except Exception as e:
        import sys
        sys.stderr.write(f"ERROR add_line: {e}\n")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/lines/clear")
async def clear_lines():
    """Очищення всіх ліній"""
    await db.clear_all_lines()
    return {"status": "success"}

@router.delete("/api/lines/{line_id}")
async def delete_line_endpoint(line_id: int):
    """Видалення лінії з бази даних"""
    await db.delete_line(line_id)
    return {"status": "success"}

