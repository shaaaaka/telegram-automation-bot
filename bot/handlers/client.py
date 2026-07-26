from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, FSInputFile
from aiogram.fsm.context import FSMContext
from bot.config import (
    BANK_TEMPLATES, get_template_photo, get_admin_id, DEFAULT_METHOD_KEY,
    PUMB_NEW_REG_INSTRUCTION, PUMB_RELINK_INSTRUCTION, PUMB_NEW_REG_EXAMPLES_DIR
)
import bot.database as db
import re
import asyncio
import logging
import time
import os

from bot.handlers.client_helpers import *
logger = logging.getLogger(__name__)
router = Router()

_client_reply_cooldowns = {}

def should_send_client_reply(client_id: int, key: str = "default", cooldown: float = 3.0) -> bool:
    """Перевіряє, чи не було аналогічної відповіді клієнту протягом останніх cooldown секунд (для захисту від дублів у альбомах/флуді)"""
    now = time.time()
    cache_key = (client_id, key)
    last_time = _client_reply_cooldowns.get(cache_key, 0)
    if now - last_time < cooldown:
        return False
    _client_reply_cooldowns[cache_key] = now
    return True
@router.message(F.text == "/id")
async def cmd_get_chat_id(message: Message):
    await message.answer(f"ID цього чату: <code>{message.chat.id}</code>", parse_mode="HTML")

@router.message(F.chat.type == "private", F.text == "⏳ Очікування номера...")
async def handle_waiting_number_text(message: Message):
    """Обробник натискання кнопки очікування номера"""
    await message.answer("Будь ласка, зачекайте, поки адміністратор призначить вам номер телефону для початку верифікації.")
