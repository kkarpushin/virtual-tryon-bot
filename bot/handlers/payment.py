"""Telegram Stars payment handler."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes, CallbackQueryHandler, PreCheckoutQueryHandler, MessageHandler, filters
from sqlalchemy import select
from datetime import datetime, timedelta
import logging

from bot.models import User, Payment, SubscriptionType, get_session
from bot.utils.telegram_utils import safe_answer
from config import settings

logger = logging.getLogger(__name__)


# Payment products
PRODUCTS = {
    "single": {
        "title": "1 примерка",
        "description": "Одна виртуальная примерка",
        "price": settings.tryon_price_stars,
        "tryons": 1,
    },
    "pack_10": {
        "title": "10 примерок",
        "description": "Пакет из 10 примерок со скидкой 20%",
        "price": settings.pack_10_price_stars,
        "tryons": 10,
    },
    "pack_50": {
        "title": "50 примерок",
        "description": "Пакет из 50 примерок со скидкой 30%",
        "price": settings.pack_50_price_stars,
        "tryons": 50,
    },
    "unlimited": {
        "title": "Безлимит на месяц",
        "description": "Неограниченное количество примерок на 30 дней",
        "price": settings.unlimited_month_price_stars,
        "tryons": 0,  # Special handling for unlimited
        "subscription": SubscriptionType.UNLIMITED_MONTH,
    },
}


async def buy_tryons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show payment options."""
    query = update.callback_query
    await safe_answer(query)

    text = """
💳 **Купить примерки**

Выберите подходящий пакет:
"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"1️⃣ 1 примерка — {PRODUCTS['single']['price']} ⭐",
            callback_data="pay:single"
        )],
        [InlineKeyboardButton(
            f"🔟 10 примерок — {PRODUCTS['pack_10']['price']} ⭐ (скидка 20%)",
            callback_data="pay:pack_10"
        )],
        [InlineKeyboardButton(
            f"🎁 50 примерок — {PRODUCTS['pack_50']['price']} ⭐ (скидка 30%)",
            callback_data="pay:pack_50"
        )],
        [InlineKeyboardButton(
            f"♾️ Безлимит на месяц — {PRODUCTS['unlimited']['price']} ⭐",
            callback_data="pay:unlimited"
        )],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")],
    ])

    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def pay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate Telegram Stars payment."""
    query = update.callback_query
    await safe_answer(query)

    product_id = query.data.split(":")[1]
    product = PRODUCTS.get(product_id)

    if not product:
        await query.message.reply_text("❌ Продукт не найден")
        return

    # Send invoice using Telegram Stars (XTR currency)
    prices = [LabeledPrice(label=product["title"], amount=product["price"])]

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=product["title"],
        description=product["description"],
        payload=product_id,  # We'll use this to identify the product later
        provider_token="",  # Empty for Telegram Stars
        currency="XTR",  # XTR = Telegram Stars
        prices=prices,
    )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pre-checkout query - validate and approve payment."""
    query = update.pre_checkout_query

    # Validate the payment
    product_id = query.invoice_payload
    product = PRODUCTS.get(product_id)

    if not product:
        await query.answer(ok=False, error_message="Продукт не найден")
        return

    # Check price matches
    if query.total_amount != product["price"]:
        await query.answer(ok=False, error_message="Неверная цена")
        return

    # All good, approve the payment
    await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful payment - add tryons to user."""
    payment = update.message.successful_payment
    user = update.effective_user

    product_id = payment.invoice_payload
    product = PRODUCTS.get(product_id)

    if not product:
        await update.message.reply_text("❌ Ошибка: продукт не найден")
        return

    async with get_session() as session:
        # Get user
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()

        if not db_user:
            await update.message.reply_text("❌ Ошибка: пользователь не найден")
            return

        # Create payment record
        payment_record = Payment(
            user_id=db_user.id,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            provider_payment_charge_id=payment.provider_payment_charge_id,
            amount_stars=payment.total_amount,
            product_type=product_id,
            tryons_added=product["tryons"]
        )
        session.add(payment_record)

        # Add tryons or activate subscription
        if product_id == "unlimited":
            db_user.subscription_type = SubscriptionType.UNLIMITED_MONTH
            db_user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            message = f"""
✅ **Оплата прошла успешно!**

♾️ Активирован безлимит на 30 дней!
Действует до: {db_user.subscription_expires_at.strftime('%d.%m.%Y')}

Теперь вы можете делать неограниченное количество примерок!
"""
        else:
            db_user.paid_tryons_remaining += product["tryons"]
            message = f"""
✅ **Оплата прошла успешно!**

🎟️ Добавлено примерок: **{product["tryons"]}**
📊 Всего доступно: **{db_user.total_tryons_available}**

Отправьте фото одежды, чтобы начать примерку!
"""

        # Process referrer bonus if applicable
        if db_user.referred_by_id:
            referrer_result = await session.execute(
                select(User).where(User.id == db_user.referred_by_id)
            )
            referrer = referrer_result.scalar_one_or_none()

            if referrer:
                referrer.paid_tryons_remaining += settings.referrer_bonus_on_payment
                logger.info(f"Referrer {referrer.telegram_id} received bonus for payment")

    await update.message.reply_text(message, parse_mode="Markdown")


async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu."""
    query = update.callback_query
    await safe_answer(query)

    user = update.effective_user

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()
        has_photo = db_user.photo_file_id is not None if db_user else False

    from .start import get_main_keyboard

    await query.message.reply_text(
        "🏠 **Главное меню**\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(has_photo)
    )


# Register handlers
def register_payment_handlers(application):
    """Register payment handlers."""
    application.add_handler(CallbackQueryHandler(buy_tryons_callback, pattern="^buy_tryons$"))
    application.add_handler(CallbackQueryHandler(pay_callback, pattern="^pay:"))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    application.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
