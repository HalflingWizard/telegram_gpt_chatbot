"""Chat command handlers for create, switch, list, inspect, and delete flows."""

from __future__ import annotations

# Accepts: /newchat, /chat, /listchats, /currentchat, /deletechat, and chat list callbacks.
# Calls: AuthService, ChatService, FormattingService, and validator helpers.
# Produces: User-visible chat management messages and inline keyboard browsing.

from telegram import CallbackQuery, Update
from telegram.ext import ContextTypes

from bot.service_locator import get_service_container
from bot.utils.validators import normalize_chat_public_id, validate_chat_public_id


async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new active chat."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    chat = services.chat_service.create_new_chat(update.effective_user.id)
    services.log_event(
        20,
        action="new_chat",
        update=update,
        success=True,
        message="Created new chat",
        chat_public_id=chat.chat_public_id,
        chat_db_id=chat.id,
    )
    await update.effective_message.reply_text(services.formatting_service.format_chat_created(chat))


async def currentchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the active chat."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    chat = services.chat_service.get_active_chat(update.effective_user.id)
    await update.effective_message.reply_text(services.formatting_service.format_current_chat(chat))


async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch to an existing chat by public ID."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /chat <id>")
        return
    public_id = normalize_chat_public_id(context.args[0])
    if not validate_chat_public_id(public_id):
        await update.effective_message.reply_text("That chat ID format is invalid.")
        return
    chat = services.chat_service.switch_active_chat(update.effective_user.id, public_id)
    if chat is None:
        services.log_event(
            30,
            action="switch_chat",
            update=update,
            success=False,
            message="Requested chat not found",
            chat_public_id=public_id,
        )
        await update.effective_message.reply_text("Chat not found.")
        return
    services.log_event(
        20,
        action="switch_chat",
        update=update,
        success=True,
        message="Switched active chat",
        chat_public_id=chat.chat_public_id,
        chat_db_id=chat.id,
    )
    await update.effective_message.reply_text(services.formatting_service.format_chat_switched(chat))


async def listchats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List recent chats and show an inline keyboard for quick loading."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    chats = services.chat_service.list_chats(update.effective_user.id)
    text = services.formatting_service.format_chat_list(chats)
    if chats:
        keyboard = services.formatting_service.build_chat_list_keyboard(chats)
        await update.effective_message.reply_text(text, reply_markup=keyboard)
        return
    await update.effective_message.reply_text(text)


async def deletechat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Soft delete a chat by public ID."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /deletechat <id>")
        return
    public_id = normalize_chat_public_id(context.args[0])
    if not validate_chat_public_id(public_id):
        await update.effective_message.reply_text("That chat ID format is invalid.")
        return
    chat = services.chat_service.delete_chat(update.effective_user.id, public_id)
    if chat is None:
        await update.effective_message.reply_text("Chat not found.")
        return
    services.log_event(
        20,
        action="delete_chat",
        update=update,
        success=True,
        message="Soft deleted chat",
        chat_public_id=chat.chat_public_id,
        chat_db_id=chat.id,
    )
    await update.effective_message.reply_text(services.formatting_service.format_chat_deleted(chat))


async def listchats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard chat-selection callbacks."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    query: CallbackQuery = update.callback_query
    await query.answer()
    _, public_id = query.data.split(":", 1)
    chat = services.chat_service.switch_active_chat(update.effective_user.id, public_id)
    if chat is None:
        await query.edit_message_text("Chat not found.")
        return
    services.log_event(
        20,
        action="switch_chat_callback",
        update=update,
        success=True,
        message="Switched active chat from callback",
        chat_public_id=chat.chat_public_id,
        chat_db_id=chat.id,
    )
    await query.edit_message_text(services.formatting_service.format_chat_switched(chat))
