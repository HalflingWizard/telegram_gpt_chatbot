"""Chat command handlers for create, switch, list, inspect, delete, and preference flows."""

from __future__ import annotations

# Accepts: /newchat, /chat, /listchats, /currentchat, /deletechat, /deleteall, /preferences, and callback updates.
# Calls: AuthService, ChatService, FormattingService, preference storage, and validator helpers.
# Produces: User-visible chat management messages and inline keyboard browsing.

from telegram import CallbackQuery, Update
from telegram.ext import ContextTypes

from bot.service_locator import get_service_container
from bot.utils.validators import normalize_chat_public_id, validate_chat_public_id


PREFERENCES_PENDING_ACTION_KEY = "pending_preferences_action"
PERSONA_PENDING_ACTION_KEY = "pending_persona_action"


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
    active_persona = services.chat_service.get_active_persona_for_chat(chat.id) if chat else None
    await update.effective_message.reply_text(
        services.formatting_service.format_current_chat(chat, active_persona)
    )


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


async def deleteall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask the user to confirm deletion of all saved data."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    await update.effective_message.reply_text(
        services.formatting_service.format_delete_all_prompt(),
        reply_markup=services.formatting_service.build_delete_all_keyboard(),
    )


async def preferences_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open the preferences menu, or save shortcut text when provided."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    current = services.auth_service.get_preferences(update.effective_user.id)
    if not context.args:
        await update.effective_message.reply_text(
            services.formatting_service.format_preferences(current),
            reply_markup=services.formatting_service.build_preferences_keyboard(bool(current)),
        )
        return

    raw_preferences = " ".join(context.args).strip()
    if raw_preferences.lower() in {"clear", "none", "reset"}:
        services.auth_service.set_preferences(update.effective_user.id, None)
        context.user_data.pop(PREFERENCES_PENDING_ACTION_KEY, None)
        await update.effective_message.reply_text(
            services.formatting_service.format_preferences_cleared()
        )
        return

    stored = services.auth_service.set_preferences(update.effective_user.id, raw_preferences)
    context.user_data.pop(PREFERENCES_PENDING_ACTION_KEY, None)
    await update.effective_message.reply_text(
        services.formatting_service.format_preferences_updated(stored or raw_preferences)
    )


async def personas_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List and manage assistant personas."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    active_chat = services.chat_service.get_active_chat(update.effective_user.id)
    if active_chat is None:
        await update.effective_message.reply_text("⚠️ No active chat. Use /newchat first.")
        return

    args = context.args or []
    if not args:
        personas = services.chat_service.list_personas(update.effective_user.id)
        active_persona = services.chat_service.get_active_persona_for_chat(active_chat.id)
        await update.effective_message.reply_text(
            services.formatting_service.format_persona_list(personas, active_persona)
        )
        return

    action = args[0].lower()
    if action == "add":
        raw_value = " ".join(args[1:]).strip()
        if not raw_value:
            context.user_data[PERSONA_PENDING_ACTION_KEY] = "add"
            await update.effective_message.reply_text(
                services.formatting_service.format_persona_prompt_request()
            )
            return
        await _save_persona_from_text(update, services, raw_value)
        return

    if action == "use":
        name = " ".join(args[1:]).strip()
        if not name:
            await update.effective_message.reply_text("Usage, /personas use <name>")
            return
        persona = services.chat_service.set_active_persona(
            telegram_user_id=update.effective_user.id,
            chat_id=active_chat.id,
            name=name,
        )
        if persona is None:
            await update.effective_message.reply_text("Persona not found.")
            return
        await update.effective_message.reply_text(services.formatting_service.format_persona_selected(persona))
        return

    if action in {"general", "clear", "reset"}:
        services.chat_service.clear_active_persona(active_chat.id)
        await update.effective_message.reply_text(services.formatting_service.format_persona_cleared())
        return

    if action == "delete":
        name = " ".join(args[1:]).strip()
        if not name:
            await update.effective_message.reply_text("Usage, /personas delete <name>")
            return
        persona = services.chat_service.delete_persona(update.effective_user.id, name)
        if persona is None:
            await update.effective_message.reply_text("Persona not found, or it is built in and cannot be deleted.")
            return
        await update.effective_message.reply_text(services.formatting_service.format_persona_deleted(persona))
        return

    await update.effective_message.reply_text("Unknown persona command. Use /personas to see options.")


async def save_pending_persona_if_needed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Save a pending persona prompt when the user is in persona setup mode."""
    if context.user_data.get(PERSONA_PENDING_ACTION_KEY) != "add":
        return False
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return True
    raw_value = update.effective_message.text or ""
    context.user_data.pop(PERSONA_PENDING_ACTION_KEY, None)
    await _save_persona_from_text(update, services, raw_value)
    return True


async def _save_persona_from_text(update: Update, services, raw_value: str) -> None:
    """Parse and save a persona from Name | prompt text."""
    if "|" not in raw_value:
        await update.effective_message.reply_text(
            "I could not save that persona. Use this format, Name | prompt"
        )
        return
    name, system_prompt = [part.strip() for part in raw_value.split("|", 1)]
    if not name or not system_prompt:
        await update.effective_message.reply_text(
            "I could not save that persona. Both name and prompt are required."
        )
        return
    persona = services.chat_service.create_persona(update.effective_user.id, name, system_prompt)
    if persona is None:
        await update.effective_message.reply_text("I could not save that persona.")
        return
    await update.effective_message.reply_text(services.formatting_service.format_persona_saved(persona))


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


async def preferences_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline preference menu actions."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    query: CallbackQuery = update.callback_query
    await query.answer()

    _, action = query.data.split(":", 1)
    current = services.auth_service.get_preferences(update.effective_user.id)

    if action == "close":
        context.user_data.pop(PREFERENCES_PENDING_ACTION_KEY, None)
        await query.edit_message_text("👌 Preferences menu closed.")
        return

    if action == "delete":
        services.auth_service.set_preferences(update.effective_user.id, None)
        context.user_data.pop(PREFERENCES_PENDING_ACTION_KEY, None)
        await query.edit_message_text(
            services.formatting_service.format_preferences(None),
            reply_markup=services.formatting_service.build_preferences_keyboard(False),
        )
        await query.message.reply_text(services.formatting_service.format_preferences_cleared())
        return

    if action in {"add", "edit"}:
        context.user_data[PREFERENCES_PENDING_ACTION_KEY] = action
        await query.message.reply_text(
            services.formatting_service.format_preferences_prompt(action, current)
        )


async def deleteall_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle confirmation callbacks for full user data deletion."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    query: CallbackQuery = update.callback_query
    await query.answer()

    _, action = query.data.split(":", 1)
    if action == "cancel":
        await query.edit_message_text("👌 Full delete canceled.")
        return

    deleted = services.auth_service.delete_all_user_data(update.effective_user.id)
    context.user_data.clear()
    if deleted:
        await query.edit_message_text(services.formatting_service.format_delete_all_done())
        return
    await query.edit_message_text("📭 There was no saved data to delete.")
