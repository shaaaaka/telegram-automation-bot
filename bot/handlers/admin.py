import os
import re
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from bot.config import ADMIN_ID, get_template_photo
import bot.database as db

router = Router()

class AddLineStates(StatesGroup):
    waiting_id = State()
    waiting_phone = State()
    waiting_bank = State()

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔌 Активні сесії"),
                KeyboardButton(text="📞 Статус ліній")
            ],
            [
                KeyboardButton(text="➕ Додати лінію"),
                KeyboardButton(text="📥 Імпорт lines.txt")
            ],
            [
                KeyboardButton(text="🗑️ Очистити лінії")
            ]
        ],
        resize_keyboard=True
    )

# Фільтр для перевірки, що повідомлення або запит від Адміна
def is_admin(message_or_query) -> bool:
    return message_or_query.from_user.id == ADMIN_ID

@router.message(Command("import"), F.from_user.id == ADMIN_ID)
async def cmd_import_lines(message: Message):
    """Імпорт ліній з файлу lines.txt"""
    if not is_admin(message):
        return

    file_path = "lines.txt"
    if not os.path.exists(file_path):
        await message.answer("Файл lines.txt не знайдено в корені проекту.")
        return

    try:
        imported_count = 0
        with open(file_path, "r", encoding="utf-8") as f:
            for line_str in f:
                line_str = line_str.strip()
                if not line_str or line_str.startswith("#"):
                    continue
                
                try:
                    # Спроба 1: новий формат "Line 28 Return:  380961175562 AmoBank"
                    match = re.match(r'(?:Line\s+)?(\d+)\s+Return:\s+(\d+)(?:\s+(.+))?', line_str, re.IGNORECASE)
                    if match:
                        line_id = int(match.group(1))
                        phone = match.group(2).strip()
                        bank = match.group(3).strip() if match.group(3) else "Невідомий"
                    else:
                        # Спроба 2: старий формат з роздільником або двокрапкою
                        if " - " in line_str:
                            main_part, bank = line_str.split(" - ", 1)
                        else:
                            main_part, bank = line_str, "Невідомий"

                        main_part = main_part.replace("Line ", "").replace("Return: ", "").strip()
                        if ":" in main_part:
                            line_id_str, phone = main_part.split(":", 1)
                        else:
                            parts = main_part.split()
                            line_id_str, phone = parts[0], parts[1]

                        line_id = int(line_id_str.strip())
                        phone = phone.strip()
                        bank = bank.strip()

                    await db.add_or_update_line(line_id, phone, bank)
                    imported_count += 1
                except Exception as e:
                    print(f"Помилка парсингу рядка '{line_str}': {e}")
                    continue

        await message.answer(f"Успішно імпортовано/оновлено {imported_count} ліній з lines.txt.")
    except Exception as e:
        await message.answer(f"Помилка при зчитуванні файлу: {str(e)}")

@router.message(Command("lines"), F.from_user.id == ADMIN_ID)
async def cmd_list_lines(message: Message):
    """Показати список усіх ліній"""
    if not is_admin(message):
        return

    import aiosqlite
    from bot.config import DB_FILE
    
    async with aiosqlite.connect(DB_FILE) as db_conn:
        db_conn.row_factory = aiosqlite.Row
        async with db_conn.execute("SELECT * FROM lines ORDER BY id") as cursor:
            lines = await cursor.fetchall()

    if not lines:
        await message.answer("Список ліній порожній. Використайте /import для завантаження.")
        return

    text = "Список ліній у базі:\n\n"
    for line in lines:
        status_text = "Вільна" if line['status'] == 'available' else "Зайнята"
        text += f"• Line {line['id']}: {line['phone_number']} ({line['bank']}) - {status_text}\n"

    await message.answer(text)

