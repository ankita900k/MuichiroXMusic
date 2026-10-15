"""Small in-memory monitoring buffers for the Muichiro Render dashboard.

Only metadata/commands are logged for general Telegram activity; arbitrary
private-message text is deliberately not stored. Buffers reset on process restart.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone

MAX_ENTRIES = 400
_lock = threading.RLock()
_music = deque(maxlen=MAX_ENTRIES)
_activity = deque(maxlen=MAX_ENTRIES)
_render = deque(maxlen=MAX_ENTRIES)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _push(target: deque, message: str, level: str = "INFO") -> None:
    entry = {"time": _now(), "level": str(level).upper(), "message": str(message)[:1200]}
    with _lock:
        target.appendleft(entry)


def music_event(message: str, level: str = "INFO") -> None:
    _push(_music, message, level)
    _push(_activity, f"MUSIC · {message}", level)


def activity_event(message: str, level: str = "INFO") -> None:
    _push(_activity, message, level)


def render_event(message: str, level: str = "INFO") -> None:
    _push(_render, message, level)


def snapshot() -> dict:
    with _lock:
        return {
            "music": list(_music),
            "activity": list(_activity),
            "render": list(_render),
        }


class _RenderLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            render_event(f"{record.name}: {record.getMessage()}", record.levelname)
        except Exception:
            pass


class _TeeStream:
    """Mirror process stdout/stderr into the dashboard while keeping Render output."""
    def __init__(self, original, stream_name: str):
        self.original = original
        self.stream_name = stream_name
        self._pending = ""

    def write(self, value):
        result = self.original.write(value)
        try:
            text = str(value)
            parts = (self._pending + text).splitlines(keepends=True)
            self._pending = ""
            for part in parts:
                if part.endswith(("\n", "\r")):
                    line = part.strip()
                    if line:
                        render_event(f"{self.stream_name}: {line}", "INFO" if self.stream_name == "stdout" else "WARNING")
                else:
                    self._pending += part
        except Exception:
            pass
        return result

    def flush(self):
        return self.original.flush()

    def isatty(self):
        return getattr(self.original, "isatty", lambda: False)()

    def fileno(self):
        return self.original.fileno()

    @property
    def encoding(self):
        return getattr(self.original, "encoding", "utf-8")


def install_render_capture() -> None:
    """Capture application output. Render build/deploy/platform logs are not exposed by its runtime API."""
    import sys
    if not isinstance(sys.stdout, _TeeStream):
        sys.stdout = _TeeStream(sys.stdout, "stdout")
    if not isinstance(sys.stderr, _TeeStream):
        sys.stderr = _TeeStream(sys.stderr, "stderr")
    root = logging.getLogger()
    if not any(isinstance(handler, _RenderLogHandler) for handler in root.handlers):
        root.addHandler(_RenderLogHandler())
    activity_event("Monitoring capture started; dashboard buffers are in-memory and reset on restart.")


def describe_update(update) -> str | None:
    """Return a privacy-conscious summary of a Telegram update."""
    user = getattr(update, "effective_user", None)
    chat = getattr(update, "effective_chat", None)
    message = getattr(update, "effective_message", None)
    if not any((user, chat, message)):
        return None
    who = (getattr(user, "full_name", None) or "Unknown user") if user else "Unknown user"
    username = f" (@{user.username})" if user and getattr(user, "username", None) else ""
    user_id = getattr(user, "id", "?") if user else "?"
    chat_id = getattr(chat, "id", "?") if chat else "?"
    chat_name = (getattr(chat, "title", None) or getattr(chat, "full_name", None) or "Private chat") if chat else "Unknown chat"
    chat_type = getattr(chat, "type", "unknown") if chat else "unknown"
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    command = text.strip().split(maxsplit=1)[0] if text.strip().startswith("/") else None
    if getattr(update, "callback_query", None):
        action = "pressed an inline control"
    elif command:
        action = f"command {command[:80]}"
    elif getattr(message, "voice", None) or getattr(message, "audio", None) or getattr(message, "video", None) or getattr(message, "document", None):
        action = "sent media/file"
    elif getattr(update, "message", None) and getattr(update.message, "new_chat_members", None):
        action = "new member joined"
    elif getattr(update, "message", None) and getattr(update.message, "left_chat_member", None):
        action = "member left"
    else:
        action = "sent a message (content not stored)"
    return f"{action} · user={who}{username} [id:{user_id}] · chat={chat_name} ({chat_type}, id:{chat_id})"
