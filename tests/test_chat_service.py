"""Tests for chat creation and switching."""

from bot.db.session import create_session_factory
from bot.services.auth_service import AuthService
from bot.services.chat_service import ChatService


def test_create_new_chat_sets_active_chat() -> None:
    """Creating a new chat should make it active."""
    session_factory = create_session_factory("sqlite:///:memory:")
    AuthService(session_factory, {123}).is_allowed(123, "alice")
    chat_service = ChatService(session_factory)

    chat = chat_service.create_new_chat(123)

    assert chat.chat_public_id
    assert chat.active is True
    assert chat_service.get_active_chat(123).chat_public_id == chat.chat_public_id


def test_switch_active_chat_changes_current_chat() -> None:
    """Switching chats should update the active pointer."""
    session_factory = create_session_factory("sqlite:///:memory:")
    AuthService(session_factory, {123}).is_allowed(123, "alice")
    chat_service = ChatService(session_factory)

    first = chat_service.create_new_chat(123)
    second = chat_service.create_new_chat(123)
    switched = chat_service.switch_active_chat(123, first.chat_public_id)

    assert switched is not None
    assert switched.chat_public_id == first.chat_public_id
    assert chat_service.get_active_chat(123).chat_public_id == first.chat_public_id
    assert second.chat_public_id != first.chat_public_id
