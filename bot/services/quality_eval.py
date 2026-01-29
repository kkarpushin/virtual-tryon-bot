"""Quality evaluation service - checks clothing identity and fit quality."""
from google import genai
from PIL import Image
import asyncio
import logging
import json
from typing import Optional
from dataclasses import dataclass

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class QualityEvaluation:
    """Result of quality evaluation."""
    score: float  # 0-10
    clothing_match_score: float  # 0-10 - насколько одежда похожа на оригинал
    fit_score: float  # 0-10 - насколько хорошо сидит
    feedback: str
    issues: list[str]
    suggestions: list[str]


class QualityEvaluator:
    """Service for evaluating quality of generated try-on images with clothing identity check."""

    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model_name = "gemini-2.5-flash"

        self.evaluation_prompt = """
Ты эксперт по оценке виртуальной примерки одежды. Оцени сгенерированное изображение.

КРИТИЧЕСКИ ВАЖНО: Одежда на результате должна выглядеть ИДЕНТИЧНО оригиналу - тот же цвет, рисунок, текстура, детали.

Оцени по шкале 0-10:
1. clothing_match_score - Насколько одежда на результате ИДЕНТИЧНА оригиналу? (цвет, рисунок, детали, форма)
2. fit_score - Насколько естественно одежда сидит на человеке?
3. score - Общая оценка (среднее от двух выше)

Ответь ТОЛЬКО в JSON формате:
{
    "score": <0-10>,
    "clothing_match_score": <0-10>,
    "fit_score": <0-10>,
    "feedback": "<краткая оценка>",
    "issues": ["проблема 1", "проблема 2"],
    "suggestions": ["как исправить 1", "как исправить 2"]
}
"""

    async def evaluate(
        self,
        generated_image_path: str,
        original_person_path: Optional[str] = None,
        original_clothing_path: Optional[str] = None
    ) -> QualityEvaluation:
        """
        Evaluate the quality with special focus on clothing identity.
        """
        try:
            contents = []

            # Оригинальная одежда - ОБЯЗАТЕЛЬНО для сравнения
            if original_clothing_path:
                contents.append("ОРИГИНАЛЬНАЯ ОДЕЖДА (должна выглядеть точно так же):")
                contents.append(Image.open(original_clothing_path))

            # Оригинальный человек
            if original_person_path:
                contents.append("Исходное фото человека:")
                contents.append(Image.open(original_person_path))

            contents.append("РЕЗУЛЬТАТ ПРИМЕРКИ (оцени это):")
            contents.append(Image.open(generated_image_path))
            contents.append(self.evaluation_prompt)

            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=contents
            )

            # Parse JSON
            text = response.text.strip()

            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]

            data = json.loads(text.strip())

            return QualityEvaluation(
                score=float(data.get("score", 0)),
                clothing_match_score=float(data.get("clothing_match_score", 0)),
                fit_score=float(data.get("fit_score", 0)),
                feedback=data.get("feedback", ""),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", [])
            )

        except Exception as e:
            logger.error(f"Error evaluating: {e}")
            return QualityEvaluation(
                score=5.0,
                clothing_match_score=5.0,
                fit_score=5.0,
                feedback=f"Ошибка оценки: {str(e)}",
                issues=["Не удалось оценить"],
                suggestions=["Попробовать снова"]
            )


quality_evaluator = QualityEvaluator()
