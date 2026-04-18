"""Time formatting helpers used by Telegram handlers."""

from __future__ import annotations

from datetime import datetime


def format_chat_timestamp(value: datetime | None) -> str:
    """Format a chat timestamp for list display."""
    if value is None:
        return "Never updated"
    return value.strftime("%Y-%m-%d %H:%M")
