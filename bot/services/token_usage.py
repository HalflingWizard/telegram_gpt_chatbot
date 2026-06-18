"""Token usage data structures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextWindowWarning:
    """User-facing context warning state."""

    level: str
    input_tokens: int
    context_window_tokens: int
    percent_used: int
