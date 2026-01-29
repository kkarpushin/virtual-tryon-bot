"""LaoZhang AI API integration for virtual try-on (Nano Banana Pro)."""
import asyncio
import aiohttp
import aiofiles
import base64
from typing import Optional, Tuple
import logging
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


class NanoBananaService:
    """
    Service for virtual try-on image generation using LaoZhang AI API.

    Uses Gemini 3 Pro Image via LaoZhang proxy with:
    - High quality image generation (up to 4K)
    - Multi-image input support
    - True async HTTP for concurrent requests
    """

    def __init__(self):
        self.api_key = settings.laozhang_api_key
        self.api_url = "https://api.laozhang.ai/v1beta/models/gemini-3-pro-image-preview:generateContent"
        self.timeout = aiohttp.ClientTimeout(total=180)  # 3 minutes

    async def _encode_image(self, image_path: str) -> Tuple[str, str]:
        """Encode image to base64 and detect mime type (async file I/O)."""
        path = Path(image_path)
        suffix = path.suffix.lower()

        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        mime_type = mime_types.get(suffix, "image/jpeg")

        async with aiofiles.open(image_path, "rb") as f:
            data = await f.read()
            image_b64 = base64.b64encode(data).decode("utf-8")

        return image_b64, mime_type

    async def generate_tryon(
        self,
        user_photo_path: str,
        clothing_photo_path: str,
        additional_instructions: str = ""
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """Generate a virtual try-on image with simple, direct prompt."""

        prompt = """Одень эту одежду на этого человека.

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

        if additional_instructions:
            prompt += f" {additional_instructions}"

        return await self.generate_with_prompt(user_photo_path, clothing_photo_path, prompt)

    async def generate_with_prompt(
        self,
        user_photo_path: str,
        clothing_photo_path: str,
        custom_prompt: str
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """Generate try-on with a custom prompt using LaoZhang API (true async)."""
        try:
            # Encode images (async file I/O)
            user_b64, user_mime = await self._encode_image(user_photo_path)
            clothing_b64, clothing_mime = await self._encode_image(clothing_photo_path)

            headers = {
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json"
            }

            # Build multi-image request
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Фото человека:"},
                        {"inline_data": {"mime_type": user_mime, "data": user_b64}},
                        {"text": "Одежда:"},
                        {"inline_data": {"mime_type": clothing_mime, "data": clothing_b64}},
                        {"text": custom_prompt}
                    ]
                }],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {
                        "aspectRatio": "1:1",
                        "imageSize": "2K"
                    }
                }
            }

            logger.info("[LaoZhang] Sending async request...")

            # True async HTTP request with aiohttp
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(self.api_url, headers=headers, json=payload) as response:
                    logger.info(f"[LaoZhang] Response status: {response.status}")

                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"[LaoZhang] Error response: {error_text[:500]}")
                        return None, f"API ошибка: {response.status}"

                    result = await response.json()

            # Check for errors in response
            if "error" in result:
                error_msg = result["error"].get("message", str(result["error"]))
                logger.error(f"[LaoZhang] API error: {error_msg}")
                return None, f"Ошибка генерации: {error_msg}"

            # Extract image from response
            try:
                candidates = result.get("candidates", [])
                if not candidates:
                    logger.warning("[LaoZhang] No candidates in response")
                    return None, "Модель не смогла сгенерировать изображение"

                content = candidates[0].get("content", {})
                parts = content.get("parts", [])

                for part in parts:
                    if "inlineData" in part:
                        image_data = part["inlineData"].get("data")
                        if image_data:
                            logger.info("[LaoZhang] Image generated successfully!")
                            return base64.b64decode(image_data), None

                logger.warning("[LaoZhang] No image data in response")
                return None, "Изображение не найдено в ответе"

            except (KeyError, IndexError) as e:
                logger.error(f"[LaoZhang] Error parsing response: {e}")
                return None, "Ошибка обработки ответа API"

        except asyncio.TimeoutError:
            logger.error("[LaoZhang] Request timeout")
            return None, "Таймаут запроса. Попробуйте ещё раз."

        except aiohttp.ClientError as e:
            logger.error(f"[LaoZhang] Client error: {e}")
            return None, f"Ошибка сети: {str(e)}"

        except Exception as e:
            logger.error(f"[LaoZhang] Unexpected error: {e}")
            return None, str(e)

    async def detect_clothing_type(self, image_path: str) -> str:
        """Detect the type of clothing from an image using text model."""
        try:
            image_b64, mime_type = await self._encode_image(image_path)

            headers = {
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json"
            }

            payload = {
                "contents": [{
                    "parts": [
                        {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                        {"text": """Определи тип одежды на фото. Ответь ОДНИМ словом:
- top (футболка, рубашка, блузка, свитер)
- bottom (штаны, джинсы, шорты, юбка)
- dress (платье, комбинезон)
- outerwear (куртка, пальто, пиджак)
- swimwear (купальник, плавки)
- underwear (нижнее белье)
- accessory (сумка, шляпа, обувь)

Ответь только одним словом: top, bottom, dress, outerwear, swimwear, underwear, accessory. Если не уверен - ответь top."""}
                    ]
                }],
                "generationConfig": {
                    "responseModalities": ["TEXT"]
                }
            }

            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.api_url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        logger.warning(f"[LaoZhang] Clothing detection failed: {response.status}")
                        return "top"

                    result = await response.json()

            text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip().lower()

            valid_types = ["top", "bottom", "dress", "outerwear", "swimwear", "underwear", "accessory"]
            for t in valid_types:
                if t in text:
                    return t

            return "top"

        except Exception as e:
            logger.error(f"[LaoZhang] Error detecting clothing type: {e}")
            return "top"


# Global service instance
nano_banana_service = NanoBananaService()
