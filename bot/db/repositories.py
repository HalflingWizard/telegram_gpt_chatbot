"""Repository layer that isolates SQLAlchemy queries from services."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from bot.db.models import Chat, ChatState, Message, MessageAttachment, User


class UserRepository:
    """CRUD operations for users."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository."""
        self.session = session

    def get_by_telegram_user_id(self, telegram_user_id: int) -> User | None:
        """Fetch a user by Telegram user ID."""
        return self.session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))

    def get_or_create(
        self,
        telegram_user_id: int,
        telegram_username: str | None,
        is_allowed: bool,
    ) -> User:
        """Fetch a user or create one if missing."""
        user = self.get_by_telegram_user_id(telegram_user_id)
        if user:
            user.telegram_username = telegram_username
            user.is_allowed = is_allowed
            user.updated_at = datetime.now(timezone.utc)
            return user
        user = User(
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            is_allowed=is_allowed,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def get_preferences(self, telegram_user_id: int) -> str | None:
        """Return saved user preferences."""
        user = self.get_by_telegram_user_id(telegram_user_id)
        return user.preferences if user else None

    def set_preferences(self, telegram_user_id: int, preferences: str | None) -> User | None:
        """Persist user preferences."""
        user = self.get_by_telegram_user_id(telegram_user_id)
        if user is None:
            return None
        user.preferences = preferences
        user.updated_at = datetime.now(timezone.utc)
        return user


class ChatRepository:
    """CRUD operations for chats and chat state."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository."""
        self.session = session

    def deactivate_user_chats(self, user_id: int) -> None:
        """Deactivate all non-deleted chats for a user."""
        for chat in self.list_for_user(user_id):
            chat.active = False

    def create_chat(self, user_id: int, chat_public_id: str, title: str = "Untitled chat") -> Chat:
        """Create a new chat and its state row."""
        self.deactivate_user_chats(user_id)
        chat = Chat(
            user_id=user_id,
            chat_public_id=chat_public_id,
            title=title,
            title_status="pending",
            active=True,
        )
        self.session.add(chat)
        self.session.flush()
        self.session.add(ChatState(chat_id=chat.id))
        self.session.flush()
        return chat

    def get_by_public_id(self, user_id: int, chat_public_id: str) -> Chat | None:
        """Fetch a non-deleted chat by its public ID."""
        return self.session.scalar(
            select(Chat)
            .where(
                Chat.user_id == user_id,
                Chat.chat_public_id == chat_public_id,
                Chat.deleted_at.is_(None),
            )
            .options(joinedload(Chat.state))
        )

    def public_id_exists(self, user_id: int, chat_public_id: str) -> bool:
        """Return whether a public ID already exists for the user, including deleted chats."""
        return (
            self.session.scalar(
                select(Chat.id).where(Chat.user_id == user_id, Chat.chat_public_id == chat_public_id)
            )
            is not None
        )

    def get_active_chat(self, user_id: int) -> Chat | None:
        """Fetch the active non-deleted chat for a user."""
        return self.session.scalar(
            select(Chat)
            .where(Chat.user_id == user_id, Chat.active.is_(True), Chat.deleted_at.is_(None))
            .options(joinedload(Chat.state))
        )

    def list_for_user(self, user_id: int, limit: int = 20) -> list[Chat]:
        """List recent non-deleted chats for a user."""
        result = self.session.scalars(
            select(Chat)
            .where(Chat.user_id == user_id, Chat.deleted_at.is_(None))
            .order_by(Chat.last_message_at.desc().nullslast(), Chat.updated_at.desc())
            .limit(limit)
        )
        return list(result)

    def set_active_chat(self, user_id: int, chat_public_id: str) -> Chat | None:
        """Mark the selected chat as the active chat for the user."""
        chat = self.get_by_public_id(user_id, chat_public_id)
        if chat is None:
            return None
        self.deactivate_user_chats(user_id)
        chat.active = True
        chat.updated_at = datetime.now(timezone.utc)
        return chat

    def soft_delete_chat(self, user_id: int, chat_public_id: str) -> Chat | None:
        """Soft delete a chat."""
        chat = self.get_by_public_id(user_id, chat_public_id)
        if chat is None:
            return None
        chat.deleted_at = datetime.now(timezone.utc)
        chat.active = False
        return chat

    def update_title(self, chat_id: int, title: str, title_status: str) -> None:
        """Update a chat title and title state."""
        chat = self.session.get(Chat, chat_id)
        if chat is None:
            return
        chat.title = title
        chat.title_status = title_status
        chat.updated_at = datetime.now(timezone.utc)

    def touch_chat(self, chat_id: int) -> None:
        """Update chat timestamps after a new message."""
        chat = self.session.get(Chat, chat_id)
        if chat is None:
            return
        timestamp = datetime.now(timezone.utc)
        chat.updated_at = timestamp
        chat.last_message_at = timestamp

    def set_last_openai_response_id(self, chat_id: int, response_id: str | None) -> None:
        """Persist the last OpenAI response ID for a chat."""
        state = self.session.scalar(select(ChatState).where(ChatState.chat_id == chat_id))
        if state is None:
            return
        state.last_openai_response_id = response_id


class MessageRepository:
    """CRUD operations for messages and attachments."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository."""
        self.session = session

    def create_message(
        self,
        chat_id: int,
        role: str,
        message_type: str,
        text_content: str | None,
        telegram_message_id: int | None = None,
        openai_response_id: str | None = None,
    ) -> Message:
        """Create and return a message row."""
        message = Message(
            chat_id=chat_id,
            role=role,
            message_type=message_type,
            text_content=text_content,
            telegram_message_id=telegram_message_id,
            openai_response_id=openai_response_id,
        )
        self.session.add(message)
        self.session.flush()
        return message

    def add_attachment(
        self,
        message_id: int,
        attachment_type: str,
        telegram_file_id: str,
        telegram_file_unique_id: str,
        openai_file_id: str | None,
        filename: str | None,
        mime_type: str | None,
        caption: str | None,
        file_size: int | None,
    ) -> MessageAttachment:
        """Create and return an attachment row."""
        attachment = MessageAttachment(
            message_id=message_id,
            attachment_type=attachment_type,
            telegram_file_id=telegram_file_id,
            telegram_file_unique_id=telegram_file_unique_id,
            openai_file_id=openai_file_id,
            filename=filename,
            mime_type=mime_type,
            caption=caption,
            file_size=file_size,
        )
        self.session.add(attachment)
        self.session.flush()
        return attachment

    def list_messages_for_chat(self, chat_id: int) -> list[Message]:
        """Return chat messages in chronological order with attachments preloaded."""
        result = self.session.scalars(
            select(Message)
            .where(Message.chat_id == chat_id)
            .options(joinedload(Message.attachments))
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return list(result.unique())
