import aiosqlite
import contextvars
import asyncio
import logging
from bot.config import DB_FILE, DEFAULT_BANK_ORDER

current_sender = contextvars.ContextVar("current_sender", default="bot")
chat_message_callbacks = []
active_subscriptions = {}

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
                description TEXT
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
            ("is_active", "INTEGER DEFAULT 1")
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
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
            # Оновлюємо некоректні довжини за замовчуванням
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

async def add_or_update_line(line_id: int, phone_number: str, bank: str):
    """Додавання нової або оновлення існуючої лінії"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO lines (line_id, phone_number, bank, status)
            VALUES (?, ?, ?, 'available')
            ON CONFLICT(line_id, bank) DO UPDATE SET
                phone_number = excluded.phone_number,
                status = 'available'
        """, (line_id, phone_number, bank))
        await db.commit()

async def get_available_lines():
    """Отримання всіх вільних ліній"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM lines WHERE status = 'available'") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_line(line_id: int):
    """Отримання інформації про конкретну лінію"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM lines WHERE id = ?", (line_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def set_line_status(line_id: int, status: str):
    """Зміна статусу лінії ('available', 'busy')"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE lines SET status = ? WHERE id = ?", (status, line_id))
        await db.commit()

async def get_unique_banks():
    """Отримання списку всіх унікальних назв банків, що є в базі ліній"""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT DISTINCT bank FROM lines") as cursor:
            rows = await cursor.fetchall()
            banks = [row[0] for row in rows if row[0] and row[0].lower() not in ('ecobank', 'pumb')]
            
            # Сортування за послідовністю користувача
            def get_sort_key(bank):
                try:
                    return DEFAULT_BANK_ORDER.index(bank)
                except ValueError:
                    # Регістронезалежне співпадіння
                    for i, item in enumerate(DEFAULT_BANK_ORDER):
                        if item.lower() == bank.lower():
                            return i
                    return len(DEFAULT_BANK_ORDER)  # Всі інші в кінець
            
            return sorted(banks, key=get_sort_key)

async def clear_all_lines():
    """Видалення всіх ліній із бази даних"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM lines")
        await db.commit()

async def delete_line(line_id: int):
    """Видалення лінії за її ID"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM lines WHERE id = ?", (line_id,))
        await db.commit()


# --- Робота з сесіями клієнтів (Sessions) ---


async def increment_session_sent_codes_count(client_id: int):
    """Збільшує лічильник відправлених кодів для сесії клієнта на 1"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            UPDATE sessions 
            SET sent_codes_count = COALESCE(sent_codes_count, 0) + 1 
            WHERE client_id = ?
        """, (client_id,))
        await db.commit()

async def create_registering_session(client_id: int, username: str):
    """Створення сесії в статусі заповнення анкети (для відображення на сайті)"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO sessions (client_id, username, client_data, status, client_message_id, selected_banks, remaining_banks, success_photo_id, card_first4, card_last4, card_photo_id, sent_codes_count)
            VALUES (?, ?, '📝 Заповнює реєстраційні дані...', 'registering', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0)
            ON CONFLICT(client_id) DO UPDATE SET
                username = excluded.username,
                client_data = excluded.client_data,
                line_id = NULL,
                client_message_id = NULL,
                selected_banks = NULL,
                remaining_banks = NULL,
                status = 'registering',
                created_at = CURRENT_TIMESTAMP,
                success_photo_id = NULL,
                card_first4 = NULL,
                card_last4 = NULL,
                card_photo_id = NULL,
                sent_codes_count = 0,
                is_verified = 0,
                verifier_message_id = NULL,
                notified_banks = ''
        """, (client_id, username))
        await db.commit()

async def create_or_update_session(client_id: int, username: str, client_data: str):
    """Створення нової сесії для клієнта (коли він надсилає свої дані)"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO sessions (client_id, username, client_data, status, client_message_id, selected_banks, remaining_banks, success_photo_id, card_first4, card_last4, card_photo_id, sent_codes_count)
            VALUES (?, ?, ?, 'registered', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0)
            ON CONFLICT(client_id) DO UPDATE SET
                username = excluded.username,
                client_data = excluded.client_data,
                line_id = NULL,
                client_message_id = NULL,
                selected_banks = NULL,
                remaining_banks = NULL,
                status = 'registered',
                created_at = CURRENT_TIMESTAMP,
                success_photo_id = NULL,
                card_first4 = NULL,
                card_last4 = NULL,
                card_photo_id = NULL,
                sent_codes_count = 0,
                is_verified = 0,
                verifier_message_id = NULL,
                notified_banks = ''
        """, (client_id, username, client_data))
        await db.commit()

async def update_session_verification_data(client_id: int, success_photo_id: str = None, card_first4: str = None, card_last4: str = None, card_photo_id: str = None):
    """Оновлення фото та маски картки верифікації в сесії"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            UPDATE sessions 
            SET success_photo_id = COALESCE(?, success_photo_id),
                card_first4 = COALESCE(?, card_first4),
                card_last4 = COALESCE(?, card_last4),
                card_photo_id = COALESCE(?, card_photo_id)
            WHERE client_id = ?
        """, (success_photo_id, card_first4, card_last4, card_photo_id, client_id))
        await db.commit()

async def get_session(client_id: int):
    """Отримання активної сесії клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_session_verifier_message_id(client_id: int, message_id: int):
    """Оновлення ID повідомлення верифікатора в сесії"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET verifier_message_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def set_session_verified(client_id: int, is_verified: int = 1):
    """Встановлення прапорця верифікації для сесії"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET is_verified = ? WHERE client_id = ?", (is_verified, client_id))
        await db.commit()

