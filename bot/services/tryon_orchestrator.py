"""Try-on orchestration service with self-improving prompt loop."""
import asyncio
import logging
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from config import settings
from .nano_banana import nano_banana_service
from .quality_eval import quality_evaluator, QualityEvaluation
from .prompt_optimizer import prompt_optimizer
from .global_prompts import global_prompt_manager
from bot.models import Tryon, PromptHistory, TryonStatus, get_session

logger = logging.getLogger(__name__)


@dataclass
class TryonResult:
    """Result of the try-on generation process."""
    success: bool
    image_path: Optional[str]
    final_score: float
    clothing_match_score: float
    iterations_used: int
    final_prompt: str
    error: Optional[str] = None


class TryonOrchestrator:
    """
    Orchestrates the try-on generation with self-improving prompt loop.
    
    Flow:
    1. Get best known prompt from global storage
    2. Generate try-on image
    3. Evaluate quality (including clothing match)
    4. If score < min_quality_score and iterations < max:
       - Optimize prompt based on feedback
       - Regenerate image
       - Repeat evaluation
    5. If final score > threshold, save improved prompt globally
    6. Return best result
    """

    def __init__(self):
        self.max_iterations = settings.max_prompt_iterations
        self.min_quality_score = settings.min_quality_score
        self.photos_dir = settings.photos_dir
        # Порог для сохранения улучшенного промпта глобально
        self.save_threshold = 8.0

    async def process_tryon(
        self,
        user_photo_path: str,
        clothing_photo_path: str,
        tryon_id: int,
        progress_callback=None  # Callback для обновления статуса
    ) -> TryonResult:
        """
        Process a try-on request (simplified single-pass generation).
        """
        async def update_status(text):
            if progress_callback:
                try:
                    await progress_callback(text)
                except Exception as e:
                    logger.debug(f"Could not update status: {e}")

        await update_status("🔍 Определяю тип одежды...")

        # Detect clothing type
        clothing_type = await nano_banana_service.detect_clothing_type(clothing_photo_path)
        logger.info(f"Detected clothing type: {clothing_type}")

        clothing_names = {
            "top": "верх (футболка/рубашка)",
            "bottom": "низ (штаны/юбка)",
            "dress": "платье",
            "outerwear": "верхняя одежда",
            "swimwear": "купальник/плавки",
            "underwear": "нижнее белье",
            "unknown": "одежда"
        }
        clothing_name = clothing_names.get(clothing_type, "одежда")

        await update_status(f"👗 Определено: {clothing_name}\n🎨 Генерирую примерку...")

        # Get best known prompt
        current_prompt = await global_prompt_manager.get_best_prompt(clothing_type)
        logger.info(f"Using global prompt for {clothing_type}")

        # Generate image (single pass - no quality loop)
        image_bytes, error = await nano_banana_service.generate_with_prompt(
            user_photo_path,
            clothing_photo_path,
            current_prompt
        )

        if error or not image_bytes:
            logger.error(f"Generation failed: {error}")
            return TryonResult(
                success=False,
                image_path=None,
                final_score=0,
                clothing_match_score=0,
                iterations_used=1,
                final_prompt=current_prompt,
                error=error or "Failed to generate image"
            )

        # Save result
        final_path = self.photos_dir / f"result_{tryon_id}.png"
        final_path.parent.mkdir(parents=True, exist_ok=True)

        with open(final_path, "wb") as f:
            f.write(image_bytes)

        # Update tryon record
        await self._update_tryon_record(
            tryon_id, str(final_path), current_prompt, 10.0, 1
        )

        return TryonResult(
            success=True,
            image_path=str(final_path),
            final_score=10.0,  # No evaluation, assume good quality
            clothing_match_score=10.0,
            iterations_used=1,
            final_prompt=current_prompt
        )

    async def _save_prompt_history(
        self,
        tryon_id: int,
        iteration: int,
        prompt: str,
        evaluation: QualityEvaluation
    ):
        """Save prompt iteration to history."""
        try:
            async with get_session() as session:
                history = PromptHistory(
                    tryon_id=tryon_id,
                    iteration=iteration,
                    prompt=prompt,
                    quality_score=evaluation.score,
                    evaluation_feedback=f"Score: {evaluation.score}, ClothingMatch: {evaluation.clothing_match_score}, Fit: {evaluation.fit_score}\n{evaluation.feedback}\nIssues: {', '.join(evaluation.issues)}"
                )
                session.add(history)
        except Exception as e:
            logger.error(f"Error saving prompt history: {e}")

    async def _update_tryon_record(
        self,
        tryon_id: int,
        result_path: str,
        prompt: str,
        score: float,
        iterations: int
    ):
        """Update tryon record with final result."""
        try:
            async with get_session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(Tryon).where(Tryon.id == tryon_id)
                )
                tryon = result.scalar_one_or_none()

                if tryon:
                    tryon.result_photo_path = result_path
                    tryon.prompt_used = prompt
                    tryon.quality_score = score
                    tryon.iterations_count = iterations
                    tryon.status = TryonStatus.COMPLETED
                    tryon.completed_at = datetime.utcnow()
        except Exception as e:
            logger.error(f"Error updating tryon record: {e}")


# Global service instance
tryon_orchestrator = TryonOrchestrator()
