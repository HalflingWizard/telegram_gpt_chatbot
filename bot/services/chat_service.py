"""Chat lifecycle service for creating, switching, listing, and persisting conversations."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from bot.db.models import Chat, Message
from bot.db.repositories import ChatRepository, MessageRepository, UserRepository
from bot.db.session import session_scope
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
            user = user_repo.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                raise ValueError("User record does not exist.")
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
