"""Repository layer that isolates SQLAlchemy queries from services."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from bot.db.models import Chat, ChatState, Message, MessageAttachment, Persona, User
from bot.services.token_usage import ContextWindowWarning


BUILTIN_GUIDE_PERSONA_NAME = "Bot Guide"
BUILTIN_GUIDE_PERSONA_PROMPT = """
You are Bot Guide, a help persona for this private Telegram GPT bot.

Your job is to explain how to use this bot in plain language.

Explain these features when relevant.
- Use /newchat to start a new saved chat.
- Use /chat <id> to reopen a saved chat.
- Use /listchats to see saved chats.
- Use /currentchat to see the active chat.
- Use /preferences to save reply preferences.
- Use /personas to manage personas.
- A persona is a named custom assistant style with its own instructions.
- Use /personas add to create a persona.
- Use /personas use <name> to use a persona in the active chat.
- Use /personas general to return the active chat to the general assistant.
- Use /personas delete <name> to delete a persona.
- Text messages sent close together are grouped into one model call.
- Photos and files sent close together are grouped into one model call.
- The bot warns when a chat gets close to the model context window.

Explain these limits when relevant.
- This is not the official ChatGPT app.
- It does not have ChatGPT app memory.
- It does not have voice mode.
- It does not browse the web.
- It does not have custom GPTs or connectors.
- It cannot see Telegram messages outside this bot.
- It cannot access email, calendars, local files, websites, or outside apps unless the code is changed later.