@router.message(Command("sessions"), F.from_user.id == ADMIN_ID)
async def cmd_list_sessions(message: Message):
    """Показати список активних сесій"""
    if not is_admin(message):
        return

    import aiosqlite
    from bot.config import DB_FILE
    
    async with aiosqlite.connect(DB_FILE) as db_conn:
        db_conn.row_factory = aiosqlite.Row
        async with db_conn.execute("SELECT * FROM sessions WHERE status != 'completed' ORDER BY created_at") as cursor:
            sessions = await cursor.fetchall()

    if not sessions:
        await message.answer("Немає активних сесій верифікації на даний момент.")
        return

    text = "Активні сесії:\n\n"
    for s in sessions:
        line_info = f"Line {s['line_id']}" if s['line_id'] else "Не призначено"
        text += (
            f"@{s['username']} (ID: {s['client_id']})\n"
            f"• Статус: {s['status']}\n"
            f"• Лінія: {line_info}\n"
            f"• Дані: {s['client_data']}\n\n"
        )

    await message.answer(text)

@router.message(Command("clear_lines"), F.from_user.id == ADMIN_ID)
async def cmd_clear_lines(message: Message):
    """Повне очищення бази даних ліній"""
    if not is_admin(message):
        return
    await db.clear_all_lines()
    await message.answer("Список ліній повністю очищено.")

# --- Обробники текстових кнопок меню адміна ---

@router.message(F.text == "🔌 Активні сесії", F.from_user.id == ADMIN_ID)
async def btn_active_sessions(message: Message):
    await cmd_list_sessions(message)

@router.message(F.text == "📞 Статус ліній", F.from_user.id == ADMIN_ID)
async def btn_list_lines(message: Message):
    await cmd_list_lines(message)

@router.message(F.text == "📥 Імпорт lines.txt", F.from_user.id == ADMIN_ID)
async def btn_import_lines(message: Message):
    await cmd_import_lines(message)

@router.message(F.text == "🗑️ Очистити лінії", F.from_user.id == ADMIN_ID)
async def btn_clear_lines(message: Message):
    await cmd_clear_lines(message)

# Фільтр для визначення прямого вставлення формату лінії
def is_direct_line_format(message: Message) -> bool:
    if not message.text:
        return False
    return bool(re.match(r'^(?:Line\s+)?(\d+)\s+Return:\s*(\d+)(?:\s+(.+))?$', message.text.strip(), re.IGNORECASE))

@router.message(F.text, F.from_user.id == ADMIN_ID, is_direct_line_format)
async def handle_direct_line_paste(message: Message, state: FSMContext):
    if not is_admin(message):
        return
    text = message.text.strip()
    match = re.match(r'^(?:Line\s+)?(\d+)\s+Return:\s*(\d+)(?:\s+(.+))?$', text, re.IGNORECASE)
    if not match:
        return
        
    line_id = int(match.group(1))
    phone = match.group(2).strip().replace(' ', '').replace('-', '').replace('+', '')
    bank = match.group(3).strip() if match.group(3) else None
    
    if bank:
        await db.add_or_update_line(line_id, phone, bank)
        await state.clear()
        await message.answer(
            f"✅ Лінію успішно додано:\n"
            f"• Line: {line_id}\n"
            f"• Телефон: +{phone}\n"
            f"• Банк: {bank}",
            reply_markup=get_admin_keyboard()
        )
    else:
        await state.clear()
        await state.update_data(line_id=line_id, phone=phone)
        
        customOrder = ["PUMB", "bank.kd", "IziBank", "EcoBank", "Alliance", "LvivBank", "AmoBank"]
        unique_banks = await db.get_unique_banks()
        all_banks = list(dict.fromkeys(customOrder + unique_banks))
        
        keyboard_buttons = []
        for b in all_banks:
            keyboard_buttons.append([InlineKeyboardButton(text=b, callback_data=f"addlinebank_{b}")])
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await message.answer(
            f"Знайдено лінію: Line {line_id}, телефон +{phone}.\n\n"
            f"Оберіть банк зі списку нижче або введіть назву банку вручну:",
            reply_markup=markup
        )
        await state.set_state(AddLineStates.waiting_bank)

@router.message(F.text == "➕ Додати лінію", F.from_user.id == ADMIN_ID)
async def btn_add_line_start(message: Message, state: FSMContext):
    if not is_admin(message):
        return
    await state.clear()
    await message.answer(
        "Введіть унікальний номер Line для нової лінії (ціле число):\n\n"
        "Для скасування надішліть /cancel",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AddLineStates.waiting_id)

