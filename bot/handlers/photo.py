"""Photo handling for user photos and clothing."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters, CallbackQueryHandler
from sqlalchemy import select
from pathlib import Path
from datetime import datetime
import logging

from bot.models import User, Tryon, TryonStatus, get_session
from bot.services import tryon_orchestrator
from config import settings

logger = logging.getLogger(__name__)


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photos."""
    user = update.effective_user
    photos = update.message.photo
    
    if not photos:
        return
    
    # Get highest resolution photo
    photo = photos[-1]
    
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()
        
        if not db_user:
            await update.message.reply_text(
                "Пожалуйста, сначала нажмите /start"
            )
            return
        
        # Check if we're expecting a new profile photo (user wants to change)
        expecting_profile_photo = context.user_data.get('expecting_profile_photo', False)
        
        # Check if user has profile photo
        if not db_user.photo_file_id or expecting_profile_photo:
            # This is profile photo upload (new or replacement)
            await handle_profile_photo(update, context, db_user, photo, session)
            # Clear the flag
            context.user_data['expecting_profile_photo'] = False
        else:
            # This is clothing photo - initiate try-on
            await handle_clothing_photo(update, context, db_user, photo, session)


async def handle_profile_photo(update, context, db_user, photo, session):
    """Handle profile photo upload."""
    file_id = photo.file_id
    
    # Download and save photo
    file = await context.bot.get_file(file_id)
    
    # Create user photo directory
    user_dir = settings.photos_dir / str(db_user.telegram_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    
    photo_path = user_dir / "profile.jpg"
    await file.download_to_drive(str(photo_path))
    
    # Update user record
    db_user.photo_file_id = file_id
    db_user.photo_path = str(photo_path)
    db_user.photo_updated_at = datetime.utcnow()
    
    await update.message.reply_text(
        f"""
✅ **Отлично! Фото сохранено!**

Теперь вы можете примерять одежду:
1. 📸 Сфотографируйте вещь в магазине
2. 📤 Отправьте фото в этот чат
3. ✨ Получите виртуальную примерку!

🎟️ Осталось примерок: **{db_user.total_tryons_available}**
""",
        parse_mode="Markdown"
    )


async def handle_clothing_photo(update, context, db_user, photo, session):
    """Handle clothing photo and initiate try-on."""
    # Check if user has available tryons
    if not db_user.has_tryons_available:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Купить примерки", callback_data="buy_tryons")]
        ])
        await update.message.reply_text(
            "❌ У вас закончились примерки.\n\nКупите дополнительные примерки, чтобы продолжить!",
            reply_markup=keyboard
        )
        return
    
    # Download clothing photo
    file_id = photo.file_id
    file = await context.bot.get_file(file_id)
    
    user_dir = settings.photos_dir / str(db_user.telegram_id) / "clothing"
    user_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    clothing_path = user_dir / f"clothing_{timestamp}.jpg"
    await file.download_to_drive(str(clothing_path))
    
    # Create tryon record
    tryon = Tryon(
        user_id=db_user.id,
        clothing_photo_file_id=file_id,
        clothing_photo_path=str(clothing_path),
        status=TryonStatus.PROCESSING
    )
    session.add(tryon)
    await session.flush()
    
    # Use tryon
    db_user.use_tryon()
    
    tryon_id = tryon.id
    user_photo_path = db_user.photo_path
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        "🔄 **Начинаю примерку...**\n\n"
        "Подождите, AI анализирует одежду...",
        parse_mode="Markdown"
    )
    
    # Progress callback to update message
    async def update_progress(status_text):
        try:
            await processing_msg.edit_text(
                status_text,
                parse_mode="Markdown"
            )
        except Exception:
            pass  # Ignore edit errors
    
    # Process tryon (this runs the self-improving loop)
    try:
        result = await tryon_orchestrator.process_tryon(
            user_photo_path,
            str(clothing_path),
            tryon_id,
            progress_callback=update_progress
        )
        
        if result.success and result.image_path:
            # Send result
            await processing_msg.delete()
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💾 Сохранить", callback_data=f"save_tryon:{tryon_id}"),
                    InlineKeyboardButton("📤 Поделиться", callback_data=f"share_tryon:{tryon_id}"),
                ],
                [InlineKeyboardButton("🔄 Повторить", callback_data=f"retry_tryon:{tryon_id}")],
            ])
            
            async with get_session() as new_session:
                user_result = await new_session.execute(
                    select(User).where(User.telegram_id == db_user.telegram_id)
                )
                updated_user = user_result.scalar_one()
                tryons_left = updated_user.total_tryons_available
            
            caption = f"""
👗 **Вот как это выглядит!**

📊 Качество: {result.final_score:.1f}/10
🔄 Итераций: {result.iterations_used}
🎟️ Осталось примерок: {tryons_left}
"""
            
            with open(result.image_path, "rb") as photo_file:
                await update.message.reply_photo(
                    photo=photo_file,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
        else:
            await processing_msg.edit_text(
                f"❌ **Не удалось создать примерку**\n\n"
                f"Ошибка: {result.error}\n\n"
                "Попробуйте отправить другое фото одежды.",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Error processing tryon: {e}")
        await processing_msg.edit_text(
            "❌ Произошла ошибка при обработке.\n"
            "Попробуйте ещё раз или обратитесь в поддержку."
        )


async def save_tryon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle saving tryon to wardrobe."""
    query = update.callback_query
    await query.answer()
    
    tryon_id = int(query.data.split(":")[1])
    user = update.effective_user
    
    async with get_session() as session:
        from bot.models import WardrobeItem
        
        # Get user
        user_result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = user_result.scalar_one_or_none()
        
        if not db_user:
            await query.message.reply_text("Ошибка: пользователь не найден")
            return
        
        # Get tryon
        tryon_result = await session.execute(
            select(Tryon).where(Tryon.id == tryon_id)
        )
        tryon = tryon_result.scalar_one_or_none()
        
        if not tryon:
            await query.message.reply_text("Ошибка: примерка не найдена")
            return
        
        # Create wardrobe item
        wardrobe_item = WardrobeItem(
            user_id=db_user.id,
            tryon_id=tryon_id,
            result_photo_file_id=tryon.result_photo_file_id,
            clothing_photo_file_id=tryon.clothing_photo_file_id
        )
        session.add(wardrobe_item)
    
    await query.message.reply_text("✅ Сохранено в гардероб!")


# Register handlers
def register_photo_handlers(application):
    """Register photo handlers."""
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(CallbackQueryHandler(save_tryon_callback, pattern="^save_tryon:"))
