"""Media handlers for image and file turns."""

from __future__ import annotations

# Accepts: Telegram photos with optional captions and documents with optional captions.
# Calls: AuthService, ChatService, TelegramFileService, OpenAIService, and TitleService.
# Produces: Assistant replies using image/file inputs, or clear upload-limit and recovery messages.

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.services.chat_service import AttachmentRecord
from bot.service_locator import get_service_container


LOGGER = logging.getLogger(__name__)


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a photo turn with an optional caption."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    active_chat = services.chat_service.get_active_chat(update.effective_user.id)
    if active_chat is None:
        await update.effective_message.reply_text("No active chat. Use /newchat or /chat <id>.")
        return
    if active_chat.state is None:
        await update.effective_message.reply_text(
            "That chat could not be restored. Start a new chat with /newchat."
        )
        return

    photo = update.effective_message.photo[-1]
    caption = update.effective_message.caption
    try:
        downloaded = await services.telegram_file_service.download_photo(context.bot, photo)
        openai_file_id = await services.openai_service.upload_user_file(
            downloaded.local_path, filename=downloaded.filename
        )
    except services.telegram_file_too_large_error as exc:
        await update.effective_message.reply_text(str(exc))
        return
    except services.openai_error:
        LOGGER.exception("OpenAI photo upload failed")
        await update.effective_message.reply_text("The image upload failed. Please try again.")
        return

    attachments = [
        AttachmentRecord(
            attachment_type="image",
            telegram_file_id=downloaded.telegram_file_id,
            telegram_file_unique_id=downloaded.telegram_file_unique_id,
            openai_file_id=openai_file_id,
            filename=downloaded.filename,
            mime_type=downloaded.mime_type,
            caption=caption,
            file_size=downloaded.file_size,
        )
    ]
    services.chat_service.store_user_message(
        chat_id=active_chat.id,
        message_type="image",
        text_content=caption,
        telegram_message_id=update.effective_message.message_id,
        attachments=attachments,
    )
    services.log_event(
        logging.INFO,
        action="photo_turn_received",
        update=update,
        success=True,
        message="Stored user photo turn",
        chat_public_id=active_chat.chat_public_id,
        chat_db_id=active_chat.id,
    )
    await _respond_to_media_turn(
        update=update,
        context=context,
        services=services,
        active_chat=active_chat,
        prompt_text=caption,
        attachment_records=attachments,
    )
    if active_chat.title == "Untitled chat":
        title_seed = caption or "Shared image"
        title, status = await services.title_service.create_title(title_seed)
        services.chat_service.update_title(chat_id=active_chat.id, title=title, title_status=status)


async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a document turn with an optional caption."""
    services = get_service_container(context)
    if not await services.authorize_update(update):
        return
    active_chat = services.chat_service.get_active_chat(update.effective_user.id)
    if active_chat is None:
        await update.effective_message.reply_text("No active chat. Use /newchat or /chat <id>.")
        return
    if active_chat.state is None:
        await update.effective_message.reply_text(
            "That chat could not be restored. Start a new chat with /newchat."
        )
        return

    document = update.effective_message.document
    caption = update.effective_message.caption
    try:
        downloaded = await services.telegram_file_service.download_document(context.bot, document)
        openai_file_id = await services.openai_service.upload_user_file(
            downloaded.local_path, filename=downloaded.filename
        )
    except services.telegram_file_too_large_error as exc:
        await update.effective_message.reply_text(str(exc))
        return
    except services.openai_error:
        LOGGER.exception("OpenAI document upload failed")
        await update.effective_message.reply_text("The file upload failed. Please try again.")
        return

    attachments = [
        AttachmentRecord(
            attachment_type="file",
            telegram_file_id=downloaded.telegram_file_id,
            telegram_file_unique_id=downloaded.telegram_file_unique_id,
            openai_file_id=openai_file_id,
            filename=downloaded.filename,
            mime_type=downloaded.mime_type,
            caption=caption,
            file_size=downloaded.file_size,
        )
    ]
    services.chat_service.store_user_message(
        chat_id=active_chat.id,
        message_type="file",
        text_content=caption,
        telegram_message_id=update.effective_message.message_id,
        attachments=attachments,
    )
    services.log_event(
        logging.INFO,
        action="document_turn_received",
        update=update,
        success=True,
        message="Stored user document turn",
        chat_public_id=active_chat.chat_public_id,
        chat_db_id=active_chat.id,
    )
    await _respond_to_media_turn(
        update=update,
        context=context,
        services=services,
        active_chat=active_chat,
        prompt_text=caption,
        attachment_records=attachments,
    )
    if active_chat.title == "Untitled chat":
        title_seed = caption or (downloaded.filename or "Shared file")
        title, status = await services.title_service.create_title(title_seed)
        services.chat_service.update_title(chat_id=active_chat.id, title=title, title_status=status)


async def _respond_to_media_turn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    services,
    active_chat,
    prompt_text: str | None,
    attachment_records: list[AttachmentRecord],
) -> None:
    """Send a photo or file turn to OpenAI and reply in Telegram."""
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
        )
    except services.openai_timeout_error:
        services.log_event(
            logging.WARNING,
            action="media_turn_openai_timeout",
            update=update,
            success=False,
            message="OpenAI media turn timed out",
            chat_public_id=active_chat.chat_public_id,
            chat_db_id=active_chat.id,
        )
        await update.effective_message.reply_text("The model timed out. Please try again.")
        return
    except services.openai_error:
        services.log_event(
            logging.ERROR,
            action="media_turn_openai_error",
            update=update,
            success=False,
            message="OpenAI media turn failed",
            chat_public_id=active_chat.chat_public_id,
            chat_db_id=active_chat.id,
            exc_info=True,
        )
        await update.effective_message.reply_text(
            "The bot could not process that upload right now. Please try again."
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
        action="media_turn_replied",
        update=update,
        success=True,
        message="Stored assistant media reply",
        chat_public_id=active_chat.chat_public_id,
        chat_db_id=active_chat.id,
    )
    await update.effective_message.reply_text(final_text)
