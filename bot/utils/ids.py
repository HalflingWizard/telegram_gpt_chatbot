"""Short ID generation helpers."""

from __future__ import annotations

import secrets


CHAT_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_chat_public_id(length: int = 6) -> str:
    """Generate a short readable public chat ID."""
    return "".join(secrets.choice(CHAT_ID_ALPHABET) for _ in range(length))
