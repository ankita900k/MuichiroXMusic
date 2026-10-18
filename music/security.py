"""
Security and error-handling helpers for the Muichiro music system.
"""

from __future__ import annotations

import logging
import re
from typing import Any


# Patterns that may contain sensitive information.
_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(bot_token|api[_-]?key|api[_-]?hash|session[_-]?string|password|secret)\s*[=:]\s*\S+"),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),  # Telegram bot-token-like values
)


def safe_exception(exc: BaseException | Any) -> str:
    """
    Return a safe, sanitized representation of an exception.

    This is intended for logs so that accidental secrets/tokens in
    exception messages are not exposed.
    """
    try:
        message = str(exc).strip()
    except Exception:
        return exc.__class__.__name__ if isinstance(exc, BaseException) else "Unknown error"

    if not message:
        return exc.__class__.__name__ if isinstance(exc, BaseException) else "Unknown error"

    for pattern in _SENSITIVE_PATTERNS:
        message = pattern.sub("[REDACTED]", message)

    # Avoid dumping huge exception messages into logs.
    if len(message) > 1000:
        message = message[:1000] + "..."

    return message


def user_error_message(exc: BaseException | Any) -> str:
    """
    Convert an internal exception into a short, user-friendly message.

    Internal details are intentionally not exposed to Telegram users.
    """
    if exc is None:
        return "Something went wrong. Please try again."

    name = exc.__class__.__name__.lower() if isinstance(exc, BaseException) else ""

    if "timeout" in name:
        return "The request timed out. Please try again."

    if "forbidden" in name:
        return "I don't have permission to perform that action."

    if "notfound" in name or "not_found" in name:
        return "The requested item could not be found."

    if "network" in name or "connection" in name:
        return "A network error occurred. Please try again."

    return "Something went wrong while processing your request. Please try again."


def log_exception(
    logger: logging.Logger,
    message: str,
    exc: BaseException | Any,
    *,
    level: int = logging.ERROR,
) -> None:
    """
    Convenience helper for safely logging an exception.
    """
    logger.log(level, "%s: %s", message, safe_exception(exc))