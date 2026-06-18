"""Text-message handler for normal conversational turns."""

from __future__ import annotations

# Accepts: plain text messages that are not commands.
# Calls: AuthService and the buffered user-turn helper.
# Produces: Assistant replies for the active chat, or a prompt to create/select a chat.

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.chat_commands import PREFERENCES_PENDING_ACTION_KEY
from bot.handlers.media_messages import buffer_user_turn_update
from bot.service_locator import get_service_container


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a plain-text conversational turn."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    pending_preferences_action = context.user_data.get(PREFERENCES_PENDING_ACTION_KEY)
    if pending_preferences_action:
        user_text = update.effective_message.text or ""
        stored = services.auth_service.set_preferences(update.effective_user.id, user_text)
        context.user_data.pop(PREFERENCES_PENDING_ACTION_KEY, None)
        await update.effective_message.reply_text(
            services.formatting_service.format_preferences_updated(stored or user_text)
        )
        return

    buffer_user_turn_update(update, context)
