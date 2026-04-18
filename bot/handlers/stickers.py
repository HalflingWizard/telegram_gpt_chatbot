"""Sticker command handler."""

from __future__ import annotations

# Accepts: /sticker command updates.
# Calls: AuthService and configuration-backed sticker lookup.
# Produces: A sticker message when configured, otherwise a short setup hint.

from telegram import Update
from telegram.ext import ContextTypes

from bot.service_locator import get_service_container


async def sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the configured sticker back to the user."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    sticker_file_id = services.settings.default_sticker_file_id
    if not sticker_file_id:
        await update.effective_message.reply_text(
            "No default sticker is configured. Set DEFAULT_STICKER_FILE_ID to enable /sticker."
        )
        return
    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=sticker_file_id)
