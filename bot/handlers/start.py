"""Start and help command handlers."""

from __future__ import annotations

# Accepts: /start and /help command updates.
# Calls: AuthService for access checks and FormattingService for display text.
# Produces: Welcome/help messages for approved users, and a short denial for others.

from telegram import Update
from telegram.ext import ContextTypes

from bot.service_locator import get_service_container


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    await update.effective_message.reply_text(services.formatting_service.format_start_text())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    await update.effective_message.reply_text(services.formatting_service.format_help_text())
