import os
import re
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from bot.config import ADMIN_ID, get_template_photo, get_bank_template_with_key
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
                KeyboardButton(text="🗑️ Очистити лінії")
            ]
        ],
        resize_keyboard=True
    )

# Фільтр для перевірки, що повідомлення або запит від Адміна
def is_admin(message_or_query) -> bool:
    return message_or_query.from_user.id == ADMIN_ID

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
        await message.answer("Список ліній порожній. Додайте нові лінії за допомогою кнопки або надішліть номер телефону прямо в чат.")
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

    await message.answer("📋 <b>Активні сесії верифікації:</b>", parse_mode="HTML")
    
    import html
    for s in sessions:
        line_info = f"Line {s['line_id']}" if s['line_id'] else "Не призначено"
        
        # Робимо гарний опис банків
        selected_banks = s['selected_banks'] or "Не обрано"
        remaining_banks = s['remaining_banks'] or "Немає"
        
        username_esc = html.escape(s['username'] or "Невідомий")
        status_esc = html.escape(s['status'] or "")
        line_info_esc = html.escape(line_info)
        selected_banks_esc = html.escape(selected_banks)
        remaining_banks_esc = html.escape(remaining_banks)
        client_data_esc = html.escape(s['client_data'] or "")
        
        card_text = (
            f"👤 <b>Клієнт:</b> @{username_esc} (ID: <code>{s['client_id']}</code>)\n"
            f"• <b>Статус:</b> <code>{status_esc}</code>\n"
            f"• <b>Лінія:</b> {line_info_esc}\n"
            f"• <b>Обрані банки:</b> {selected_banks_esc}\n"
            f"• <b>Залишилось пройти:</b> {remaining_banks_esc}\n"
            f"• <b>Дані:</b> \n<pre>{client_data_esc}</pre>"
        )
        
        buttons = [
            [
                InlineKeyboardButton(text="💳 Банки", callback_data=f"managebanks_{s['client_id']}"),
                InlineKeyboardButton(text="📞 Лінія", callback_data=f"reassignline_{s['client_id']}")
            ]
        ]
        
        if s['line_id']:
            buttons.append([
                InlineKeyboardButton(text="❌ Звільнити лінію", callback_data=f"unassignline_{s['client_id']}")
            ])
            
        buttons.append([
            InlineKeyboardButton(text="✅ Завершити", callback_data=f"completesession_{s['client_id']}"),
            InlineKeyboardButton(text="🚫 Закрити", callback_data=f"terminate_{s['client_id']}")
        ])
        
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(card_text, reply_markup=markup, parse_mode="HTML")

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

@router.message(F.text == "🗑️ Очистити лінії", F.from_user.id == ADMIN_ID)
async def btn_clear_lines(message: Message):
    await cmd_clear_lines(message)

# Фільтр для визначення прямого вставлення формату лінії
def is_direct_line_format(message: Message) -> bool:
    if not message.text:
        return False
    text = message.text.strip()
    f1 = bool(re.match(r'^(?:Line\s+)?(\d+)\s+Return:\s*(\d+)(?:\s+(.+))?$', text, re.IGNORECASE))
    f2 = bool(re.match(r'^\+?(\d{10,15})\s+([a-zA-Z0-9\.\-_ ]+)$', text))
    f3 = bool(re.match(r'^\+?(\d{10,15})$', text))
    return f1 or f2 or f3

