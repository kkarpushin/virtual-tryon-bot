"""Gemini 3 Pro Image API integration for virtual try-on (Nano Banana Pro)."""
from google import genai
from google.genai import types
from PIL import Image
import asyncio
from typing import Optional, Tuple
import logging

from config import settings

logger = logging.getLogger(__name__)


class NanoBananaService:
    """
    Service for virtual try-on image generation using Gemini 3 Pro Image.
    
    Uses the most powerful model with:
    - Thinking process (enabled by default, cannot be disabled)
    - High quality image generation (up to 4K)
    - Multi-image input support
    """
    
    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        # Gemini 3 Pro Image - most powerful model for image generation
        self.model_name = "gemini-3-pro-image-preview"
        # For text tasks - use stable model name
        self.text_model_name = "gemini-2.5-flash"
        
        # Image generation config for high quality output
        self.image_config = types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(
                image_size="2K",  # High resolution output
            )
        )
    
    async def generate_tryon(
        self,
        user_photo_path: str,
        clothing_photo_path: str,
        additional_instructions: str = ""
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """Generate a virtual try-on image with simple, direct prompt."""
        try:
            user_image = Image.open(user_photo_path)
            clothing_image = Image.open(clothing_photo_path)
            
            # Простой и прямой промпт с акцентом на сохранение пропорций
            prompt = """Одень эту одежду на этого человека. 

ВАЖНО:
- Одежда должна выглядеть точно так же как на исходном фото - тот же цвет, текстура, рисунок, детали
- НЕ МЕНЯТЬ тело человека: рост, вес, пропорции, телосложение должны остаться ТОЧНО такими же
- Если одежда слишком большая - она должна висеть, выглядеть мешковато
- Если одежда слишком маленькая - она должна выглядеть тесной, обтягивающей
- Покажи РЕАЛИСТИЧНУЮ посадку одежды на РЕАЛЬНОЕ тело человека
- Сохрани позу, лицо и внешность человека"""
            
            if additional_instructions:
                prompt += f" {additional_instructions}"
            
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=[
                    "Фото человека:",
                    user_image,
                    "Одежда для примерки:",
                    clothing_image,
                    prompt,
                ],
                config=self.image_config
            )
            
            # Log response for debugging
            logger.info(f"Response type: {type(response)}")
            logger.info(f"Response: {response}")
            
            # Check if response is valid
            if response is None:
                logger.error("Response is None")
                return None, "Модель вернула пустой ответ"
            
            # Log full response for debugging
            num_candidates = len(response.candidates) if hasattr(response, 'candidates') and response.candidates else 0
            logger.info(f"Response candidates count: {num_candidates}")
            
            if hasattr(response, 'prompt_feedback'):
                logger.info(f"Prompt feedback: {response.prompt_feedback}")
            
            if num_candidates > 0:
                for i, cand in enumerate(response.candidates):
                    if hasattr(cand, 'finish_reason'):
                        logger.info(f"Candidate {i} finish_reason: {cand.finish_reason}")
                    if hasattr(cand, 'safety_ratings') and cand.safety_ratings:
                        logger.info(f"Candidate {i} safety_ratings: {cand.safety_ratings}")
            
            # Check if response has parts (may be empty due to content policy)
            if not response or not response.parts:
                # Check for blocked reason
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    logger.warning(f"Generation blocked by prompt_feedback: {response.prompt_feedback}")
                    return None, "Генерация заблокирована политикой безопасности. Попробуйте другое фото одежды."
                # Check candidates for finish reason
                if response and response.candidates:
                    for cand in response.candidates:
                        if hasattr(cand, 'finish_reason') and cand.finish_reason:
                            logger.warning(f"Generation stopped: {cand.finish_reason}")
                            if "SAFETY" in str(cand.finish_reason):
                                return None, "Генерация заблокирована по соображениям безопасности"
                return None, "Модель не смогла сгенерировать изображение. Попробуйте другое фото."
            
            # Get the final (non-thought) image
            for part in response.parts:
                if part.text is not None and not getattr(part, 'thought', False):
                    logger.info(f"Model text: {part.text[:200]}...")
                elif part.inline_data is not None and not getattr(part, 'thought', False):
                    return part.inline_data.data, None
            
            # Fallback: return any image if no non-thought image found
            for part in response.parts:
                if part.inline_data is not None:
                    return part.inline_data.data, None
            
            return None, "No image generated"
            
        except Exception as e:
            logger.error(f"Error generating try-on: {e}")
            return None, str(e)
    
    async def generate_with_prompt(
        self,
        user_photo_path: str,
        clothing_photo_path: str,
        custom_prompt: str
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """Generate try-on with a custom prompt using Thinking model."""
        try:
            user_image = Image.open(user_photo_path)
            clothing_image = Image.open(clothing_photo_path)
            
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=[
                    "Фото человека:",
                    user_image,
                    "Одежда:",
                    clothing_image,
                    custom_prompt,
                ],
                config=self.image_config
            )
            
            # Detailed logging for debugging
            logger.info(f"[generate_with_prompt] Response received")
            logger.info(f"[generate_with_prompt] Response type: {type(response)}")
            
            if response is None:
                logger.error("[generate_with_prompt] Response is None!")
                return None, "Модель вернула пустой ответ"
            
            # Log candidates
            if hasattr(response, 'candidates') and response.candidates:
                logger.info(f"[generate_with_prompt] Candidates: {len(response.candidates)}")
                for i, cand in enumerate(response.candidates):
                    logger.info(f"[generate_with_prompt] Candidate {i}: finish_reason={getattr(cand, 'finish_reason', 'N/A')}")
                    if hasattr(cand, 'content') and cand.content:
                        num_parts = len(cand.content.parts) if hasattr(cand.content, 'parts') and cand.content.parts else 0
                        logger.info(f"[generate_with_prompt] Candidate {i} has {num_parts} parts")
            else:
                logger.warning("[generate_with_prompt] No candidates in response!")
            
            # Log prompt feedback  
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                logger.warning(f"[generate_with_prompt] Prompt feedback: {response.prompt_feedback}")
            
            # Check if response has parts (may be empty due to content policy)
            if not response.parts:
                logger.warning("[generate_with_prompt] response.parts is empty!")
                
                # Check finish reason for why generation failed
                if response.candidates:
                    for cand in response.candidates:
                        finish_reason = getattr(cand, 'finish_reason', None)
                        if finish_reason:
                            finish_str = str(finish_reason)
                            if "IMAGE_OTHER" in finish_str or "SAFETY" in finish_str:
                                return None, "⚠️ К сожалению, модель отказала в генерации этого типа одежды. Попробуйте другую одежду (футболки, платья, верхняя одежда работают лучше)."
                
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    return None, f"Заблокировано: {response.prompt_feedback}"
                return None, "Модель не смогла сгенерировать изображение. Попробуйте другое фото."
            
            # Get the final (non-thought) image - this is the best quality result
            for part in response.parts:
                if part.inline_data is not None and not getattr(part, 'thought', False):
                    return part.inline_data.data, None
            
            # Fallback: return any image if no non-thought image found
            for part in response.parts:
                if part.inline_data is not None:
                    return part.inline_data.data, None
            
            return None, "No image generated"
            
        except Exception as e:
            logger.error(f"Error generating: {e}")
            return None, str(e)
    
    async def detect_clothing_type(self, clothing_photo_path: str) -> str:
        """Detect the type of clothing in the photo."""
        try:
            clothing_image = Image.open(clothing_photo_path)
            
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.text_model_name,
                contents=[
                    clothing_image,
                    "Определи тип одежды на изображении. Ответь ОДНИМ словом из списка: top, bottom, dress, outerwear, swimwear, underwear, accessory, shoes. Если не уверен - ответь top или bottom.",
                ]
            )
            
            result = response.text.strip().lower()
            valid_types = ["top", "bottom", "dress", "outerwear", "swimwear", "underwear", "accessory", "shoes"]
            
            # Map some types to default if not in valid list
            if result not in valid_types:
                # Try to extract valid type from response
                for valid in valid_types:
                    if valid in result:
                        return valid
                return "top"  # Default to top instead of unknown
            
            return result
            
        except Exception as e:
            logger.error(f"Error detecting clothing type: {e}")
            return "top"  # Default to top instead of unknown


nano_banana_service = NanoBananaService()
