"""Wardrobe and referral handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from sqlalchemy import select
import logging

from bot.models import User, WardrobeItem, Tryon, get_session
from config import settings

logger = logging.getLogger(__name__)


async def wardrobe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's saved wardrobe items."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    async with get_session() as session:
        # Get user
        user_result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = user_result.scalar_one_or_none()
        
        if not db_user:
            await query.message.reply_text("❌ Пользователь не найден")
            return
        
        # Get wardrobe items
        items_result = await session.execute(
            select(WardrobeItem)
            .where(WardrobeItem.user_id == db_user.id)
            .order_by(WardrobeItem.created_at.desc())
            .limit(10)
        )
        items = items_result.scalars().all()
    
    if not items:
        await query.message.reply_text(
            "👗 **Ваш гардероб пуст**\n\n"
            "Сохраняйте понравившиеся примерки, чтобы они появились здесь!",
            parse_mode="Markdown"
        )
        return
    
    text = f"👗 **Ваш гардероб** ({len(items)} образов)\n\n"
    
    keyboard_buttons = []
    for i, item in enumerate(items, 1):
        date_str = item.created_at.strftime("%d.%m")
        name = item.name or f"Образ {i}"
        keyboard_buttons.append([
            InlineKeyboardButton(
                f"{i}. {name} ({date_str})",
                callback_data=f"view_wardrobe:{item.id}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")])
    
    await query.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard_buttons)
    )


async def view_wardrobe_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View a specific wardrobe item."""
    query = update.callback_query
    await query.answer()
    
    item_id = int(query.data.split(":")[1])
    
    async with get_session() as session:
        result = await session.execute(
            select(WardrobeItem).where(WardrobeItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        
        if not item:
            await query.message.reply_text("❌ Образ не найден")
            return
        
        # Get associated tryon for the image
        if item.tryon_id:
            tryon_result = await session.execute(
                select(Tryon).where(Tryon.id == item.tryon_id)
            )
            tryon = tryon_result.scalar_one_or_none()
            
            if tryon and tryon.result_photo_path:
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_wardrobe:{item_id}"),
                        InlineKeyboardButton("📤 Поделиться", callback_data=f"share_wardrobe:{item_id}"),
                    ],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="wardrobe")],
                ])
                
                try:
                    with open(tryon.result_photo_path, "rb") as photo:
                        await query.message.reply_photo(
                            photo=photo,
                            caption=f"👗 {item.name or 'Сохранённый образ'}\n📅 {item.created_at.strftime('%d.%m.%Y')}",
                            reply_markup=keyboard
                        )
                except FileNotFoundError:
                    await query.message.reply_text("❌ Фото не найдено")
                return
    
    await query.message.reply_text("❌ Не удалось загрузить образ")


async def delete_wardrobe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a wardrobe item."""
    query = update.callback_query
    await query.answer()
    
    item_id = int(query.data.split(":")[1])
    user = update.effective_user
    
    async with get_session() as session:
        # Verify ownership
        user_result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = user_result.scalar_one_or_none()
        
        result = await session.execute(
            select(WardrobeItem).where(
                WardrobeItem.id == item_id,
                WardrobeItem.user_id == db_user.id
            )
        )
        item = result.scalar_one_or_none()
        
        if item:
            await session.delete(item)
            await query.message.reply_text("✅ Образ удалён из гардероба")
        else:
            await query.message.reply_text("❌ Образ не найден")


async def referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show referral info and link."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()
        
        if not db_user:
            await query.message.reply_text("❌ Пользователь не найден")
            return
        
        # Count referrals
        referrals_result = await session.execute(
            select(User).where(User.referred_by_id == db_user.id)
        )
        referrals = referrals_result.scalars().all()
    
    # Get bot username for referral link
    bot_username = settings.bot_username or (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={db_user.referral_code}"
    
    text = f"""
👥 **Пригласи друга**

Приглашай друзей и получай бонусные примерки!

🎁 **Бонусы:**
• Тебе: **+{settings.referral_bonus_tryons}** примерок за каждого друга
• +1 примерка, когда друг делает покупку

📊 **Твоя статистика:**
Приглашено друзей: **{len(referrals)}**

🔗 **Твоя реферальная ссылка:**
`{referral_link}`

Нажми на ссылку, чтобы скопировать, или поделись с друзьями!
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📤 Поделиться ссылкой",
            switch_inline_query=f"Примеряй одежду виртуально! Попробуй бесплатно: {referral_link}"
        )],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")],
    ])
    
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# Register handlers
def register_wardrobe_handlers(application):
    """Register wardrobe and referral handlers."""
    application.add_handler(CallbackQueryHandler(wardrobe_callback, pattern="^wardrobe$"))
    application.add_handler(CallbackQueryHandler(view_wardrobe_item_callback, pattern="^view_wardrobe:"))
    application.add_handler(CallbackQueryHandler(delete_wardrobe_callback, pattern="^delete_wardrobe:"))
    application.add_handler(CallbackQueryHandler(referral_callback, pattern="^referral$"))
