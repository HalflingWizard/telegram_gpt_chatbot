"""Chat title generation and fallback sanitization."""

from __future__ import annotations

from bot.services.openai_service import OpenAIService, OpenAITurnError


class TitleService:
    """Generate and sanitize short chat titles."""

    def __init__(self, openai_service: OpenAIService) -> None:
        """Initialize the service."""
        self.openai_service = openai_service

    async def create_title(self, first_message_text: str) -> tuple[str, str]:
        """Return a sanitized title and status."""
        if not first_message_text.strip():
            return "Untitled chat", "failed"
        try:
            raw_title = await self.openai_service.generate_title(first_message_text)
        except OpenAITurnError:
            return "Untitled chat", "failed"
        sanitized = self._sanitize_title(raw_title)
        return sanitized or "Untitled chat", "ready"

    def _sanitize_title(self, value: str) -> str:
        """Normalize a model-generated title into a short plain string."""
        compact = " ".join(value.replace('"', "").replace("'", "").split())
        compact = compact.rstrip(".,!?;:")
        words = compact.split()
        return " ".join(words[:7])
