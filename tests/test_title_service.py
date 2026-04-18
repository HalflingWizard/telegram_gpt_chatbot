"""Tests for title generation sanitization and fallback behavior."""

from bot.services.openai_service import OpenAITurnError
from bot.services.title_service import TitleService


class SuccessfulOpenAIService:
    """Fake OpenAI service that returns a fixed title."""

    async def generate_title(self, first_message_text: str) -> str:
        """Return a predictable fake title."""
        return '"Ideas for long-term project planning."'


class FailingOpenAIService:
    """Fake OpenAI service that raises an error."""

    async def generate_title(self, first_message_text: str) -> str:
        """Raise a predictable failure."""
        raise OpenAITurnError("boom")


async def test_title_service_sanitizes_generated_title() -> None:
    """Model output should be normalized into a short title."""
    service = TitleService(SuccessfulOpenAIService())
    title, status = await service.create_title("Help me plan a field study")
    assert title == "Ideas for long-term project planning"
    assert status == "ready"


async def test_title_service_falls_back_on_error() -> None:
    """Failures should use the fallback title."""
    service = TitleService(FailingOpenAIService())
    title, status = await service.create_title("Help me plan a field study")
    assert title == "Untitled chat"
    assert status == "failed"
