
import aiosqlite
from fastapi import APIRouter, HTTPException

import bot.database as db
from bot.config import DB_FILE
from web.models import *


router = APIRouter()

@router.get("/api/ai/rules")
async def get_ai_rules():
    """Отримання всіх правил ШІ"""
    try:
        rules = await db.get_all_ai_rules()
        return rules
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch rules: {e}")

@router.post("/api/ai/rules")
async def create_ai_rule(body: AIRuleCreate):
    """Створення нового правила ШІ"""
    try:
        rule_id = await db.add_ai_rule(body.rule_text, body.category, is_active=1)
        return {"status": "success", "id": rule_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create rule: {e}")

@router.put("/api/ai/rules/{rule_id}/toggle")
async def toggle_ai_rule_endpoint(rule_id: int):
    """Перемикання активності правила ШІ"""
    try:
        await db.toggle_ai_rule(rule_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle rule: {e}")

@router.delete("/api/ai/rules/{rule_id}")
async def delete_ai_rule_endpoint(rule_id: int):
    """Видалення правила ШІ"""
    try:
        await db.delete_ai_rule(rule_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete rule: {e}")

@router.get("/api/ai/examples")
async def get_ai_examples():
    """Отримання всіх few-shot прикладів"""
    try:
        examples = await db.get_all_ai_examples()
        return examples
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch examples: {e}")

@router.post("/api/ai/examples")
async def create_ai_example(body: AIExampleCreate):
    """Створення нового few-shot прикладу"""
    try:
        example_id = await db.add_ai_example(body.client_message, body.bot_response, is_active=1)
        return {"status": "success", "id": example_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create example: {e}")

@router.delete("/api/ai/examples/{example_id}")
async def delete_ai_example_endpoint(example_id: int):
    """Видалення few-shot прикладу"""
    try:
        await db.delete_ai_example(example_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete example: {e}")

@router.get("/api/ai/settings")
async def get_ai_settings():
    """Отримання поточних лімітів та паролів для ШІ"""
    try:
        income = await db.get_setting("ai_income_limit", "25000")
        turnover = await db.get_setting("ai_turnover_limit", "30000")
        password_kd = await db.get_setting("ai_password_kd", "12345")
        password_other = await db.get_setting("ai_password_other", "1111, 1234 або 1232")
        return {
            "ai_income_limit": income,
            "ai_turnover_limit": turnover,
            "ai_password_kd": password_kd,
            "ai_password_other": password_other
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch AI settings: {e}")

@router.post("/api/ai/settings")
async def update_ai_settings(body: AISettingsUpdate):
    """Оновлення лімітів та паролів для ШІ"""
    try:
        await db.set_setting("ai_income_limit", body.ai_income_limit)
        await db.set_setting("ai_turnover_limit", body.ai_turnover_limit)
        await db.set_setting("ai_password_kd", body.ai_password_kd)
        await db.set_setting("ai_password_other", body.ai_password_other)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update AI settings: {e}")

@router.get("/api/ai/learnable-chats")
async def get_learnable_chats():
    """Отримання списку сесій/клієнтів для вибору в інтерфейсі (і активні, і архівні)"""
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("""
                SELECT client_id, username, client_data, status
                FROM sessions
                ORDER BY created_at DESC
                LIMIT 50
            """) as cursor:
                rows = await cursor.fetchall()
                
        chats = []
        for row in rows:
            client_id = row["client_id"]
            username = row["username"] if row["username"] else f"ID: {client_id}"
            chats.append({
                "client_id": client_id,
                "username": username,
                "client_data": row["client_data"],
                "status": row["status"]
            })
        return chats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch learnable chats: {e}")

@router.post("/api/ai/learn")
async def trigger_ai_learn(body: AILearnRequest = None):
    """Аналіз останніх діалогів за участю адміна та автогенерація правил-чернеток"""
    from bot.openai_client import analyze_chat_and_propose_rule
    
    try:
        client_ids = []
        if body and body.client_ids:
            client_ids = body.client_ids
        else:
            # 1. Знаходимо клієнтів, у діалогах яких брав участь адмін (за замовчуванням останні 10)
            async with aiosqlite.connect(db.DB_FILE) as conn:
                async with conn.execute("""
                    SELECT DISTINCT client_id 
                    FROM chat_logs 
                    WHERE sender = 'admin' 
                    ORDER BY id DESC 
                    LIMIT 10
                """) as cursor:
                    client_ids = [row[0] for row in await cursor.fetchall()]
                
        if not client_ids:
            return {
                "status": "success", 
                "proposed_rules": [], 
                "message": "Не знайдено діалогів за участю адміністратора для аналізу."
            }
            
        proposed_rules = []
        
        # Отримуємо вже існуючі правила, щоб не створювати дублікати
        existing_rules_list = await db.get_all_ai_rules()
        existing_rules_texts = [r['rule_text'].lower().strip() for r in existing_rules_list]
        
        for c_id in client_ids:
            session = await db.get_session(c_id)
            username = session['username'] if session and session['username'] else f"Client {c_id}"
            
            logs = await db.get_chat_logs(c_id)
            if not logs:
                continue
                
            # Формуємо лог діалогу для аналізу
            chat_lines = []
            for log in logs:
                sender = log['sender'].capitalize()
                text = log['message_text'] or "[Скріншот/Фото]"
                chat_lines.append(f"{sender}: {text}")
                
            chat_history_text = "\n".join(chat_lines)
            
            # Запускаємо аналізатор
            proposed_rule_text = await analyze_chat_and_propose_rule(chat_history_text)
            
            if proposed_rule_text and proposed_rule_text.lower().strip() not in existing_rules_texts:
                if proposed_rule_text not in [r['rule_text'] for r in proposed_rules]:
                    # Зберігаємо в базу як вимкнену чернетку
                    rule_id = await db.add_ai_rule(
                        rule_text=proposed_rule_text, 
                        category='troubleshooting', 
                        is_active=0
                    )
                    proposed_rules.append({
                        "id": rule_id,
                        "rule_text": proposed_rule_text,
                        "category": "troubleshooting",
                        "is_active": 0,
                        "username": username
                    })
                    
        return {
            "status": "success",
            "proposed_rules": proposed_rules,
            "message": f"Проаналізовано {len(client_ids)} діалогів. Згенеровано {len(proposed_rules)} нових правил-чернеток."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run AI learning loop: {e}")

