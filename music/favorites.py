"""Persistent per-user favourite songs for Muichiro Music."""
from __future__ import annotations

import threading
from typing import Any

from database import db, cursor, USE_POSTGRES

_DB_LOCK = threading.RLock()

if USE_POSTGRES:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS music_favorites (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            source_key TEXT NOT NULL,
            title TEXT NOT NULL,
            artist TEXT,
            source_url TEXT NOT NULL,
            thumbnail TEXT,
            duration INTEGER,
            provider TEXT,
            isrc TEXT,
            album TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, source_key)
        )
    """)
else:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS music_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_key TEXT NOT NULL,
            title TEXT NOT NULL,
            artist TEXT,
            source_url TEXT NOT NULL,
            thumbnail TEXT,
            duration INTEGER,
            provider TEXT,
            isrc TEXT,
            album TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, source_key)
        )
    """)
db.commit()

_FIELDS = ("id", "user_id", "source_key", "title", "artist", "source_url", "thumbnail", "duration", "provider", "isrc", "album", "added_at")

def _row_dict(row) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    return dict(zip(_FIELDS, row))

def _source_key(track) -> str:
    isrc = (getattr(track, "isrc", None) or "").strip().upper()
    if isrc:
        return f"isrc:{isrc}"
    source = (getattr(track, "source_url", None) or getattr(track, "query", "")).strip()
    provider = (getattr(track, "provider", None) or "hep_media").strip()
    return f"{provider}:{source}"

MAX_FAVORITES_PER_USER = 10

def add_favorite(user_id: int, track) -> tuple[bool, int]:
    """Save up to 10 unique tracks per user; position -1 means the limit was reached."""
    key = _source_key(track)
    values = (
        int(user_id), key, str(track.title or "Unknown Track"),
        str(track.artist or "Unknown Artist"), str(track.source_url or track.query),
        track.thumbnail, track.duration, track.provider, track.isrc, track.album,
    )
    with _DB_LOCK:
        cursor.execute("SELECT id FROM music_favorites WHERE user_id = %s AND source_key = %s" if USE_POSTGRES else "SELECT id FROM music_favorites WHERE user_id = ? AND source_key = ?", (int(user_id), key))
        existing = cursor.fetchone()
        if not existing:
            count_sql = "SELECT COUNT(*) FROM music_favorites WHERE user_id = %s" if USE_POSTGRES else "SELECT COUNT(*) FROM music_favorites WHERE user_id = ?"
            cursor.execute(count_sql, (int(user_id),))
            if int(cursor.fetchone()[0]) >= MAX_FAVORITES_PER_USER:
                return False, -1
            sql = (
                "INSERT INTO music_favorites (user_id, source_key, title, artist, source_url, thumbnail, duration, provider, isrc, album) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                if USE_POSTGRES else
                "INSERT INTO music_favorites (user_id, source_key, title, artist, source_url, thumbnail, duration, provider, isrc, album) VALUES (?,?,?,?,?,?,?,?,?,?)"
            )
            cursor.execute(sql, values)
            db.commit()
        cursor.execute("SELECT id FROM music_favorites WHERE user_id = %s AND source_key = %s" if USE_POSTGRES else "SELECT id FROM music_favorites WHERE user_id = ? AND source_key = ?", (int(user_id), key))
        row = cursor.fetchone()
        fav_id = row[0] if row else None
        cursor.execute("SELECT COUNT(*) FROM music_favorites WHERE user_id = %s AND id <= %s" if USE_POSTGRES else "SELECT COUNT(*) FROM music_favorites WHERE user_id = ? AND id <= ?", (int(user_id), fav_id))
        position = int(cursor.fetchone()[0]) if fav_id is not None else 0
        return existing is None, position

def list_favorites(user_id: int, limit: int | None = None) -> list[dict[str, Any]]:
    sql = "SELECT id, user_id, source_key, title, artist, source_url, thumbnail, duration, provider, isrc, album, added_at FROM music_favorites WHERE user_id = %s ORDER BY id ASC" if USE_POSTGRES else "SELECT id, user_id, source_key, title, artist, source_url, thumbnail, duration, provider, isrc, album, added_at FROM music_favorites WHERE user_id = ? ORDER BY id ASC"
    params: tuple[Any, ...] = (int(user_id),)
    if limit is not None:
        sql += " LIMIT %s" if USE_POSTGRES else " LIMIT ?"
        params += (int(limit),)
    with _DB_LOCK:
        cursor.execute(sql, params)
        return [_row_dict(row) for row in cursor.fetchall()]
