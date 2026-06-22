"""Tests for Telegram Bot API 10.1 rich message helpers."""

from unittest.mock import AsyncMock

from bot.services.telegram_rich_text_service import TelegramRichTextService


async def test_send_rich_message_uses_bot_api_10_1_method() -> None:
    """Persistent rich replies should call sendRichMessage."""
    service = TelegramRichTextService()
    bot = AsyncMock()

    sent = await service.send_rich_message(
        bot,
        chat_id=123,
        markdown="**General assistant**\n\nhello",
        reply_to_message_id=10,
    )

    assert sent is True
    bot.do_api_request.assert_awaited_once_with(
        "sendRichMessage",
        api_kwargs={
            "chat_id": 123,
            "rich_message": {"markdown": "**General assistant**\n\nhello"},
            "reply_parameters": {"message_id": 10},
        },
    )


async def test_send_rich_message_draft_uses_streaming_method() -> None:
    """Draft updates should call sendRichMessageDraft."""
    service = TelegramRichTextService()
    bot = AsyncMock()

    sent = await service.send_rich_message_draft(
        bot,
        chat_id=123,
        draft_id=10,
        markdown="<tg-thinking>Thinking...</tg-thinking>",
    )

    assert sent is True
    bot.do_api_request.assert_awaited_once_with(
        "sendRichMessageDraft",
        api_kwargs={
            "chat_id": 123,
            "draft_id": 10,
            "rich_message": {"markdown": "<tg-thinking>Thinking...</tg-thinking>"},
        },
    )
