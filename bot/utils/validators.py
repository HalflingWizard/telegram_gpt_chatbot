"""Input validation helpers."""

from __future__ import annotations

import re


CHAT_ID_PATTERN = re.compile(r"^[A-Z2-9]{5,8}$")


def normalize_chat_public_id(value: str) -> str:
    """Normalize a user-supplied chat ID for lookup."""
    return value.strip().upper()


def validate_chat_public_id(value: str) -> bool:
    """Return whether a chat ID matches the supported format."""
    return bool(CHAT_ID_PATTERN.match(normalize_chat_public_id(value)))
