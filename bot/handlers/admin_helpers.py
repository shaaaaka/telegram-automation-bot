import re
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
import bot.database as db

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
def is_admin(message_or_query) -> bool:
    from bot.config import get_admin_id
    return message_or_query.from_user.id == get_admin_id()
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
def is_direct_line_format(message: Message) -> bool:
    if not message.text:
        return False
    text = message.text.strip()
    f1 = bool(re.match(r'^(?:Line\s+)?(\d+)\s+Return:\s*(\d+)(?:\s+(.+))?$', text, re.IGNORECASE))
    f2 = bool(re.match(r'^\+?(\d{10,15})\s+([a-zA-Z0-9\.\-_ ]+)$', text))
    f3 = bool(re.match(r'^\+?(\d{10,15})$', text))
    return f1 or f2 or f3
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
