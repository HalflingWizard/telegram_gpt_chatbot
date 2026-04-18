"""Tests for handler-level user-visible behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.chat_commands import (
    PREFERENCES_PENDING_ACTION_KEY,
    currentchat_command,
    preferences_callback,
    preferences_command,
)
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

    def build_preferences_keyboard(self, has_preferences) -> str:
        """Return a fake keyboard marker."""
        return f"keyboard:{has_preferences}"

    def format_preferences_prompt(self, mode, current) -> str:
        """Return a fake prompt."""
        return f"prompt:{mode}:{current}"


class FakeServices:
    """Minimal service container for handler tests."""

    def __init__(self) -> None:
        """Initialize fake dependencies."""
        self.chat_service = SimpleNamespace(get_active_chat=lambda user_id: None)
        self.auth_service = SimpleNamespace(
            get_preferences=lambda user_id: None,
            set_preferences=lambda user_id, preferences: preferences,
        )
        self.formatting_service = FakeFormattingService()
        self.authorize_update = AsyncMock(return_value=True)


def make_context(services: FakeServices):
    """Create a fake Telegram context."""
    return SimpleNamespace(
        application=SimpleNamespace(bot_data={"services": services}),
        bot=AsyncMock(),
        user_data={},
    )


def make_update():
    """Create a fake Telegram update with reply support."""
    message = SimpleNamespace(
        text="hello",
        message_id=99,
        reply_text=AsyncMock(),
    )
    user = SimpleNamespace(id=123, username="alice")
    chat = SimpleNamespace(id=456)
    return SimpleNamespace(effective_message=message, effective_user=user, effective_chat=chat)


async def test_text_handler_requires_active_chat() -> None:
    """Text messages without an active chat should be rejected safely."""
    services = FakeServices()
    update = make_update()
    context = make_context(services)

    await handle_text_message(update, context)

    update.effective_message.reply_text.assert_awaited_once_with(
        "⚠️ No active chat. Use /newchat or /chat <id>."
    )


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
