"""Global Telegram error handler."""

from __future__ import annotations

# Accepts: exceptions raised by any Telegram handler.
# Calls: standard logging and sends a short safe fallback message when possible.
# Produces: Structured server-side logs and a user-visible retry message.

import logging

from telegram import Update
from telegram.ext import ContextTypes


LOGGER = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log unexpected handler failures and notify the user when possible."""
    LOGGER.exception("Unhandled Telegram handler error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Something went wrong while handling that update. Please try again."
        )
