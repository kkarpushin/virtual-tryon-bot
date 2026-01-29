"""Main entry point for the Virtual Try-On Telegram Bot."""
import logging
from telegram.ext import Application

from config import settings
from bot.models import init_db
from bot.handlers import register_all_handlers

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Start the bot."""
    logger.info("Starting Virtual Try-On Bot...")
    
    # Ensure directories exist
    settings.ensure_directories()
    
    # Create application
    application = (
        Application.builder()
        .token(settings.bot_token)
        .build()
    )
    
    # Register all handlers
    register_all_handlers(application)
    
    # Add post-init for database
    async def post_init(app):
        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialized successfully")
        
        # Initialize default prompts
        from bot.services.global_prompts import global_prompt_manager
        await global_prompt_manager.initialize_defaults()
        logger.info("Global prompts initialized")
    
    application.post_init = post_init
    
    # Start polling (this handles event loop internally)
    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=["message", "callback_query", "pre_checkout_query"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
