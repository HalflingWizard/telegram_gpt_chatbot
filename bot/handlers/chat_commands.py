"""Chat command handlers for create, switch, list, inspect, and delete flows."""

from __future__ import annotations

# Accepts: /newchat, /chat, /listchats, /currentchat, /deletechat, /preferences, and callback updates.
# Calls: AuthService, ChatService, FormattingService, preference storage, and validator helpers.
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
    await services.send_default_sticker(context.bot, update.effective_chat.id)


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
    await update.effective_message.reply_text(
        services.formatting_service.format_history_prompt(chat),
        reply_markup=services.formatting_service.build_history_prompt_keyboard(chat.chat_public_id),
    )


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


async def preferences_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show, set, or clear saved user preferences."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    if not context.args:
        current = services.auth_service.get_preferences(update.effective_user.id)
        await update.effective_message.reply_text(
            services.formatting_service.format_preferences(current)
        )
        return

    raw_preferences = " ".join(context.args).strip()
    if raw_preferences.lower() in {"clear", "none", "reset"}:
        services.auth_service.set_preferences(update.effective_user.id, None)
        await update.effective_message.reply_text(
            services.formatting_service.format_preferences_cleared()
        )
        return

    stored = services.auth_service.set_preferences(update.effective_user.id, raw_preferences)
    await update.effective_message.reply_text(
        services.formatting_service.format_preferences_updated(stored or raw_preferences)
    )


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
    await query.message.reply_text(
        services.formatting_service.format_history_prompt(chat),
        reply_markup=services.formatting_service.build_history_prompt_keyboard(chat.chat_public_id),
    )


async def history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle transcript preview callbacks after a chat is loaded."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    query: CallbackQuery = update.callback_query
    await query.answer()

    _, action, public_id = query.data.split(":", 2)
    if action == "no":
        await query.edit_message_text("👌 No problem. You can continue the chat now.")
        return

    history = services.chat_service.get_chat_history(update.effective_user.id, public_id)
    await query.edit_message_text(f"📜 Previous messages from chat {public_id}:")
    for chunk in services.formatting_service.format_chat_history(history):
        await query.message.reply_text(chunk)
