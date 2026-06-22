"""Telegram Bot API 10.1 rich message helpers."""

from __future__ import annotations

import logging
import time

from telegram.error import TelegramError


LOGGER = logging.getLogger(__name__)
MAX_RICH_MESSAGE_LENGTH = 32768
MIN_DRAFT_INTERVAL_SECONDS = 0.8


class TelegramRichTextService:
    """Send Telegram rich messages through raw Bot API methods."""

    async def send_rich_message(self, bot, chat_id: int, markdown: str, reply_to_message_id: int | None = None) -> bool:
        """Send a persistent rich message. Return False if Telegram rejects it."""
        try:
            payload = {
                "chat_id": chat_id,
                "rich_message": {"markdown": _trim_rich_markdown(markdown)},
            }
            if reply_to_message_id:
                payload["reply_parameters"] = {"message_id": reply_to_message_id}
            await bot.do_api_request("sendRichMessage", api_kwargs=payload)
        except TelegramError:
            LOGGER.exception("Telegram sendRichMessage failed")
            return False
        return True

    async def send_rich_message_draft(self, bot, chat_id: int, draft_id: int, markdown: str) -> bool:
        """Send an ephemeral rich message draft. Return False if Telegram rejects it."""
        try:
            await bot.do_api_request(
                "sendRichMessageDraft",
                api_kwargs={
                    "chat_id": chat_id,
                    "draft_id": draft_id,
                    "rich_message": {"markdown": _trim_rich_markdown(markdown)},
                },
            )
        except TelegramError:
            LOGGER.exception("Telegram sendRichMessageDraft failed")
            return False
        return True

    def make_streamer(self, bot, chat_id: int, draft_id: int, label: str):
        """Create a throttled rich draft streamer for one response."""
        return TelegramRichMessageStreamer(self, bot, chat_id, draft_id, label)


class TelegramRichMessageStreamer:
    """Throttle Telegram draft updates while model text streams in."""

    def __init__(self, service: TelegramRichTextService, bot, chat_id: int, draft_id: int, label: str) -> None:
        """Initialize one draft stream."""
        self.service = service
        self.bot = bot
        self.chat_id = chat_id
        self.draft_id = draft_id
        self.label = label
        self.text = ""
        self.last_sent_at = 0.0
        self.enabled = True

    async def start(self) -> None:
        """Show an initial thinking draft."""
        self.enabled = await self.service.send_rich_message_draft(
            self.bot,
            self.chat_id,
            self.draft_id,
            f"**{self.label}**\n\n<tg-thinking>Thinking...</tg-thinking>",
        )
        self.last_sent_at = time.monotonic()

    async def add_delta(self, delta: str) -> None:
        """Add streamed text and send a draft update when enough time has passed."""
        self.text += delta
        if not self.enabled:
            return
        now = time.monotonic()
        if now - self.last_sent_at < MIN_DRAFT_INTERVAL_SECONDS:
            return
        self.enabled = await self.service.send_rich_message_draft(
            self.bot,
            self.chat_id,
            self.draft_id,
            self.render(self.text),
        )
        self.last_sent_at = now

    async def flush(self) -> None:
        """Send the latest draft once more."""
        if not self.enabled or not self.text.strip():
            return
        self.enabled = await self.service.send_rich_message_draft(
            self.bot,
            self.chat_id,
            self.draft_id,
            self.render(self.text),
        )

    def render(self, text: str) -> str:
        """Return the current rich markdown draft."""
        return f"**{self.label}**\n\n{text.strip() or '<tg-thinking>Thinking...</tg-thinking>'}"


def _trim_rich_markdown(markdown: str) -> str:
    """Keep rich messages inside Telegram's 10.1 character limit."""
    if len(markdown) <= MAX_RICH_MESSAGE_LENGTH:
        return markdown
    return markdown[: MAX_RICH_MESSAGE_LENGTH - 20].rstrip() + "\n\n[truncated]"