async def get_session_by_verifier_message_id(message_id: int):
    """Отримання сесії за ID повідомлення верифікатора"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE verifier_message_id = ?", (message_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_session_by_proceedings_question_message_id(message_id: int):
    """Отримання сесії за ID повідомлення запитання про провадження"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE proceedings_question_msg_id = ?", (message_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def set_session_waiting_proceedings(client_id: int, waiting: int):
    """Встановлення прапорця очікування проваджень для сесії"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET waiting_proceedings = ? WHERE client_id = ?", (waiting, client_id))
        await db.commit()

async def set_session_proceedings_question_msg_id(client_id: int, message_id: int):
    """Встановлення ID повідомлення запитання про провадження"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET proceedings_question_msg_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def get_latest_waiting_verification_session():
    """Отримання останньої сесії, яка чекає перевірки"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE status = 'waiting_verification' ORDER BY created_at DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_active_session_by_line(line_id: int):
    """Пошук активної сесії за номером лінії"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE line_id = ? AND status != 'completed'", (line_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_all_waiting_sessions():
    """Отримання всіх сесій, які зараз чекають на код"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE status = 'waiting_code'") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def assign_line_to_session(client_id: int, line_id: int):
    """Призначення лінії для клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        # Відкриваємо транзакцію з негайним блокуванням запису для уникнення race condition
        await db.execute("BEGIN IMMEDIATE")
        
        # Отримуємо попередньо призначену лінію (якщо вона є), старий банк та список сповіщених банків
        old_bank = None
        notified_banks_str = ""
        async with db.execute("SELECT line_id, bank, notified_banks FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                old_bank = row['bank']
                notified_banks_str = row['notified_banks'] or ""
                if row['line_id'] and row['line_id'] != line_id:
                    await db.execute("UPDATE lines SET status = 'available' WHERE id = ?", (row['line_id'],))

        # Отримуємо назву банку лінії
        bank_name = None
        async with db.execute("SELECT bank FROM lines WHERE id = ?", (line_id,)) as cursor:
            l_row = await cursor.fetchone()
            if l_row:
                bank_name = l_row['bank']

        # Якщо банк змінився, видаляємо новий банк зі списку сповіщених банків (notified_banks)
        if bank_name and old_bank != bank_name:
            notified_list = [b.strip() for b in notified_banks_str.split(",") if b.strip()]
            if bank_name in notified_list:
                notified_list.remove(bank_name)
            new_notified_banks = ",".join(notified_list)
        else:
            new_notified_banks = notified_banks_str

        # Встановлюємо статус сесії та очищуємо верифікаційні дані від попереднього банку
        await db.execute("""
            UPDATE sessions 
            SET line_id = ?, status = 'number_assigned',
                bank = ?,
                success_photo_id = NULL,
                card_photo_id = NULL,
                card_first4 = NULL,
                card_last4 = NULL,
                sent_codes_count = 0,
                notified_banks = ?
            WHERE client_id = ?
        """, (line_id, bank_name, new_notified_banks, client_id))
        # Маркуємо лінію як зайняту
        await db.execute("UPDATE lines SET status = 'busy' WHERE id = ?", (line_id,))
        await db.commit()

async def update_session_message_id(client_id: int, message_id: int):
    """Оновлення ID повідомлення з кнопкою у клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET client_message_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def update_session_waiting_message_id(client_id: int, message_id: int):
    """Оновлення ID повідомлення про очікування номера у клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET waiting_message_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def update_session_instruction_message_id(client_id: int, message_id: int):
    """Оновлення ID повідомлення з інструкцією банку у клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET instruction_message_id = ? WHERE client_id = ?", (message_id, client_id))
        await db.commit()

async def update_session_client_phone(client_id: int, phone: str):
    """Збереження номера телефону клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET client_phone = ? WHERE client_id = ?", (phone, client_id))
        await db.commit()

async def update_session_banks(client_id: int, selected_banks: str, remaining_banks: str):
    """Оновлення списків обраних та залишкових банків для сесії"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            UPDATE sessions 
            SET selected_banks = ?, remaining_banks = ? 
            WHERE client_id = ?
        """, (selected_banks, remaining_banks, client_id))
        await db.commit()

async def set_session_status(client_id: int, status: str):
    """Зміна статусу сесії ('registered', 'number_assigned', 'waiting_code', 'completed')"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE sessions SET status = ? WHERE client_id = ?", (status, client_id))
        await db.commit()

async def complete_current_bank(client_id: int, result: str) -> dict | None:
    """Завершення верифікації поточного банку: звільняє лінію, логує, оновлює сесію.

    result: 'success' | 'release' | 'failure' | 'banned'
    """
    session = await get_session(client_id)
    if not session or not session.get('line_id'):
        return None

    line_id = session['line_id']
    line_info = await get_line(line_id)
    bank_name = line_info['bank'] if line_info else "Банк"

    if result in ('success', 'release'):
        line_status = 'success' if result == 'success' else 'available'
        log_status = 'success' if result == 'success' else 'released'
    else:
        line_status = 'banned'
        log_status = 'banned'

    await set_line_status(line_id, line_status)
    await log_verification_end(client_id, bank_name, log_status)

    async with aiosqlite.connect(DB_FILE) as db_conn:
        await db_conn.execute("""
            UPDATE sessions
            SET line_id = NULL, client_message_id = NULL, status = 'registered', sent_codes_count = 0
            WHERE client_id = ?
        """, (client_id,))
        await db_conn.commit()

    remaining = session['remaining_banks'].split(",") if session.get('remaining_banks') else []
    if bank_name in remaining:
        remaining.remove(bank_name)
    new_remaining = ",".join(remaining)
    await update_session_banks(client_id, session.get('selected_banks', ''), new_remaining)

    session['remaining_banks'] = new_remaining
    return {
        "session": session,
        "line_id": line_id,
        "bank_name": bank_name,
        "line_status": line_status,
        "log_status": log_status,
        "remaining": remaining,
        "remaining_banks": new_remaining,
        "selected_banks": session.get('selected_banks', ''),
    }

async def send_archive_report(client_id: int, bot):
    """Генерує текстовий звіт про сесію та надсилає його в архівну групу"""
    try:
        from bot.config import get_archive_group_id, LOG_BOT_TOKEN
        archive_group_id = get_archive_group_id()
        if not archive_group_id:
            return
            
        import re
        from aiogram import Bot
        
        # 1. Отримуємо дані сесії
        session = await get_session(client_id)
        if not session:
            return
            
        # 2. Формуємо текст картки-звіту
        username = session['username'] or "Невідомий"
        
        # Парсимо client_data (вона містить ПІБ, ДР, Телефон тощо)
        client_data = session['client_data'] or ""
        
        # Спробуємо дістати телефон та інші дані з тексту
        phone_match = re.search(r'(?:Телефон|Тлф|Номер):\s*([^\n]+)', client_data, re.IGNORECASE)
        phone = phone_match.group(1).strip() if phone_match else "Не вказано"
        
        # Отримуємо реквізити картки
        card_first4 = session.get('card_first4') or ""
        card_last4 = session.get('card_last4') or ""
        card_info = f"{card_first4}...{card_last4}" if (card_first4 and card_last4) else "Не розпізнано"
        
        # Запит на успішно пройдені банки
        passed_banks = []
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("""
                SELECT bank, status FROM bank_verifications 
                WHERE client_id = ? AND status = 'success'
            """, (client_id,)) as cursor:
                rows = await cursor.fetchall()
                passed_banks = [r['bank'] for r in rows]
        
        banks_str = ", ".join(passed_banks) if passed_banks else "Немає успішних реєстрацій"
        
        # Формуємо красивий звіт
        report_lines = [
            "✅ <b>СЕСІЮ ЗАВЕРШЕНО</b>",
            f"👤 <b>Клієнт:</b> @{username} (ID: <code>{client_id}</code>)",
            f"📞 <b>Телефон:</b> <code>{phone}</code>",
            f"🏦 <b>Пройдені банки:</b> {banks_str}",
            f"💳 <b>Картка:</b> <code>{card_info}</code>",
        ]
        
        # Спробуємо виділити ПІБ та ДР
        pib_match = re.search(r'(?:ПІБ|ФИО|Ім\'я):\s*([^\n]+)', client_data, re.IGNORECASE)
        dob_match = re.search(r'(?:ДР|Дата народження|Дата|Дар):\s*([^\n]+)', client_data, re.IGNORECASE)
        if pib_match:
            report_lines.insert(2, f"📝 <b>ПІБ:</b> {pib_match.group(1).strip()}")
        if dob_match:
            report_lines.insert(3, f"📅 <b>ДР:</b> {dob_match.group(1).strip()}")
            
        report_text = "\n".join(report_lines)
        
        # Створюємо/вибираємо інстанс бота для відправки логів
        send_bot = bot
        close_send_bot = False
        if LOG_BOT_TOKEN:
            try:
                send_bot = Bot(token=LOG_BOT_TOKEN)
                close_send_bot = True
            except Exception as e:
                logging.error(f"Помилка створення log_bot з LOG_BOT_TOKEN: {e}. Використовуємо дефолтного бота.")
                send_bot = bot

        try:
            # Надсилаємо картку-звіт
            await send_bot.send_message(
                chat_id=archive_group_id,
                text=report_text,
                parse_mode="HTML"
            )
        finally:
            # Закриваємо сесію log_bot, якщо створювали новий інстанс
            if close_send_bot:
                try:
                    await send_bot.session.close()
                except Exception as e:
                    logging.error(f"Помилка закриття сесії log_bot: {e}")
                
    except Exception as e:
        logging.error(f"Помилка надсилання архівного звіту: {e}")

async def close_session(client_id: int):
    """Завершення сесії: звільняємо лінію та видаляємо/архівуємо сесію"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Отримуємо інформацію про лінію перед видаленням сесії
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT line_id FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['line_id']:
                # Звільняємо лінію
                await db.execute("UPDATE lines SET status = 'available' WHERE id = ?", (row['line_id'],))
        
        # Переводимо сесію в статус завершеної
        await db.execute("UPDATE sessions SET status = 'completed' WHERE client_id = ?", (client_id,))
        await db.commit()

    # Видаляємо активні підписки стеження за цим клієнтом
    for admin_id, sub_client_id in list(active_subscriptions.items()):
        if sub_client_id == client_id:
            active_subscriptions.pop(admin_id, None)

    # Відправляємо звіт та лог чату в Telegram групу-архів
    try:
        import web.core
        bot = web.core.bot
        if bot:
            await send_archive_report(client_id, bot)
    except Exception as e:
        logging.error(f"Помилка відправки архівного звіту: {e}")

async def get_max_line_id() -> int:
    """Отримання максимального ID лінії в базі даних"""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT MAX(line_id) FROM lines") as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

async def unassign_line_from_session(client_id: int):
    """Звільнення лінії від сесії клієнта (повернення в доступні)"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT line_id FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['line_id']:
                # Звільняємо лінію
                await db.execute("UPDATE lines SET status = 'available' WHERE id = ?", (row['line_id'],))
        
        # Очищуємо призначення лінії та пов'язані верифікаційні дані в сесії
        await db.execute("""
            UPDATE sessions 
            SET line_id = NULL, 
                status = 'registered',
                success_photo_id = NULL,
                card_photo_id = NULL,
                card_first4 = NULL,
                card_last4 = NULL
            WHERE client_id = ?
        """, (client_id,))
        await db.commit()

# --- Статистика, Налаштування та Шаблони (Stats, Settings & Templates) ---

async def get_setting(key: str, default: str = None) -> str:
    """Отримання значення налаштування з БД"""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key: str, value: str):
    """Збереження значення налаштування в БД"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()

async def get_all_settings() -> dict:
    """Отримання всіх налаштувань"""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT key, value FROM app_settings") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

async def get_all_bank_templates() -> dict:
    """Отримання всіх шаблонів банків"""
    async with aiosqlite.connect(DB_FILE) as db:
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
                    'is_active': row['is_active'] if 'is_active' in row.keys() else 1
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
    is_active: int = 1
):
    """Збереження або оновлення шаблону банку"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO bank_templates (key, command, text, code_length, logo_path, screenshot_path, download_screenshot_path, success_screenshot_path, report_template, ai_rules, required_screenshots, description, display_name, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                is_active = excluded.is_active
        """, (key, command, text, code_length, logo_path, screenshot_path, download_screenshot_path, success_screenshot_path, report_template, ai_rules, required_screenshots, description, display_name, is_active))
        await db.commit()

