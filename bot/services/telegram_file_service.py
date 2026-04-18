"""Telegram file download and metadata extraction helpers."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir

from telegram import Bot, Document, PhotoSize


@dataclass
class DownloadedTelegramFile:
    """A Telegram file downloaded to local disk."""

    attachment_type: str
    telegram_file_id: str
    telegram_file_unique_id: str
    local_path: Path
    filename: str | None
    mime_type: str | None
    file_size: int | None


class TelegramFileTooLargeError(RuntimeError):
    """Raised when a Telegram file exceeds the configured download limit."""


class TelegramFileService:
    """Download Telegram media before passing it to OpenAI."""

    def __init__(self, file_size_limit_bytes: int) -> None:
        """Initialize the service."""
        self.file_size_limit_bytes = file_size_limit_bytes

    async def download_photo(self, bot: Bot, photo: PhotoSize) -> DownloadedTelegramFile:
        """Download the highest-resolution Telegram photo."""
        self._ensure_within_limit(photo.file_size)
        suffix = ".jpg"
        local_path = Path(gettempdir()) / f"{photo.file_unique_id}{suffix}"
        telegram_file = await bot.get_file(photo.file_id)
        await telegram_file.download_to_drive(custom_path=str(local_path))
        return DownloadedTelegramFile(
            attachment_type="image",
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            local_path=local_path,
            filename=local_path.name,
            mime_type="image/jpeg",
            file_size=photo.file_size,
        )

    async def download_document(self, bot: Bot, document: Document) -> DownloadedTelegramFile:
        """Download a Telegram document."""
        self._ensure_within_limit(document.file_size)
        suffix = Path(document.file_name or "").suffix
        local_path = Path(gettempdir()) / f"{document.file_unique_id}{suffix}"
        telegram_file = await bot.get_file(document.file_id)
        await telegram_file.download_to_drive(custom_path=str(local_path))
        return DownloadedTelegramFile(
            attachment_type="file",
            telegram_file_id=document.file_id,
            telegram_file_unique_id=document.file_unique_id,
            local_path=local_path,
            filename=document.file_name,
            mime_type=document.mime_type or mimetypes.guess_type(document.file_name or "")[0],
            file_size=document.file_size,
        )

    def _ensure_within_limit(self, file_size: int | None) -> None:
        """Raise if the Telegram file is larger than the configured limit."""
        if file_size is not None and file_size > self.file_size_limit_bytes:
            max_mb = self.file_size_limit_bytes // (1024 * 1024)
            raise TelegramFileTooLargeError(
                f"Telegram bot downloads are limited to {max_mb} MB in this bot."
            )
