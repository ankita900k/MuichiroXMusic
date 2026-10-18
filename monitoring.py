"""SQLite-backed, privacy-conscious event logging for Muichiro HQ."""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

MAX_ENTRIES = max(100, min(int(os.environ.get("MONITOR_MAX_ENTRIES", "2000")), 20000))
DB_PATH = os.environ.get("MONITOR_DB_PATH", "monitor_logs.sqlite3")
_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _connect():
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db():
    with _lock, _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS monitor_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL CHECK(category IN ('music','activity','render')),
            time TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_monitor_category_id ON monitor_events(category, id DESC)")
        conn.commit()


_init_db()


def _push(category: str, message: str, level: str = "INFO") -> None:
    safe_message = str(message)[:1200]
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO monitor_events(category,time,level,message) VALUES(?,?,?,?)",
            (category, _now(), str(level).upper()[:16], safe_message),
        )
        conn.execute(
            "DELETE FROM monitor_events WHERE id NOT IN (SELECT id FROM monitor_events ORDER BY id DESC LIMIT ?)",
            (MAX_ENTRIES * 3,),
        )
        conn.commit()


def music_event(message: str, level: str = "INFO") -> None:
    _push("music", message, level)
    _push("activity", f"MUSIC · {message}", level)


def activity_event(message: str, level: str = "INFO") -> None:
    _push("activity", message, level)


def render_event(message: str, level: str = "INFO") -> None:
    _push("render", message, level)


def snapshot(limit: int = 250) -> dict:
    limit = max(20, min(int(limit), 1000))
    with _lock, _connect() as conn:
        result = {}
        for category in ("music", "activity", "render"):
            rows = conn.execute(
                "SELECT time,level,message FROM monitor_events WHERE category=? ORDER BY id DESC LIMIT ?",
                (category, limit),
            ).fetchall()
            result[category] = [dict(row) for row in rows]
        counts = conn.execute(
            "SELECT category,COUNT(*) AS count FROM monitor_events GROUP BY category"
        ).fetchall()
        result["counts"] = {row["category"]: row["count"] for row in counts}
        result["database"] = "sqlite"
        return result


def clear_logs() -> int:
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM monitor_events")
        conn.commit()
        return cur.rowcount


class _RenderLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            render_event(f"{record.name}: {record.getMessage()}", record.levelname)
        except Exception:
            pass


class _TeeStream:
    """Mirror stdout/stderr to SQLite while preserving Render's original stream."""
    def __init__(self, original, stream_name: str):
        self.original = original
        self.stream_name = stream_name
        self._pending = ""

    def write(self, value):
        result = self.original.write(value)
        try:
            parts = (self._pending + str(value)).splitlines(keepends=True)
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
    if not isinstance(sys.stdout, _TeeStream):
        sys.stdout = _TeeStream(sys.stdout, "stdout")
    if not isinstance(sys.stderr, _TeeStream):
        sys.stderr = _TeeStream(sys.stderr, "stderr")
    root = logging.getLogger()
    if not any(isinstance(handler, _RenderLogHandler) for handler in root.handlers):
        root.addHandler(_RenderLogHandler())
    activity_event(f"Monitoring capture started; SQLite database: {DB_PATH}")


def describe_update(update) -> str | None:
    """Summarize Telegram activity without storing arbitrary message contents."""
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
