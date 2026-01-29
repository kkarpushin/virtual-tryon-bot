"""Gift tryons to all users and notify them."""
import asyncio
import logging
from sqlalchemy import select, update
from telegram import Bot

import sys
sys.path.insert(0, '.')

from config import settings
from bot.models import User, get_session, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GIFT_AMOUNT = 10
GIFT_MESSAGE = """
🎁 **Подарок от разработчика!**

Вам начислено **+10 бесплатных примерок**!

Спасибо, что пользуетесь нашим ботом! 💜

Отправьте фото одежды, чтобы начать примерку!
"""


async def main():
    # Initialize database
    await init_db()
    
    bot = Bot(token=settings.bot_token)
    
    async with get_session() as session:
        # Get all users
        result = await session.execute(select(User))
        users = result.scalars().all()
        
        logger.info(f"Found {len(users)} users")
        
        # Update all users - add 10 free tryons
        await session.execute(
            update(User).values(
                free_tryons_remaining=User.free_tryons_remaining + GIFT_AMOUNT
            )
        )
        await session.commit()
        logger.info(f"Added {GIFT_AMOUNT} tryons to all users")
        
        # Send messages to all users
        success_count = 0
        for user in users:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=GIFT_MESSAGE,
                    parse_mode="Markdown"
                )
                logger.info(f"Sent gift message to {user.telegram_id}")
                success_count += 1
                await asyncio.sleep(0.1)  # Rate limiting
            except Exception as e:
                logger.warning(f"Could not send to {user.telegram_id}: {e}")
        
        logger.info(f"Done! Sent messages to {success_count}/{len(users)} users")


if __name__ == "__main__":
    asyncio.run(main())
