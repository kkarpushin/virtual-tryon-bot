"""Image utilities for photo processing."""
from PIL import Image
from pathlib import Path
from typing import Tuple, Optional
import io


def resize_image(
    image_path: str,
    max_size: Tuple[int, int] = (1024, 1024),
    output_path: Optional[str] = None
) -> str:
    """
    Resize image to fit within max_size while maintaining aspect ratio.
    
    Args:
        image_path: Path to source image
        max_size: Maximum (width, height)
        output_path: Optional output path, defaults to overwriting source
        
    Returns:
        Path to resized image
    """
    img = Image.open(image_path)
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    output = output_path or image_path
    img.save(output, quality=95)
    
    return output


def is_valid_image(image_path: str) -> bool:
    """Check if file is a valid image."""
    try:
        img = Image.open(image_path)
        img.verify()
        return True
    except Exception:
        return False


def get_image_dimensions(image_path: str) -> Tuple[int, int]:
    """Get image width and height."""
    with Image.open(image_path) as img:
        return img.size


def bytes_to_image(image_bytes: bytes) -> Image.Image:
    """Convert bytes to PIL Image."""
    return Image.open(io.BytesIO(image_bytes))


def image_to_bytes(image: Image.Image, format: str = "PNG") -> bytes:
    """Convert PIL Image to bytes."""
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    return buffer.getvalue()
