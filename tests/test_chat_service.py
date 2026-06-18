"""Tests for chat creation and switching."""

import json

from bot.db.models import ChatState
from bot.db.session import create_session_factory, session_scope
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


def test_record_token_usage_persists_warning_state() -> None:
    """Token usage should be saved in chat state notes."""
    session_factory = create_session_factory("sqlite:///:memory:")
    AuthService(session_factory, {123}).is_allowed(123, "alice")
    chat_service = ChatService(session_factory)
    chat = chat_service.create_new_chat(123)

    warning = chat_service.record_token_usage(
        chat_id=chat.id,
        input_tokens=76,
        output_tokens=10,
        total_tokens=86,
        context_window_tokens=100,
    )

    assert warning is not None
    assert warning.level == "medium"
    assert warning.percent_used == 76
    with session_scope(session_factory) as session:
        state = session.query(ChatState).filter_by(chat_id=chat.id).one()
        notes = json.loads(state.notes)
    assert notes["token_usage"]["last_input_tokens"] == 76
    assert notes["token_usage"]["cumulative_total_tokens"] == 86

    repeated = chat_service.record_token_usage(
        chat_id=chat.id,
        input_tokens=80,
        output_tokens=10,
        total_tokens=90,
        context_window_tokens=100,
    )
    assert repeated is None


def test_persona_creation_and_selection() -> None:
    """Users should be able to create and select personas."""
    session_factory = create_session_factory("sqlite:///:memory:")
    AuthService(session_factory, {123}).is_allowed(123, "alice")
    chat_service = ChatService(session_factory)
    chat = chat_service.create_new_chat(123)

    personas = chat_service.list_personas(123)
    assert [persona.name for persona in personas] == ["Bot Guide"]

    created = chat_service.create_persona(
        telegram_user_id=123,
        name="Study Coach",
        system_prompt="Explain step by step.",
    )
    assert created.name == "Study Coach"

    selected = chat_service.set_active_persona(
        telegram_user_id=123,
        chat_id=chat.id,
        name="Study Coach",
    )
    active = chat_service.get_active_persona_for_chat(chat.id)

    assert selected.name == "Study Coach"
    assert active.system_prompt == "Explain step by step."

    chat_service.clear_active_persona(chat.id)
    assert chat_service.get_active_persona_for_chat(chat.id) is None
