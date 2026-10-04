"""Cookie-free yt-dlp backend for Muichiro Music.

Important:
- No browser cookies.
- No cookie files.
- No login/session credentials.
- No attempt to bypass YouTube anti-bot or identity checks.

The downloader keeps extraction/download off the Telegram event loop and turns
YouTube's common anti-bot rejection into a clean, identifiable exception so
handlers can show a short user-facing error instead of a huge traceback.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

import yt_dlp

log = logging.getLogger(__name__)


class YouTubeAccessError(RuntimeError):
    """YouTube refused the request because an access/verification check failed."""


_YOUTUBE_BLOCK_PATTERNS = (
    "sign in to confirm you're not a bot",
    "sign in to confirm you’re not a bot",
    "confirm you're not a bot",
    "confirm you’re not a bot",
    "use --cookies-from-browser",
    "use --cookies for the authentication",
)


def _is_youtube_access_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(pattern in text for pattern in _YOUTUBE_BLOCK_PATTERNS)


def _base_opts() -> dict[str, Any]:
    """Common yt-dlp settings. Deliberately cookie-free."""
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        # Explicitly disable cookies/browser authentication.
        "cookiefile": None,

        "cachedir": False,
        "retries": 2,
        "fragment_retries": 2,
        "file_access_retries": 2,
        "socket_timeout": 15,
        "concurrent_fragment_downloads": 4,

        # Keep normal HTTP behaviour; this is NOT intended to bypass
        # YouTube verification.
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
        },
    }


def _normalise_info(info: dict[str, Any]) -> dict[str, Any]:
    """Convert yt-dlp's result into the structure expected by handlers."""
    if info.get("_type") == "playlist":
        entries = [entry for entry in (info.get("entries") or []) if entry]
        info = entries[0] if entries else info

    title = info.get("title") or "Unknown Track"
    artist = (
        info.get("artist")
        or info.get("uploader")
        or info.get("channel")
        or "Unknown Artist"
    )

    duration = info.get("duration")
    try:
        duration = int(duration) if duration else None
    except (TypeError, ValueError):
        duration = None

    return {
        "id": info.get("id"),
        "title": title,
        "artist": artist,
        "webpage_url": (
            info.get("webpage_url")
            or info.get("original_url")
            or info.get("url")
        ),
        "thumbnail": info.get("thumbnail"),
        "duration": duration,
        "stream_url": info.get("url"),
    }


def _extract_sync(query: str) -> dict[str, Any]:
    target = query.strip()
    if not target:
        raise ValueError("Empty music query")

    # Search is intentionally limited to one result.
    if not target.startswith(("http://", "https://")):
        target = f"ytsearch1:{target}"

    opts = _base_opts()
    opts.update(
        {
            "skip_download": True,
            "extract_flat": False,
        }
    )

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)

        if not info:
            raise RuntimeError("yt-dlp returned no result")

        return _normalise_info(info)

    except yt_dlp.utils.DownloadError as exc:
        if _is_youtube_access_error(exc):
            raise YouTubeAccessError(
                "YouTube rejected this request with an anti-bot/verification check."
            ) from exc
        raise


async def resolve(query: str) -> dict[str, Any]:
    """Resolve a search query or URL without blocking the event loop."""
    return await asyncio.to_thread(_extract_sync, query)


def _download_sync(info: dict[str, Any]) -> str:
    source = (
        info.get("webpage_url")
        or info.get("original_url")
        or info.get("query")
    )

    if not source:
        raise RuntimeError("No downloadable source URL was resolved")

    root = Path(tempfile.mkdtemp(prefix="muichiro_ytdlp_"))
    outtmpl = str(root / "track.%(ext)s")

    opts = _base_opts()
    opts.update(
        {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": outtmpl,
            "paths": {"home": str(root)},
            "prefer_ffmpeg": True,
            "keepvideo": False,
        }
    )

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([source])

        candidates = [
            p
            for p in root.iterdir()
            if p.is_file() and p.stat().st_size > 1024
        ]

        if not candidates:
            raise RuntimeError(
                "yt-dlp finished without producing an audio file"
            )

        return str(max(candidates, key=lambda p: p.stat().st_size))

    except yt_dlp.utils.DownloadError as exc:
        if _is_youtube_access_error(exc):
            raise YouTubeAccessError(
                "YouTube rejected the audio request with an anti-bot/verification check."
            ) from exc
        raise

    except Exception:
        raise

    finally:
        # Keep the downloaded file alive. cleanup_media() removes it after use.
        pass


async def download_audio(info: dict[str, Any]) -> str:
    """Download the resolved track without blocking the event loop."""
    return await asyncio.to_thread(_download_sync, info)


def cleanup_media(path: str | None) -> None:
    """Remove a temporary downloaded audio file."""
    if not path:
        return

    p = Path(path)

    try:
        if p.exists():
            p.unlink()

        parent = p.parent

        if parent.name.startswith("muichiro_ytdlp_"):
            try:
                parent.rmdir()
            except OSError:
                pass

    except OSError:
        pass


def is_youtube_access_error(exc: BaseException) -> bool:
    """Public helper for handlers that want a friendly Telegram message."""
    return isinstance(exc, YouTubeAccessError) or _is_youtube_access_error(exc)
