"""Formatting helpers for Telegram responses."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import Chat
from bot.utils.time import format_chat_timestamp


class FormattingService:
    """Build Telegram-friendly text and keyboard layouts."""

    def format_help_text(self) -> str:
        """Return the help message shown to users."""
        return (
            "Available commands\n\n"
            "/newchat\nCreate a new chat and make it active\n\n"
            "/chat <id>\nResume a saved chat by ID\n\n"
            "/listchats\nShow your recent chats\n\n"
            "/currentchat\nShow the active chat\n\n"
            "/deletechat <id>\nDelete a chat\n\n"
            "/sticker\nSend the configured sticker"
        )

    def format_start_text(self) -> str:
        """Return the start message shown to users."""
        return (
            "Welcome. This bot is private and only works for approved Telegram users.\n\n"
            "Use /newchat to begin, /chat <id> to resume a saved thread, and /listchats to browse."
        )

    def format_current_chat(self, chat: Chat | None) -> str:
        """Return a readable current-chat summary."""
        if chat is None:
            return "No active chat. Use /newchat or /chat <id>."
        updated = format_chat_timestamp(chat.last_message_at or chat.updated_at)
        return f"Active chat: {chat.chat_public_id}\nTitle: {chat.title}\nLast updated: {updated}"

    def format_chat_created(self, chat: Chat) -> str:
        """Return the new chat confirmation message."""
        return f"New chat created. ID is {chat.chat_public_id}. This is now your active chat."

    def format_chat_switched(self, chat: Chat) -> str:
        """Return the chat switch confirmation message."""
        return f"Loaded chat {chat.chat_public_id}. This is now your active chat."

    def format_chat_deleted(self, chat: Chat) -> str:
        """Return the chat deletion confirmation message."""
        return f"Deleted chat {chat.chat_public_id}."

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
            return "No saved chats yet. Use /newchat to create one."
        lines = ["Saved chats:"]
        for chat in chats:
            updated = format_chat_timestamp(chat.last_message_at or chat.updated_at)
            lines.append(f"- {chat.title} | {chat.chat_public_id} | {updated}")
        return "\n".join(lines)
