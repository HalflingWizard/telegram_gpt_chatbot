"""Chat lifecycle service for creating, switching, listing, and persisting conversations."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from bot.db.models import Chat, Message
from bot.db.repositories import ChatRepository, MessageRepository, PersonaRepository, UserRepository
from bot.db.session import session_scope
from bot.services.token_usage import ContextWindowWarning
from bot.utils.ids import generate_chat_public_id
from bot.utils.validators import normalize_chat_public_id


@dataclass
class AttachmentRecord:
    """Attachment payload stored alongside a user message."""

    attachment_type: str
    telegram_file_id: str
    telegram_file_unique_id: str
    openai_file_id: str | None
    filename: str | None
    mime_type: str | None
    caption: str | None
    file_size: int | None


@dataclass
class TranscriptMessage:
    """Serializable chat-history row for Telegram previews."""

    role: str
    text_content: str | None
    message_type: str
    attachment_types: list[str]


@dataclass
class PersonaSummary:
    """Serializable persona data for handlers and prompts."""

    id: int
    name: str
    system_prompt: str
    is_builtin: bool


class ChatService:
    """Encapsulate chat CRUD and message persistence."""

    def __init__(self, session_factory: sessionmaker) -> None:
        """Initialize the service."""
        self.session_factory = session_factory

    def create_new_chat(self, telegram_user_id: int) -> Chat:
        """Create a new active chat for a Telegram user."""
        with session_scope(self.session_factory) as session:
            user_repo = UserRepository(session)
            chat_repo = ChatRepository(session)
            persona_repo = PersonaRepository(session)
            user = user_repo.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                raise ValueError("User record does not exist.")
            persona_repo.ensure_builtin_personas(user.id)
            chat_public_id = self._generate_unique_chat_id(chat_repo, user.id)
            return chat_repo.create_chat(user_id=user.id, chat_public_id=chat_public_id)

    def get_active_chat(self, telegram_user_id: int) -> Chat | None:
        """Return the currently active chat for a Telegram user."""
        with session_scope(self.session_factory) as session:
            user_repo = UserRepository(session)
            chat_repo = ChatRepository(session)
            user = user_repo.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                return None
            return chat_repo.get_active_chat(user.id)

    def switch_active_chat(self, telegram_user_id: int, chat_public_id: str) -> Chat | None:
        """Switch the user's active chat."""
        with session_scope(self.session_factory) as session:
            user_repo = UserRepository(session)
            chat_repo = ChatRepository(session)
            user = user_repo.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                return None
            return chat_repo.set_active_chat(user.id, normalize_chat_public_id(chat_public_id))

    def list_chats(self, telegram_user_id: int, limit: int = 20) -> list[Chat]:
        """List recent chats for a Telegram user."""
        with session_scope(self.session_factory) as session:
            user_repo = UserRepository(session)
            chat_repo = ChatRepository(session)
            user = user_repo.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                return []
            return chat_repo.list_for_user(user.id, limit=limit)

    def delete_chat(self, telegram_user_id: int, chat_public_id: str) -> Chat | None:
        """Soft delete a chat by its public ID."""
        with session_scope(self.session_factory) as session:
            user_repo = UserRepository(session)
            chat_repo = ChatRepository(session)
            user = user_repo.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                return None
            return chat_repo.soft_delete_chat(user.id, normalize_chat_public_id(chat_public_id))

    def store_user_message(
        self,
        chat_id: int,
        message_type: str,
        text_content: str | None,
        telegram_message_id: int | None,
        attachments: list[AttachmentRecord] | None = None,
    ) -> Message:
        """Persist a user message and its attachments."""
        with session_scope(self.session_factory) as session:
            message_repo = MessageRepository(session)
            chat_repo = ChatRepository(session)
            message = message_repo.create_message(
                chat_id=chat_id,
                role="user",
                message_type=message_type,
                text_content=text_content,
                telegram_message_id=telegram_message_id,
            )
            for attachment in attachments or []:
                message_repo.add_attachment(
                    message_id=message.id,
                    attachment_type=attachment.attachment_type,
                    telegram_file_id=attachment.telegram_file_id,
                    telegram_file_unique_id=attachment.telegram_file_unique_id,
                    openai_file_id=attachment.openai_file_id,
                    filename=attachment.filename,
                    mime_type=attachment.mime_type,
                    caption=attachment.caption,
                    file_size=attachment.file_size,
                )
            chat_repo.touch_chat(chat_id)
            return message

    def store_assistant_message(
        self,
        chat_id: int,
        text_content: str,
        openai_response_id: str | None,
    ) -> Message:
        """Persist an assistant message and update the response chain pointer."""
        with session_scope(self.session_factory) as session:
            message_repo = MessageRepository(session)
            chat_repo = ChatRepository(session)
            message = message_repo.create_message(
                chat_id=chat_id,
                role="assistant",
                message_type="text",
                text_content=text_content,
                openai_response_id=openai_response_id,
            )
            chat_repo.touch_chat(chat_id)
            chat_repo.set_last_openai_response_id(chat_id, openai_response_id)
            return message

    def clear_last_openai_response_id(self, chat_id: int) -> None:
        """Reset a broken OpenAI response chain for a chat."""
        with session_scope(self.session_factory) as session:
            ChatRepository(session).set_last_openai_response_id(chat_id, None)

    def record_token_usage(
        self,
        chat_id: int,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        context_window_tokens: int,
    ) -> ContextWindowWarning | None:
        """Persist token usage and return a warning when context is nearly full."""
        with session_scope(self.session_factory) as session:
            chat_repo = ChatRepository(session)
            warning = chat_repo.record_token_usage(
                chat_id=chat_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                context_window_tokens=context_window_tokens,
            )
            chat_repo.touch_chat(chat_id)
            return warning

    def get_chat_for_user(self, telegram_user_id: int, chat_public_id: str) -> Chat | None:
        """Return a single chat by public ID for a Telegram user."""
        with session_scope(self.session_factory) as session:
            user_repo = UserRepository(session)
            chat_repo = ChatRepository(session)
            user = user_repo.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                return None
            return chat_repo.get_by_public_id(user.id, normalize_chat_public_id(chat_public_id))

    def update_title(self, chat_id: int, title: str, title_status: str) -> None:
        """Persist a chat title update."""
        with session_scope(self.session_factory) as session:
            ChatRepository(session).update_title(chat_id=chat_id, title=title, title_status=title_status)

    def list_personas(self, telegram_user_id: int) -> list[PersonaSummary]:
        """List personas for a Telegram user."""
        with session_scope(self.session_factory) as session:
            user = UserRepository(session).get_by_telegram_user_id(telegram_user_id)
            if user is None:
                return []
            repo = PersonaRepository(session)
            repo.ensure_builtin_personas(user.id)
            return [self._persona_summary(persona) for persona in repo.list_for_user(user.id)]

    def create_persona(self, telegram_user_id: int, name: str, system_prompt: str) -> PersonaSummary | None:
        """Create or update a persona for a Telegram user."""
        with session_scope(self.session_factory) as session:
            user = UserRepository(session).get_by_telegram_user_id(telegram_user_id)
            if user is None:
                return None
            repo = PersonaRepository(session)
            repo.ensure_builtin_personas(user.id)
            persona = repo.create_or_update(
                user_id=user.id,
                name=name.strip(),
                system_prompt=system_prompt.strip(),
                is_builtin=False,
            )
            return self._persona_summary(persona)

    def delete_persona(self, telegram_user_id: int, name: str) -> PersonaSummary | None:
        """Delete a non-built-in persona."""
        with session_scope(self.session_factory) as session:
            user = UserRepository(session).get_by_telegram_user_id(telegram_user_id)
            if user is None:
                return None
            persona = PersonaRepository(session).delete_by_name(user.id, name.strip())
            return self._persona_summary(persona) if persona else None

    def set_active_persona(
        self,
        telegram_user_id: int,
        chat_id: int,
        name: str,
    ) -> PersonaSummary | None:
        """Select a persona for a chat."""
        with session_scope(self.session_factory) as session:
            user = UserRepository(session).get_by_telegram_user_id(telegram_user_id)
            if user is None:
                return None
            persona_repo = PersonaRepository(session)
            persona_repo.ensure_builtin_personas(user.id)
            persona = persona_repo.get_by_name(user.id, name.strip())
            if persona is None:
                return None
            ChatRepository(session).set_active_persona_id(chat_id, persona.id)
            return self._persona_summary(persona)

    def clear_active_persona(self, chat_id: int) -> None:
        """Return a chat to the general assistant."""
        with session_scope(self.session_factory) as session:
            ChatRepository(session).set_active_persona_id(chat_id, None)

    def get_active_persona_for_chat(self, chat_id: int) -> PersonaSummary | None:
        """Return the active persona for a chat."""
        with session_scope(self.session_factory) as session:
            chat_repo = ChatRepository(session)
            persona_id = chat_repo.get_active_persona_id(chat_id)
            if persona_id is None:
                return None
            chat = session.get(Chat, chat_id)
            if chat is None:
                return None
            persona = PersonaRepository(session).get_by_id(chat.user_id, persona_id)
            return self._persona_summary(persona) if persona else None

    def get_chat_history(self, telegram_user_id: int, chat_public_id: str) -> list[TranscriptMessage]:
        """Return a chat transcript suitable for Telegram display."""
        with session_scope(self.session_factory) as session:
            user_repo = UserRepository(session)
            chat_repo = ChatRepository(session)
            message_repo = MessageRepository(session)
            user = user_repo.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                return []
            chat = chat_repo.get_by_public_id(user.id, normalize_chat_public_id(chat_public_id))
            if chat is None:
                return []
            messages = message_repo.list_messages_for_chat(chat.id)
            return [
                TranscriptMessage(
                    role=message.role,
                    text_content=message.text_content,
                    message_type=message.message_type,
                    attachment_types=[attachment.attachment_type for attachment in message.attachments],
                )
                for message in messages
                if message.role in {"user", "assistant"}
            ]

    def _generate_unique_chat_id(self, chat_repo: ChatRepository, user_id: int) -> str:
        """Generate a unique public ID for the user's chats."""
        for _ in range(20):
            candidate = generate_chat_public_id()
            if not chat_repo.public_id_exists(user_id, candidate):
                return candidate
        raise RuntimeError("Could not generate a unique chat ID.")

    def _persona_summary(self, persona) -> PersonaSummary:
        """Return a detached persona summary."""
        return PersonaSummary(
            id=persona.id,
            name=persona.name,
            system_prompt=persona.system_prompt,
            is_builtin=persona.is_builtin,
        )