@router.message(CommandStart(), F.chat.type == "private")
@router.message(F.chat.type == "private", F.text.in_({"Розпочати знову", "🔄 Розпочати знову"}))
async def cmd_start(message: Message, state: FSMContext):
    """Обробник команди /start для клієнта"""
    # Якщо адмін пише просто /start без deep link — показуємо адмін-меню
    # Якщо є deep link параметр — запускаємо клієнт-флоу (для тестування різних методів)
    is_admin_user = message.from_user.id == get_admin_id()
    has_start_param = bool(message.text and message.text.startswith("/start ") and message.text.split(" ", 1)[1].strip())
    if is_admin_user and not has_start_param:
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

    # Перевірка режиму сну
    from bot.sleep_mode import is_in_sleep_mode
    if is_in_sleep_mode():
        from bot.config import get_cached_setting
        reply_text = get_cached_setting("sleep_mode_reply", "На жаль, зараз не робочий час. Поверніться пізніше.")
        await message.answer(reply_text, reply_markup=ReplyKeyboardRemove())
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

    # Визначаємо метод з deep link (/start wolf, /start manager_x)
    start_param = ""
    method_key = DEFAULT_METHOD_KEY
    if message.text and message.text.startswith("/start "):
        start_param = message.text.split(" ", 1)[1].strip()
        method = await db.get_verification_method(start_param)
        if method and method.get('is_active'):
            method_key = start_param
        else:
            start_param = ""

    await db.create_registering_session(client_id, username_db, method_key=method_key, start_param=start_param)
    await register_reg_msg(state, message.message_id)
    
    # Перевіряємо можливість автозаповнення з попередньої/поточної сесії (тільки для методів з ПІБ/Дата/ІПН)
    method = await db.get_verification_method(method_key)
    required_fields = await db.get_method_required_fields(method_key)
    has_pib_dob_ipn = {"pib", "dob", "ipn"}.issubset(set(required_fields))

    if has_pib_dob_ipn and existing_session and existing_session['client_data']:
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
            await state.update_data(welcome_msg_ids=[msg.message_id], old_pib=pib, old_dob=dob, old_ipn=ipn, method_key=method_key)
            await state.set_state(RegistrationStates.waiting_pib_dob)
            return

    # Для методів з ask_relink_at_start спочатку чекаємо вибору банку адміном
    if method and method.get('ask_relink_at_start'):
        await wait_for_admin_bank_selection(client_id, message.bot, state, method_key, username_db, start_param)
        return

    # Інакше одразу запускаємо збір даних/скріншотів
    await _start_method_flow(message, state, method_key, is_relink=0)
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
async def continue_client_flow(client_id: int, bot: Bot, client_state: FSMContext, method_key: str, is_relink: int = 0):
    """Запускає збір текстових полів або скріншотів для обраного методу"""
    await db.update_session_is_relink(client_id, is_relink)

    method = await db.get_verification_method(method_key)
    required_fields = await db.get_method_required_fields(method_key)

    initial_message = method.get('initial_message') if method else None
    if not initial_message:
        initial_message = "Напишіть мені будь ласка Ваші\nПІБ та Дату Народження"

    await db.update_session_client_phone(client_id, None)

    if required_fields:
        if required_fields == ["pib", "dob", "ipn"]:
            pib_msg = await bot.send_message(chat_id=client_id, text=initial_message, reply_markup=get_cancel_keyboard())
            await register_reg_msg(client_state, pib_msg.message_id)
            await client_state.update_data(pib_prompt_msg_id=pib_msg.message_id, method_key=method_key)
            await client_state.set_state(RegistrationStates.waiting_pib_dob)
        else:
            msg = await bot.send_message(chat_id=client_id, text=initial_message, reply_markup=get_cancel_keyboard())
            await register_reg_msg(client_state, msg.message_id)
            await client_state.update_data(
                method_key=method_key,
                required_fields=required_fields,
                current_field_idx=0,
                collected_data={}
            )
            await client_state.set_state(RegistrationStates.collecting_method_field)
    else:
        # Спеціальний флоу для ПУМБ (diia_screens) — нова реєстрація vs перев'яз
        if method and method.get('key') == 'diia_screens':
            if is_relink:
                msg = await bot.send_message(chat_id=client_id, text=PUMB_RELINK_INSTRUCTION, reply_markup=get_cancel_keyboard())
                await register_reg_msg(client_state, msg.message_id)
                await client_state.update_data(
                    method_key=method_key,
                    required_screenshots=1,
                    collected_screenshots=[],
                    collected_data={}
                )
                await client_state.set_state(RegistrationStates.waiting_method_screenshots)
            else:
                # Нова реєстрація: інструкція + приклади фото
                instruction_msg = await bot.send_message(chat_id=client_id, text=PUMB_NEW_REG_INSTRUCTION, reply_markup=get_cancel_keyboard())
                await register_reg_msg(client_state, instruction_msg.message_id)

                # Шукаємо будь-які фото у папці прикладів
                valid_paths = []
                if os.path.isdir(PUMB_NEW_REG_EXAMPLES_DIR):
                    for fname in sorted(os.listdir(PUMB_NEW_REG_EXAMPLES_DIR)):
                        if fname.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            valid_paths.append(os.path.join(PUMB_NEW_REG_EXAMPLES_DIR, fname))

                if valid_paths:
                    from aiogram.types import InputMediaPhoto
                    media = [InputMediaPhoto(media=FSInputFile(p), caption="Приклад" if idx == 0 else None) for idx, p in enumerate(valid_paths)]
                    try:
                        await bot.send_media_group(chat_id=client_id, media=media)
                    except Exception as e:
                        logger.error("Помилка надсилання прикладів фото для ПУМБ: %s", e)
                else:
                    logger.warning("Приклади фото для ПУМБ не знайдено у %s", PUMB_NEW_REG_EXAMPLES_DIR)

                await client_state.update_data(
                    method_key=method_key,
                    required_screenshots=method.get('required_screenshots', 0) if method else 0,
                    collected_screenshots=[],
                    collected_data={}
                )
                await client_state.set_state(RegistrationStates.waiting_method_screenshots)
        else:
            screenshot_instructions = method.get('screenshot_instructions') if method else "Надішліть, будь ласка, необхідні скріншоти."
            msg = await bot.send_message(chat_id=client_id, text=screenshot_instructions, reply_markup=get_cancel_keyboard())
            await register_reg_msg(client_state, msg.message_id)
            await client_state.update_data(
                method_key=method_key,
                required_screenshots=method.get('required_screenshots', 0) if method else 0,
                collected_screenshots=[],
                collected_data={}
            )
            await client_state.set_state(RegistrationStates.waiting_method_screenshots)

async def _start_method_flow(message: Message, state: FSMContext, method_key: str, is_relink: int = 0):
    """Запускає збір даних одразу (для методів без очікування вибору банку)"""
    await continue_client_flow(message.from_user.id, message.bot, state, method_key, is_relink)

async def ask_start_relink_choice(client_id: int, bot: Bot, client_state: FSMContext, method_key: str):
    """Запитуємо клієнта про тип верифікації після вибору банку адміном"""
    await client_state.update_data(method_key=method_key)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 Нова реєстрація", callback_data=f"start_relink_new_{method_key}")],
        [InlineKeyboardButton(text="🔄 Перев'яз існуючого акаунту", callback_data=f"start_relink_relink_{method_key}")]
    ])
    msg = await bot.send_message(
        chat_id=client_id,
        text="Оберіть, будь ласка, тип верифікації:",
        reply_markup=keyboard
    )
    await register_reg_msg(client_state, msg.message_id)
    await client_state.set_state(RegistrationStates.waiting_start_relink_choice)

async def wait_for_admin_bank_selection(client_id: int, bot: Bot, state: FSMContext, method_key: str, username: str, start_param: str = None):
    """Ставимо клієнта в очікування, поки адмін не обере банк"""
    await state.set_state(RegistrationStates.waiting_admin_bank_selection)
    await db.set_session_status(client_id, 'waiting_admin_bank_selection')
    wait_msg = await bot.send_message(
        chat_id=client_id,
        text="Будь ласка, зачекайте. Адміністратор обирає банк для верифікації..."
    )
    await register_reg_msg(state, wait_msg.message_id)
    await notify_admin_for_bank_selection(client_id, username, "Очікує вибору банку адміністратором", bot, method_key=method_key, start_param=start_param)

