"""Fast, cookie-free yt-dlp backend for Muichiro Music.

No browser cookies, cookie files, login sessions, or account credentials are
read by this module. yt-dlp runs in worker threads so the Telegram event loop
never blocks while extracting or downloading media.
"""
import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yt_dlp

log = logging.getLogger(__name__)

# These diagnostics appear in Render logs so deployment/runtime problems can be
# spotted without opening a shell or typing commands in the Render dashboard.
try:
    from yt_dlp.version import __version__ as _YTDLP_VERSION
except Exception:
    _YTDLP_VERSION = "unknown"
log.info("Muichiro music downloader: yt-dlp=%s, Deno=%s", _YTDLP_VERSION, shutil.which("deno") or "not found")


def _base_opts() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "cookiefile": None,
        "cachedir": False,
        # yt-dlp EJS: enable a supported JavaScript runtime for YouTube
        # challenge solving. No browser cookies or account sessions are read.
        "js_runtimes": {"deno": {}},
        "retries": 2,
        "fragment_retries": 2,
        "file_access_retries": 2,
        "socket_timeout": 15,
        "concurrent_fragment_downloads": 4,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        },
    }


def _normalise_info(ydl: yt_dlp.YoutubeDL, info: dict[str, Any]) -> dict[str, Any]:
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        info = entries[0] if entries else info

    title = info.get("title") or "Unknown Track"
    artist = info.get("artist") or info.get("uploader") or info.get("channel") or "Unknown Artist"
    duration = info.get("duration")
    try:
        duration = int(duration) if duration else None
    except (TypeError, ValueError):
        duration = None

    return {
        "id": info.get("id"),
        "title": title,
        "artist": artist,
        "webpage_url": info.get("webpage_url") or info.get("original_url") or info.get("url"),
        "thumbnail": info.get("thumbnail"),
        "duration": duration,
        "stream_url": info.get("url"),
    }


def _extract_sync(query: str) -> dict[str, Any]:
    target = query.strip()
    if not target:
        raise ValueError("Empty music query")
    if not target.startswith(("http://", "https://")):
        target = f"ytsearch1:{target}"

    opts = _base_opts()
    opts.update({
        "skip_download": True,
        "extract_flat": False,
    })
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target, download=False)
        if not info:
            raise RuntimeError("yt-dlp returned no result")
        return _normalise_info(ydl, info)


async def resolve(query: str) -> dict[str, Any]:
    return await asyncio.to_thread(_extract_sync, query)


def _download_sync(info: dict[str, Any]) -> str:
    source = info.get("webpage_url") or info.get("original_url") or info.get("query")
    if not source:
        raise RuntimeError("No downloadable source URL was resolved")

    root = Path(tempfile.mkdtemp(prefix="muichiro_ytdlp_"))
    outtmpl = str(root / "track.%(ext)s")
    opts = _base_opts()
    opts.update({
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": outtmpl,
        "paths": {"home": str(root)},
        "prefer_ffmpeg": True,
        "keepvideo": False,
    })

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([source])
        candidates = [p for p in root.iterdir() if p.is_file() and p.stat().st_size > 1024]
        if not candidates:
            raise RuntimeError("yt-dlp finished without producing an audio file")
        return str(max(candidates, key=lambda p: p.stat().st_size))
    except Exception:
        for p in root.glob("*"):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            root.rmdir()
        except OSError:
            pass
        raise


async def download_audio(info: dict[str, Any]) -> str:
    return await asyncio.to_thread(_download_sync, info)


def cleanup_media(path: str | None):
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
