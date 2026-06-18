"""Tests for handler-level user-visible behavior."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import bot.handlers.media_messages as media_messages
from bot.handlers.chat_commands import (
    PREFERENCES_PENDING_ACTION_KEY,
    currentchat_command,
    deleteall_callback,
    deleteall_command,
    preferences_callback,
    preferences_command,
)
from bot.handlers.media_messages import handle_document_message, handle_photo_message
from bot.handlers.text_messages import handle_text_message


class FakeFormattingService:
    """Formatting stub for handler tests."""

    def format_current_chat(self, chat) -> str:
        """Return a fixed message."""
        return "⚠️ No active chat. Use /newchat or /chat <id>."

    def format_preferences(self, preferences) -> str:
        """Return a fixed preference message."""
        return "⚙️ Preferences\n\nNo preferences saved yet." if not preferences else f"⚙️ Preferences\n\n{preferences}"

    def format_preferences_updated(self, preferences) -> str:
        """Return a fixed preference update message."""
        return f"✅ Preferences saved.\n\n{preferences}"

    def format_context_window_warning(self, warning) -> str:
        """Return a fake context warning."""
        return f"context-warning:{warning.level}:{warning.percent_used}"

    def build_preferences_keyboard(self, has_preferences) -> str:
        """Return a fake keyboard marker."""
        return f"keyboard:{has_preferences}"

    def format_preferences_prompt(self, mode, current) -> str:
        """Return a fake prompt."""
        return f"prompt:{mode}:{current}"

    def format_delete_all_prompt(self) -> str:
        """Return a fake delete-all prompt."""
        return "delete-all-prompt"

    def build_delete_all_keyboard(self) -> str:
        """Return a fake delete-all keyboard."""
        return "delete-all-keyboard"

    def format_delete_all_done(self) -> str:
        """Return a fake delete-all confirmation."""
        return "delete-all-done"


class FakeServices:
    """Minimal service container for handler tests."""

    def __init__(self) -> None:
        """Initialize fake dependencies."""
        self.chat_service = SimpleNamespace(get_active_chat=lambda user_id: None)
        self.auth_service = SimpleNamespace(
            get_preferences=lambda user_id: None,
            set_preferences=lambda user_id, preferences: preferences,
            delete_all_user_data=lambda user_id: True,
        )
        self.formatting_service = FakeFormattingService()
        self.authorize_update = AsyncMock(return_value=True)


class FakeMediaServices:
    """Service container stub for media handler tests."""

    def __init__(self, active_chat=None) -> None:
        """Initialize fake media dependencies."""
        self.active_chat = active_chat
        if self.active_chat is None:
            self.active_chat = SimpleNamespace(
                id=1,
                state=SimpleNamespace(last_openai_response_id="resp_prev"),
                title="Untitled chat",
                chat_public_id="abc123",
            )
        self.chat_service = SimpleNamespace(
            get_active_chat=lambda user_id: self.active_chat,
            store_user_message=Mock(),
            store_assistant_message=Mock(),
            record_token_usage=Mock(return_value=None),
            update_title=Mock(),
        )
        self.settings = SimpleNamespace(openai_context_window_tokens=100)
        self.auth_service = SimpleNamespace(get_preferences=lambda user_id: "Reply briefly")
        self.formatting_service = FakeFormattingService()
        self.telegram_file_service = SimpleNamespace(download_photo=AsyncMock(), download_document=AsyncMock())
        self.openai_service = SimpleNamespace(
            upload_user_file=AsyncMock(side_effect=["file_1", "file_2"]),
            create_response=AsyncMock(return_value=SimpleNamespace(text="answer", response_id="resp_new", usage=None)),
        )
        self.title_service = SimpleNamespace(create_title=AsyncMock(return_value=("Shared images", "generated")))
        self.openai_input_attachment = lambda **kwargs: SimpleNamespace(**kwargs)
        self.telegram_file_too_large_error = RuntimeError
        self.openai_error = RuntimeError
        self.openai_timeout_error = TimeoutError
        self.authorize_update = AsyncMock(return_value=True)
        self.log_event = Mock()


class FakeApplication:
    """Application stub that records background tasks."""

    def __init__(self, services) -> None:
        """Initialize fake app data."""
        self.bot_data = {"services": services}
        self.created_tasks = []

    def create_task(self, coroutine, update=None):
        """Create and record an asyncio task."""
        task = asyncio.create_task(coroutine)
        self.created_tasks.append(task)
        return task


def make_context(services: FakeServices):
    """Create a fake Telegram context."""
    return SimpleNamespace(
        application=SimpleNamespace(bot_data={"services": services}),
        bot=AsyncMock(),
        user_data={},
    )


def make_media_context(services: FakeMediaServices):
    """Create a fake Telegram context for media tests."""
    application = FakeApplication(services)
    return SimpleNamespace(
        application=application,
        bot=AsyncMock(),
        user_data={},
    )


def make_update():
    """Create a fake Telegram update with reply support."""
    message = SimpleNamespace(
        text="hello",
        caption=None,
        photo=[],
        document=None,
        message_id=99,
        reply_text=AsyncMock(),
    )
    user = SimpleNamespace(id=123, username="alice")
    chat = SimpleNamespace(id=456)
    return SimpleNamespace(effective_message=message, effective_user=user, effective_chat=chat)


def make_text_update(message_id: int, text: str):
    """Create a fake text update."""
    message = SimpleNamespace(
        text=text,
        caption=None,
        photo=[],
        document=None,
        message_id=message_id,
        reply_text=AsyncMock(),
    )
    user = SimpleNamespace(id=123, username="alice")
    chat = SimpleNamespace(id=456)
    return SimpleNamespace(effective_message=message, effective_user=user, effective_chat=chat)


def make_photo_update(message_id: int, media_group_id: str, caption: str | None = None):
    """Create a fake photo update."""
    photo = SimpleNamespace(file_id=f"telegram_file_{message_id}", file_unique_id=f"unique_{message_id}")
    message = SimpleNamespace(
        message_id=message_id,
        media_group_id=media_group_id,
        caption=caption,
        photo=[photo],
        document=None,
        reply_text=AsyncMock(),
    )
    user = SimpleNamespace(id=123, username="alice")
    chat = SimpleNamespace(id=456)
    return SimpleNamespace(effective_message=message, effective_user=user, effective_chat=chat)


def make_document_update(message_id: int, media_group_id: str, caption: str | None = None):
    """Create a fake document update."""
    document = SimpleNamespace(file_id=f"telegram_file_{message_id}", file_unique_id=f"unique_{message_id}")
    message = SimpleNamespace(
        message_id=message_id,
        media_group_id=media_group_id,
        caption=caption,
        photo=[],
        document=document,
        reply_text=AsyncMock(),
    )
    user = SimpleNamespace(id=123, username="alice")
    chat = SimpleNamespace(id=456)
    return SimpleNamespace(effective_message=message, effective_user=user, effective_chat=chat)


def make_downloaded_photo(index: int):
    """Create fake downloaded Telegram photo metadata."""
    return SimpleNamespace(
        telegram_file_id=f"telegram_file_{index}",
        telegram_file_unique_id=f"unique_{index}",
        local_path=SimpleNamespace(name=f"image_{index}.jpg"),
        filename=f"image_{index}.jpg",
        mime_type="image/jpeg",
        file_size=1024,
    )


def make_downloaded_document(index: int):
    """Create fake downloaded Telegram document metadata."""
    return SimpleNamespace(
        telegram_file_id=f"telegram_file_{index}",
        telegram_file_unique_id=f"unique_{index}",
        local_path=SimpleNamespace(name=f"file_{index}.pdf"),
        filename=f"file_{index}.pdf",
        mime_type="application/pdf",
        file_size=2048,
    )


async def test_text_handler_requires_active_chat(monkeypatch) -> None:
    """Text messages without an active chat should be rejected safely."""
    monkeypatch.setattr(media_messages, "USER_TURN_BUFFER_SECONDS", 0.01)
    services = FakeMediaServices(active_chat=None)
    services.chat_service.get_active_chat = lambda user_id: None
    update = make_update()
    context = make_media_context(services)

    await handle_text_message(update, context)
    await asyncio.gather(*context.application.created_tasks, return_exceptions=True)

    update.effective_message.reply_text.assert_awaited_once_with(
        "⚠️ No active chat. Use /newchat or /chat <id>."
    )


async def test_split_text_messages_use_one_openai_call(monkeypatch) -> None:
    """Nearby text messages should be joined into one model turn."""
    monkeypatch.setattr(media_messages, "USER_TURN_BUFFER_SECONDS", 0.01)
    services = FakeMediaServices()
    context = make_media_context(services)
    first_update = make_text_update(message_id=11, text="This is part one.")
    second_update = make_text_update(message_id=12, text="This is part two.")

    await handle_text_message(first_update, context)
    await handle_text_message(second_update, context)
    await asyncio.gather(*context.application.created_tasks, return_exceptions=True)

    services.openai_service.create_response.assert_awaited_once()
    call_kwargs = services.openai_service.create_response.await_args.kwargs
    assert call_kwargs["prompt_text"] == "This is part one.\n\nThis is part two."
    assert call_kwargs["attachments"] == []
    stored_kwargs = services.chat_service.store_user_message.call_args.kwargs
    assert stored_kwargs["message_type"] == "text"
    assert stored_kwargs["text_content"] == "This is part one.\n\nThis is part two."
    first_update.effective_message.reply_text.assert_awaited_once_with("answer")


async def test_context_warning_is_sent_after_reply(monkeypatch) -> None:
    """A new context warning should be sent after the assistant answer."""
    monkeypatch.setattr(media_messages, "USER_TURN_BUFFER_SECONDS", 0.01)
    warning = SimpleNamespace(level="high", percent_used=86)
    services = FakeMediaServices()
    services.openai_service.create_response.return_value = SimpleNamespace(
        text="answer",
        response_id="resp_new",
        usage=SimpleNamespace(input_tokens=86, output_tokens=10, total_tokens=96),
    )
    services.chat_service.record_token_usage.return_value = warning
    context = make_media_context(services)
    update = make_text_update(message_id=11, text="hello")

    await handle_text_message(update, context)
    await asyncio.gather(*context.application.created_tasks, return_exceptions=True)

    services.chat_service.record_token_usage.assert_called_once_with(
        chat_id=1,
        input_tokens=86,
        output_tokens=10,
        total_tokens=96,
        context_window_tokens=100,
    )
    assert update.effective_message.reply_text.await_args_list[0].args == ("answer",)
    assert update.effective_message.reply_text.await_args_list[1].args == ("context-warning:high:86",)


async def test_photo_media_group_uses_one_openai_call(monkeypatch) -> None:
    """Photo albums should be sent to OpenAI as one turn."""
    monkeypatch.setattr(media_messages, "USER_TURN_BUFFER_SECONDS", 0.01)
    services = FakeMediaServices()
    services.telegram_file_service.download_photo.side_effect = [
        make_downloaded_photo(1),
        make_downloaded_photo(2),
    ]
    context = make_media_context(services)
    first_update = make_photo_update(message_id=11, media_group_id="album-1", caption="Compare these")
    second_update = make_photo_update(message_id=12, media_group_id="album-1")

    await handle_photo_message(first_update, context)
    await handle_photo_message(second_update, context)
    await asyncio.gather(*context.application.created_tasks, return_exceptions=True)

    services.openai_service.create_response.assert_awaited_once()
    call_kwargs = services.openai_service.create_response.await_args.kwargs
    assert call_kwargs["prompt_text"] == "Compare these"
    assert len(call_kwargs["attachments"]) == 2
    assert [item.attachment_type for item in call_kwargs["attachments"]] == ["image", "image"]
    services.chat_service.store_user_message.assert_called_once()
    stored_kwargs = services.chat_service.store_user_message.call_args.kwargs
    assert stored_kwargs["message_type"] == "image"
    assert len(stored_kwargs["attachments"]) == 2
    first_update.effective_message.reply_text.assert_awaited_once_with("answer")


async def test_mixed_media_group_uses_one_openai_call(monkeypatch) -> None:
    """Mixed albums should keep images and files in one turn."""
    monkeypatch.setattr(media_messages, "USER_TURN_BUFFER_SECONDS", 0.01)
    services = FakeMediaServices()
    services.telegram_file_service.download_photo.return_value = make_downloaded_photo(1)
    services.telegram_file_service.download_document.return_value = make_downloaded_document(2)
    context = make_media_context(services)
    photo_update = make_photo_update(message_id=11, media_group_id="album-2", caption="Review these")
    document_update = make_document_update(message_id=12, media_group_id="album-2")

    await handle_photo_message(photo_update, context)
    await handle_document_message(document_update, context)
    await asyncio.gather(*context.application.created_tasks, return_exceptions=True)

    services.openai_service.create_response.assert_awaited_once()
    call_kwargs = services.openai_service.create_response.await_args.kwargs
    assert call_kwargs["prompt_text"] == "Review these"
    assert [item.attachment_type for item in call_kwargs["attachments"]] == ["image", "file"]
    stored_kwargs = services.chat_service.store_user_message.call_args.kwargs
    assert stored_kwargs["message_type"] == "mixed_media"
    assert len(stored_kwargs["attachments"]) == 2


async def test_currentchat_reports_no_active_chat() -> None:
    """The current chat command should return the formatter output."""
    services = FakeServices()
    update = make_update()
    context = make_context(services)

    await currentchat_command(update, context)

    update.effective_message.reply_text.assert_awaited_once_with(
        "⚠️ No active chat. Use /newchat or /chat <id>."
    )


async def test_preferences_command_saves_preferences() -> None:
    """The preferences command should persist provided text."""
    services = FakeServices()
    update = make_update()
    context = make_context(services)
    context.args = ["Reply", "briefly"]

    await preferences_command(update, context)

    update.effective_message.reply_text.assert_awaited_once_with(
        "✅ Preferences saved.\n\nReply briefly"
    )


async def test_preferences_command_opens_menu() -> None:
    """The preferences command without args should open the menu."""
    services = FakeServices()
    update = make_update()
    context = make_context(services)
    context.args = []

    await preferences_command(update, context)

    update.effective_message.reply_text.assert_awaited_once_with(
        "⚙️ Preferences\n\nNo preferences saved yet.",
        reply_markup="keyboard:False",
    )


async def test_preferences_callback_sets_pending_state() -> None:
    """The add/edit buttons should switch the user into preference input mode."""
    services = FakeServices()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123, username="alice"),
        callback_query=SimpleNamespace(
            data="prefs:add",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        ),
    )
    context = make_context(services)

    await preferences_callback(update, context)

    assert context.user_data[PREFERENCES_PENDING_ACTION_KEY] == "add"
    update.callback_query.edit_message_text.assert_not_awaited()
    update.callback_query.message.reply_text.assert_awaited_once_with("prompt:add:None")


async def test_text_handler_saves_pending_preferences_before_chatting() -> None:
    """A pending preference input should be saved instead of treated as chat text."""
    services = FakeServices()
    update = make_update()
    context = make_context(services)
    context.user_data[PREFERENCES_PENDING_ACTION_KEY] = "add"

    await handle_text_message(update, context)

    assert PREFERENCES_PENDING_ACTION_KEY not in context.user_data
    update.effective_message.reply_text.assert_awaited_once_with(
        "✅ Preferences saved.\n\nhello"
    )


async def test_deleteall_command_opens_confirmation() -> None:
    """The deleteall command should ask for confirmation."""
    services = FakeServices()
    update = make_update()
    context = make_context(services)

    await deleteall_command(update, context)

    update.effective_message.reply_text.assert_awaited_once_with(
        "delete-all-prompt",
        reply_markup="delete-all-keyboard",
    )


async def test_deleteall_callback_confirms_and_clears_state() -> None:
    """Confirmed delete-all should wipe data and clear local state."""
    services = FakeServices()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123, username="alice"),
        callback_query=SimpleNamespace(
            data="deleteall:confirm",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        ),
    )
    context = make_context(services)
    context.user_data[PREFERENCES_PENDING_ACTION_KEY] = "add"

    await deleteall_callback(update, context)

    assert context.user_data == {}
    update.callback_query.edit_message_text.assert_awaited_once_with("delete-all-done")
