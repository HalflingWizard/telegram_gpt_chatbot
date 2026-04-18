"""Tests for OpenAI request construction."""

from types import SimpleNamespace

from bot.config import Settings
from bot.services.openai_service import OpenAIInputAttachment, OpenAIService


class FakeResponsesAPI:
    """Fake Responses API client."""

    def __init__(self) -> None:
        """Initialize the fake client."""
        self.calls = []

    async def create(self, **kwargs):
        """Record the request and return a fake response."""
        self.calls.append(kwargs)
        return SimpleNamespace(output_text="done", id="resp_123")


async def test_file_input_uses_only_file_id_and_includes_preferences() -> None:
    """File inputs should not send filename alongside file_id."""
    service = OpenAIService.__new__(OpenAIService)
    service.settings = Settings(
        telegram_bot_token="token",
        openai_api_key="key",
        allowed_telegram_user_ids=frozenset({1}),
        openai_main_model="gpt-5.1",
        openai_title_model="gpt-5-mini",
        openai_reasoning_effort="medium",
        database_url="sqlite:///:memory:",
        log_level="INFO",
        openai_timeout_seconds=30,
        telegram_file_size_limit_bytes=20 * 1024 * 1024,
        default_sticker_file_id=None,
    )
    fake_responses = FakeResponsesAPI()
    service.client = SimpleNamespace(responses=fake_responses)

    reply = await service.create_response(
        prompt_text="Summarize this",
        attachments=[
            OpenAIInputAttachment(
                attachment_type="file",
                openai_file_id="file_123",
                caption="caption",
                filename="notes.pdf",
            )
        ],
        previous_response_id="resp_prev",
        user_preferences="Reply briefly",
    )

    assert reply.text == "done"
    payload = fake_responses.calls[0]
    assert "Reply briefly" in payload["instructions"]
    file_item = payload["input"][0]["content"][1]
    assert file_item == {"type": "input_file", "file_id": "file_123"}
