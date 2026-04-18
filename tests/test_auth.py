"""Tests for whitelist authorization behavior."""

from bot.db.repositories import UserRepository
from bot.db.session import create_session_factory
from bot.services.auth_service import AuthService
from bot.db.session import session_scope


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


def test_delete_all_user_data_removes_user_record() -> None:
    """Full user deletion should remove the saved user row."""
    session_factory = create_session_factory("sqlite:///:memory:")
    service = AuthService(session_factory, {123})
    service.is_allowed(123, "alice")

    assert service.delete_all_user_data(123) is True

    with session_scope(session_factory) as session:
        assert UserRepository(session).get_by_telegram_user_id(123) is None
