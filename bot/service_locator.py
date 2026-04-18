"""Shared accessors for retrieving the app service container."""

from __future__ import annotations

from typing import Any

from telegram.ext import ContextTypes


SERVICES_KEY = "services"


def get_service_container(context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Return the shared service container stored in bot_data."""
    return context.application.bot_data[SERVICES_KEY]
