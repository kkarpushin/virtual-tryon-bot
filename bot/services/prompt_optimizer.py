"""Prompt optimization service for self-improving generation."""
from google import genai
from PIL import Image
import asyncio
import logging
from typing import Optional
from dataclasses import dataclass

from config import settings
from .quality_eval import QualityEvaluation

logger = logging.getLogger(__name__)


@dataclass
class OptimizedPrompt:
    """Result of prompt optimization."""
    prompt: str
    changes_made: str
    expected_improvements: list[str]


class PromptOptimizer:
    """Service for optimizing prompts based on quality feedback."""
    
    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model_name = "gemini-2.5-flash"
        
        self.optimization_prompt = """
Ты эксперт по промптам для генерации изображений виртуальной примерки.

Проблемы с предыдущим результатом:
{issues}

Оценка: {feedback}
Соответствие одежды оригиналу: {clothing_match}/10
Качество посадки: {fit_score}/10

Предыдущий промпт:
{previous_prompt}

Создай УЛУЧШЕННЫЙ промпт, который:
1. Исправит указанные проблемы
2. Особенно подчеркнёт ИДЕНТИЧНОСТЬ одежды (тот же цвет, рисунок, текстура)
3. Будет простым и прямым

Ответь ТОЛЬКО новым промптом, без объяснений.
"""
    
    async def optimize(
        self,
        previous_prompt: str,
        evaluation: QualityEvaluation,
        target_score: float = 7.0
    ) -> OptimizedPrompt:
        """Optimize a prompt based on quality evaluation feedback."""
        try:
            prompt = self.optimization_prompt.format(
                issues="\n".join(f"- {issue}" for issue in evaluation.issues) or "Нет",
                feedback=evaluation.feedback,
                clothing_match=evaluation.clothing_match_score,
                fit_score=evaluation.fit_score,
                previous_prompt=previous_prompt
            )
            
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=[prompt]
            )
            
            new_prompt = response.text.strip()
            
            return OptimizedPrompt(
                prompt=new_prompt,
                changes_made=f"Оптимизирован на основе {len(evaluation.issues)} проблем",
                expected_improvements=evaluation.suggestions
            )
            
        except Exception as e:
            logger.error(f"Error optimizing prompt: {e}")
            # Fallback - добавляем акцент на идентичность
            enhanced = previous_prompt + " ВАЖНО: Одежда должна быть ИДЕНТИЧНА оригиналу - точный цвет, рисунок, текстура!"
            return OptimizedPrompt(
                prompt=enhanced,
                changes_made="Добавлен акцент на идентичность (fallback)",
                expected_improvements=["Лучшее соответствие одежды"]
            )
    
    async def create_initial_prompt(
        self,
        clothing_type: str,
        additional_context: str = ""
    ) -> str:
        """Create an initial prompt for a specific clothing type."""
        base = "Одень эту одежду на этого человека. Одежда должна выглядеть точно так же как на исходном фото - тот же цвет, текстура, рисунок, детали. Сохрани позу и внешность человека."
        
        type_additions = {
            "top": " Обрати внимание на посадку плеч и длину рукавов.",
            "bottom": " Обрати внимание на посадку на талии и длину.",
            "dress": " Обрати внимание на всю длину платья и силуэт.",
            "outerwear": " Покажи как верхняя одежда сидит поверх других вещей.",
        }
        
        prompt = base + type_additions.get(clothing_type, "")
        if additional_context:
            prompt += f" {additional_context}"
        
        return prompt


prompt_optimizer = PromptOptimizer()
