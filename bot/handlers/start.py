"""Start command and onboarding handler."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from sqlalchemy import select
import secrets
import logging

from bot.models import User, get_session
from bot.utils.telegram_utils import safe_answer
from config import settings

logger = logging.getLogger(__name__)


# Texts
WELCOME_TEXT = """
👗 **Добро пожаловать в Virtual Try-On!**

Примеряйте одежду виртуально — сфотографируйте вещь в магазине и посмотрите, как она будет выглядеть на вас!

🎁 У вас есть **{free_tryons} бесплатных примерок**

**Как это работает:**
1️⃣ Загрузите своё фото (один раз)
2️⃣ Сфотографируйте одежду в магазине
3️⃣ Получите AI-генерацию примерки!

⬇️ Для начала загрузите своё фото
"""

UPLOAD_PHOTO_TEXT = """
📸 **Загрузите своё фото**

Для лучшего результата:
• Фото в полный рост или по пояс
• Хорошее освещение
• Нейтральный фон
• Простая одежда (футболка/майка)

Просто отправьте фото в этот чат!
"""

PHOTO_SAVED_TEXT = """
✅ **Отлично! Фото сохранено!**

Теперь вы можете примерять одежду:
1. Сфотографируйте вещь в магазине
2. Отправьте фото в этот чат
3. Получите виртуальную примерку!

📊 Осталось примерок: **{tryons_remaining}**
"""


def get_main_keyboard(has_photo: bool = False) -> InlineKeyboardMarkup:
    """Get main menu keyboard."""
    buttons = []

    if not has_photo:
        buttons.append([InlineKeyboardButton("📸 Загрузить фото", callback_data="upload_photo")])
    else:
        buttons.append([InlineKeyboardButton("📷 Моё фото", callback_data="my_photo")])

    buttons.extend([
        [InlineKeyboardButton("👗 Мой гардероб", callback_data="wardrobe")],
        [InlineKeyboardButton("💳 Купить примерки", callback_data="buy_tryons")],
        [InlineKeyboardButton("👥 Пригласить друга", callback_data="referral")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
    ])

    return InlineKeyboardMarkup(buttons)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    referral_code = None

    # Check for referral code in start parameter
    if context.args:
        referral_code = context.args[0]

    async with get_session() as session:
        # Check if user exists
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()

        if not db_user:
            # Create new user
            db_user = User(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                free_tryons_remaining=settings.free_tryons_limit,
                referral_code=secrets.token_urlsafe(8)
            )

            # Process referral
            if referral_code:
                referrer_result = await session.execute(
                    select(User).where(User.referral_code == referral_code)
                )
                referrer = referrer_result.scalar_one_or_none()

                if referrer and referrer.telegram_id != user.id:
                    db_user.referred_by_id = referrer.id
                    # Give bonus to referrer
                    referrer.free_tryons_remaining += settings.referral_bonus_tryons
                    logger.info(f"Referral bonus given to user {referrer.telegram_id}")

            session.add(db_user)
            await session.flush()

        has_photo = db_user.photo_file_id is not None
        tryons = db_user.total_tryons_available

    await update.message.reply_text(
        WELCOME_TEXT.format(free_tryons=settings.free_tryons_limit),
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(has_photo)
    )


async def upload_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle upload photo button."""
    query = update.callback_query
    await safe_answer(query)

    await query.message.reply_text(
        UPLOAD_PHOTO_TEXT,
        parse_mode="Markdown"
    )


async def my_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current photo and allow changing it."""
    query = update.callback_query
    await safe_answer(query)

    user = update.effective_user

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()

        if not db_user or not db_user.photo_file_id:
            await query.message.reply_text(
                "У вас ещё нет загруженного фото. Отправьте фото в чат!"
            )
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Заменить фото", callback_data="change_photo")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")],
        ])

        # Send current photo
        await query.message.reply_photo(
            photo=db_user.photo_file_id,
            caption=f"""📷 **Ваше текущее фото**

Загружено: {db_user.photo_updated_at.strftime('%d.%m.%Y %H:%M') if db_user.photo_updated_at else 'N/A'}

Чтобы заменить — нажмите кнопку ниже или просто отправьте новое фото.""",
            parse_mode="Markdown",
            reply_markup=keyboard
        )


async def change_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle change photo button - set flag to expect new profile photo."""
    query = update.callback_query
    await safe_answer(query)

    # Set flag in user_data to indicate we're expecting a new profile photo
    context.user_data['expecting_profile_photo'] = True

    await query.message.reply_text(
        """📸 **Отправьте новое фото**

Ваше следующее фото заменит текущее.

Для лучшего результата:
• Фото в полный рост или по пояс
• Хорошее освещение
• Нейтральный фон""",
        parse_mode="Markdown"
    )


async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to menu button."""
    query = update.callback_query
    await safe_answer(query)

    user = update.effective_user

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()
        has_photo = db_user.photo_file_id is not None if db_user else False

    await query.message.reply_text(
        "📱 **Главное меню**\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(has_photo)
    )


async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stats button."""
    query = update.callback_query
    await safe_answer(query)

    user = update.effective_user

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()

        if not db_user:
            await query.message.reply_text("Пользователь не найден. Нажмите /start")
            return

        # Count tryons
        from bot.models import Tryon, TryonStatus
        tryons_result = await session.execute(
            select(Tryon).where(
                Tryon.user_id == db_user.id,
                Tryon.status == TryonStatus.COMPLETED
            )
        )
        tryons = tryons_result.scalars().all()

    stats_text = f"""
📊 **Ваша статистика**

👤 Профиль: {'✅ Фото загружено' if db_user.photo_file_id else '❌ Фото не загружено'}

🎟️ **Примерки:**
• Бесплатных осталось: **{db_user.free_tryons_remaining}**
• Оплаченных осталось: **{db_user.paid_tryons_remaining}**
• Всего выполнено: **{len(tryons)}**

📅 Зарегистрирован: {db_user.created_at.strftime('%d.%m.%Y')}
"""

    await query.message.reply_text(stats_text, parse_mode="Markdown")


# Register handlers
def register_start_handlers(application):
    """Register start and onboarding handlers."""
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CallbackQueryHandler(upload_photo_callback, pattern="^upload_photo$"))
    application.add_handler(CallbackQueryHandler(my_photo_callback, pattern="^my_photo$"))
    application.add_handler(CallbackQueryHandler(change_photo_callback, pattern="^change_photo$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(stats_callback, pattern="^stats$"))
