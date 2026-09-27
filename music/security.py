"""Small helpers for keeping secrets and Telegram errors out of user messages/logs."""
import os
import re
from urllib.parse import quote, urlsplit, urlunsplit, parse_qsl, urlencode

_SECRET_ENV_NAMES = (
    "ANNIE_API_KEY",
    "API_HASH",
    "SESSION_STRING",
    "BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN",
)


def redact_secrets(value: object) -> str:
    """Return text with known configured secrets and common token forms masked."""
    text = str(value or "")

    # Replace configured secret values wherever they appear, including URL-encoded forms.
    for name in _SECRET_ENV_NAMES:
        secret = os.getenv(name, "")
        if secret:
            text = text.replace(secret, "[REDACTED]")
            try:
                text = text.replace(quote(secret, safe=""), "[REDACTED]")
            except Exception:
                pass

    # Never expose query-string credentials even if the secret wasn't loaded in this process.
    try:
        parts = urlsplit(text)
        if parts.scheme and parts.netloc and parts.query:
            pairs = parse_qsl(parts.query, keep_blank_values=True)
            safe_pairs = []
            for key, val in pairs:
                if key.lower() in {"api_key", "apikey", "api-hash", "api_hash", "token", "access_token"}:
                    val = "[REDACTED]"
                safe_pairs.append((key, val))
            text = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_pairs), parts.fragment))
    except Exception:
        pass

    # Common Telegram bot-token shape.
    text = re.sub(r"\b\d{7,12}:[A-Za-z0-9_-]{25,}\b", "[REDACTED_TOKEN]", text)
    return text


def safe_exception(exc: BaseException) -> str:
    """Short, non-secret diagnostic suitable for a log or controlled admin log."""
    return redact_secrets(f"{type(exc).__name__}: {exc}")


def user_error_message(exc: BaseException, fallback: str) -> str:
    """Return a friendly user-facing error without implementation details or secrets."""
    # Deliberately do not echo exception text into Telegram.
    return fallback
