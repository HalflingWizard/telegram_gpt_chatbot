"""Formatting helpers for Telegram responses."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import Chat
from bot.services.chat_service import TranscriptMessage
from bot.utils.time import format_chat_timestamp


class FormattingService:
    """Build Telegram-friendly text and keyboard layouts."""

    def format_help_text(self) -> str:
        """Return the help message shown to users."""
        return (
            "✨ Available commands\n\n"
            "/newchat\nCreate a new chat and make it active\n\n"
            "/chat <id>\nResume a saved chat by ID\n\n"
            "/listchats\nShow your recent chats\n\n"
            "/currentchat\nShow the active chat\n\n"
            "/deletechat <id>\nDelete a chat\n\n"
            "/deleteall\nDelete all your chats and preferences\n\n"
            "/preferences\nOpen your preferences menu"
        )

    def format_start_text(self) -> str:
        """Return the start message shown to users."""
        return (
            "👋 Welcome. This bot is private and only works for approved Telegram users.\n\n"
            "💬 Use /newchat to begin, /chat <id> to resume a saved thread, and /listchats to browse."
        )

    def format_current_chat(self, chat: Chat | None) -> str:
        """Return a readable current-chat summary."""
        if chat is None:
            return "⚠️ No active chat. Use /newchat or /chat <id>."
        updated = format_chat_timestamp(chat.last_message_at or chat.updated_at)
        return f"🧵 Active chat: {chat.chat_public_id}\n📝 Title: {chat.title}\n🕒 Last updated: {updated}"

    def format_chat_created(self, chat: Chat) -> str:
        """Return the new chat confirmation message."""
        return f"✨ New chat created. ID is {chat.chat_public_id}. This is now your active chat."

    def format_chat_switched(self, chat: Chat) -> str:
        """Return the chat switch confirmation message."""
        return f"🔄 Loaded chat {chat.chat_public_id}. This is now your active chat."

    def format_chat_deleted(self, chat: Chat) -> str:
        """Return the chat deletion confirmation message."""
        return f"🗑️ Deleted chat {chat.chat_public_id}."

    def format_delete_all_prompt(self) -> str:
        """Return the confirmation message for deleting all user data."""
        return (
            "⚠️ This will permanently delete all your chats, messages, and preferences.\n\n"
            "Are you sure you want to delete everything?"
        )

    def format_delete_all_done(self) -> str:
        """Return the full-delete confirmation message."""
        return "🧨 All your saved chats, messages, and preferences have been deleted."

    def build_delete_all_keyboard(self) -> InlineKeyboardMarkup:
        """Return the confirmation keyboard for full account data deletion."""
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🗑️ Yes, delete all", callback_data="deleteall:confirm"),
                    InlineKeyboardButton("❌ Cancel", callback_data="deleteall:cancel"),
                ]
            ]
        )

    def format_preferences(self, preferences: str | None) -> str:
        """Return the saved preference summary."""
        if not preferences:
            return "⚙️ Preferences\n\nNo preferences saved yet."
        return f"⚙️ Preferences\n\n{preferences}"

    def format_preferences_updated(self, preferences: str) -> str:
        """Return the preference update confirmation."""
        return f"✅ Preferences saved.\n\n{preferences}"

    def format_preferences_cleared(self) -> str:
        """Return the preference clear confirmation."""
        return "🧹 Preferences cleared."

    def build_preferences_keyboard(self, has_preferences: bool) -> InlineKeyboardMarkup:
        """Return the preference-management keyboard."""
        rows = [[InlineKeyboardButton("➕ Add Preference", callback_data="prefs:add")]]
        if has_preferences:
            rows.append([InlineKeyboardButton("✏️ Edit Preferences", callback_data="prefs:edit")])
            rows.append([InlineKeyboardButton("🗑️ Delete Preferences", callback_data="prefs:delete")])
        rows.append([InlineKeyboardButton("❌ Close", callback_data="prefs:close")])
        return InlineKeyboardMarkup(rows)

    def format_preferences_prompt(self, mode: str, current: str | None) -> str:
        """Return the prompt for collecting preference text."""
        if mode == "edit" and current:
            return (
                "✏️ Send your updated preferences in one message.\n\n"
                f"Current preferences:\n{current}"
            )
        return "➕ Send your preferences in one message."

    def build_chat_list_keyboard(self, chats: list[Chat]) -> InlineKeyboardMarkup:
        """Return an inline keyboard for the chat list."""
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{chat.title} ({chat.chat_public_id})",
                    callback_data=f"chat:{chat.chat_public_id}",
                )
            ]
            for chat in chats
        ]
        return InlineKeyboardMarkup(rows)

    def format_chat_list(self, chats: list[Chat]) -> str:
        """Return a multi-line summary of recent chats."""
        if not chats:
            return "📭 No saved chats yet. Use /newchat to create one."
        lines = ["📚 Saved chats:"]
        for chat in chats:
            updated = format_chat_timestamp(chat.last_message_at or chat.updated_at)
            lines.append(f"- {chat.title} | {chat.chat_public_id} | {updated}")
        return "\n".join(lines)

    def build_history_prompt_keyboard(self, chat_public_id: str) -> InlineKeyboardMarkup:
        """Return yes/no buttons for showing an old chat transcript."""
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Yes", callback_data=f"history:yes:{chat_public_id}"),
                    InlineKeyboardButton("❌ No", callback_data=f"history:no:{chat_public_id}"),
                ]
            ]
        )

    def format_history_prompt(self, chat: Chat) -> str:
        """Return the prompt asking whether to show a restored chat transcript."""
        return f"🧠 Do you want to view the previous messages in chat {chat.chat_public_id}?"

    def format_chat_history(self, messages: list[TranscriptMessage]) -> list[str]:
        """Return the chat transcript split into Telegram-safe chunks."""
        if not messages:
            return ["📭 This chat does not have any saved messages yet."]

        lines: list[str] = []
        for message in messages:
            if message.role == "user":
                lines.append(f"🗿 - {self._format_user_history_content(message)}")
            elif message.role == "assistant":
                lines.append(f"🤖 - {message.text_content or '[No text reply]'}")

        chunks: list[str] = []
        current = ""
        for line in lines:
            next_value = f"{current}\n{line}".strip() if current else line
            if len(next_value) > 3500:
                chunks.append(current)
                current = line
            else:
                current = next_value
        if current:
            chunks.append(current)
        return chunks

    def _format_user_history_content(self, message: TranscriptMessage) -> str:
        """Render a user transcript line with attachment labels."""
        parts: list[str] = []
        labels = []
        if "image" in message.attachment_types or message.message_type == "image":
            labels.append("[🖼️ image]")
        if "file" in message.attachment_types or message.message_type == "file":
            labels.append("[📄 file]")
        if labels:
            parts.append(" ".join(labels))
        if message.text_content:
            parts.append(message.text_content)
        return " ".join(parts) if parts else "[No text]"