@router.message(F.text, F.from_user.id == ADMIN_ID, is_direct_line_format)
async def handle_direct_line_paste(message: Message, state: FSMContext):
    if not is_admin(message):
        return
    text = message.text.strip()
    
    match1 = re.match(r'^(?:Line\s+)?(\d+)\s+Return:\s*(\d+)(?:\s+(.+))?$', text, re.IGNORECASE)
    match2 = re.match(r'^\+?(\d{10,15})\s+([a-zA-Z0-9\.\-_ ]+)$', text)
    match3 = re.match(r'^\+?(\d{10,15})$', text)
    
    if match1:
        line_id = int(match1.group(1))
        phone = match1.group(2).strip().replace(' ', '').replace('-', '').replace('+', '')
        bank = match1.group(3).strip() if match1.group(3) else None
    elif match2:
        phone = match2.group(1).strip().replace(' ', '').replace('-', '').replace('+', '')
        bank = match2.group(2).strip()
        max_id = await db.get_max_line_id()
        line_id = max_id + 1
    elif match3:
        phone = match3.group(1).strip().replace(' ', '').replace('-', '').replace('+', '')
        bank = None
        max_id = await db.get_max_line_id()
        line_id = max_id + 1
    else:
        return
        
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
    unique_banks_db = await db.get_unique_banks()
    custom_order = ["PUMB", "bank.kd", "IziBank", "EcoBank", "Alliance", "LvivBank", "AmoBank"]
    all_banks = list(dict.fromkeys(custom_order + unique_banks_db))
    
    keyboard_buttons = []
    row = []
    for b in all_banks:
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

    # Сповіщаємо клієнта: спочатку надсилаємо інструкцію завантаження банку
    bank_name = line_info['bank']
    key, template = get_bank_template_with_key(bank_name)
    if template:
        photo_path = get_template_photo(key)
        if photo_path:
            try:
                await bot.send_photo(
                    chat_id=client_id,
                    photo=FSInputFile(photo_path),
                    caption=template['text']
                )
            except Exception as e:
                print(f"Помилка надсилання фото шаблону банку: {e}")
                try:
                    await bot.send_message(chat_id=client_id, text=template['text'])
                except Exception:
                    pass
        else:
            try:
                await bot.send_message(chat_id=client_id, text=template['text'])
            except Exception as e:
                print(f"Помилка надсилання тексту шаблону банку: {e}")

    client_kbd = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Запросити SMS-код")]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )
    
    client_msg = await bot.send_message(
        chat_id=client_id,
        text=(
            f"Номер телефону:\n\n"
            f"`+{line_info['phone_number']}`\n\n"
            f"Коли надішлете SMS і вам знадобиться код, тисніть кнопку нижче."
        ),
        parse_mode="Markdown"
    )

    try:
        await bot.send_message(
            chat_id=client_id,
            text="З'явилася кнопка внизу для швидкого запиту коду 👇",
            reply_markup=client_kbd
        )
    except Exception as e:
        print(f"Помилка надсилання клавіатури клієнту: {e}")

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
        text="На жаль, ваш запит на верифікацію було відхилено адміністратором.",
        reply_markup=ReplyKeyboardRemove()
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

    client_kbd = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Запросити SMS-код")]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )

    # 1. Відправляємо код клієнту
    await bot.send_message(
        chat_id=client_id,
        text=f"Ваш SMS-код для банку {bank_name}:\n\n`{code}`",
        reply_markup=client_kbd,
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
        # 2. Позначаємо лінію відповідно та логуємо завершення
        line_status = 'success' if result == 'success' else 'available'
        await db.set_line_status(line_id, line_status)
        await db.log_verification_end(client_id, bank_name, result)

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
                kbd = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📋 Мої дані")]],
                    resize_keyboard=True,
                    one_time_keyboard=False,
                    is_persistent=True
                )
                await bot.send_message(
                    chat_id=client_id,
                    text="Роботу завершено. Дякуємо за співпрацю.",
                    parse_mode="Markdown",
                    reply_markup=kbd
                )
            except Exception as e:
                print(f"Не вдалося надіслати клієнту повідомлення про завершення: {e}")

            await db.close_session(client_id)
            await callback.message.answer(
                f"Верифікацію для клієнта @{session['username']} успішно завершено по всіх обраних банках! Сесію закрито."
            )
        else:
            try:
                kbd = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="⏳ Очікування номера...")]],
                    resize_keyboard=True,
                    one_time_keyboard=False,
                    is_persistent=True
                )
                await bot.send_message(
                    chat_id=client_id,
                    text=f"Верифікацію для банку {bank_name} завершено. Очікуйте наступний номер.",
                    parse_mode="Markdown",
                    reply_markup=kbd
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
                kbd = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📋 Мої дані")]],
                    resize_keyboard=True,
                    one_time_keyboard=False,
                    is_persistent=True
                )
                await bot.send_message(
                    chat_id=client_id,
                    text="Роботу завершено. Дякуємо за співпрацю.",
                    parse_mode="Markdown",
                    reply_markup=kbd
                )
            except Exception as e:
                print(f"Помилка надсилання клієнту повідомлення про завершення: {e}")

            await db.close_session(client_id)
            await callback.message.answer(
                f"Верифікацію для клієнта @{session['username']} завершено по всіх банках після відмови в останньому. Сесію закрито."
            )
        else:
            # Повідомляємо клієнта про заміну номера
            try:
                kbd = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="⏳ Очікування номера...")]],
                    resize_keyboard=True,
                    one_time_keyboard=False,
                    is_persistent=True
                )
                await bot.send_message(
                    chat_id=client_id,
                    text=f"На жаль, виникла помилка з цим номером (відмова банку {bank_name}). Будь ласка, зачекайте, ми призначимо вам новий номер для цього банку.",
                    parse_mode="Markdown",
                    reply_markup=kbd
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
        kbd = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📋 Мої дані")]],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )
        await bot.send_message(
            chat_id=client_id,
            text="Роботу завершено. Дякуємо за співпрацю.",
            parse_mode="Markdown",
            reply_markup=kbd
        )
    except Exception as e:
        print(f"Не вдалося надіслати клієнту повідомлення: {e}")

    # 2. Повністю закриваємо сесію (статус completed)
    await db.close_session(client_id)

    # 3. Оновлюємо повідомлення для адміна
    await callback.message.edit_reply_markup(reply_markup=None)
    import html
    username_esc = html.escape(session['username'] or "Невідомий")
    await callback.message.edit_text(
        f"Сесію для клієнта @{username_esc} остаточно закрито.",
        parse_mode="HTML"
    )
    await callback.answer("Сесію закрито!")

@router.callback_query(F.data.startswith("managebanks_"))
async def handle_manage_banks(callback: CallbackQuery, bot: Bot):
    """Показ чекбоксів вибору банків для керування сесією"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[1])
    
    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return
        
    selected_banks = session['selected_banks']
    selected = selected_banks.split(",") if selected_banks else []
    
    unique_banks_db = await db.get_unique_banks()
    custom_order = ["PUMB", "bank.kd", "IziBank", "EcoBank", "Alliance", "LvivBank", "AmoBank"]
    all_banks = list(dict.fromkeys(custom_order + unique_banks_db))
    
    keyboard_buttons = []
    row = []
    for b in all_banks:
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
    
    await callback.message.edit_text(
        f"Оберіть банки для клієнта @{session['username']}:",
        reply_markup=markup
    )
    await callback.answer()

@router.callback_query(F.data.startswith("reassignline_"))
async def handle_reassign_line_menu(callback: CallbackQuery, bot: Bot):
    """Показ меню призначення/зміни лінії"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[1])
    await show_next_assignment_menu(callback.message, client_id, edit=True)
    await callback.answer()

@router.callback_query(F.data.startswith("unassignline_"))
async def handle_unassign_line(callback: CallbackQuery, bot: Bot):
    """Звільнення призначеної лінії без завершення сесії"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[1])
    
    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return
        
    line_id = session['line_id']
    if not line_id:
        await callback.answer("Лінія не призначена.", show_alert=True)
        return
        
    await db.unassign_line_from_session(client_id)
    
    # Вилучаємо reply markup у клієнта
    if session['client_message_id']:
        try:
            await bot.edit_message_reply_markup(
                chat_id=client_id,
                message_id=session['client_message_id'],
                reply_markup=None
            )
        except Exception as e:
            print(f"Помилка видалення кнопки у клієнта: {e}")
            
    try:
        kbd = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⏳ Очікування номера...")]],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )
        await bot.send_message(
            chat_id=client_id,
            text="Номер відкріплено. Будь ласка, очікуйте нового призначення.",
            reply_markup=kbd
        )
    except Exception as e:
        print(f"Помилка надсилання повідомлення про відкріплення клієнту: {e}")
            
    await callback.answer("Лінію звільнено!")
    await callback.message.answer(f"Лінію {line_id} для клієнта @{session['username']} успішно звільнено. Статус сесії скинуто.")
    await show_next_assignment_menu(callback.message, client_id, edit=True)

@router.callback_query(F.data.startswith("completesession_"))
async def handle_complete_session_manually(callback: CallbackQuery, bot: Bot):
    """Ручне успішне завершення сесії верифікації клієнта"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[1])
    
    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return
        
    try:
        kbd = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📋 Мої дані")]],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )
        await bot.send_message(
            chat_id=client_id,
            text="Роботу завершено. Дякуємо за співпрацю.",
            reply_markup=kbd
        )
    except Exception as e:
        print(f"Не вдалося надіслати клієнту повідомлення: {e}")
        
    await db.close_session(client_id)
    
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(f"Сесію для клієнта @{session['username']} успішно завершено.")
    await callback.answer("Сесію завершено!")

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

    import html
    remaining_text = ", ".join(remaining_banks)
    username_esc = html.escape(session['username'] or "Невідомий")
    remaining_text_esc = html.escape(remaining_text)
    text = (
        f"Оберіть лінію для наступного банку для @{username_esc}:\n"
        f"• Залишилося пройти банки: {remaining_text_esc}\n\n"
        f"Оберіть лінію для призначення:"
    )

    if not filtered_lines:
        text += "\n\nПопередження: немає вільних ліній для решти банків! Додайте нові номери прямо в чат або вивільніть існуючі лінії."

    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")

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

