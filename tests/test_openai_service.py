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
        return SimpleNamespace(
            output_text="done",
            id="resp_123",
            usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120),
        )

    def stream(self, **kwargs):
        """Record the streamed request and return fake events."""
        self.calls.append(kwargs)
        return FakeResponseStream()


class FakeResponseStream:
    """Fake Responses API stream context manager."""

    async def __aenter__(self):
        """Enter the fake stream."""
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        """Exit the fake stream."""
        return None

    def __aiter__(self):
        """Return the async iterator."""
        self.events = iter(
            [
                SimpleNamespace(type="response.output_text.delta", delta="do"),
                SimpleNamespace(type="response.output_text.delta", delta="ne"),
            ]
        )
        return self

    async def __anext__(self):
        """Return the next fake stream event."""
        try:
            return next(self.events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def get_final_response(self):
        """Return a fake final response."""
        return SimpleNamespace(
            output_text="done",
            id="resp_stream",
            usage=SimpleNamespace(input_tokens=50, output_tokens=10, total_tokens=60),
        )


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
        openai_context_window_tokens=270000,
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
        persona_name="Study Coach",
        persona_prompt="Explain slowly.",
    )

    assert reply.text == "done"
    assert reply.usage.input_tokens == 100
    assert reply.usage.output_tokens == 20
    assert reply.usage.total_tokens == 120
    payload = fake_responses.calls[0]
    assert "Reply briefly" in payload["instructions"]
    assert "Study Coach" in payload["instructions"]
    assert "Explain slowly." in payload["instructions"]
    file_item = payload["input"][0]["content"][1]
    assert file_item == {"type": "input_file", "file_id": "file_123"}


async def test_streaming_response_forwards_text_deltas() -> None:
    """Streaming responses should expose text deltas and return final usage."""
    service = OpenAIService.__new__(OpenAIService)
    service.settings = Settings(
        telegram_bot_token="token",
        openai_api_key="key",
        allowed_telegram_user_ids=frozenset({1}),
        openai_main_model="gpt-5.1",
        openai_title_model="gpt-5-mini",
        openai_reasoning_effort="medium",
        openai_context_window_tokens=270000,
        database_url="sqlite:///:memory:",
        log_level="INFO",
        openai_timeout_seconds=30,
        telegram_file_size_limit_bytes=20 * 1024 * 1024,
        default_sticker_file_id=None,
    )
    fake_responses = FakeResponsesAPI()
    service.client = SimpleNamespace(responses=fake_responses)
    deltas = []

    async def collect_delta(delta: str) -> None:
        deltas.append(delta)

    reply = await service.create_response_streaming(
        prompt_text="Hello",
        attachments=[],
        previous_response_id=None,
        on_text_delta=collect_delta,
    )

    assert deltas == ["do", "ne"]
    assert reply.text == "done"
    assert reply.response_id == "resp_stream"
    assert reply.usage.total_tokens == 60
    assert fake_responses.calls[0]["model"] == "gpt-5.1"
