"""OpenAI Responses API integration for text, image, and file turns."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import APIError, APITimeoutError, AsyncOpenAI

from bot.config import Settings


LOGGER = logging.getLogger(__name__)

DEVELOPER_INSTRUCTIONS = (
    "You are a private Telegram assistant. Answer the user directly and helpfully. "
    "Do not reveal hidden reasoning. Return only the final answer.\n\n"
    "You are running inside a custom Telegram bot, not the official ChatGPT app. "
    "You can respond to text, images, and files that the user sends to this bot. "
    "You can continue saved chats through the bot's stored conversation state. "
    "You can follow user preferences saved in this bot.\n\n"
    "You do not have ChatGPT app memory, voice mode, web browsing, custom GPTs, connectors, "
    "email, calendar access, file system access, device control, or access to Telegram messages "
    "outside this bot chat. If the user asks for something this bot cannot do, apologize briefly, "
    "explain the limit in plain language, and suggest what they can paste or upload here instead.\n\n"
    "The bot may warn the user when a chat is close to the model context window. If that happens, "
    "help the user make a short summary and continue in a new chat."
)


@dataclass
class OpenAIInputAttachment:
    """Attachment data prepared for a Responses API request."""

    attachment_type: str
    openai_file_id: str
    caption: str | None
    filename: str | None


@dataclass
class TokenUsage:
    """Token usage returned by an OpenAI response."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass
class AssistantReply:
    """Assistant text plus the response ID used for continuation."""

    text: str
    response_id: str | None
    usage: TokenUsage | None = None


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
        user_preferences: str | None = None,
        persona_name: str | None = None,
        persona_prompt: str | None = None,
    ) -> AssistantReply:
        """Create an assistant response for the current user turn."""
        request = self._build_response_request(
            prompt_text=prompt_text,
            attachments=attachments,
            previous_response_id=previous_response_id,
            user_preferences=user_preferences,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )
        try:
            response = await self.client.responses.create(**request)
        except APITimeoutError as exc:
            raise OpenAITurnTimeoutError("OpenAI request timed out.") from exc
        except APIError as exc:
            raise OpenAITurnError(str(exc)) from exc

        return AssistantReply(
            text=(response.output_text or "").strip(),
            response_id=response.id,
            usage=_extract_token_usage(response),
        )

    async def create_response_streaming(
        self,
        prompt_text: str | None,
        attachments: list[OpenAIInputAttachment] | None,
        previous_response_id: str | None,
        user_preferences: str | None = None,
        persona_name: str | None = None,
        persona_prompt: str | None = None,
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> AssistantReply:
        """Create an assistant response and forward text deltas as they arrive."""
        request = self._build_response_request(
            prompt_text=prompt_text,
            attachments=attachments,
            previous_response_id=previous_response_id,
            user_preferences=user_preferences,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
        )
        try:
            async with self.client.responses.stream(**request) as stream:
                async for event in stream:
                    if getattr(event, "type", None) == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta and on_text_delta:
                            await on_text_delta(delta)
                response = await stream.get_final_response()
        except APITimeoutError as exc:
            raise OpenAITurnTimeoutError("OpenAI request timed out.") from exc
        except APIError as exc:
            raise OpenAITurnError(str(exc)) from exc

        return AssistantReply(
            text=(response.output_text or "").strip(),
            response_id=response.id,
            usage=_extract_token_usage(response),
        )

    def _build_response_request(
        self,
        prompt_text: str | None,
        attachments: list[OpenAIInputAttachment] | None,
        previous_response_id: str | None,
        user_preferences: str | None = None,
        persona_name: str | None = None,
        persona_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Build the Responses API request payload for a user turn."""
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
                    }
                )
        if not content:
            content.append({"type": "input_text", "text": "Continue."})

        instructions = DEVELOPER_INSTRUCTIONS
        if persona_prompt:
            instructions = (
                f"{instructions}\n\n"
                f"Active persona name\n{persona_name or 'Custom persona'}\n\n"
                "Custom persona instructions\n"
                f"{persona_prompt}\n\n"
                "Follow the custom persona instructions unless they conflict with safety or higher-level instructions."
            )
        if user_preferences:
            instructions = (
                f"{instructions}\n\nUser preferences:\n"
                f"{user_preferences}\n\nFollow these preferences unless they conflict with safety."
            )

        return {
            "model": self.settings.openai_main_model,
            "reasoning": {"effort": self.settings.openai_reasoning_effort},
            "instructions": instructions,
            "previous_response_id": previous_response_id,
            "input": [{"role": "user", "content": content}],
        }

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


def _extract_token_usage(response) -> TokenUsage | None:
    """Return token usage from a Responses API object when available."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")

    if input_tokens is None or output_tokens is None or total_tokens is None:
        return None
    return TokenUsage(
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        total_tokens=int(total_tokens),
    )
