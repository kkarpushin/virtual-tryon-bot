"""Global prompt management service - self-learning prompt evolution."""
import logging
from typing import Optional
from sqlalchemy import select, update

from bot.models import GlobalPrompt, get_session
from .quality_eval import QualityEvaluation

logger = logging.getLogger(__name__)


# Базовая инструкция для всех промптов
BASE_INSTRUCTION = """Одень эту одежду на этого человека.

КРИТИЧЕСКИ ВАЖНО - ЦВЕТ:
- ЦВЕТ ОДЕЖДЫ ДОЛЖЕН ОСТАТЬСЯ ТОЧНО ТАКИМ ЖЕ КАК НА ФОТО - НЕ МЕНЯТЬ!
- Не корректируй цвет под освещение, не делай его светлее/темнее
- Точно сохрани оттенок, насыщенность и яркость цвета

ВАЖНО:
- Одежда должна выглядеть точно так же как на исходном фото - тот же цвет, текстура, рисунок, детали
- НЕ МЕНЯТЬ тело человека: рост, вес, пропорции, телосложение должны остаться ТОЧНО такими же
- Если одежда слишком большая - она должна висеть, выглядеть мешковато
- Если одежда слишком маленькая - она должна выглядеть тесной, обтягивающей
- Покажи РЕАЛИСТИЧНУЮ посадку одежды на РЕАЛЬНОЕ тело человека
- Сохрани позу, лицо и внешность человека"""

# Дефолтные промпты для инициализации
DEFAULT_PROMPTS = {
    "default": BASE_INSTRUCTION,
    "top": BASE_INSTRUCTION + "\n- Обрати особое внимание на посадку плеч и длину рукавов",
    "bottom": BASE_INSTRUCTION + "\n- Обрати особое внимание на посадку на талии и длину штанин/юбки",
    "dress": BASE_INSTRUCTION + "\n- Обрати особое внимание на всю длину платья и силуэт\n- СОХРАНИ ТОЧНЫЙ ЦВЕТ ПЛАТЬЯ!",
    "outerwear": BASE_INSTRUCTION + "\n- Покажи как верхняя одежда сидит поверх других вещей",
    "swimwear": BASE_INSTRUCTION + "\n- Это купальник или плавки - покажи реалистично как они сидят\n- Сохрани естественный вид тела, не изменяй фигуру",
    "underwear": BASE_INSTRUCTION + "\n- Это нижнее белье - покажи реалистично как оно сидит\n- Сохрани естественный вид тела",
}


class GlobalPromptManager:
    """Manages global prompts with evolution tracking."""

    async def get_best_prompt(self, clothing_type: str) -> str:
        """
        Get the best performing prompt for a clothing type.
        Falls back to default if no specific prompt exists.
        """
        try:
            async with get_session() as session:
                # Try to get active prompt for this clothing type
                result = await session.execute(
                    select(GlobalPrompt)
                    .where(GlobalPrompt.clothing_type == clothing_type)
                    .where(GlobalPrompt.is_active == True)
                    .order_by(GlobalPrompt.version.desc())
                    .limit(1)
                )
                prompt = result.scalar_one_or_none()

                if prompt:
                    logger.info(f"Using global prompt v{prompt.version} for {clothing_type}")
                    return prompt.prompt

                # Try default
                result = await session.execute(
                    select(GlobalPrompt)
                    .where(GlobalPrompt.clothing_type == "default")
                    .where(GlobalPrompt.is_active == True)
                    .order_by(GlobalPrompt.version.desc())
                    .limit(1)
                )
                prompt = result.scalar_one_or_none()

                if prompt:
                    return prompt.prompt

        except Exception as e:
            logger.error(f"Error getting best prompt: {e}")

        # Fallback to hardcoded default
        return DEFAULT_PROMPTS.get(clothing_type, DEFAULT_PROMPTS["default"])

    async def record_usage(
        self,
        clothing_type: str,
        prompt_used: str,
        evaluation: QualityEvaluation
    ):
        """
        Record usage of a prompt and update its performance metrics.
        """
        try:
            async with get_session() as session:
                # Find the prompt
                result = await session.execute(
                    select(GlobalPrompt)
                    .where(GlobalPrompt.prompt == prompt_used)
                    .where(GlobalPrompt.is_active == True)
                )
                global_prompt = result.scalar_one_or_none()

                if global_prompt:
                    # Update metrics
                    global_prompt.total_uses += 1

                    # Update average scores
                    old_avg = global_prompt.avg_quality_score
                    old_match = global_prompt.avg_clothing_match
                    n = global_prompt.total_uses

                    global_prompt.avg_quality_score = ((old_avg * (n - 1)) + evaluation.score) / n
                    global_prompt.avg_clothing_match = ((old_match * (n - 1)) + evaluation.clothing_match_score) / n

                    if evaluation.score >= 7:
                        global_prompt.successful_uses += 1

                    logger.info(f"Updated prompt metrics: avg={global_prompt.avg_quality_score:.2f}, uses={n}")

        except Exception as e:
            logger.error(f"Error recording prompt usage: {e}")

    async def save_improved_prompt(
        self,
        clothing_type: str,
        new_prompt: str,
        old_prompt: str,
        improvement_reason: str,
        initial_score: float
    ) -> Optional[int]:
        """
        Save a new improved prompt version.
        Returns the new prompt ID if saved.
        """
        try:
            async with get_session() as session:
                # Find parent prompt
                result = await session.execute(
                    select(GlobalPrompt)
                    .where(GlobalPrompt.prompt == old_prompt)
                    .where(GlobalPrompt.is_active == True)
                )
                parent = result.scalar_one_or_none()

                parent_id = parent.id if parent else None
                new_version = (parent.version + 1) if parent else 1

                # Deactivate old prompt
                if parent:
                    parent.is_active = False

                # Create new prompt
                new_global_prompt = GlobalPrompt(
                    clothing_type=clothing_type,
                    prompt=new_prompt,
                    version=new_version,
                    avg_quality_score=initial_score,
                    avg_clothing_match=initial_score,
                    total_uses=1,
                    successful_uses=1 if initial_score >= 7 else 0,
                    is_active=True,
                    parent_prompt_id=parent_id,
                    improvement_reason=improvement_reason
                )
                session.add(new_global_prompt)
                await session.flush()

                logger.info(f"Saved new prompt v{new_version} for {clothing_type}: {improvement_reason}")
                return new_global_prompt.id

        except Exception as e:
            logger.error(f"Error saving improved prompt: {e}")
            return None

    async def initialize_defaults(self):
        """Initialize default prompts if not exist."""
        try:
            async with get_session() as session:
                for clothing_type, prompt_text in DEFAULT_PROMPTS.items():
                    # Check if exists
                    result = await session.execute(
                        select(GlobalPrompt)
                        .where(GlobalPrompt.clothing_type == clothing_type)
                        .limit(1)
                    )
                    exists = result.scalar_one_or_none()

                    if not exists:
                        new_prompt = GlobalPrompt(
                            clothing_type=clothing_type,
                            prompt=prompt_text,
                            version=1,
                            is_active=True
                        )
                        session.add(new_prompt)
                        logger.info(f"Initialized default prompt for {clothing_type}")

        except Exception as e:
            logger.error(f"Error initializing default prompts: {e}")


# Global instance
global_prompt_manager = GlobalPromptManager()
