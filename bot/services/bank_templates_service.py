import aiosqlite
import bot.database as db_mod
from bot.config import normalize_bank_name, DEFAULT_BANK_ORDER

async def get_all_bank_templates() -> dict:
    """Отримання всіх шаблонів банків"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bank_templates") as cursor:
            rows = await cursor.fetchall()
            return {
                row['key']: {
                    'command': row['command'],
                    'text': row['text'],
                    'code_length': row['code_length'],
                    'logo_path': row['logo_path'] if 'logo_path' in row.keys() else None,
                    'screenshot_path': row['screenshot_path'] if 'screenshot_path' in row.keys() else None,
                    'download_screenshot_path': row['download_screenshot_path'] if 'download_screenshot_path' in row.keys() else None,
                    'success_screenshot_path': row['success_screenshot_path'] if 'success_screenshot_path' in row.keys() else None,
                    'report_template': row['report_template'] if ('report_template' in row.keys() and row['report_template']) else None,
                    'ai_rules': row['ai_rules'] if 'ai_rules' in row.keys() else None,
                    'required_screenshots': row['required_screenshots'] if 'required_screenshots' in row.keys() else 1,
                    'description': row['description'] if 'description' in row.keys() else row['key'],
                    'display_name': row['display_name'] if ('display_name' in row.keys() and row['display_name']) else row['key'],
                    'is_active': row['is_active'] if 'is_active' in row.keys() else 1,
                    'deletion_requirement': row['deletion_requirement'] if 'deletion_requirement' in row.keys() else 'none',
                    'deletion_screenshot_path': row['deletion_screenshot_path'] if 'deletion_screenshot_path' in row.keys() else None,
                    'instruction_text': row['instruction_text'] if 'instruction_text' in row.keys() else None,
                    'success_text': row['success_text'] if 'success_text' in row.keys() else None,
                    'deletion_text': row['deletion_text'] if 'deletion_text' in row.keys() else None,
                    'allow_relink': row['allow_relink'] if 'allow_relink' in row.keys() else 0,
                    'relink_instruction_text': row['relink_instruction_text'] if 'relink_instruction_text' in row.keys() else None
                } for row in rows
            }

async def save_bank_template(
    key: str,
    command: str,
    text: str,
    code_length: int = 4,
    logo_path: str = None,
    screenshot_path: str = None,
    download_screenshot_path: str = None,
    success_screenshot_path: str = None,
    report_template: str = None,
    ai_rules: str = None,
    required_screenshots: int = 1,
    description: str = None,
    display_name: str = None,
    deletion_requirement: str = 'none',
    deletion_screenshot_path: str = None,
    is_active: int = 1,
    clear_download_screenshot: bool = False,
    clear_success_screenshot: bool = False,
    clear_screenshots: bool = False,
    clear_logo: bool = False,
    clear_deletion_screenshot: bool = False,
    instruction_text: str = None,
    success_text: str = None,
    deletion_text: str = None,
    allow_relink: int = 0,
    relink_instruction_text: str = None
):
    """Збереження або оновлення шаблону банку"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("""
            INSERT INTO bank_templates (key, command, text, code_length, logo_path, screenshot_path, download_screenshot_path, success_screenshot_path, report_template, ai_rules, required_screenshots, description, display_name, is_active, deletion_requirement, deletion_screenshot_path, instruction_text, success_text, deletion_text, allow_relink, relink_instruction_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                command = excluded.command,
                text = excluded.text,
                code_length = excluded.code_length,
                logo_path = COALESCE(excluded.logo_path, bank_templates.logo_path),
                screenshot_path = COALESCE(excluded.screenshot_path, bank_templates.screenshot_path),
                download_screenshot_path = COALESCE(excluded.download_screenshot_path, bank_templates.download_screenshot_path),
                success_screenshot_path = COALESCE(excluded.success_screenshot_path, bank_templates.success_screenshot_path),
                report_template = excluded.report_template,
                ai_rules = excluded.ai_rules,
                required_screenshots = excluded.required_screenshots,
                description = COALESCE(excluded.description, bank_templates.description),
                display_name = excluded.display_name,
                is_active = excluded.is_active,
                deletion_requirement = excluded.deletion_requirement,
                deletion_screenshot_path = COALESCE(excluded.deletion_screenshot_path, bank_templates.deletion_screenshot_path),
                instruction_text = excluded.instruction_text,
                success_text = excluded.success_text,
                deletion_text = excluded.deletion_text,
                allow_relink = excluded.allow_relink,
                relink_instruction_text = excluded.relink_instruction_text
        """, (key, command, text, code_length, logo_path, screenshot_path, download_screenshot_path, success_screenshot_path, report_template, ai_rules, required_screenshots, description, display_name, is_active, deletion_requirement, deletion_screenshot_path, instruction_text, success_text, deletion_text, allow_relink, relink_instruction_text))
        
        if clear_logo:
            await db.execute("UPDATE bank_templates SET logo_path = NULL WHERE key = ?", (key,))
        if clear_screenshots:
            await db.execute("UPDATE bank_templates SET screenshot_path = NULL WHERE key = ?", (key,))
        if clear_download_screenshot:
            await db.execute("UPDATE bank_templates SET download_screenshot_path = NULL WHERE key = ?", (key,))
        if clear_success_screenshot:
            await db.execute("UPDATE bank_templates SET success_screenshot_path = NULL WHERE key = ?", (key,))
        if clear_deletion_screenshot:
            await db.execute("UPDATE bank_templates SET deletion_screenshot_path = NULL WHERE key = ?", (key,))
            
        await db.commit()

async def delete_bank_template(key: str):
    """Видалення шаблону банку"""
    async with aiosqlite.connect(db_mod.DB_FILE) as db:
        await db.execute("DELETE FROM bank_templates WHERE key = ?", (key,))
        await db.commit()

async def get_bank_template_db(bank_name: str):
    """Отримання шаблону за назвою банку (async версія)"""
    if not bank_name:
        return None
    templates = await get_all_bank_templates()
    name_norm = normalize_bank_name(bank_name)
    for key, val in templates.items():
        key_norm = normalize_bank_name(key)
        if key_norm == name_norm or key_norm in name_norm or name_norm in key_norm:
            return val
    return None

async def get_bank_template_with_key_db(bank_name: str):
    """Отримання шаблону та ключа за назвою банку (async версія)"""
    if not bank_name:
        return None, None
    templates = await get_all_bank_templates()
    name_norm = normalize_bank_name(bank_name)
    for key, val in templates.items():
        key_norm = normalize_bank_name(key)
        if key_norm == name_norm or key_norm in name_norm or name_norm in key_norm:
            return key, val
    return None, None

async def get_bank_display_name(bank_name: str) -> str:
    """Повертає зрозумілу назву банку для відображення (наприклад, AmoBank)"""
    if not bank_name:
        return "Невідомий банк"
    
    tpl = await get_bank_template_db(bank_name)
    if tpl and tpl.get('display_name'):
        return tpl['display_name']
    
    name_norm = normalize_bank_name(bank_name)
    mapping = {
        "izi": "IziBank",
        "amo": "AmoBank",
        "lviv": "LvivBank",
        "kd": "bank.kd",
        "alliance": "Alliance"
    }
    
    for key, val in mapping.items():
        if key == name_norm or key in name_norm or name_norm in key:
            return val
            
    return bank_name[0].upper() + bank_name[1:] if len(bank_name) > 0 else bank_name
