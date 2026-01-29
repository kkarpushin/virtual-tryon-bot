"""Database models for the Virtual Try-On bot."""
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Float,
    ForeignKey, Text, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum

Base = declarative_base()


class SubscriptionType(str, Enum):
    """User subscription types."""
    FREE = "free"
    PACK_10 = "pack_10"
    PACK_50 = "pack_50"
    UNLIMITED_MONTH = "unlimited_month"


class TryonStatus(str, Enum):
    """Try-on generation status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    """User model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)

    # Photo
    photo_file_id = Column(String(255), nullable=True)
    photo_path = Column(String(500), nullable=True)
    photo_updated_at = Column(DateTime, nullable=True)

    # Limits & Subscription
    free_tryons_remaining = Column(Integer, default=5)
    paid_tryons_remaining = Column(Integer, default=0)
    subscription_type = Column(SQLEnum(SubscriptionType), default=SubscriptionType.FREE)
    subscription_expires_at = Column(DateTime, nullable=True)

    # Referral
    referral_code = Column(String(50), unique=True, nullable=True)
    referred_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Easter egg - companion mode
    companion_mode = Column(String(20), nullable=True)  # "female", "male", or None

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    tryons = relationship("Tryon", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    wardrobe_items = relationship("WardrobeItem", back_populates="user")
    referred_users = relationship("User", backref="referrer", remote_side=[id])

    @property
    def has_tryons_available(self) -> bool:
        """Check if user has available try-ons."""
        if self.subscription_type == SubscriptionType.UNLIMITED_MONTH:
            if self.subscription_expires_at and self.subscription_expires_at > datetime.utcnow():
                return True
        return self.free_tryons_remaining > 0 or self.paid_tryons_remaining > 0

    @property
    def total_tryons_available(self) -> int:
        """Get total available try-ons."""
        if self.subscription_type == SubscriptionType.UNLIMITED_MONTH:
            if self.subscription_expires_at and self.subscription_expires_at > datetime.utcnow():
                return float('inf')
        return self.free_tryons_remaining + self.paid_tryons_remaining

    def use_tryon(self) -> bool:
        """Use one try-on. Returns True if successful."""
        if self.subscription_type == SubscriptionType.UNLIMITED_MONTH:
            if self.subscription_expires_at and self.subscription_expires_at > datetime.utcnow():
                return True

        if self.free_tryons_remaining > 0:
            self.free_tryons_remaining -= 1
            return True
        elif self.paid_tryons_remaining > 0:
            self.paid_tryons_remaining -= 1
            return True
        return False


class Tryon(Base):
    """Try-on record model."""
    __tablename__ = "tryons"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Input
    clothing_photo_file_id = Column(String(255), nullable=False)
    clothing_photo_path = Column(String(500), nullable=True)
    clothing_type = Column(String(50), nullable=True)  # top, bottom, dress, etc.

    # Output
    result_photo_path = Column(String(500), nullable=True)
    result_photo_file_id = Column(String(255), nullable=True)

    # AI Processing
    status = Column(SQLEnum(TryonStatus), default=TryonStatus.PENDING)
    prompt_used = Column(Text, nullable=True)
    quality_score = Column(Float, nullable=True)
    iterations_count = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="tryons")
    prompt_history = relationship("PromptHistory", back_populates="tryon")


class PromptHistory(Base):
    """Prompt optimization history."""
    __tablename__ = "prompt_history"

    id = Column(Integer, primary_key=True)
    tryon_id = Column(Integer, ForeignKey("tryons.id"), nullable=False)

    iteration = Column(Integer, default=1)
    prompt = Column(Text, nullable=False)
    quality_score = Column(Float, nullable=True)
    evaluation_feedback = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    tryon = relationship("Tryon", back_populates="prompt_history")


class Payment(Base):
    """Payment record model."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Telegram payment info
    telegram_payment_charge_id = Column(String(255), unique=True, nullable=False)
    provider_payment_charge_id = Column(String(255), nullable=True)

    # Payment details
    amount_stars = Column(Integer, nullable=False)
    product_type = Column(String(50), nullable=False)  # single, pack_10, pack_50, unlimited
    tryons_added = Column(Integer, default=0)

    # Status
    is_refunded = Column(Boolean, default=False)
    refunded_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="payments")


class WardrobeItem(Base):
    """Saved wardrobe items."""
    __tablename__ = "wardrobe_items"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tryon_id = Column(Integer, ForeignKey("tryons.id"), nullable=True)

    # Item details
    name = Column(String(255), nullable=True)
    collection = Column(String(255), nullable=True)  # e.g., "Summer", "Office"

    # Photos
    result_photo_file_id = Column(String(255), nullable=True)
    clothing_photo_file_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="wardrobe_items")


class GlobalPrompt(Base):
    """
    Global prompt storage for self-learning system.
    Stores the best performing prompts that evolve over time.
    """
    __tablename__ = "global_prompts"

    id = Column(Integer, primary_key=True)

    # Clothing type this prompt is for (or 'default' for general)
    clothing_type = Column(String(50), nullable=False, index=True)

    # The prompt text
    prompt = Column(Text, nullable=False)

    # Version number - increments when prompt is improved
    version = Column(Integer, default=1)

    # Performance metrics
    avg_quality_score = Column(Float, default=0.0)  # Average quality across uses
    avg_clothing_match = Column(Float, default=0.0)  # Average clothing match score
    total_uses = Column(Integer, default=0)  # How many times used
    successful_uses = Column(Integer, default=0)  # Uses with score >= 7

    # Is this the currently active prompt for this clothing type?
    is_active = Column(Boolean, default=True)

    # Track evolution
    parent_prompt_id = Column(Integer, ForeignKey("global_prompts.id"), nullable=True)
    improvement_reason = Column(Text, nullable=True)  # Why this version was created

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