async def delete_bank_template(key: str):
    """Видалення шаблону банку"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM bank_templates WHERE key = ?", (key,))
        await db.commit()

async def get_bank_template_db(bank_name: str):
    """Отримання шаблону за назвою банку (async версія)"""
    if not bank_name:
        return None
    templates = await get_all_bank_templates()
    name_norm = bank_name.lower().replace(" ", "").replace("-", "")
    for key, val in templates.items():
        key_norm = key.lower().replace(" ", "").replace("-", "")
        if key_norm in name_norm or name_norm in key_norm:
            return val
    return None

async def get_bank_template_with_key_db(bank_name: str):
    """Отримання шаблону та ключа за назвою банку (async версія)"""
    if not bank_name:
        return None, None
    templates = await get_all_bank_templates()
    name_norm = bank_name.lower().replace(" ", "").replace("-", "")
    for key, val in templates.items():
        key_norm = key.lower().replace(" ", "").replace("-", "")
        if key_norm in name_norm or name_norm in key_norm:
            return key, val
    return None, None

async def get_bank_display_name(bank_name: str) -> str:
    """Повертає зрозумілу назву банку для відображення (наприклад, AmoBank)"""
    if not bank_name:
        return "Невідомий банк"
    
    # Спробуємо знайти назву в шаблонах бази даних
    tpl = await get_bank_template_db(bank_name)
    if tpl and tpl.get('display_name'):
        return tpl['display_name']
    
    name_norm = bank_name.lower().replace(" ", "").replace("-", "").replace(".", "")
    mapping = {
        "izibank": "IziBank",
        "amobank": "AmoBank",
        "lvivbank": "LvivBank",
        "bankkd": "bank.kd",
        "alliance": "Alliance"
    }
    
    for key, val in mapping.items():
        if key in name_norm or name_norm in key:
            return val
            
    return bank_name[0].upper() + bank_name[1:] if len(bank_name) > 0 else bank_name


async def log_verification_start(client_id: int, username: str, bank: str, phone_number: str):
    """Логування початку верифікації для лінії"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Оновлюємо час призначення та скидаємо статус нагадування в сесії
        await db.execute("""
            UPDATE sessions
            SET assigned_at = CURRENT_TIMESTAMP, last_reminder_sent_at = NULL
            WHERE client_id = ?
        """, (client_id,))
        
        # Створюємо запис у таблиці статистики
        await db.execute("""
            INSERT INTO bank_verifications (client_id, username, bank, phone_number, assigned_at, status)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'pending')
        """, (client_id, username or 'Невідомий', bank, phone_number))
        await db.commit()

