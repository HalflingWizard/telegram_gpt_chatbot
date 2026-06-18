"""Handlers and helpers for media turns and buffered user turns."""

from __future__ import annotations

# Accepts: Telegram text, photos with optional captions, and documents with optional captions.
# Calls: AuthService, ChatService, TelegramFileService, OpenAIService, and TitleService.
# Produces: Assistant replies using text/image/file inputs, or clear upload-limit and recovery messages.

import asyncio
import logging
from dataclasses import dataclass

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.services.chat_service import AttachmentRecord
from bot.service_locator import get_service_container


LOGGER = logging.getLogger(__name__)
PENDING_USER_TURNS_KEY = "pending_user_turns"
USER_TURN_BUFFER_SECONDS = 1.2


@dataclass
class PendingUserTurn:
    """Buffered Telegram updates waiting to be processed as one user turn."""

    updates: list[Update]
    task: asyncio.Task | None = None


def buffer_user_turn_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Collect nearby user messages before sending one model request."""
    groups = context.application.bot_data.setdefault(PENDING_USER_TURNS_KEY, {})
    key = _user_turn_key(update)
    pending = groups.get(key)
    if pending is None:
        pending = PendingUserTurn(updates=[])
        groups[key] = pending
    pending.updates.append(update)
    if pending.task and not pending.task.done():
        pending.task.cancel()
    pending.task = context.application.create_task(
        _flush_user_turn_after_delay(key, context),
        update=update,
    )


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a photo turn with an optional caption."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    buffer_user_turn_update(update, context)


async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a document turn with an optional caption."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    buffer_user_turn_update(update, context)


async def _flush_user_turn_after_delay(key: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Wait briefly, then process one complete buffered user turn."""
    try:
        await asyncio.sleep(USER_TURN_BUFFER_SECONDS)
    except asyncio.CancelledError:
        return

    groups = context.application.bot_data.setdefault(PENDING_USER_TURNS_KEY, {})
    pending = groups.pop(key, None)
    if pending is None or not pending.updates:
        return

    first_update = min(pending.updates, key=lambda item: item.effective_message.message_id)
    services = get_service_container(context)
    active_chat = services.chat_service.get_active_chat(first_update.effective_user.id)
    if active_chat is None:
        await first_update.effective_message.reply_text("⚠️ No active chat. Use /newchat or /chat <id>.")
        return
    if active_chat.state is None:
        await first_update.effective_message.reply_text(
            "⚠️ That chat could not be restored. Start a new chat with /newchat."
        )
        return

    await _process_turn_updates(
        updates=pending.updates,
        context=context,
        services=services,
        active_chat=active_chat,
    )


async def _process_turn_updates(
    updates: list[Update],
    context: ContextTypes.DEFAULT_TYPE,
    services,
    active_chat,
) -> None:
    """Download, store, and answer one or more updates in one turn."""
    ordered_updates = sorted(updates, key=lambda item: item.effective_message.message_id)
    prompt_text = _combined_message_text(ordered_updates)
    attachments: list[AttachmentRecord] = []
    first_update = ordered_updates[0]

    try:
        for item in ordered_updates:
            if _is_text_update(item):
                continue
            attachment = await _upload_media_update(item, context, services)
            attachments.append(attachment)
    except services.telegram_file_too_large_error as exc:
        await first_update.effective_message.reply_text(str(exc))
        return
    except services.openai_error:
        LOGGER.exception("OpenAI upload failed")
        await first_update.effective_message.reply_text("⚠️ One of the uploads failed. Please try again.")
        return

    services.chat_service.store_user_message(
        chat_id=active_chat.id,
        message_type=_message_type_for_turn(prompt_text, attachments),
        text_content=prompt_text,
        telegram_message_id=first_update.effective_message.message_id,
        attachments=attachments,
    )
    services.log_event(
        logging.INFO,
        action="user_turn_received",
        update=first_update,
        success=True,
        message="Stored buffered user turn",
        chat_public_id=active_chat.chat_public_id,
        chat_db_id=active_chat.id,
    )
    await _respond_to_user_turn(
        update=first_update,
        context=context,
        services=services,
        active_chat=active_chat,
        prompt_text=prompt_text,
        attachment_records=attachments,
    )
    if active_chat.title == "Untitled chat":
        title_seed = prompt_text or _title_seed_for_attachments(attachments)
        title, status = await services.title_service.create_title(title_seed)
        services.chat_service.update_title(chat_id=active_chat.id, title=title, title_status=status)


