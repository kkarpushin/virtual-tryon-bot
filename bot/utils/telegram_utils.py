"""Telegram utilities."""
from telegram.error import BadRequest
import logging

logger = logging.getLogger(__name__)


async def safe_answer(query):
    """Safely answer callback query, ignoring timeout errors.
    
    Telegram requires callback queries to be answered within 30 seconds.
    If the user clicks an old button, this will fail gracefully.
    """
    try:
        await query.answer()
    except BadRequest as e:
        logger.debug(f"Could not answer callback query: {e}")
