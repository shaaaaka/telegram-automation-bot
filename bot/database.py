import aiosqlite
import contextvars
import asyncio
import logging
from bot.config import DB_FILE, DEFAULT_BANK_ORDER, normalize_bank_name

from bot.services.chat_log_service import (
    current_sender,
    chat_message_callbacks,
    active_subscriptions,
    log_verification_start,
    log_verification_end,
    get_client_verification_history,
    get_statistics,
    clear_statistics,
    log_chat_message,
    get_chat_logs,
    clear_chat_logs,
)


async def init_db():
    """Ініціалізація бази даних та створення таблиць"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Налаштування SQLite для паралельної роботи в SaaS (WAL-режим)
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")

        # Перевірка наявності та формату таблиці lines
        table_exists = False
        has_line_id = False
        try:
            async with db.execute("PRAGMA table_info(lines)") as cursor:
                columns = await cursor.fetchall()
                if columns:
                    table_exists = True
                    for col in columns:
                        if col[1] == 'line_id':
                            has_line_id = True
                            break
        except Exception:
            pass

        if table_exists and not has_line_id:
            # Міграція старої таблиці
            await db.execute("ALTER TABLE lines RENAME TO lines_old")
            await db.execute("""
                CREATE TABLE lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    line_id INTEGER NOT NULL,
                    phone_number TEXT NOT NULL,
                    bank TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available',
                    UNIQUE(line_id, bank)
                )
            """)
            await db.execute("""
                INSERT INTO lines (id, line_id, phone_number, bank, status)
                SELECT id, id, phone_number, bank, status FROM lines_old
            """)
            await db.execute("DROP TABLE lines_old")
            await db.commit()
        elif not table_exists:
            # Створення з нуля
            await db.execute("""
                CREATE TABLE lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    line_id INTEGER NOT NULL,
                    phone_number TEXT NOT NULL,
                    bank TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available',
                    UNIQUE(line_id, bank)
                )
            """)
            await db.commit()
        
        # Перевіряємо та додаємо унікальне обмеження на (line_id, bank) якщо його немає
        # Отримуємо унікальні індекси таблиці lines
        unique_indexes = []
        async with db.execute("PRAGMA index_list(lines)") as cursor:
            async for idx in cursor:
                if idx[2] == 1:  # Прапорець унікальності (unique)
                    unique_indexes.append(idx[1])
        
        # Перевіряємо, чи є унікальний індекс на (line_id, bank)
        has_unique_constraint = False
        for idx_name in unique_indexes:
            async with db.execute(f"PRAGMA index_info({idx_name})") as idx_cursor:
                columns = []
                async for col in idx_cursor:
                    columns.append(col[2])  # Назва стовпця
                if len(columns) == 2 and 'line_id' in columns and 'bank' in columns:
                    has_unique_constraint = True
                    break
        
        if not has_unique_constraint:
            try:
                await db.execute("CREATE UNIQUE INDEX idx_lines_line_bank ON lines(line_id, bank)")
                logging.info("Додано унікальний індекс на (line_id, bank) для таблиці lines")
            except Exception as e:
                logging.error(f"Помилка при додаванні унікального індексу: {e}")
        
        # Таблиця для збереження активних сесій верифікації
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                client_id INTEGER PRIMARY KEY,
                username TEXT,
                client_data TEXT NOT NULL,
                line_id INTEGER REFERENCES lines(id),
                client_message_id INTEGER,
                selected_banks TEXT,  -- Список обраних банків (через кому)
                remaining_banks TEXT, -- Список банків, які залишилося пройти (через кому)
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_at TIMESTAMP,
                last_reminder_sent_at TIMESTAMP
            )
        """)
        
        # Отримуємо існуючі колонки таблиці sessions
        sessions_columns = set()
        async with db.execute("PRAGMA table_info(sessions)") as cursor:
            async for col in cursor:
                sessions_columns.add(col[1])

        new_columns = [
            ("assigned_at", "TIMESTAMP"),
            ("last_reminder_sent_at", "TIMESTAMP"),
            ("success_photo_id", "TEXT"),
            ("card_first4", "TEXT"),
            ("card_last4", "TEXT"),
            ("card_photo_id", "TEXT"),
            ("waiting_message_id", "INTEGER"),
            ("instruction_message_id", "INTEGER"),
            ("client_phone", "TEXT"),
            ("bank", "TEXT"),
            ("sent_codes_count", "INTEGER DEFAULT 0"),
            ("is_paused", "INTEGER DEFAULT 0"),
            ("verifier_message_id", "INTEGER"),
            ("is_verified", "INTEGER DEFAULT 0"),
            ("waiting_proceedings", "INTEGER DEFAULT 0"),
            ("proceedings_question_msg_id", "INTEGER"),
            ("notified_banks", "TEXT DEFAULT ''")
        ]
        
        for col_name, col_type in new_columns:
            if col_name not in sessions_columns:
                try:
                    await db.execute(f"ALTER TABLE sessions ADD COLUMN {col_name} {col_type}")
                    logging.info(f"Додано нову колонку '{col_name}' ({col_type}) до таблиці sessions")
                except Exception as e:
                    logging.error(f"Помилка при додаванні колонки '{col_name}': {e}")
                    raise

        # Таблиця для логування статистики верифікацій
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bank_verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                username TEXT,
                bank TEXT,
                phone_number TEXT,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT, -- 'success', 'banned', 'released', 'pending'
                duration_seconds INTEGER
            )
        """)

        # Таблиця для загальних налаштувань
        await db.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Таблиця для шаблонів завантаження банків
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bank_templates (
                key TEXT PRIMARY KEY,
                command TEXT,
                text TEXT,
                code_length INTEGER DEFAULT 4,
                logo_path TEXT,
                screenshot_path TEXT,
                download_screenshot_path TEXT,
                success_screenshot_path TEXT,
                report_template TEXT,
                ai_rules TEXT,
                required_screenshots INTEGER DEFAULT 1,
                description TEXT,
                instruction_text TEXT,
                success_text TEXT,
                deletion_text TEXT
            )
        """)
        for col, col_def in [
            ("code_length", "INTEGER DEFAULT 4"),
            ("logo_path", "TEXT"),
            ("screenshot_path", "TEXT"),
            ("download_screenshot_path", "TEXT"),
            ("success_screenshot_path", "TEXT"),
            ("report_template", "TEXT"),
            ("ai_rules", "TEXT"),
            ("required_screenshots", "INTEGER DEFAULT 1"),
            ("description", "TEXT"),
            ("display_name", "TEXT"),
            ("is_active", "INTEGER DEFAULT 1"),
            ("deletion_requirement", "TEXT DEFAULT 'none'"),
            ("deletion_screenshot_path", "TEXT"),
            ("instruction_text", "TEXT"),
            ("success_text", "TEXT"),
            ("deletion_text", "TEXT"),
            ("allow_relink", "INTEGER DEFAULT 0"),
            ("relink_instruction_text", "TEXT")
        ]:
            try:
                await db.execute(f"ALTER TABLE bank_templates ADD COLUMN {col} {col_def}")
            except Exception:
                pass
        
        # Таблиця для збереження історії чату з дропом
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                sender TEXT NOT NULL,
                message_text TEXT,
                photo_id TEXT,
                message_id INTEGER,
                reply_to_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            await db.execute("ALTER TABLE chat_logs ADD COLUMN message_id INTEGER;")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE chat_logs ADD COLUMN reply_to_message_id INTEGER;")
        except Exception:
            pass
        
        # Таблиця для додаткових інструкцій / правил ШІ
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_text TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблиця для прикладів діалогів ШІ (Few-Shot Examples)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_examples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_message TEXT NOT NULL,
                bot_response TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблиця для заблокованих користувачів
        await db.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                client_id INTEGER PRIMARY KEY,
                username TEXT,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблиця для обліку токенів ШІ
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_usage (
                date TEXT PRIMARY KEY,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                requests INTEGER DEFAULT 0
            )
        """)

        # Таблиця для детермінованих fallback-правил (Regex matcher)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_fallback_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL,
                bank_name TEXT,
                response_text TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Таблиця для pHash кешування скріншотів ШІ
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_image_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_hash TEXT NOT NULL,
                bank_name TEXT,
                task TEXT NOT NULL,
                result_text TEXT,
                is_valid INTEGER,
                reason TEXT,
                extracted_data TEXT,
                prompt_version TEXT DEFAULT '1',
                source_size INTEGER DEFAULT 0,
                hit_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_hit_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(image_hash, bank_name, task, prompt_version)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ai_image_cache_lookup ON ai_image_cache(task, bank_name, prompt_version)")
        
        # Заповнюємо налаштування за замовчуванням
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('reminder_delay_minutes', '5')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('reminder_text', 'Ви отримали номер телефону для реєстрації. Будь ласка, введіть його в додатку, щоб ми могли надіслати вам код. Якщо виникли труднощі — напишіть нам!')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('giver_request_format', 'Запрос {line_id} {bank_name}')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('giver_request_retry_format', 'Запрос {line_id} {bank_name} (ПОВТОРНО)')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('client_number_assigned_format', 'Банк: *{bank_name}*\nНомер телефону:\n\n`+{phone_number}`\n\nКоли надішлете SMS і вам знадобиться код, тисніть кнопку нижче.')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('sleep_mode_enabled', '0')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('sleep_mode_start', '22:00')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('sleep_mode_end', '08:00')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('sleep_mode_timezone', 'Europe/Kyiv')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('sleep_mode_reply', 'На жаль, зараз не робочий час. Поверніться пізніше.')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('ai_daily_token_limit', '1000000')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('ai_image_cache_enabled', '1')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('ai_image_cache_threshold', '4')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('ai_image_cache_prompt_version', '1')")
        await db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('ai_image_cache_ttl_days', '30')")

        # Заповнюємо базові fallback-правила за замовчуванням
        async with db.execute("SELECT COUNT(*) FROM ai_fallback_rules") as cursor:
            count_row = await cursor.fetchone()
            if count_row and count_row[0] == 0:
                default_fallbacks = [
                    (r'який (пін|пінкод|пароль)', None, "Вказуйте будь-який зручний пін-код, головне запам'ятати його.", 10),
                    (r'(що таке|де взяти) (іпн|рнокпп)', None, "ІПН (РНОКПП) — це ваш 10-значний податковий номер, його можна знайти в додатку Дія або довідці.", 10),
                    (r'код (підійшов|ввів|є|прийшов)', None, "Чудово! Продовжуйте наступні кроки за інструкцією.", 10),
                    (r'не можу зробити скрін', None, "Якщо додаток блокує скріншот, зробіть фото екрана іншим телефоном.", 10),
                    (r'(навіщо|для чого) (телефон|номер)', None, "Номер телефону потрібен для реєстрації облікового запису в банку.", 10)
                ]
                await db.executemany(
                    "INSERT INTO ai_fallback_rules (pattern, bank_name, response_text, priority, is_active) VALUES (?, ?, ?, ?, 1)",
                    default_fallbacks
                )

        # Заповнюємо базові правила ШІ за замовчуванням
        async with db.execute("SELECT COUNT(*) FROM ai_rules") as cursor:
            count_row = await cursor.fetchone()
            if count_row and count_row[0] == 0:
                default_rules = [
                    ("Звертатися до клієнта виключно на 'ви', але з маленької літери (ви, вам, вас).", "general"),
                    ("ПІБ — це Прізвище, Ім'я, По батькові. Наприклад: Шевченко Тарас Григорович.", "general"),
                    ("ІПН (індивідуальний податковий номер) — це також РНОКПП (10 цифр), його можна швидко знайти та скопіювати в додатку Дія або знайти на паперовій довідці.", "general"),
                    ("Для bank.kd пропонуйте ставити легкий 5-значний пін, наприклад 12345", "bank_rules"),
                    ("Для інших банків пропонуйте легкі пін-коди, наприклад 1111 або 1234", "bank_rules"),
                    ("Якщо зависла Дія або банківський додаток, порадьте повністю закрити додаток, вивантажити з фону і зайти знову за 15 секунд.", "troubleshooting"),
                    ("Якщо не приходить SMS-код, попросіть зачекати 1-2 хвилини або надіслати повторно.", "troubleshooting"),
                    ("Якщо клієнт запитує про гроші, виплати, реферальні програми тощо — ніколи не вигадуйте цифри. Пишіть коротко: 'Щодо виплат — це до менеджера, зараз підключиться. Наша задача — закінчити верифікацію банку.'", "limits"),
                    ("Пристрій не підтримується / root-права: пояснити, що додаток блокує система безпеки.", "troubleshooting"),
                    ("Помилки геолокації / VPN: нагадати вимкнути VPN та увімкнути GPS (це критично для банків України).", "troubleshooting"),
                    ("Збій Дія-шерингу: порадити оновити Дію в Play Market / App Store.", "troubleshooting")
                ]
                await db.executemany("INSERT INTO ai_rules (rule_text, category, is_active) VALUES (?, ?, 1)", default_rules)

        # Заповнюємо базові приклади few-shot за замовчуванням
        async with db.execute("SELECT COUNT(*) FROM ai_examples") as cursor:
            count_row = await cursor.fetchone()
            if count_row and count_row[0] == 0:
                default_examples = [
                    ("Ой, а що писати в графі роботи?", "Пишіть, що тимчасово не працюєте, або фрілансер. Все ок."),
                    ("Дія не підписує, кручу головою і нічого", "Спробуйте протерти фронталку і підійти до вікна, там світло вирішує."),
                    ("А скільки платять за верифікацію?", "Щодо виплат — це до менеджера, зараз підключиться. Наша задача — закінчити верифікацію банку."),
                    ("Що це за ІПН?", "Це індивідуальний податковий номер (або РНОКПП). Його можна швидко знайти та скопіювати в додатку Дія (він там підписаний як РНОКПП або ІПН), або знайти на паперовій довідці платника податків."),
                    ("що це", "Це індивідуальний податковий номер (або РНОКПП). Його можна швидко знайти та скопіювати в додатку Дія (він там підписаний як РНОКПП або ІПН), або знайти на паперовій довідці платника податків.")
                ]
                await db.executemany("INSERT INTO ai_examples (client_message, bot_response, is_active) VALUES (?, ?, 1)", default_examples)

        # Синхронізуємо стандартні шаблони банків з конфігом
        from bot.config import BANK_TEMPLATES
        if BANK_TEMPLATES:
            await db.execute("UPDATE bank_templates SET code_length = 4 WHERE key = 'amobank' AND code_length = 6")
            await db.execute("UPDATE bank_templates SET code_length = 6 WHERE key = 'lvivbank' AND code_length = 4")
            await db.execute("UPDATE bank_templates SET code_length = 6 WHERE key = 'bank.kd' AND code_length = 5")

            for key, val in BANK_TEMPLATES.items():
                await db.execute(
                    "INSERT OR IGNORE INTO bank_templates (key, command, text, code_length) VALUES (?, ?, ?, ?)",
                    (key, val['command'], val['text'], val.get('code_length', 4))
                )

        await db.commit()



# --- Робота з лініями (Lines) ---

from bot.services.lines_service import (
    add_or_update_line,
    get_all_lines,
    get_available_lines,
    get_line,
    set_line_status,
    get_unique_banks,
    clear_all_lines,
    delete_line,
    get_max_line_id,
)

# --- Робота з сесіями клієнтів (Sessions) ---

from bot.services.sessions_service import (
    increment_session_sent_codes_count,
    create_registering_session,
    create_or_update_session,
    update_session_verification_data,
    get_session,
    update_session_verifier_message_id,
    set_session_verified,
    get_session_by_verifier_message_id,
    get_session_by_proceedings_question_message_id,
    set_session_waiting_proceedings,
    set_session_proceedings_question_msg_id,
    get_latest_waiting_verification_session,
    get_active_session_by_line,
    get_all_waiting_sessions,
    assign_line_to_session,
    update_session_message_id,
    update_session_waiting_message_id,
    update_session_instruction_message_id,
    update_session_client_phone,
    update_session_banks,
    set_session_status,
    complete_current_bank,
    send_archive_report,
    close_session,
    unassign_line_from_session,
    add_notified_bank,
    delete_session_completely,
)

# --- Налаштування (Settings) ---


from bot.services.settings_service import (
    get_setting,
    set_setting,
    get_all_settings,
)

# --- Шаблони банків (Bank Templates) ---

from bot.services.bank_templates_service import (
    get_all_bank_templates,
    save_bank_template,
    delete_bank_template,
    get_bank_template_db,
    get_bank_template_with_key_db,
    get_bank_display_name,
)

# --- Керування правилами та прикладами ШІ (AI Rules & Examples Management) ---



from bot.services.ai_rules_service import (
    get_all_ai_rules,
    get_active_ai_rules,
    add_ai_rule,
    toggle_ai_rule,
    delete_ai_rule,
    update_ai_rule,
    get_all_ai_examples,
    get_active_ai_examples,
    add_ai_example,
    delete_ai_example,
    update_ai_example,
    toggle_ai_example,
)

# --- Блокування користувачів (Ban System) ---

from bot.services.ban_service import ban_user, unban_user, is_user_banned, get_banned_users










