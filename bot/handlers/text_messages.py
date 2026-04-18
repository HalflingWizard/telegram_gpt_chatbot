"""Text-message handler for normal conversational turns."""

from __future__ import annotations

# Accepts: plain text messages that are not commands.
# Calls: AuthService, ChatService, OpenAIService, TitleService, and logging helpers.
# Produces: Assistant replies for the active chat, or a prompt to create/select a chat.

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.service_locator import get_service_container


LOGGER = logging.getLogger(__name__)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a plain-text conversational turn."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    active_chat = services.chat_service.get_active_chat(update.effective_user.id)
    if active_chat is None:
        await update.effective_message.reply_text("⚠️ No active chat. Use /newchat or /chat <id>.")
        return
    if active_chat.state is None:
        await update.effective_message.reply_text(
            "⚠️ That chat could not be restored. Start a new chat with /newchat."
        )
        return

    user_text = update.effective_message.text or ""
    services.chat_service.store_user_message(
        chat_id=active_chat.id,
        message_type="text",
        text_content=user_text,
        telegram_message_id=update.effective_message.message_id,
    )
    services.log_event(
        logging.INFO,
        action="text_turn_received",
        update=update,
        success=True,
        message="Stored user text turn",
        chat_public_id=active_chat.chat_public_id,
        chat_db_id=active_chat.id,
    )

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        assistant_reply = await services.openai_service.create_response(
            prompt_text=user_text,
            attachments=None,
            previous_response_id=active_chat.state.last_openai_response_id,
            user_preferences=services.auth_service.get_preferences(update.effective_user.id),
        )
    except services.openai_timeout_error:
        services.log_event(
            logging.WARNING,
            action="text_turn_openai_timeout",
            update=update,
            success=False,
            message="OpenAI text turn timed out",
            chat_public_id=active_chat.chat_public_id,
            chat_db_id=active_chat.id,
        )
        await update.effective_message.reply_text("⏳ The model timed out. Please try again.")
        return
    except services.openai_error:
        services.log_event(
            logging.ERROR,
            action="text_turn_openai_error",
            update=update,
            success=False,
            message="OpenAI text turn failed",
            chat_public_id=active_chat.chat_public_id,
            chat_db_id=active_chat.id,
            exc_info=True,
        )
        await update.effective_message.reply_text(
            "⚠️ The bot could not get a response right now. Please try again."
        )
        return

    final_text = assistant_reply.text or "I could not produce a response."
    services.chat_service.store_assistant_message(
        chat_id=active_chat.id,
        text_content=final_text,
        openai_response_id=assistant_reply.response_id,
    )
    services.log_event(
        logging.INFO,
        action="text_turn_replied",
        update=update,
        success=True,
        message="Stored assistant text reply",
        chat_public_id=active_chat.chat_public_id,
        chat_db_id=active_chat.id,
    )
    await update.effective_message.reply_text(final_text)

    if active_chat.title == "Untitled chat":
        title, status = await services.title_service.create_title(user_text)
        services.chat_service.update_title(chat_id=active_chat.id, title=title, title_status=status)
