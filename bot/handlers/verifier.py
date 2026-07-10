import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, MessageReactionUpdated, ReplyKeyboardRemove
from bot.config import ANKETA_CHAT_ID, ADMIN_ID
import bot.database as db

logger = logging.getLogger(__name__)
router = Router()

async def process_approval(session: dict, bot: Bot, reply_to_message: Message = None, message_for_reply: Message = None):
    """Схвалення анкети дропа"""
    client_id = session['client_id']
    username = session['username'] or "Невідомий"
    
    # Оновлюємо статус в БД
    await db.set_session_verified(client_id, 1)
    await db.set_session_status(client_id, 'registered')
    
    # Відповідь верифікатору відключена за запитом користувача
    pass

    # Сповіщаємо адміна
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 <b>Анкету схвалено верифікатором!</b>\n• Дроп: @{username} (ID: {client_id})",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не вдалося сповістити адміна про схвалення: {e}")

async def process_rejection(session: dict, bot: Bot, ban: bool = True, reply_to_message: Message = None, message_for_reply: Message = None):
    """Відхилення анкети"""
    client_id = session['client_id']
    username = session['username'] or "Невідомий"
    
    if ban:
        # Блокуємо користувача в БД
        await db.ban_user(client_id, username)
        
        # Сповіщаємо клієнта про бан
        try:
            await bot.send_message(
                chat_id=client_id,
                text="Нажаль менеджер по певним причинам не хоче приймати від вас банки",
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error(f"Не вдалося сповістити клієнта {client_id} про бан: {e}")
            
        # Сповіщаємо адміна про бан
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"❌ <b>Анкету відхилено верифікатором!</b>\n• Дроп: @{username} (ID: {client_id}) заблокований.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не вдалося сповістити адміна про бан: {e}")
    else:
        # Просто сповіщаємо про відхилення без бану
        try:
            await bot.send_message(
                chat_id=client_id,
                text="Нажаль менеджер по певним причинам не хоче приймати від вас банки",
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error(f"Не вдалося сповістити клієнта {client_id} про відхилення: {e}")
            
        # Сповіщаємо адміна про відхилення без бану
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ <b>Анкету відхилено верифікатором (без блокування).</b>\n• Дроп: @{username} (ID: {client_id})",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не вдалося сповістити адміна про відхилення: {e}")

    # Прибираємо кнопку очікування у клієнта
    if session.get('waiting_message_id'):
        try:
            await bot.edit_message_reply_markup(
                chat_id=client_id,
                message_id=session['waiting_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
            
    # Закриваємо сесію
    await db.close_session(client_id)
    
    # Відповідь верифікатору відключена за запитом користувача
    pass

async def is_verifier_action(message: Message) -> bool:
    """Визначає, чи є повідомлення дією верифікатора"""
    if not message.text:
        return False
    text = message.text.strip().lower()
    logger.info(f"Checking message in verifier chat: '{text}' (reply: {message.reply_to_message is not None})")
    
    # 0. Якщо очікуємо відповідь на запитання про провадження
    session = await db.get_latest_waiting_verification_session()
    if session and session.get('proceedings_question_msg_id'):
        return True

    # 1. Схвалення (+)
    if text == "+" or text.startswith("+"):
        return True
        
    # 2. Відповідь (reply) на анкету
    if message.reply_to_message:
        reply_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        if "ІПН:" in reply_text or "ПІБ:" in reply_text:
            return True
            
    # 3. Відповідь на запитання про провадження
    if message.reply_to_message and message.reply_to_message.text == "Відкриті провадження?":
        return True
            
    # 4. Standalone команди для відхилення/чс
    reject_keywords = (
        "чс", "ч/с", "сдавал", "сдал", "сдавала", "делала", "була", "был", 
        "делал", "занят", "занята", "отказ", "отклон", "отклонить", "отклонено",
        "не подходит", "не подошел", "не подошла", "була вже", "був вже",
        "була уже", "був уже", "уже була", "уже був", "вже була", "вже був",
        "був", "була", "вже", "уже", "была", "был", "были", "провадження", "вп"
    )
    if text == "-" or text.startswith("-") or any(kw in text for kw in reject_keywords):
        return True
        
    return False

async def verifier_chat_filter(message: Message) -> bool:
    if message.chat.id != ANKETA_CHAT_ID:
        return False
    return await is_verifier_action(message)

async def process_proceedings_request(session: dict, bot: Bot):
    """Запит інформації про виконавчі провадження у клієнта"""
    client_id = session['client_id']
    
    # Встановлюємо статус waiting_proceedings = 1
    await db.set_session_waiting_proceedings(client_id, 1)
    
    # Сповіщаємо клієнта
    try:
        await bot.send_message(
            chat_id=client_id,
            text="у вас закриті провадження?"
        )
    except Exception as e:
        logger.error(f"Не вдалося відправити запит проваджень клієнту {client_id}: {e}")

@router.message(verifier_chat_filter)
async def handle_verifier_message(message: Message, bot: Bot):
    """Обробник повідомлень від верифікатора в робочому чаті"""
    if not message.text:
        return
        
    text = message.text.strip().lower()
    logger.info(f"Handling verifier action message: '{text}'")
    
    # 1. Перевірка, чи очікується відповідь на запитання про провадження
    session = None
    if message.reply_to_message:
        session = await db.get_session_by_verifier_message_id(message.reply_to_message.message_id)
        if not session:
            session = await db.get_session_by_proceedings_question_message_id(message.reply_to_message.message_id)
                        
    if not session:
        session = await db.get_latest_waiting_verification_session()
        
    if session and session.get('proceedings_question_msg_id'):
        # Очищуємо прапорець
        await db.set_session_proceedings_question_msg_id(session['client_id'], None)
        
        if text in ("так", "да", "+") or text.startswith("так") or text.startswith("да") or text.startswith("+"):
            await process_proceedings_request(session, bot)
        else:
            # Якщо ні / - / інше, відхиляємо сесію
            await process_rejection(session, bot, ban=False)
        return

    # 2. Звичайна перевірка ключових слів
    is_approve = text == "+" or text.startswith("+")
    
    # Перевірка на ключові слова проваджень
    proceedings_keywords = ("провадження", "вп")
    is_proceedings = any(kw in text for kw in proceedings_keywords)
    
    is_reject = False
    reject_keywords = (
        "чс", "ч/с", "сдавал", "сдал", "сдавала", "делала", "була", "был", 
        "делал", "занят", "занята", "отказ", "отклон", "отклонить", "отклонено",
        "не подходит", "не подошел", "не подошла"
    )
    if text == "-" or text.startswith("-") or any(kw in text for kw in reject_keywords):
        is_reject = True
        
    # Якщо це відповідь на анкету і не схвалення, то це автоматично вважається відхиленням
    if message.reply_to_message and not is_approve and not is_proceedings:
        reply_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        if "ІПН:" in reply_text or "ПІБ:" in reply_text:
            is_reject = True
            
    if not (is_approve or is_reject or is_proceedings):
        return
        
    session = None
    if message.reply_to_message:
        session = await db.get_session_by_verifier_message_id(message.reply_to_message.message_id)
    if not session:
        session = await db.get_latest_waiting_verification_session()
        
    if not session:
        await message.reply("⚠️ Не знайдено активної сесії клієнта, яка б очікувала перевірки.")
        return
        
    if is_approve:
        await process_approval(session, bot, message_for_reply=message)
    elif is_proceedings:
        await process_proceedings_request(session, bot)
    elif is_reject:
        should_ban = "чс" in text or "ч/с" in text
        await process_rejection(session, bot, ban=should_ban, message_for_reply=message)

@router.message_reaction()
async def handle_verifier_reaction(reaction: MessageReactionUpdated, bot: Bot):
    """Обробник реакцій верифікатора на анкети"""
    logger.info(f"Received reaction update in chat {reaction.chat.id}, message {reaction.message_id}")
    if reaction.chat.id != ANKETA_CHAT_ID:
        logger.info(f"Reaction chat.id {reaction.chat.id} does not match ANKETA_CHAT_ID {ANKETA_CHAT_ID}")
        return
        
    # Шукаємо реакцію 👎 у списку нових реакцій
    has_thumbs_down = False
    for r in reaction.new_reaction:
        logger.info(f"Found reaction type: {r.type}, emoji: {getattr(r, 'emoji', None)}, custom_emoji_id: {getattr(r, 'custom_emoji_id', None)}")
        if r.type == "emoji" and r.emoji == "👎":
            has_thumbs_down = True
            break
            
    if not has_thumbs_down:
        return
        
    session = await db.get_session_by_verifier_message_id(reaction.message_id)
    if not session:
        logger.warning(f"No session found for verifier message ID {reaction.message_id}")
        return
        
    logger.info(f"Thumbs down reaction detected. Asking verifier for verification type.")
    try:
        sent_msg = await bot.send_message(
            chat_id=reaction.chat.id,
            text="Відкриті провадження?",
            reply_to_message_id=reaction.message_id
        )
        await db.set_session_proceedings_question_msg_id(session['client_id'], sent_msg.message_id)
    except Exception as e:
        logger.error(f"Не вдалося надіслати запитання верифікатору: {e}")
