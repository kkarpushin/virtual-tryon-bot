"""Validation utilities."""
from PIL import Image
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class PhotoValidationResult:
    """Result of photo validation."""
    def __init__(self, is_valid: bool, message: str = ""):
        self.is_valid = is_valid
        self.message = message


def validate_profile_photo(image_path: str) -> PhotoValidationResult:
    """
    Validate a profile photo for use in try-on.
    
    Checks:
    - Minimum resolution (512x512)
    - Aspect ratio (not too wide/narrow)
    - File format (JPEG, PNG, WEBP)
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            
            # Check minimum resolution
            if width < 512 or height < 512:
                return PhotoValidationResult(
                    False,
                    f"Фото слишком маленькое ({width}x{height}). "
                    "Минимальный размер: 512x512 пикселей."
                )
            
            # Check aspect ratio
            aspect_ratio = width / height
            if aspect_ratio < 0.4 or aspect_ratio > 2.5:
                return PhotoValidationResult(
                    False,
                    "Неподходящие пропорции фото. "
                    "Используйте вертикальное или квадратное фото."
                )
            
            # Check format
            if img.format not in ["JPEG", "PNG", "WEBP", "JPG"]:
                return PhotoValidationResult(
                    False,
                    f"Неподдерживаемый формат ({img.format}). "
                    "Используйте JPEG, PNG или WEBP."
                )
            
            return PhotoValidationResult(True, "Фото подходит")
            
    except Exception as e:
        logger.error(f"Error validating photo: {e}")
        return PhotoValidationResult(False, "Не удалось прочитать фото")


def validate_clothing_photo(image_path: str) -> PhotoValidationResult:
    """
    Validate a clothing photo for try-on.
    
    Checks:
    - Minimum resolution (256x256)
    - File format
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            
            if width < 256 or height < 256:
                return PhotoValidationResult(
                    False,
                    f"Фото одежды слишком маленькое ({width}x{height})."
                )
            
            return PhotoValidationResult(True, "OK")
            
    except Exception as e:
        logger.error(f"Error validating clothing photo: {e}")
        return PhotoValidationResult(False, "Не удалось прочитать фото")