@router.message(AddLineStates.waiting_id, F.from_user.id == ADMIN_ID)
async def add_line_id(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Додавання лінії скасовано.", reply_markup=get_admin_keyboard())
        return
        
    line_id_str = message.text.strip()
    if not line_id_str.isdigit():
        await message.answer("Номер Line має бути цілим числом. Спробуйте ще раз (або /cancel):")
        return
        
    line_id = int(line_id_str)
    
    existing_line = await db.get_line(line_id)
    if existing_line:
        await message.answer(f"Лінія {line_id} вже існує (+{existing_line['phone_number']}, {existing_line['bank']}). Введіть інший номер Line (або /cancel):")
        return
        
    await state.update_data(line_id=line_id)
    await message.answer("Тепер введіть номер телефону (наприклад, +380961175562 або 380961175562):")
    await state.set_state(AddLineStates.waiting_phone)

@router.message(AddLineStates.waiting_phone, F.from_user.id == ADMIN_ID)
async def add_line_phone(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Додавання лінії скасовано.", reply_markup=get_admin_keyboard())
        return
        
    phone = message.text.strip().replace(' ', '').replace('-', '').replace('+', '')
    if not phone.isdigit() or len(phone) < 9:
        await message.answer("Неправильний формат телефону. Введіть ще раз (наприклад, 380961175562 або /cancel):")
        return
        
    await state.update_data(phone=phone)
    
    customOrder = ["PUMB", "bank.kd", "IziBank", "EcoBank", "Alliance", "LvivBank", "AmoBank"]
    unique_banks = await db.get_unique_banks()
    all_banks = list(dict.fromkeys(customOrder + unique_banks))
    
    keyboard_buttons = []
    for bank in all_banks:
        keyboard_buttons.append([InlineKeyboardButton(text=bank, callback_data=f"addlinebank_{bank}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer(
        "Оберіть банк зі списку нижче або введіть назву банку вручну:",
        reply_markup=markup
    )
    await state.set_state(AddLineStates.waiting_bank)

@router.callback_query(F.data.startswith("addlinebank_"), AddLineStates.waiting_bank)
async def add_line_bank_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        return
    bank = callback.data.split("_")[1]
    data = await state.get_data()
    line_id = data['line_id']
    phone = data['phone']
    
    await db.add_or_update_line(line_id, phone, bank)
    await state.clear()
    
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Лінію успішно додано:\n"
        f"• Line: {line_id}\n"
        f"• Телефон: +{phone}\n"
        f"• Банк: {bank}",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

@router.message(AddLineStates.waiting_bank, F.from_user.id == ADMIN_ID)
async def add_line_bank_text(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Додавання лінії скасовано.", reply_markup=get_admin_keyboard())
        return
        
    bank = message.text.strip()
    if not bank:
        await message.answer("Назва банку не може бути порожньою. Введіть ще раз (або /cancel):")
        return
        
    data = await state.get_data()
    line_id = data['line_id']
    phone = data['phone']
    
    await db.add_or_update_line(line_id, phone, bank)
    await state.clear()
    
    await message.answer(
        f"✅ Лінію успішно додано:\n"
        f"• Line: {line_id}\n"
        f"• Телефон: +{phone}\n"
        f"• Банк: {bank}",
        reply_markup=get_admin_keyboard()
    )

# --- Callback обробники для Адміна ---

@router.callback_query(F.data.startswith("toggle_"))
async def handle_toggle_bank(callback: CallbackQuery, bot: Bot):
    """Адмін перемикає вибір банку для клієнта (чекбокси)"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return

    # Формат: toggle_{client_id}_{bank}
    parts = callback.data.split("_")
    client_id = int(parts[1])
    bank = parts[2]

    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return

    selected_banks = session['selected_banks']
    selected = selected_banks.split(",") if selected_banks else []

    # Тоглимо вибір
    if bank in selected:
        selected.remove(bank)
    else:
        selected.append(bank)

    # Зберігаємо оновлений вибір
    new_selected_str = ",".join(selected)
    await db.update_session_banks(client_id, new_selected_str, "")

    # Отримуємо унікальні назви банків з бази для перемальовування
    unique_banks = await db.get_unique_banks()
    
    keyboard_buttons = []
    row = []
    for b in unique_banks:
        checkbox = "[x]" if b in selected else "[ ]"
        button_text = f"{checkbox} {b}"
        callback_data = f"toggle_{client_id}_{b}"
        row.append(InlineKeyboardButton(text=button_text, callback_data=callback_data))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
        
    keyboard_buttons.append([InlineKeyboardButton(text="Зберегти та продовжити", callback_data=f"savebanks_{client_id}")])
    keyboard_buttons.append([InlineKeyboardButton(text="Відхилити запит", callback_data=f"reject_{client_id}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    # Оновлюємо клавіатуру на повідомленні
    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data.startswith("savebanks_"))
async def handle_save_banks(callback: CallbackQuery, bot: Bot):
    """Адмін зберігає вибір банків і переходить до першого призначення"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return

    client_id = int(callback.data.split("_")[1])
    
    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return

    selected_banks = session['selected_banks']
    if not selected_banks:
        await callback.answer("Оберіть хоча б один банк для верифікації!", show_alert=True)
        return

    # Ініціалізуємо список залишкових банків (копіюємо туди обрані банки)
    await db.update_session_banks(client_id, selected_banks, selected_banks)

    # Показуємо меню вибору першого номеру
    await show_next_assignment_menu(callback.message, client_id, edit=True)
    await callback.answer()

@router.callback_query(F.data.startswith("assign_"))
async def handle_assign_line(callback: CallbackQuery, bot: Bot):
    """Адмін призначає лінію клієнту"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return

    parts = callback.data.split("_")
    client_id = int(parts[1])
    line_id = int(parts[2])

    # Отримуємо інформацію про лінію
    line_info = await db.get_line(line_id)
    if not line_info or line_info['status'] != 'available':
        await callback.answer("Ця лінія вже зайнята або не існує!", show_alert=True)
        return

    # Призначаємо лінію сесії
    await db.assign_line_to_session(client_id, line_id)

    # Прибираємо кнопки під повідомленням адміна
    await callback.message.edit_reply_markup(reply_markup=None)

    # Сповіщаємо клієнта (без смайликів)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Запросити SMS-код", callback_data="request_code")]
    ])
    
    client_msg = await bot.send_message(
        chat_id=client_id,
        text=(
            f"Номер телефону:\n\n"
            f"`+{line_info['phone_number']}`\n\n"
            f"Коли надішлете SMS і вам знадобиться код, тисніть кнопку нижче."
        ),
        reply_markup=markup,
        parse_mode="Markdown"
    )

    # Зберігаємо ID повідомлення з кнопкою у клієнта
    await db.update_session_message_id(client_id, client_msg.message_id)

    # Отримуємо інформацію про клієнта
    session_info = await db.get_session(client_id)
    username = session_info['username'] if session_info else "Невідомий"

    # Відправляємо адміну повідомлення з кнопкою завершення сесії
    complete_markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Зареєстрував", callback_data=f"complete_success_{client_id}"),
            InlineKeyboardButton(text="❌ Відмова", callback_data=f"complete_failure_{client_id}")
        ],
        [
            InlineKeyboardButton(text="🔄 Завершити реєстрацію банку", callback_data=f"complete_release_{client_id}")
        ]
    ])

    await callback.message.answer(
        text=(
            f"Лінію {line_id} ({line_info['bank']}) призначено клієнту @{username}!\n\n"
            f"Клієнт може запрошувати коди необхідну кількість разів.\n"
            f"Коли верифікацію буде закінчено, натисніть відповідну кнопку нижче."
        ),
        reply_markup=complete_markup,
        parse_mode="Markdown"
    )
    await callback.answer("Призначено!")

@router.callback_query(F.data.startswith("reject_"))
async def handle_reject_client(callback: CallbackQuery, bot: Bot):
    """Адмін відхиляє запит клієнта"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return

    client_id = int(callback.data.split("_")[1])

    # Закриваємо сесію
    await db.close_session(client_id)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Запит відхилено, сесію закрито.")
    await callback.answer("Запит відхилено.")

    # Повідомляємо клієнта
    await bot.send_message(
        chat_id=client_id,
        text="На жаль, ваш запит на верифікацію було відхилено адміністратором."
    )

@router.callback_query(F.data.startswith("route_"))
async def handle_route_code(callback: CallbackQuery, bot: Bot):
    """Адмін вручну перенаправляє код клієнту (Сценарій 3)"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return

    # Format: route_{client_id}_{code}
    parts = callback.data.split("_")
    client_id = int(parts[1])
    code = parts[2]

    session = await db.get_session(client_id)
    if not session or session['status'] != 'waiting_code':
        await callback.answer("Клієнт вже не очікує код або сесія закрита.", show_alert=True)
        return

    line_id = session['line_id']
    line_info = await db.get_line(line_id)
    bank_name = line_info['bank'] if line_info else "Банк"

    # 1. Відправляємо код клієнту
    await bot.send_message(
        chat_id=client_id,
        text=f"Ваш SMS-код для банку {bank_name}:\n\n`{code}`",
        parse_mode="Markdown"
    )

    # 2. Повертаємо статус сесії на 'number_assigned'
    await db.set_session_status(client_id, 'number_assigned')

    # Видаляємо з веб-списку нерозподілених кодів
    try:
        from web.app import unrouted_codes
        for c in list(unrouted_codes):
            if c['code'] == code:
                unrouted_codes.remove(c)
    except Exception as e:
        print(f"Помилка видалення коду з веб-панелі: {e}")

    # 3. Оновлюємо повідомлення для адміна
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(
        f"Код {code} перенаправлено користувачу @{session['username']} (Line {line_id} - {bank_name}).\n"
        f"Сесія залишається активною для наступних запитів.",
        parse_mode="Markdown"
    )
    await callback.answer("Код перенаправлено!")

@router.callback_query(F.data.startswith("complete_"))
async def handle_complete_session(callback: CallbackQuery, bot: Bot):
    """Адмін завершує верифікацію в поточному банку (успіх або відмова)"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return

    # Розпізнаємо тип результату
    parts = callback.data.split("_")
    if len(parts) >= 3:
        client_id = int(parts[2])
        result = parts[1] # "success", "failure", or "release"
    else:
        client_id = int(parts[1])
        result = "success"
    
    session = await db.get_session(client_id)
    if not session or session['status'] == 'completed':
        await callback.answer("Сесія вже завершена або не існує.", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    line_id = session['line_id']
    line_info = await db.get_line(line_id)
    bank_name = line_info['bank'] if line_info else "Банк"

    # 1. Видаляємо кнопку запиту коду у клієнта
    if session['client_message_id']:
        try:
            await bot.edit_message_reply_markup(
                chat_id=client_id,
                message_id=session['client_message_id'],
                reply_markup=None
            )
        except Exception as e:
            print(f"Помилка видалення кнопки у клієнта: {e}")

    if result in ("success", "release"):
        # 2. Позначаємо лінію відповідно
        line_status = 'success' if result == 'success' else 'available'
        await db.set_line_status(line_id, line_status)

        # Оновлюємо статус сесії в БД на 'registered' (без лінії)
        import aiosqlite
        from bot.config import DB_FILE
        async with aiosqlite.connect(DB_FILE) as db_conn:
            await db_conn.execute("UPDATE sessions SET line_id = NULL, client_message_id = NULL, status = 'registered' WHERE client_id = ?", (client_id,))
            await db_conn.commit()

        # 3. Вилучаємо пройдений bank зі списку залишкових банків
        remaining_banks_str = session['remaining_banks']
        remaining = remaining_banks_str.split(",") if remaining_banks_str else []
        if bank_name in remaining:
            remaining.remove(bank_name)

        new_remaining_str = ",".join(remaining)
        await db.update_session_banks(client_id, session['selected_banks'], new_remaining_str)

        # Прибираємо кнопки з повідомлення завершення
        await callback.message.edit_reply_markup(reply_markup=None)
        
        status_word = "Успішна" if result == "success" else "Вільна"
        await callback.message.edit_text(
            f"Верифікацію для клієнта @{session['username']} в банку {bank_name} завершено.\n"
            f"Лінія {line_id} позначена як {status_word}.",
            parse_mode="Markdown"
        )

        # 4. Перевіряємо чи залишилися ще банки для проходження
        if not remaining:
            try:
                from bot.handlers.client import get_client_idle_keyboard
                await bot.send_message(
                    chat_id=client_id,
                    text="Роботу завершено. Дякуємо за співпрацю.",
                    parse_mode="Markdown",
                    reply_markup=get_client_idle_keyboard()
                )
            except Exception as e:
                print(f"Не вдалося надіслати клієнту повідомлення про завершення: {e}")

            await db.close_session(client_id)
            await callback.message.answer(
                f"Верифікацію для клієнта @{session['username']} успішно завершено по всіх обраних банках! Сесію закрито."
            )
        else:
            try:
                await bot.send_message(
                    chat_id=client_id,
                    text=f"Верифікацію для банку {bank_name} завершено. Очікуйте наступний номер.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Не вдалося надіслати клієнту повідомлення: {e}")

            await show_next_assignment_menu(callback.message, client_id, edit=False)
    else:
        # Відмова (Failure)
        # 2. Позначаємо лінію як заблоковану (banned) та логуємо
        await db.set_line_status(line_id, 'banned')
        await db.log_verification_end(client_id, bank_name, 'banned')

        # Оновлюємо статус сесії в БД на 'registered'
        import aiosqlite
        from bot.config import DB_FILE
        async with aiosqlite.connect(DB_FILE) as db_conn:
            await db_conn.execute("UPDATE sessions SET line_id = NULL, client_message_id = NULL, status = 'registered' WHERE client_id = ?", (client_id,))
            await db_conn.commit()

        # 3. Вилучаємо пройдений bank зі списку залишкових банків
        remaining_banks_str = session['remaining_banks']
        remaining = remaining_banks_str.split(",") if remaining_banks_str else []
        if bank_name in remaining:
            remaining.remove(bank_name)

        new_remaining_str = ",".join(remaining)
        await db.update_session_banks(client_id, session['selected_banks'], new_remaining_str)

        # Прибираємо кнопки з повідомлення завершення
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.edit_text(
            f"Реєстрацію для клієнта @{session['username']} в банку {bank_name} скасовано (Відмова банку).\n"
            f"Лінія {line_id} позначена як Відмова (Заблокована).",
            parse_mode="Markdown"
        )

        # 4. Перевіряємо чи залишилися ще банки для проходження
        if not remaining:
            try:
                from bot.handlers.client import get_client_idle_keyboard
                await bot.send_message(
                    chat_id=client_id,
                    text="Роботу завершено. Дякуємо за співпрацю.",
                    parse_mode="Markdown",
                    reply_markup=get_client_idle_keyboard()
                )
            except Exception as e:
                print(f"Не вдалося надіслати клієнту повідомлення про завершення: {e}")

            await db.close_session(client_id)
            await callback.message.answer(
                f"Верифікацію для клієнта @{session['username']} завершено по всіх банках після відмови в останньому. Сесію закрито."
            )
        else:
            # Повідомляємо клієнта про заміну номера
            try:
                await bot.send_message(
                    chat_id=client_id,
                    text=f"На жаль, виникла помилка з цим номером (відмова банку {bank_name}). Будь ласка, зачекайте, ми призначимо вам новий номер для цього банку.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Не вдалося надіслати клієнту повідомлення про відмову: {e}")

            # Показуємо меню вибору лінії знову
            await show_next_assignment_menu(callback.message, client_id, edit=False)

    await callback.answer("Виконано!")

@router.callback_query(F.data.startswith("terminate_"))
async def handle_terminate_session(callback: CallbackQuery, bot: Bot):
    """Адмін остаточно закриває сесію верифікації клієнта"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return

    client_id = int(callback.data.split("_")[1])
    
    session = await db.get_session(client_id)
    if not session or session['status'] == 'completed':
        await callback.answer("Сесія вже завершена або не існує.", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    # 1. Повідомляємо клієнта про остаточне завершення роботи
    try:
        from bot.handlers.client import get_client_idle_keyboard
        await bot.send_message(
            chat_id=client_id,
            text="Роботу завершено. Дякуємо за співпрацю.",
            parse_mode="Markdown",
            reply_markup=get_client_idle_keyboard()
        )
    except Exception as e:
        print(f"Не вдалося надіслати клієнту повідомлення: {e}")

    # 2. Повністю закриваємо сесію (статус completed)
    await db.close_session(client_id)

    # 3. Оновлюємо повідомлення для адміна
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(
        f"Сесію для клієнта @{session['username']} остаточно закрито.",
        parse_mode="Markdown"
    )
    await callback.answer("Сесію закрито!")

# --- Допоміжні функції ---

async def show_next_assignment_menu(message: Message, client_id: int, edit: bool = True):
    """Допоміжна функція для показу меню вибору ліній на основі залишкового списку банків"""
    session = await db.get_session(client_id)
    if not session:
        return

    remaining_banks_str = session['remaining_banks']
    remaining_banks = remaining_banks_str.split(",") if remaining_banks_str else []

    if not remaining_banks:
        # Закриваємо сесію
        await db.close_session(client_id)
        text = f"Верифікацію для клієнта @{session['username']} завершено."
        if edit:
            await message.edit_reply_markup(reply_markup=None)
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    # Отримуємо всі вільні лінії
    available_lines = await db.get_available_lines()
    
    # Фільтруємо лінії: залишаємо лише ті, які підходять під залишкові банки
    filtered_lines = [line for line in available_lines if line['bank'] in remaining_banks]

    keyboard_buttons = []
    for line in filtered_lines:
        button_text = f"Line {line['id']} ({line['bank']})"
        callback_data = f"assign_{client_id}_{line['id']}"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
    
    # Кнопка для остаточного закриття сесії
    keyboard_buttons.append([InlineKeyboardButton(text="Закрити сесію остаточно", callback_data=f"terminate_{client_id}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    remaining_text = ", ".join(remaining_banks)
    text = (
        f"Оберіть лінію для наступного банку для @{session['username']}:\n"
        f"• Залишилося пройти банки: {remaining_text}\n\n"
        f"Оберіть лінію для призначення:"
    )

    if not filtered_lines:
        text += "\n\nПопередження: немає вільних ліній для решти банків! Використайте /import або вивільніть лінії."

    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="Markdown")

@router.message(Command("setphoto"), F.from_user.id == ADMIN_ID)
async def cmd_set_photo_help(message: Message):
    await message.answer(
        "Інструкція для налаштування фото:\n\n"
        "Надішліть боту будь-яке фото та додайте підпис (caption):\n"
        "`/setphoto <ключ>`\n\n"
        "Приклади:\n"
        "• `/setphoto izibank` — для додатку izibank\n"
        "• `/setphoto екорег` — для інструкції /екорег\n\n"
        "Бот автоматично збереже це фото та надсилатиме його користувачам."
    )

@router.message(F.chat.type == "private", F.from_user.id == ADMIN_ID, F.photo, F.caption.startswith("/setphoto"))
async def cmd_set_photo(message: Message, bot: Bot):
    """Обробник для завантаження фото інструкцій/шаблонів адміном"""
    caption = message.caption or ""
    parts = caption.strip().split()
    if len(parts) < 2:
        await message.answer("Будь ласка, вкажіть ключ. Приклад: /setphoto izibank")
        return
    
    key = parts[1].strip().lower().replace("/", "")
    photo = message.photo[-1]  # Отримуємо найбільший розмір фото
    
    # Створюємо папку, якщо її не існує
    images_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "images")
    os.makedirs(images_dir, exist_ok=True)
    
    target_path = os.path.join(images_dir, f"{key}.png")
    
    try:
        # Завантажуємо фото на диск
        await bot.download(photo, destination=target_path)
        await message.answer(f"✅ Фото для '{key}' успішно збережено!")
    except Exception as e:
        await message.answer(f"❌ Помилка при збереженні фото: {str(e)}")

