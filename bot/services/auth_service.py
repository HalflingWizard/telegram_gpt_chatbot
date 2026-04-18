"""Authorization and whitelist checks for Telegram users."""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from bot.db.repositories import UserRepository
from bot.db.session import session_scope


class AuthService:
    """Validate Telegram users against the configured whitelist."""

    def __init__(self, session_factory: sessionmaker, allowed_user_ids: set[int] | frozenset[int]) -> None:
        """Initialize the service."""
        self.session_factory = session_factory
        self.allowed_user_ids = set(allowed_user_ids)

    def ensure_user(self, telegram_user_id: int, telegram_username: str | None) -> bool:
        """Persist the user record and return whether the user is allowed."""
        is_allowed = telegram_user_id in self.allowed_user_ids
        with session_scope(self.session_factory) as session:
            user_repo = UserRepository(session)
            user_repo.get_or_create(
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
                is_allowed=is_allowed,
            )
        return is_allowed

    def is_allowed(self, telegram_user_id: int, telegram_username: str | None) -> bool:
        """Return whether a Telegram user may use the bot."""
        return self.ensure_user(telegram_user_id, telegram_username)

    def get_preferences(self, telegram_user_id: int) -> str | None:
        """Return saved preferences for a Telegram user."""
        with session_scope(self.session_factory) as session:
            return UserRepository(session).get_preferences(telegram_user_id)

    def set_preferences(self, telegram_user_id: int, preferences: str | None) -> str | None:
        """Save preferences for a Telegram user and return the stored value."""
        normalized = preferences.strip() if preferences else None
        if normalized == "":
            normalized = None
        with session_scope(self.session_factory) as session:
            user = UserRepository(session).set_preferences(telegram_user_id, normalized)
            return user.preferences if user else None

    def delete_all_user_data(self, telegram_user_id: int) -> bool:
        """Delete a user and all locally stored data."""
        with session_scope(self.session_factory) as session:
            return UserRepository(session).delete_user_and_related_data(telegram_user_id)