async def log_verification_end(client_id: int, bank: str, status: str):
    """Логування завершення верифікації (успіх/відмова/випуск)"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Шукаємо останню незавершену верифікацію для цього клієнта та банку
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT id, assigned_at FROM bank_verifications
            WHERE client_id = ? AND bank = ? AND status = 'pending'
            ORDER BY id DESC LIMIT 1
        """, (client_id, bank)) as cursor:
            row = await cursor.fetchone()
            if row:
                # Вираховуємо тривалість у секундах
                await db.execute("""
                    UPDATE bank_verifications
                    SET completed_at = CURRENT_TIMESTAMP,
                        status = ?,
                        duration_seconds = CAST((strftime('%s', CURRENT_TIMESTAMP) - strftime('%s', assigned_at)) AS INTEGER)
                    WHERE id = ?
                """, (status, row['id']))
                await db.commit()

async def get_client_verification_history(client_id: int):
    """Отримання історії верифікацій клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT bank, status, assigned_at, completed_at, phone_number, duration_seconds
            FROM bank_verifications
            WHERE client_id = ?
            ORDER BY assigned_at DESC
            LIMIT 50
        """, (client_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_statistics() -> dict:
    """Отримання агрегованої статистики для веб-панелі"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        
        # Загальні показники
        async with db.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' OR status = 'released' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'banned' THEN 1 ELSE 0 END) as failure_count
            FROM bank_verifications
            WHERE status != 'pending'
        """) as cursor:
            totals = dict(await cursor.fetchone())
            
        # Показники за сьогодні
        async with db.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' OR status = 'released' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'banned' THEN 1 ELSE 0 END) as failure_count
            FROM bank_verifications
            WHERE status != 'pending' AND date(assigned_at) = date('now')
        """) as cursor:
            today = dict(await cursor.fetchone())
            
        # Середня тривалість по банках
        async with db.execute("""
            SELECT 
                bank,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' OR status = 'released' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'banned' THEN 1 ELSE 0 END) as failure,
                ROUND(AVG(duration_seconds)) as avg_duration
            FROM bank_verifications
            WHERE status != 'pending' AND duration_seconds IS NOT NULL
            GROUP BY bank
            ORDER BY total DESC
        """) as cursor:
            banks_stats = [dict(row) for row in await cursor.fetchall()]
            
        return {
            "totals": totals,
            "today": today,
            "banks": banks_stats
        }

async def clear_statistics():
    """Видалення всієї статистики верифікацій"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM bank_verifications")
        await db.commit()

