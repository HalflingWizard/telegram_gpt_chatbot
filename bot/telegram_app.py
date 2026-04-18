"""Telegram application wiring, dependency container, and service access."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.config import Settings, load_settings
from bot.db.session import create_session_factory
from bot.handlers.chat_commands import (
    chat_command,
    currentchat_command,
    deletechat_command,
    listchats_callback,
    listchats_command,
    newchat_command,
)
from bot.handlers.errors import error_handler
from bot.handlers.media_messages import handle_document_message, handle_photo_message
from bot.handlers.start import help_command, start_command
from bot.handlers.stickers import sticker_command
from bot.handlers.text_messages import handle_text_message
from bot.logging_setup import configure_logging
from bot.services.auth_service import AuthService
from bot.services.chat_service import ChatService
from bot.services.formatting_service import FormattingService
from bot.services.openai_service import (
    OpenAIInputAttachment,
    OpenAIService,
    OpenAITurnError,
    OpenAITurnTimeoutError,
)
from bot.services.telegram_file_service import TelegramFileService, TelegramFileTooLargeError
from bot.services.title_service import TitleService
from bot.service_locator import SERVICES_KEY


LOGGER = logging.getLogger(__name__)


@dataclass
class ServiceContainer:
    """Application service registry shared by Telegram handlers."""

    settings: Settings
    auth_service: AuthService
    chat_service: ChatService
    openai_service: OpenAIService
    title_service: TitleService
    telegram_file_service: TelegramFileService
    formatting_service: FormattingService
    openai_error: type[OpenAITurnError]
    openai_timeout_error: type[OpenAITurnTimeoutError]
    telegram_file_too_large_error: type[TelegramFileTooLargeError]
    openai_input_attachment: type[OpenAIInputAttachment]

    async def authorize_update(self, update: Update) -> bool:
        """Validate the Telegram user and deny access before expensive work."""
        user = update.effective_user
        if user is None:
            return False
        is_allowed = self.auth_service.is_allowed(user.id, user.username)
        if is_allowed:
            return True
        if update.effective_message:
            await update.effective_message.reply_text("You are not authorized to use this bot.")
        self.log_event(
            logging.WARNING,
            action="authorization_denied",
            update=update,
            success=False,
            message="Unauthorized Telegram user blocked",
        )
        return False

    def log_event(
        self,
        level: int,
        action: str,
        update: Update | None,
        success: bool,
        message: str,
        chat_public_id: str | None = None,
        chat_db_id: int | None = None,
        exc_info=None,
    ) -> None:
        """Emit a structured log entry with request context."""
        LOGGER.log(
            level,
            message,
            exc_info=exc_info,
            extra={
                "telegram_user_id": update.effective_user.id if update and update.effective_user else None,
                "chat_public_id": chat_public_id,
                "chat_db_id": chat_db_id,
                "telegram_message_id": (
                    update.effective_message.message_id
                    if update and update.effective_message
                    else None
                ),
                "action": action,
                "success": success,
            },
        )


def build_application(settings: Settings | None = None) -> Application:
    """Create and configure the Telegram application."""
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    session_factory = create_session_factory(settings.database_url)
    auth_service = AuthService(session_factory, settings.allowed_telegram_user_ids)
    chat_service = ChatService(session_factory)
    openai_service = OpenAIService(settings)
    title_service = TitleService(openai_service)
    telegram_file_service = TelegramFileService(settings.telegram_file_size_limit_bytes)
    formatting_service = FormattingService()

    application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    application.bot_data[SERVICES_KEY] = ServiceContainer(
        settings=settings,
        auth_service=auth_service,
        chat_service=chat_service,
        openai_service=openai_service,
        title_service=title_service,
        telegram_file_service=telegram_file_service,
        formatting_service=formatting_service,
        openai_error=OpenAITurnError,
        openai_timeout_error=OpenAITurnTimeoutError,
        telegram_file_too_large_error=TelegramFileTooLargeError,
        openai_input_attachment=OpenAIInputAttachment,
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("newchat", newchat_command))
    application.add_handler(CommandHandler("chat", chat_command))
    application.add_handler(CommandHandler("listchats", listchats_command))
    application.add_handler(CommandHandler("currentchat", currentchat_command))
    application.add_handler(CommandHandler("deletechat", deletechat_command))
    application.add_handler(CommandHandler("sticker", sticker_command))
    application.add_handler(CallbackQueryHandler(listchats_callback, pattern=r"^chat:"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_error_handler(error_handler)

    LOGGER.info("Telegram application configured")
    return application
def run() -> None:
    """Start the bot in long-polling mode."""
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)
