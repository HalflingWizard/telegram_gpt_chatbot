"""Configuration loading for the Telegram bot."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_WELCOME_STICKER = "CAACAgQAAxkBAAEQ8fVp4vqqCT9aBQmZK2iVdB1-ILgauwAC_gwAAhexSFBbzkvZt_rnPzsE"


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    telegram_bot_token: str
    openai_api_key: str
    allowed_telegram_user_ids: frozenset[int]
    openai_main_model: str
    openai_title_model: str
    openai_reasoning_effort: str
    database_url: str
    log_level: str
    openai_timeout_seconds: float
    telegram_file_size_limit_bytes: int
    default_sticker_file_id: str | None


def load_settings() -> Settings:
    """Load, validate, and return application settings."""
    load_dotenv()

    telegram_bot_token = _require_env("TELEGRAM_BOT_TOKEN")
    openai_api_key = _require_env("OPENAI_API_KEY")
    allowed_ids = _parse_allowed_ids(_require_env("ALLOWED_TELEGRAM_USER_IDS"))

    return Settings(
        telegram_bot_token=telegram_bot_token,
        openai_api_key=openai_api_key,
        allowed_telegram_user_ids=frozenset(allowed_ids),
        openai_main_model=os.getenv("OPENAI_MAIN_MODEL", "gpt-5.1"),
        openai_title_model=os.getenv("OPENAI_TITLE_MODEL", "gpt-5-mini"),
        openai_reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "medium"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/telegram_gpt_bot.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        openai_timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "90")),
        telegram_file_size_limit_bytes=int(
            float(os.getenv("TELEGRAM_FILE_SIZE_LIMIT_MB", "20")) * 1024 * 1024
        ),
        default_sticker_file_id=os.getenv("DEFAULT_STICKER_FILE_ID", DEFAULT_WELCOME_STICKER),
    )


def _require_env(name: str) -> str:
    """Return a required environment variable or raise a helpful error."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _parse_allowed_ids(value: str) -> set[int]:
    """Parse a comma-separated whitelist of Telegram user IDs."""
    parsed_ids: set[int] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        parsed_ids.add(int(item))
    if not parsed_ids:
        raise ValueError("ALLOWED_TELEGRAM_USER_IDS must contain at least one numeric ID.")
    return parsed_ids
