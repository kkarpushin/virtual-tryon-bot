"""Handlers module."""
from .start import register_start_handlers
from .photo import register_photo_handlers
from .payment import register_payment_handlers
from .wardrobe import register_wardrobe_handlers


def register_all_handlers(application):
    """Register all bot handlers."""
    register_start_handlers(application)
    register_photo_handlers(application)
    register_payment_handlers(application)
    register_wardrobe_handlers(application)
    # companion handlers removed - easter egg is now automatic!


__all__ = [
    "register_all_handlers",
    "register_start_handlers",
    "register_photo_handlers",
    "register_payment_handlers",
    "register_wardrobe_handlers",
]
