"""Easter egg: Companion mode handler."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from sqlalchemy import select
import logging

from bot.models import User, get_session
from bot.utils.telegram_utils import safe_answer

logger = logging.getLogger(__name__)


COMPANION_MENU_TEXT = """
🔥 **Секретный режим: Компаньон**

Добавь привлекательного человека рядом с собой на примерке!

Выбери:
"""


async def companion_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /companion command - show companion mode menu."""
    user = update.effective_user

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()

        if not db_user:
            await update.message.reply_text("Сначала нажмите /start")
            return

        current_mode = db_user.companion_mode

    status_text = ""
    if current_mode == "female":
        status_text = "\n\n✅ Сейчас: **Девушка**"
    elif current_mode == "male":
        status_text = "\n\n✅ Сейчас: **Парень**"
    else:
        status_text = "\n\n❌ Сейчас: **Выключен**"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👩 Девушка", callback_data="companion:female"),
            InlineKeyboardButton("👨 Парень", callback_data="companion:male"),
        ],
        [InlineKeyboardButton("❌ Выключить", callback_data="companion:off")],
    ])

    await update.message.reply_text(
        COMPANION_MENU_TEXT + status_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def companion_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle companion mode selection."""
    query = update.callback_query
    await safe_answer(query)

    mode = query.data.split(":")[1]  # "female", "male", or "off"
    user = update.effective_user

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()

        if not db_user:
            await query.message.reply_text("Ошибка: пользователь не найден")
            return

        if mode == "off":
            db_user.companion_mode = None
            await query.message.edit_text(
                "❌ **Режим компаньона выключен**\n\n"
                "Примерки будут без дополнительных людей.",
                parse_mode="Markdown"
            )
        elif mode == "female":
            db_user.companion_mode = "female"
            await query.message.edit_text(
                "👩 **Режим: Девушка**\n\n"
                "Теперь на примерках рядом с тобой будет красивая девушка!\n\n"
                "Чтобы выключить: /companion",
                parse_mode="Markdown"
            )
        elif mode == "male":
            db_user.companion_mode = "male"
            await query.message.edit_text(
                "👨 **Режим: Парень**\n\n"
                "Теперь на примерках рядом с тобой будет красивый мужчина!\n\n"
                "Чтобы выключить: /companion",
                parse_mode="Markdown"
            )

        logger.info(f"User {user.id} set companion mode to: {mode}")


def register_companion_handlers(application):
    """Register companion mode handlers."""
    application.add_handler(CommandHandler("companion", companion_command))
    application.add_handler(CallbackQueryHandler(companion_callback, pattern="^companion:"))
