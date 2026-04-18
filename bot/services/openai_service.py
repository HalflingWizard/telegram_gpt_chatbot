"""OpenAI Responses API integration for text, image, and file turns."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import APIError, APITimeoutError, AsyncOpenAI

from bot.config import Settings


LOGGER = logging.getLogger(__name__)

DEVELOPER_INSTRUCTIONS = (
    "You are a private Telegram assistant. Answer the user directly and helpfully. "
    "Do not reveal hidden reasoning. Return only the final answer."
)


@dataclass
class OpenAIInputAttachment:
    """Attachment data prepared for a Responses API request."""

    attachment_type: str
    openai_file_id: str
    caption: str | None
    filename: str | None


@dataclass
class AssistantReply:
    """Assistant text plus the response ID used for continuation."""

    text: str
    response_id: str | None


class OpenAIService:
    """Wrap calls to the OpenAI Responses and Files APIs."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the OpenAI client."""
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)

    async def upload_user_file(self, file_path: Path, filename: str | None = None) -> str:
        """Upload a Telegram-downloaded file for use as model input."""
        with file_path.open("rb") as handle:
            created = await self.client.files.create(file=handle, purpose="user_data")
        return created.id

    async def create_response(
        self,
        prompt_text: str | None,
        attachments: list[OpenAIInputAttachment] | None,
        previous_response_id: str | None,
    ) -> AssistantReply:
        """Create an assistant response for the current user turn."""
        content: list[dict[str, Any]] = []
        if prompt_text:
            content.append({"type": "input_text", "text": prompt_text})
        for attachment in attachments or []:
            if attachment.attachment_type == "image":
                content.append(
                    {
                        "type": "input_image",
                        "file_id": attachment.openai_file_id,
                        "detail": "auto",
                    }
                )
            else:
                content.append(
                    {
                        "type": "input_file",
                        "file_id": attachment.openai_file_id,
                        "filename": attachment.filename,
                    }
                )
        if not content:
            content.append({"type": "input_text", "text": "Continue."})

        try:
            response = await self.client.responses.create(
                model=self.settings.openai_main_model,
                reasoning={"effort": self.settings.openai_reasoning_effort},
                instructions=DEVELOPER_INSTRUCTIONS,
                previous_response_id=previous_response_id,
                input=[{"role": "user", "content": content}],
            )
        except APITimeoutError as exc:
            raise OpenAITurnTimeoutError("OpenAI request timed out.") from exc
        except APIError as exc:
            raise OpenAITurnError(str(exc)) from exc

        return AssistantReply(text=(response.output_text or "").strip(), response_id=response.id)

    async def generate_title(self, first_message_text: str) -> str:
        """Generate a short conversation title with a smaller model."""
        prompt = (
            "Write a concise title for this conversation.\n\n"
            "Rules\n"
            "- Maximum 7 words\n"
            "- No quotation marks\n"
            "- No ending punctuation\n"
            "- Be specific\n"
            "- Use plain English\n\n"
            f"User's first message\n{first_message_text}"
        )
        try:
            response = await self.client.responses.create(
                model=self.settings.openai_title_model,
                input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            )
        except APIError as exc:
            LOGGER.warning("Title generation failed: %s", exc)
            raise OpenAITurnError("Title generation failed.") from exc
        return (response.output_text or "").strip()


class OpenAITurnError(RuntimeError):
    """Raised when the OpenAI API returns an application-level failure."""


class OpenAITurnTimeoutError(OpenAITurnError):
    """Raised when an OpenAI request times out."""