async def log_chat_message(client_id: int, sender: str, message_text: str = None, photo_id: str = None):
    """Збереження повідомлення в історію чату"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO chat_logs (client_id, sender, message_text, photo_id)
            VALUES (?, ?, ?, ?)
        """, (client_id, sender, message_text, photo_id))
        await db.commit()
    
    # Виклик зареєстрованих колбеків для оновлення в реальному часі
    for cb in chat_message_callbacks:
        try:
            asyncio.create_task(cb(client_id, sender, message_text, photo_id))
        except Exception as e:
            logging.error(f"Error in chat_message_callback: {e}")

async def get_chat_logs(client_id: int):
    """Отримання всієї історії чату для конкретного клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM chat_logs WHERE client_id = ? ORDER BY created_at ASC
        """, (client_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def clear_chat_logs(client_id: int):
    """Видалення всієї історії чату для конкретного клієнта"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM chat_logs WHERE client_id = ?", (client_id,))
        await db.commit()

async def delete_session_completely(client_id: int):
    """Повне видалення сесії, логів та верифікацій клієнта з вивільненням лінії"""
    async with aiosqlite.connect(DB_FILE) as db:
        # Звільняємо лінію, якщо вона була призначена
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT line_id FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['line_id']:
                await db.execute("UPDATE lines SET status = 'available' WHERE id = ?", (row['line_id'],))
        
        # Видаляємо всі дані
        await db.execute("DELETE FROM bank_verifications WHERE client_id = ?", (client_id,))
        await db.execute("DELETE FROM chat_logs WHERE client_id = ?", (client_id,))
        await db.execute("DELETE FROM sessions WHERE client_id = ?", (client_id,))
        await db.commit()


# --- Керування правилами та прикладами ШІ (AI Rules & Examples Management) ---

async def get_all_ai_rules():
    """Отримання всіх правил ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ai_rules ORDER BY category, id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_active_ai_rules(category: str = None):
    """Отримання списку активних правил ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        if category:
            query = "SELECT * FROM ai_rules WHERE is_active = 1 AND category = ? ORDER BY id ASC"
            params = (category,)
        else:
            query = "SELECT * FROM ai_rules WHERE is_active = 1 ORDER BY category, id ASC"
            params = ()
            
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def add_ai_rule(rule_text: str, category: str = 'general', is_active: int = 1) -> int:
    """Додавання нового правила ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            INSERT INTO ai_rules (rule_text, category, is_active)
            VALUES (?, ?, ?)
        """, (rule_text, category, is_active))
        await db.commit()
        return cursor.lastrowid

async def toggle_ai_rule(rule_id: int, is_active: int = None) -> bool:
    """Увімкнення/вимкнення правила ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        if is_active is None:
            await db.execute("""
                UPDATE ai_rules 
                SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END
                WHERE id = ?
            """, (rule_id,))
        else:
            await db.execute("""
                UPDATE ai_rules 
                SET is_active = ?
                WHERE id = ?
            """, (is_active, rule_id))
        await db.commit()
        return True

async def delete_ai_rule(rule_id: int) -> bool:
    """Видалення правила ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM ai_rules WHERE id = ?", (rule_id,))
        await db.commit()
        return True

async def get_all_ai_examples():
    """Отримання всіх few-shot прикладів діалогу ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ai_examples ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_active_ai_examples():
    """Отримання активних few-shot прикладів діалогу ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ai_examples WHERE is_active = 1 ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def add_ai_example(client_message: str, bot_response: str, is_active: int = 1) -> int:
    """Додавання прикладу діалогу для ШІ"""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            INSERT INTO ai_examples (client_message, bot_response, is_active)
            VALUES (?, ?, ?)
        """, (client_message, bot_response, is_active))
        await db.commit()
        return cursor.lastrowid