@router.callback_query(RegistrationStates.waiting_start_relink_choice, F.data.startswith("start_relink_"))
async def handle_start_relink_choice(callback: CallbackQuery, state: FSMContext):
    """Обробник вибору Нова реєстрація / Перев'яз після вибору банку"""
    data = callback.data
    is_relink = None
    method_key = None

    prefix_new = "start_relink_new_"
    prefix_relink = "start_relink_relink_"
    if data.startswith(prefix_new):
        method_key = data[len(prefix_new):]
        is_relink = 0
    elif data.startswith(prefix_relink):
        method_key = data[len(prefix_relink):]
        is_relink = 1
    else:
        await callback.answer("Невідомий вибір", show_alert=True)
        return

    await callback.answer("Нова реєстрація" if is_relink == 0 else "Перев'яз акаунту")
    try:
        await callback.message.delete()
    except Exception:
        pass

    client_id = callback.from_user.id
    await db.update_session_is_relink(client_id, is_relink)
    await continue_client_flow(client_id, callback.bot, state, method_key, is_relink)

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

    # Шукаємо ІПН (10 цифр, перша не нуль)
    ipn_match = re.search(r'\b([1-9]\d{9})\b', text)
    if ipn_match:
        ipn_val = ipn_match.group(1)
        await state.update_data(ipn=ipn_val)
        text = text.replace(ipn_val, '').strip()

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
        
        # Перевіряємо, чи ми вже розпізнали ІПН на попередньому кроці
        state_data = await state.get_data()
        saved_ipn = state_data.get('ipn')
        
        if saved_ipn:
            confirm_text = (
                f"Перевірте ваші дані:\n\n"
                f"ІПН: {saved_ipn}\n"
                f"ПІБ: {saved_pib}\n"
                f"Дата народження: {saved_dob}"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Підтвердити та надіслати", callback_data="confirm_reg")],
                [InlineKeyboardButton(text="🔄 Заповнити заново", callback_data="restart_reg")]
            ])
            msg = await message.answer(confirm_text, reply_markup=keyboard, parse_mode="Markdown")
            await register_reg_msg(state, msg.message_id)
            await state.set_state(RegistrationStates.waiting_confirm)
        else:
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
    
    # Зберігаємо метод, якщо він є в стані
    state_data = await state.get_data()
    method_key = state_data.get('method_key')
    start_param = state_data.get('start_param')
    if method_key:
        await db.update_session_method(client_id, method_key)
    if start_param:
        await db.update_session_start_param(client_id, start_param)
        
    msg = await callback.message.answer(
        "Зачекайте будь ласка кілька хвилин",
        reply_markup=get_waiting_keyboard()
    )
    await db.update_session_waiting_message_id(client_id, msg.message_id)
    await callback.answer("Дані підтверджено!")

    # Сповіщаємо адміна для вибору банків
    await notify_admin_for_bank_selection(client_id, username, client_data, bot, method_key=method_key, start_param=start_param)
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
    client_id = message.from_user.id
    session = await db.get_session(client_id)

    if session and session.get('client_phone'):
        # Якщо в базі вже є збережений номер, просто використовуємо його
        await continue_after_phone(message, state, message.bot, client_id)
        return

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

    # 1. Пряме детерміноване розпізнавання номера телефону через регулярні вирази
    phone_digits = re.sub(r'\D', '', text)
    extracted_phone = None
    if len(phone_digits) == 10 and phone_digits.startswith('0'):
        extracted_phone = "+38" + phone_digits
    elif len(phone_digits) == 12 and phone_digits.startswith('380'):
        extracted_phone = "+" + phone_digits
    elif len(phone_digits) == 9 and not phone_digits.startswith('0'):
        extracted_phone = "+380" + phone_digits

    if extracted_phone:
        logger.info(f"Phone number '{extracted_phone}' recognized directly via regex for client {client_id}")
        await db.update_session_client_phone(client_id, extracted_phone)
        await message.answer("Дякую! Номер телефону прийнято.")
        await continue_after_phone(message, state, bot, client_id)
        return

    # 2. Якщо номер не підходить під дефолтний формат, використовуємо ШІ для аналізу (відмова, запитання тощо)
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
                    chat_id=get_admin_id(),
                    text=f"⚠️ <b>Увага!</b> Клієнт @{username} (ID: {client_id}) відмовився надавати номер телефону.\nПовідомлення клієнта: <i>{text}</i>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Не вдалося надіслати сповіщення адміну про відмову телефону: {e}")
        
        # Якщо ШІ не розпізнав номер, просимо повторити (надсилаємо очищену відповідь ШІ)
        clean_text = re.sub(r'\[[^\]]*\]?', '', response).strip()
        await message.answer(clean_text or "Будь ласка, надішліть коректний номер телефону.")
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
@router.message(no_code_message_filter, StateFilter("*"))
async def handle_universal_no_code(message: Message, state: FSMContext, bot: Bot):
    """Універсальний обробник повідомлень про відсутність коду (працює в будь-якому FSM стані)"""
    # Завжди відповідаємо клієнту шаблонною фразою, не змінюючи статус сесії в БД та не сповіщаючи адміна
    await message.answer("Ще не надійшов, ще чекаємо")
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
            if should_send_client_reply(client_id, key="registered_wait", cooldown=3.0):
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

        from bot.services.ai_task_manager import register_ai_task, unregister_ai_task, is_session_ai_paused
        current_task = asyncio.current_task()
        if current_task:
            register_ai_task(client_id, current_task)

        try:
            from bot.openai_client import get_support_response
            response = await get_support_response(
                user_text=message.text,
                client_data=client_data,
                current_bank_name=current_bank_name,
                chat_history=chat_history,
                sent_codes_count=sent_codes_count
            )
            
            if await is_session_ai_paused(client_id):
                logger.info(f"🛑 AI response cancelled for client {client_id} (paused in DB)")
                return

            # Імітація людського друку перед надсиланням відповіді
            import random
            char_count = len(response)
            delay = min(7.0, max(3.0, char_count / 15.0)) + random.uniform(-0.5, 1.0)
            delay = max(3.0, min(8.0, delay))
            await simulate_typing(bot, client_id, delay)
            
            if await is_session_ai_paused(client_id):
                logger.info(f"🛑 AI response cancelled for client {client_id} before sending answer")
                return

            if "[SUCCESS_VERIFICATION]" in response:
                bank_label = current_bank_name if current_bank_name else "банк"
                await state.update_data(support_requests_count=0)
                
                success_text = None
                if current_bank_name:
                    template = await db.get_bank_template_db(current_bank_name)
                    if template and template.get('success_text'):
                        success_text = template['success_text']
                
                prompt_msg = success_text or f"Чудово! Будь ласка, надішліть скріншот, який підтверджує успішну реєстрацію в {bank_label}."
                await message.answer(
                    prompt_msg,
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

            raw_parts = re.split(r'\[SPLIT\]?', response, flags=re.IGNORECASE)
            clean_parts = []
            for part in raw_parts:
                clean_part = re.sub(r'\[[^\]]*\]?', '', part).strip()
                if clean_part:
                    clean_parts.append(clean_part)

            for i, part in enumerate(clean_parts):
                if await is_session_ai_paused(client_id):
                    logger.info(f"🛑 AI response cancelled for client {client_id} during part sending")
                    return
                try:
                    await bot.send_chat_action(chat_id=client_id, action="typing")
                except Exception:
                    pass
                import random
                char_count = len(part)
                delay = min(4.0, max(1.5, char_count / 15.0)) + random.uniform(-0.3, 0.5)
                await asyncio.sleep(delay)
                
                if await is_session_ai_paused(client_id):
                    logger.info(f"🛑 AI response cancelled for client {client_id} during part sending sleep")
                    return

                is_last = (i == len(clean_parts) - 1)
                reply_markup = ReplyKeyboardRemove() if is_last else None
                await message.answer(part, reply_markup=reply_markup)
        except asyncio.CancelledError:
            logger.info(f"🛑 AI Task cancelled via CancelledError for client {client_id}")
            return
        finally:
            unregister_ai_task(client_id, current_task)

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

        # Якщо в відповіді ШІ згадується мультивалютна карта для bank.kd, додатково надсилаємо фото-інструкцію (лише один раз за сесію)
        is_bank_kd = current_bank_name and "bank.kd" in current_bank_name.lower()
        if is_bank_kd and any(word in response.lower() for word in ["мультивалютн"]):
            state_data = await state.get_data()
            if not state_data.get("bank_kd_cards_photo_sent"):
                import os
                from aiogram.types import FSInputFile
                cards_photo_path = os.path.join(os.path.dirname(__file__), "..", "resources", "images", "bank.kd_cards_instruction.png")
                if os.path.exists(cards_photo_path):
                    try:
                        await bot.send_photo(
                            chat_id=client_id,
                            photo=FSInputFile(cards_photo_path)
                        )
                        await state.update_data(bank_kd_cards_photo_sent=True)
                    except Exception as e:
                        logger.error(f"Error sending bank.kd card choice instruction photo in text: {e}")
        return

    # Якщо користувач не у стані анкетування, пропонуємо йому почати з команди /start
    await message.answer("Для початку верифікації напишіть **/start**.", parse_mode="Markdown")
@router.message(StateFilter(None), F.chat.type == "private", F.photo)
async def handle_client_photo(message: Message, state: FSMContext, bot: Bot):
    """Обробник скріншоту від користувача (ШІ розпізнавання помилок)"""
    client_id = message.from_user.id
    
    # Якщо це частина альбому (media_group_id) і відповідь уже надсилалася — ігноруємо дубль
    if message.media_group_id and not should_send_client_reply(client_id, key=f"mg_{message.media_group_id}", cooldown=5.0):
        logger.info(f"Skipping duplicate media_group response for client {client_id}, mg: {message.media_group_id}")
        return

    # Перевіряємо, чи є вже активна сесія
    existing_session = await db.get_session(client_id)
    if existing_session:
        if existing_session.get('is_paused'):
            logger.info(f"AI bot is paused for client {client_id}. Ignoring automatic AI photo support response.")
            return
        if existing_session['status'] == 'registered':
            if should_send_client_reply(client_id, key="registered_wait", cooldown=3.0):
                await message.answer("Будь ласка, зачекайте, поки адміністратор призначить вам номер телефону для початку верифікації.")
            return
        elif existing_session['status'] == 'waiting_verification':
            if int(existing_session.get('waiting_proceedings') or 0) == 1:
                # Дозволяємо надсилання скріншоту
                pass
            else:
                if should_send_client_reply(client_id, key="verif_wait", cooldown=3.0):
                    await message.answer("Ваша анкета знаходиться на перевірці у верифікатора. Будь ласка, зачекайте.")
                return
        elif existing_session['status'] not in ('number_assigned', 'waiting_code'):
            if should_send_client_reply(client_id, key="start_prompt", cooldown=3.0):
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
        

        
        from bot.services.ai_task_manager import register_ai_task, unregister_ai_task, is_session_ai_paused
        current_task = asyncio.current_task()
        if current_task:
            register_ai_task(client_id, current_task)

        try:
            from bot.openai_client import get_support_response
            response = await get_support_response(
                user_text=message.caption,
                image_bytes=photo_data,
                client_data=client_data,
                current_bank_name=current_bank_name,
                sent_codes_count=sent_codes_count
            )
            
            if await is_session_ai_paused(client_id):
                logger.info(f"🛑 AI photo response cancelled for client {client_id} (paused in DB)")
                return

            # Імітація людського друку перед надсиланням відповіді
            import random
            char_count = len(response)
            delay = min(7.0, max(3.0, char_count / 15.0)) + random.uniform(-0.5, 1.0)
            delay = max(3.0, min(8.0, delay))
            await simulate_typing(bot, client_id, delay)

            if await is_session_ai_paused(client_id):
                logger.info(f"🛑 AI photo response cancelled for client {client_id} before sending answer")
                return
        except asyncio.CancelledError:
            logger.info(f"🛑 AI photo Task cancelled via CancelledError for client {client_id}")
            return
        finally:
            unregister_ai_task(client_id, current_task)
        
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
            
            # --- Робота з кількома скріншотами ---
            # Якщо банк змінився, скидаємо список
            last_verified_bank = state_data.get("last_verified_bank")
            uploaded_screenshots = state_data.get("uploaded_screenshots") or []
            if last_verified_bank != current_bank_name:
                uploaded_screenshots = []
                await state.update_data(uploaded_screenshots=[], last_verified_bank=current_bank_name)

            # Отримуємо ліміт скріншотів для поточного банку
            key, template = await db.get_bank_template_with_key_db(current_bank_name)
            required_count = 1
            if template and template.get('required_screenshots'):
                try:
                    required_count = int(template['required_screenshots'])
                except Exception:
                    pass

            if photo.file_id not in [s['file_id'] for s in uploaded_screenshots]:
                uploaded_screenshots.append({
                    'file_id': photo.file_id,
                    'card_first4': card_first4,
                    'card_last4': card_last4
                })
                await state.update_data(uploaded_screenshots=uploaded_screenshots)

            if len(uploaded_screenshots) < required_count:
                remaining = required_count - len(uploaded_screenshots)
                # Повідомляємо клієнта про необхідність надіслати наступний скріншот
                await message.answer(f"Дякую! Скріншот прийнято. Будь ласка, надішліть наступний скріншот (залишилось завантажити: {remaining}).")
                return

            # Об'єднуємо всі file_id через кому, щоб зберегти історію в БД
            success_photos_str = ",".join([s['file_id'] for s in uploaded_screenshots])
            
            await state.update_data(success_photo_id=photo.file_id)
            await db.update_session_verification_data(
                client_id, 
                success_photo_id=success_photos_str, 
                card_first4=card_first4, 
                card_last4=card_last4
            )

            if is_lvivbank:
                if existing_session and existing_session.get('client_phone'):
                    # Якщо є збережений телефон для lvivbank, відразу продовжуємо
                    await continue_after_phone(message, state, bot, client_id)
                else:
                    success_text = (
                        "Дякую! Усі скріншоти прийнято.\n\n"
                        "Будь ласка, напишіть Ваш номер телефону?"
                    )
                    await message.answer(success_text, reply_markup=ReplyKeyboardRemove())
                    await state.set_state(RegistrationStates.waiting_phone)
            else:
                state_data = await state.get_data()
                if state_data.get('is_relink'):
                    success_text = (
                        "Дякую! Усі скріншоти прийнято.\n\n"
                        "Який пін-код стояв на застосунку?"
                    )
                else:
                    success_text = (
                        "Дякую! Усі скріншоти прийнято.\n\n"
                        "Який пін-код чи пароль ставали на додаток?"
                    )
                await message.answer(success_text, reply_markup=ReplyKeyboardRemove())
                await state.set_state(RegistrationStates.waiting_password)
            return
        else:
            if "[OFFER_AMOBANK_INSTRUCTIONS]" in response:
                await state.set_state(RegistrationStates.waiting_amobank_instruction_confirm)
            if "[OFFER_LVIV_SUCCESS_SCREEN]" in response:
                await state.set_state(RegistrationStates.waiting_lviv_success_confirm)

            raw_parts = re.split(r'\[SPLIT\]?', response, flags=re.IGNORECASE)
            clean_parts = []
            for part in raw_parts:
                clean_part = re.sub(r'\[[^\]]*\]?', '', part).strip()
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
@router.callback_query(F.data == "wrongcode_yes")
async def handle_wrongcode_yes(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    
    await callback.message.answer(
        "Запросіть новий SMS-код у додатку банку. Як тільки зробите це — напишіть мені «новий код» або «потрібен код».",
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
            "Запросіть новий SMS-код у додатку банку. Як тільки зробите це — напишіть мені «новий код» або «потрібен код».",
            parse_mode="Markdown"
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

@router.message(RegistrationStates.waiting_deletion_proof, F.chat.type == "private")
async def process_deletion_proof(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    raw_bank = data.get('bank_name')
    template_data = await db.get_bank_template_db(raw_bank) if raw_bank else None
    
    # Визначаємо гарне відображення назви банку
    bank_name = (template_data.get('display_name') if template_data and template_data.get('display_name') else raw_bank) or "банку"
    deletion_req = template_data.get('deletion_requirement', 'none') if template_data else 'none'
    proof_label = "скріншот" if deletion_req == 'screenshot' else "відео"
    
    media_id = None
    media_type = None
    
    if message.photo:
        media_id = message.photo[-1].file_id
        media_type = 'photo'
    elif message.video:
        media_id = message.video.file_id
        media_type = 'video'
    elif message.document:
        mime = message.document.mime_type or ""
        if mime.startswith('image/'):
            media_id = message.document.file_id
            media_type = 'photo'
        elif mime.startswith('video/'):
            media_id = message.document.file_id
            media_type = 'video'
            
    if not media_id:
        await message.answer(f"Будь ласка, надішліть саме {proof_label} видалення додатку {bank_name} для підтвердження.")
        return

    # Надсилаємо статус перевірки
    status_msg = await message.answer("Хвилинку")
    
    try:
        # Завантажуємо медіа
        from io import BytesIO
        file_info = await bot.get_file(media_id)
        file_buffer = BytesIO()
        await bot.download_file(file_info.file_path, file_buffer)
        media_bytes = file_buffer.getvalue()
        
        # Викликаємо ШІ-верифікацію із передачею конкретної назви банку
        from bot.openai_client import verify_deletion_proof as ai_verify
        is_valid, reason = await ai_verify(media_bytes, media_type, bank_name=bank_name)
        
        # Видаляємо статус-повідомлення
        try:
            await status_msg.delete()
        except Exception:
            pass
            
        if is_valid:
            await state.update_data(deletion_proof_media=media_id, deletion_proof_type=media_type)
            await continue_after_phone(message, state, bot, message.from_user.id)
        else:
            fail_text = f"{proof_label.capitalize()} не прийнято."
            if reason:
                fail_text += f" {reason}"
            fail_text += f" Надішліть інший {proof_label}, будь ласка."
            await message.answer(fail_text)
            
    except Exception as e:
        logger.error(f"Помилка при авто-перевірці доказу: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass
        # У разі критичної помилки дозволяємо пройти далі, щоб не блокувати користувача
        await message.answer("Виникла технічна затримка під час авто-перевірки, але ваш файл збережено для ручної перевірки оператором. Продовжуємо...")
        await state.update_data(deletion_proof_media=media_id, deletion_proof_type=media_type)
        await continue_after_phone(message, state, bot, message.from_user.id)

@router.callback_query(F.data.startswith("relink_choice_"))
async def handle_relink_choice(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split("_")
    choice = parts[2]  # "relink" or "fresh"
    line_id = int(parts[3])
    bank_key = "_".join(parts[4:])
    
    template_data = await db.get_bank_template_db(bank_key)
    bank_name = (template_data.get('display_name') if template_data and template_data.get('display_name') else bank_key) or bank_key
    
    if choice == "relink":
        await state.update_data(is_relink=True, bank_name=bank_key, assign_line_id=line_id)
        await state.set_state(RegistrationStates.waiting_relink_initial_screenshot)
        
        relink_msg = (template_data.get('relink_instruction_text') if template_data else None) or (
            f"Надішліть, будь ласка, скріншот Головного екрану або вкладки Картки у додатку {bank_name}, щоб перевірити стан акаунту."
        )
        try:
            await callback.message.edit_text(relink_msg)
        except Exception:
            await callback.message.answer(relink_msg)
        await callback.answer("Обрано Перев'яз")
    else:
        client_id = callback.from_user.id
        await state.update_data(is_relink=False, bank_name=bank_key)
        try:
            await callback.message.delete()
        except Exception:
            pass
        from bot.services.line_assignment import send_assigned_phone_to_client
        await send_assigned_phone_to_client(client_id, line_id, bot, is_relink=False)
        await db.set_session_status(client_id, 'number_assigned')
        await state.set_state(RegistrationStates.waiting_code)
        await callback.answer("Обрано Нову реєстрацію")

@router.message(RegistrationStates.waiting_relink_initial_screenshot, F.chat.type == "private")
async def process_relink_initial_screenshot(message: Message, state: FSMContext, bot: Bot):
    media_id = None
    media_type = None
    
    if message.photo:
        media_id = message.photo[-1].file_id
        media_type = 'photo'
    elif message.document:
        mime = message.document.mime_type or ""
        if mime.startswith('image/'):
            media_id = message.document.file_id
            media_type = 'photo'

    if not media_id:
        await message.answer("Будь ласка, надішліть саме скріншот додатку для перевірки.")
        return

    data = await state.get_data()
    bank_key = data.get('bank_name') or "bank"
    line_id = data.get('assign_line_id')
    template_data = await db.get_bank_template_db(bank_key)
    bank_name = (template_data.get('display_name') if template_data and template_data.get('display_name') else bank_key) or bank_key

    status_msg = await message.answer("Хвилинку")

    try:
        from io import BytesIO
        file_info = await bot.get_file(media_id)
        file_buffer = BytesIO()
        await bot.download_file(file_info.file_path, file_buffer)
        media_bytes = file_buffer.getvalue()

        from bot.openai_client import verify_relink_initial_screenshot as ai_verify_relink
        is_valid, reason = await ai_verify_relink(media_bytes, bank_name=bank_name)

        try:
            await status_msg.delete()
        except Exception:
            pass

        if is_valid:
            client_id = message.from_user.id
            
            await state.update_data(initial_relink_photo_id=media_id, is_relink=True)
            await db.set_session_status(client_id, 'number_assigned')
            
            # Повідомляємо клієнту про успішну перевірку та надсилаємо призначений номер
            await message.answer("Акаунт перевірено, все ок! 👍")
            
            from bot.services.line_assignment import send_assigned_phone_to_client
            await send_assigned_phone_to_client(client_id, line_id, bot, is_relink=True)
            await state.set_state(RegistrationStates.waiting_code)
            
            # Сповіщаємо адміна / гівера про Перев'яз
            from bot.config import get_admin_id
            username = message.from_user.username or "Немає юзернейму"
            admin_msg = (
                f"🔄 <b>[ПЕРЕВ'ЯЗ] Початок зміни номера!</b>\n"
                f"• Клієнт: @{username} (ID: {client_id})\n"
                f"• Банк: {bank_name}\n"
                f"• Стан акаунту: ✅ Активний (перевірено ШІ)\n"
                f"• Лінія: Line {line_id}"
            )
            await bot.send_message(chat_id=get_admin_id(), text=admin_msg, parse_mode="HTML")
        else:
            await message.answer(
                f"Скріншот не прийнято. {reason}\nНадішліть інший скріншот додатку {bank_name}, будь ласка."
            )
    except Exception as e:
        logger.error(f"Помилка при авто-перевірці первинного скріншота перев'язу: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await message.answer("Виникла технічна затримка під час авто-перевірки. Надішліть скріншот ще раз.")


@router.message(RegistrationStates.collecting_method_field, F.chat.type == "private")
async def process_method_field(message: Message, state: FSMContext, bot: Bot):
    """Універсальний обробник збору текстових полів методу верифікації"""
    state_data = await state.get_data()
    method_key = state_data.get('method_key', 'volk')
    required_fields = state_data.get('required_fields', [])
    current_idx = state_data.get('current_field_idx', 0)
    collected_data = state_data.get('collected_data', {})

    method = await db.get_verification_method(method_key)
    if not method or not required_fields or current_idx >= len(required_fields):
        await message.answer("Помилка: метод не знайдено або всі поля вже зібрані. Спробуйте /start.")
        await state.clear()
        return

    field_key = required_fields[current_idx]
    is_valid, value_or_error = validate_method_field(field_key, message.text or "")

    if not is_valid:
        await message.answer(f"{value_or_error}\n\n{get_field_prompt(field_key, method)}", reply_markup=get_cancel_keyboard())
        return

    collected_data[field_key] = value_or_error
    current_idx += 1

    if current_idx >= len(required_fields):
        # Всі поля зібрані
        await state.update_data(collected_data=collected_data)
        await _finish_method_collection(message, state, bot, method, collected_data)
        return

    # Запитуємо наступне поле
    next_field = required_fields[current_idx]
    await state.update_data(current_field_idx=current_idx, collected_data=collected_data)
    next_prompt = get_field_prompt(next_field, method)
    msg = await message.answer(next_prompt, reply_markup=get_cancel_keyboard())
    await register_reg_msg(state, msg.message_id)


@router.message(RegistrationStates.waiting_method_screenshots, F.chat.type == "private")
async def process_method_screenshots(message: Message, state: FSMContext, bot: Bot):
    """Обробник збору скріншотів для методів без текстових полів"""
    state_data = await state.get_data()
    method_key = state_data.get('method_key', 'diia_screens')
    required_screenshots = state_data.get('required_screenshots', 0)
    collected_screenshots = state_data.get('collected_screenshots', [])

    if not message.photo:
        await message.answer("Будь ласка, надішліть скріншот фото.")
        return

    photo_id = message.photo[-1].file_id
    collected_screenshots.append(photo_id)

    if len(collected_screenshots) < required_screenshots:
        remaining = required_screenshots - len(collected_screenshots)
        await state.update_data(collected_screenshots=collected_screenshots)
        await message.answer(f"Залишилося ще {remaining} скріншот(ів).")
        return

    # Всі скріншоти зібрані
    await state.update_data(collected_screenshots=collected_screenshots)
    method = await db.get_verification_method(method_key)
    await _finish_method_screenshots(message, state, bot, method, collected_screenshots)


async def _finish_method_collection(message: Message, state: FSMContext, bot: Bot, method: dict, collected_data: dict):
    """Завершення збору текстових полів: створення сесії та сповіщення адміна"""
    client_id = message.from_user.id
    username = message.from_user.username or "Немає юзернейму"
    state_data = await state.get_data()
    start_param = state_data.get('start_param')

    client_data = format_client_data_from_method(collected_data, method)
    if message.from_user.username:
        client_data += f"\n\nДроп - @{message.from_user.username}"

    await db.create_or_update_session(client_id, username, client_data)
    await db.update_session_method(client_id, method['key'])
    if start_param:
        await db.update_session_start_param(client_id, start_param)

    await state.clear()

    waiting_msg = await message.answer("Зачекайте будь ласка кілька хвилин", reply_markup=get_waiting_keyboard())
    await db.update_session_waiting_message_id(client_id, waiting_msg.message_id)

    await notify_admin_after_data_collection(client_id, username, client_data, bot, method, start_param)


async def _finish_method_screenshots(message: Message, state: FSMContext, bot: Bot, method: dict, screenshots: list):
    """Завершення збору скріншотів: відправка адміну/верифікатору"""
    client_id = message.from_user.id
    username = message.from_user.username or "Немає юзернейму"
    state_data = await state.get_data()
    start_param = state_data.get('start_param')

    await db.create_or_update_session(client_id, username, '📷 Скріншоти верифікації')
    await db.update_session_method(client_id, method['key'])
    if start_param:
        await db.update_session_start_param(client_id, start_param)

    await state.clear()

    waiting_msg = await message.answer("Дякуємо! Скріншоти прийнято. Очікуйте перевірки.", reply_markup=get_waiting_keyboard())
    await db.update_session_waiting_message_id(client_id, waiting_msg.message_id)

    # Відправляємо скріншоти адміну для ручної обробки
    from aiogram.types import InputMediaPhoto
    from bot.config import get_admin_id
    caption = method.get('report_template') or f"Скріншоти верифікації (метод: {method['key']})\nДроп: @{username}\nstart: {start_param or '-'}"
    try:
        if len(screenshots) == 1:
            await bot.send_photo(chat_id=get_admin_id(), photo=screenshots[0], caption=caption)
        else:
            media = [InputMediaPhoto(media=photo_id, caption=caption if idx == 0 else None) for idx, photo_id in enumerate(screenshots)]
            await bot.send_media_group(chat_id=get_admin_id(), media=media)
    except Exception as e:
        logger.error(f"Помилка відправки скріншотів адміну: {e}")

    # Повідомляємо адміна, що можна призначати лінію
    await notify_admin_after_data_collection(client_id, username, f"📷 Скріншоти верифікації ({len(screenshots)} шт.)", bot, method, start_param)


async def notify_admin_after_data_collection(client_id: int, username: str, text: str, bot: Bot, method: dict, start_param: str = None):
    """Сповіщення адміна після збору даних: призначити лінію або обрати банк"""
    if method and method.get('ask_relink_at_start'):
        # Для ask_relink методів банк вже обраний — пропонуємо одразу призначити лінію
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📞 Призначити лінію", callback_data=f"reassignline_{client_id}")]
        ])
        try:
            await bot.send_message(
                chat_id=get_admin_id(),
                text=f"{text}\n\nДроп: @{username}\nstart: {start_param or '-'}\n\nБанк вже обрано. Можна призначати лінію.",
                reply_markup=markup,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Помилка надсилання адміну після збору даних: {e}")
    else:
        # Для інших методів — стандартний вибір банку
        await notify_admin_for_bank_selection(client_id, username, text, bot, method_key=method['key'] if method else None, start_param=start_param)
