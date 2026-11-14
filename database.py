"""Muichiro database bootstrap and resilient PostgreSQL connection layer.

Neon PostgreSQL is the authoritative database.  Transient connection failures
trigger bounded reconnect attempts.  Failed writes are NEVER replayed
automatically because their commit status may be unknown.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from typing import Any

import psycopg2
from psycopg2 import OperationalError, InterfaceError

log = logging.getLogger("muichiro.database")

DATABASE_URL = (
    os.getenv("NEON_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
)
USE_POSTGRES = bool(DATABASE_URL)
DB_CONNECT_TIMEOUT = max(3, int(os.getenv("DB_CONNECT_TIMEOUT", "10")))
DB_RECONNECT_ATTEMPTS = max(1, int(os.getenv("DB_RECONNECT_ATTEMPTS", "3")))
DB_RECONNECT_DELAY = max(1, float(os.getenv("DB_RECONNECT_DELAY", "2")))

_connection_lock = threading.RLock()
_connection: Any = None
_connection_generation = 0
_last_error: str | None = None


class DatabaseUnavailable(RuntimeError):
    """Raised when the primary database cannot be reached safely."""


def _connect():
    global _connection, _connection_generation, _last_error
    if not DATABASE_URL:
        raise DatabaseUnavailable(
            "NEON_DATABASE_URL (or DATABASE_URL) is not configured."
        )

    last_exc = None
    with _connection_lock:
        for attempt in range(1, DB_RECONNECT_ATTEMPTS + 1):
            try:
                conn = psycopg2.connect(
                    DATABASE_URL,
                    connect_timeout=DB_CONNECT_TIMEOUT,
                    sslmode=os.getenv("DB_SSLMODE", "require"),
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=3,
                    application_name="MuichiroBot",
                )
                conn.autocommit = False
                old = _connection
                _connection = conn
                _connection_generation += 1
                _last_error = None
                if old is not None:
                    try:
                        old.close()
                    except Exception:
                        pass
                log.info("Neon PostgreSQL connection established (generation %s).", _connection_generation)
                return conn
            except Exception as exc:
                last_exc = exc
                _last_error = f"{type(exc).__name__}: {exc}"
                log.warning(
                    "PostgreSQL connection attempt %s/%s failed: %s",
                    attempt, DB_RECONNECT_ATTEMPTS, _last_error,
                )
                if attempt < DB_RECONNECT_ATTEMPTS:
                    time.sleep(DB_RECONNECT_DELAY * attempt)

    raise DatabaseUnavailable(
        f"Neon PostgreSQL is unavailable after {DB_RECONNECT_ATTEMPTS} attempts: {last_exc}"
    ) from last_exc


def _get_connection():
    global _connection
    with _connection_lock:
        if _connection is None or getattr(_connection, "closed", 1):
            return _connect()
        return _connection


def reconnect() -> bool:
    """Reconnect for subsequent operations; never replays the failed statement."""
    try:
        _connect()
        return True
    except DatabaseUnavailable:
        return False


def health_check() -> bool:
    """Perform a lightweight database ping."""
    try:
        conn = _get_connection()
        with conn.cursor() as check_cursor:
            check_cursor.execute("SELECT 1")
            check_cursor.fetchone()
        return True
    except Exception as exc:
        log.warning("Database health check failed: %s", exc)
        reconnect()
        return False


def get_status() -> dict[str, Any]:
    conn = _connection
    return {
        "backend": "postgresql" if USE_POSTGRES else "unconfigured",
        "connected": bool(conn is not None and not getattr(conn, "closed", 1)),
        "generation": _connection_generation,
        "last_error": _last_error,
    }


class _CursorProxy:
    """Keep existing `from database import cursor` call sites compatible."""
    def __init__(self):
        self._cursor = None
        self._generation = -1

    def _current(self):
        global _connection_generation
        conn = _get_connection()
        if self._cursor is None or self._generation != _connection_generation:
            try:
                if self._cursor is not None:
                    self._cursor.close()
            except Exception:
                pass
            self._cursor = conn.cursor()
            self._generation = _connection_generation
        return self._cursor

    def execute(self, query, params=None):
        cur = self._current()
        try:
            if params is None:
                return cur.execute(query)
            return cur.execute(query, params)
        except (OperationalError, InterfaceError) as exc:
            # SELECT is safe to retry once after reconnecting. Writes are never
            # replayed because their execution/commit status may be uncertain.
            log.error("Database statement failed; reconnecting: %s", exc)
            if not reconnect():
                raise DatabaseUnavailable(
                    "Database connection was lost and reconnection failed."
                ) from exc
            is_read_only = str(query).lstrip().upper().startswith("SELECT")
            if is_read_only:
                self._cursor = None
                retry_cursor = self._current()
                try:
                    if params is None:
                        return retry_cursor.execute(query)
                    return retry_cursor.execute(query, params)
                except (OperationalError, InterfaceError) as retry_exc:
                    reconnect()
                    raise DatabaseUnavailable(
                        "Database read failed after one safe retry."
                    ) from retry_exc
            raise DatabaseUnavailable(
                "Database connection was lost during a write. The write was not replayed; "
                "check its result before attempting it again."
            ) from exc

    def executemany(self, query, params):
        cur = self._current()
        try:
            return cur.executemany(query, params)
        except (OperationalError, InterfaceError) as exc:
            log.error("Database batch failed; reconnecting for next operation: %s", exc)
            reconnect()
            raise DatabaseUnavailable(
                "Database connection was lost during a batch. The batch was not replayed."
            ) from exc

    def __getattr__(self, name):
        return getattr(self._current(), name)


class _ConnectionProxy:
    """Compatibility proxy for existing `db.commit()/rollback()` calls."""
    def cursor(self, *args, **kwargs):
        return _get_connection().cursor(*args, **kwargs)

    def commit(self):
        try:
            _get_connection().commit()
        except (OperationalError, InterfaceError) as exc:
            log.error("Database commit failed; reconnecting without replay: %s", exc)
            reconnect()
            raise DatabaseUnavailable(
                "Commit status is unknown because the connection was lost. "
                "Do not blindly repeat the write."
            ) from exc

    def rollback(self):
        try:
            _get_connection().rollback()
        except (OperationalError, InterfaceError):
            reconnect()

    def close(self):
        if _connection is not None:
            _connection.close()

    @property
    def closed(self):
        return getattr(_connection, "closed", 1) if _connection is not None else 1

    def __getattr__(self, name):
        return getattr(_get_connection(), name)


# Establish the primary connection at startup.  We deliberately do not silently
# switch to a local SQLite file: Render's filesystem is ephemeral unless a
# persistent disk is explicitly configured, and that could split user data.
_connect()
db = _ConnectionProxy()
cursor = _CursorProxy()


# ==========================================
# CORE TABLES
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS members(
    user_id BIGINT,
    chat_id BIGINT,
    username TEXT,
    full_name TEXT,
    PRIMARY KEY(user_id, chat_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS welcome_settings(
    chat_id BIGINT PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    text TEXT,
    file_id TEXT,
    media_type TEXT DEFAULT 'text'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS music_provider_settings(
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider TEXT NOT NULL DEFAULT 'hep',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
cursor.execute("""
INSERT INTO music_provider_settings (id, provider)
VALUES (1, 'hep')
ON CONFLICT (id) DO NOTHING
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_users(
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_chats(
    chat_id BIGINT PRIMARY KEY,
    title TEXT,
    chat_type TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_groups(
    chat_id BIGINT PRIMARY KEY,
    title TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS chat_memory(
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_mood_memory(
    user_id BIGINT PRIMARY KEY,
    mood TEXT DEFAULT 'calm',
    personality TEXT DEFAULT 'normal',
    interests TEXT,
    preferences TEXT,
    notes TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_personality(
    id INTEGER PRIMARY KEY,
    personality TEXT DEFAULT 'normal',
    mood TEXT DEFAULT 'calm',
    CONSTRAINT bot_personality_single_row CHECK (id = 1)
)
""")

cursor.execute("""
INSERT INTO bot_personality (id, personality, mood)
VALUES (1, 'normal', 'calm')
ON CONFLICT (id) DO NOTHING
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_group_activity(
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    username TEXT,
    full_name TEXT,
    activity_date TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    UNIQUE(chat_id, user_id, activity_date)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS mystery_member(
    chat_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username TEXT,
    full_name TEXT,
    mystery_date DATE NOT NULL
)
""")

db.commit()
log.info("Muichiro core database tables are ready.")