async def _upload_media_update(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    services,
) -> AttachmentRecord:
    """Upload one Telegram media update and return the stored attachment data."""
    message = update.effective_message
    if message.photo:
        downloaded = await services.telegram_file_service.download_photo(context.bot, message.photo[-1])
        attachment_type = "image"
    else:
        downloaded = await services.telegram_file_service.download_document(context.bot, message.document)
        attachment_type = "file"
    openai_file_id = await services.openai_service.upload_user_file(
        downloaded.local_path, filename=downloaded.filename
    )
    return AttachmentRecord(
        attachment_type=attachment_type,
        telegram_file_id=downloaded.telegram_file_id,
        telegram_file_unique_id=downloaded.telegram_file_unique_id,
        openai_file_id=openai_file_id,
        filename=downloaded.filename,
        mime_type=downloaded.mime_type,
        caption=message.caption,
        file_size=downloaded.file_size,
    )


def _user_turn_key(update: Update) -> str:
    """Build a stable key for one user's buffered turn in one chat."""
    return f"{update.effective_chat.id}:{update.effective_user.id}"


def _is_text_update(update: Update) -> bool:
    """Return whether this update is a plain text message."""
    return bool(getattr(update.effective_message, "text", None))


def _combined_message_text(updates: list[Update]) -> str | None:
    """Combine text messages and captions into one prompt."""
    text_parts = []
    for update in updates:
        message = update.effective_message
        text = message.text if _is_text_update(update) else message.caption
        if text:
            text_parts.append(text)
    if not text_parts:
        return None
    return "\n\n".join(text_parts)


def _message_type_for_turn(prompt_text: str | None, attachments: list[AttachmentRecord]) -> str:
    """Return a compact stored message type for the buffered turn."""
    if prompt_text and not attachments:
        return "text"
    attachment_types = {item.attachment_type for item in attachments}
    if attachment_types == {"image"}:
        return "image"
    if attachment_types == {"file"}:
        return "file"
    return "mixed_media"


def _title_seed_for_attachments(attachments: list[AttachmentRecord]) -> str:
    """Return fallback title text for a media-only chat."""
    message_type = _message_type_for_turn(None, attachments)
    if message_type == "image":
        return "Shared images" if len(attachments) > 1 else "Shared image"
    if message_type == "file":
        return "Shared files" if len(attachments) > 1 else "Shared file"
    return "Shared media"


async def _respond_to_user_turn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    services,
    active_chat,
    prompt_text: str | None,
    attachment_records: list[AttachmentRecord],
) -> None:
    """Send a buffered user turn to OpenAI and reply in Telegram."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        assistant_reply = await services.openai_service.create_response(
            prompt_text=prompt_text,
            attachments=[
                services.openai_input_attachment(
                    attachment_type=item.attachment_type,
                    openai_file_id=item.openai_file_id,
                    caption=item.caption,
                    filename=item.filename,
                )
                for item in attachment_records
                if item.openai_file_id
            ],
            previous_response_id=active_chat.state.last_openai_response_id,
            user_preferences=services.auth_service.get_preferences(update.effective_user.id),
        )
    except services.openai_timeout_error:
        services.log_event(
            logging.WARNING,
            action="user_turn_openai_timeout",
            update=update,
            success=False,
            message="OpenAI user turn timed out",
            chat_public_id=active_chat.chat_public_id,
            chat_db_id=active_chat.id,
        )
        await update.effective_message.reply_text("⏳ The model timed out. Please try again.")
        return
    except services.openai_error:
        services.log_event(
            logging.ERROR,
            action="user_turn_openai_error",
            update=update,
            success=False,
            message="OpenAI user turn failed",
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
    context_warning = None
    if assistant_reply.usage:
        context_warning = services.chat_service.record_token_usage(
            chat_id=active_chat.id,
            input_tokens=assistant_reply.usage.input_tokens,
            output_tokens=assistant_reply.usage.output_tokens,
            total_tokens=assistant_reply.usage.total_tokens,
            context_window_tokens=services.settings.openai_context_window_tokens,
        )
    services.log_event(
        logging.INFO,
        action="user_turn_replied",
        update=update,
        success=True,
        message="Stored assistant user-turn reply",
        chat_public_id=active_chat.chat_public_id,
        chat_db_id=active_chat.id,
    )
    await update.effective_message.reply_text(final_text)
    if context_warning:
        await update.effective_message.reply_text(
            services.formatting_service.format_context_window_warning(context_warning)
        )