async def delete_ai_example(example_id: int) -> bool:
    """Видалення прикладу діалогу"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM ai_examples WHERE id = ?", (example_id,))
        await db.commit()
        return True


# --- Блокування користувачів (Ban System) ---

async def ban_user(client_id: int, username: str = None):
    """Додавання користувача до чорного списку"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO banned_users (client_id, username) VALUES (?, ?)", (client_id, username))
        await db.commit()

async def unban_user(client_id: int):
    """Видалення користувача з чорного списку"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM banned_users WHERE client_id = ?", (client_id,))
        await db.commit()

async def is_user_banned(client_id: int) -> bool:
    """Перевірка чи користувач заблокований"""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT 1 FROM banned_users WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def get_banned_users() -> list:
    """Отримання списку всіх заблокованих користувачів"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT client_id, username, banned_at FROM banned_users ORDER BY banned_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def add_notified_bank(client_id: int, bank_name: str):
    """Додає назву банку до списку сповіщених банків у сесії"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT notified_banks FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                current = row['notified_banks'] or ''
                banks = [b.strip() for b in current.split(",") if b.strip()]
                if bank_name not in banks:
                    banks.append(bank_name)
                    new_val = ",".join(banks)
                    await db.execute("UPDATE sessions SET notified_banks = ? WHERE client_id = ?", (new_val, client_id))
                    await db.commit()