If the user asks for something the bot cannot do, apologize briefly and suggest what they can paste or upload here.
""".strip()


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

    def delete_user_and_related_data(self, telegram_user_id: int) -> bool:
        """Delete a user and all related chats, messages, attachments, and state."""
        user = self.get_by_telegram_user_id(telegram_user_id)
        if user is None:
            return False

        chat_ids = list(
            self.session.scalars(select(Chat.id).where(Chat.user_id == user.id))
        )
        if chat_ids:
            message_ids = list(
                self.session.scalars(select(Message.id).where(Message.chat_id.in_(chat_ids)))
            )
            if message_ids:
                self.session.execute(
                    delete(MessageAttachment).where(MessageAttachment.message_id.in_(message_ids))
                )
                self.session.execute(delete(Message).where(Message.id.in_(message_ids)))
            self.session.execute(delete(ChatState).where(ChatState.chat_id.in_(chat_ids)))
            self.session.execute(delete(Chat).where(Chat.id.in_(chat_ids)))
        self.session.execute(delete(Persona).where(Persona.user_id == user.id))

        self.session.delete(user)
        self.session.flush()
        return True


class PersonaRepository:
    """CRUD operations for user personas."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository."""
        self.session = session

    def ensure_builtin_personas(self, user_id: int) -> None:
        """Create built-in personas for a user when missing."""
        existing = self.get_by_name(user_id, BUILTIN_GUIDE_PERSONA_NAME)
        if existing is not None:
            return
        persona = Persona(
            user_id=user_id,
            name=BUILTIN_GUIDE_PERSONA_NAME,
            system_prompt=BUILTIN_GUIDE_PERSONA_PROMPT,
            is_builtin=True,
        )
        self.session.add(persona)
        self.session.flush()

    def list_for_user(self, user_id: int) -> list[Persona]:
        """List personas for a user."""
        result = self.session.scalars(
            select(Persona)
            .where(Persona.user_id == user_id)
            .order_by(Persona.is_builtin.desc(), Persona.name.asc())
        )
        return list(result)

    def get_by_name(self, user_id: int, name: str) -> Persona | None:
        """Fetch a persona by exact name."""
        return self.session.scalar(
            select(Persona).where(Persona.user_id == user_id, Persona.name == name)
        )

    def get_by_id(self, user_id: int, persona_id: int) -> Persona | None:
        """Fetch a persona by ID."""
        return self.session.scalar(
            select(Persona).where(Persona.user_id == user_id, Persona.id == persona_id)
        )

    def create_or_update(
        self,
        user_id: int,
        name: str,
        system_prompt: str,
        is_builtin: bool = False,
    ) -> Persona:
        """Create or update a persona by name."""
        existing = self.get_by_name(user_id, name)
        if existing is not None:
            existing.system_prompt = system_prompt
            existing.is_builtin = is_builtin
            existing.updated_at = datetime.now(timezone.utc)
            return existing
        persona = Persona(
            user_id=user_id,
            name=name,
            system_prompt=system_prompt,
            is_builtin=is_builtin,
        )
        self.session.add(persona)
        self.session.flush()
        return persona

    def delete_by_name(self, user_id: int, name: str) -> Persona | None:
        """Delete a non-built-in persona by name."""
        persona = self.get_by_name(user_id, name)
        if persona is None or persona.is_builtin:
            return None
        self.session.delete(persona)
        self.session.flush()
        return persona


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

    def set_active_persona_id(self, chat_id: int, persona_id: int | None) -> None:
        """Persist the selected persona for a chat."""
        state = self.session.scalar(select(ChatState).where(ChatState.chat_id == chat_id))
        if state is None:
            return
        notes = self._load_state_notes(state.notes)
        if persona_id is None:
            notes.pop("active_persona_id", None)
        else:
            notes["active_persona_id"] = persona_id
        state.notes = json.dumps(notes, sort_keys=True)

    def get_active_persona_id(self, chat_id: int) -> int | None:
        """Return the selected persona ID for a chat."""
        state = self.session.scalar(select(ChatState).where(ChatState.chat_id == chat_id))
        if state is None:
            return None
        notes = self._load_state_notes(state.notes)
        persona_id = notes.get("active_persona_id")
        return int(persona_id) if persona_id is not None else None

    def record_token_usage(
        self,
        chat_id: int,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        context_window_tokens: int,
    ) -> ContextWindowWarning | None:
        """Record token usage in chat state notes and return a new warning."""
        state = self.session.scalar(select(ChatState).where(ChatState.chat_id == chat_id))
        if state is None:
            return None

        notes = self._load_state_notes(state.notes)
        usage = notes.get("token_usage", {})
        previous_warning_level = usage.get("last_warning_level")

        usage["turn_count"] = int(usage.get("turn_count", 0)) + 1
        usage["last_input_tokens"] = input_tokens
        usage["last_output_tokens"] = output_tokens
        usage["last_total_tokens"] = total_tokens
        usage["max_input_tokens"] = max(int(usage.get("max_input_tokens", 0)), input_tokens)
        usage["cumulative_input_tokens"] = int(usage.get("cumulative_input_tokens", 0)) + input_tokens
        usage["cumulative_output_tokens"] = int(usage.get("cumulative_output_tokens", 0)) + output_tokens
        usage["cumulative_total_tokens"] = int(usage.get("cumulative_total_tokens", 0)) + total_tokens
        usage["context_window_tokens"] = context_window_tokens

        warning_level = self._context_warning_level(input_tokens, context_window_tokens)
        warning = None
        if warning_level and self._is_higher_warning_level(warning_level, previous_warning_level):
            usage["last_warning_level"] = warning_level
            warning = ContextWindowWarning(
                level=warning_level,
                input_tokens=input_tokens,
                context_window_tokens=context_window_tokens,
                percent_used=round((input_tokens / context_window_tokens) * 100),
            )

        notes["token_usage"] = usage
        state.notes = json.dumps(notes, sort_keys=True)
        return warning

    def _load_state_notes(self, raw_notes: str | None) -> dict:
        """Load JSON notes while preserving legacy free-text notes."""
        if not raw_notes:
            return {}
        try:
            loaded = json.loads(raw_notes)
        except json.JSONDecodeError:
            return {"legacy_notes": raw_notes}
        return loaded if isinstance(loaded, dict) else {"legacy_notes": raw_notes}

    def _context_warning_level(self, input_tokens: int, context_window_tokens: int) -> str | None:
        """Return warning level based on context usage."""
        if context_window_tokens <= 0:
            return None
        ratio = input_tokens / context_window_tokens
        if ratio >= 0.95:
            return "critical"
        if ratio >= 0.85:
            return "high"
        if ratio >= 0.75:
            return "medium"
        return None

    def _is_higher_warning_level(self, new_level: str, previous_level: str | None) -> bool:
        """Return whether a warning level is higher than the previous one."""
        levels = {"medium": 1, "high": 2, "critical": 3}
        return levels.get(new_level, 0) > levels.get(previous_level or "", 0)


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
