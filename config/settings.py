"""Bot configuration settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Bot
    bot_token: str = Field(..., alias="BOT_TOKEN")
    bot_username: str = Field("", alias="BOT_USERNAME")

    # AI API
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")

    # Database
    database_url: str = Field("sqlite:///./data/bot.db", alias="DATABASE_URL")

    # Limits
    free_tryons_limit: int = Field(5, alias="FREE_TRYONS_LIMIT")
    max_prompt_iterations: int = Field(3, alias="MAX_PROMPT_ITERATIONS")
    min_quality_score: int = Field(7, alias="MIN_QUALITY_SCORE")

    # Payments (Telegram Stars)
    tryon_price_stars: int = Field(10, alias="TRYON_PRICE_STARS")
    pack_10_price_stars: int = Field(80, alias="PACK_10_PRICE_STARS")
    pack_50_price_stars: int = Field(350, alias="PACK_50_PRICE_STARS")
    unlimited_month_price_stars: int = Field(500, alias="UNLIMITED_MONTH_PRICE_STARS")

    # Storage
    photos_dir: Path = Field(Path("./data/photos"), alias="PHOTOS_DIR")

    # Referral bonuses
    referral_bonus_tryons: int = Field(3, alias="REFERRAL_BONUS_TRYONS")
    referrer_bonus_on_payment: int = Field(1, alias="REFERRER_BONUS_ON_PAYMENT")

    # Admin
    admin_chat_id: Optional[int] = Field(default=None, alias="ADMIN_CHAT_ID")

    @field_validator("admin_chat_id", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if v == "" or v is None:
            return None
        return int(v)

    def ensure_directories(self):
        """Create necessary directories if they don't exist."""
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        Path("./data").mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
