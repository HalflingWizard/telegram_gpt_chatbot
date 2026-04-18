"""Tests for whitelist authorization behavior."""

from bot.db.session import create_session_factory
from bot.services.auth_service import AuthService


def test_allowed_user_is_persisted_and_authorized() -> None:
    """Allowed users should be marked as authorized."""
    session_factory = create_session_factory("sqlite:///:memory:")
    service = AuthService(session_factory, {123})
    assert service.is_allowed(123, "alice") is True


def test_disallowed_user_is_persisted_and_rejected() -> None:
    """Unknown users should be denied."""
    session_factory = create_session_factory("sqlite:///:memory:")
    service = AuthService(session_factory, {123})
    assert service.is_allowed(999, "mallory") is False
