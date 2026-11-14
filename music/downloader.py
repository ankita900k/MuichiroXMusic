"""Hep.gg-backed audio provider for Muichiro Music.

Uses Hep.gg's documented Music API. Search-by-name resolves through the Hep.gg
music library; a supported public media URL uses the unified /media endpoint.
Audio is saved as MP3 for both Telegram delivery and PyTgCalls playback.
"""
from __future__ import annotations

import asyncio
import email.message
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import aiohttp

from .annie import annie
from .provider_settings import get_music_provider

log = logging.getLogger(__name__)

HEP_BASE_URL = os.getenv("HEP_MUSIC_BASE_URL", "https://music.jakeypri.me").rstrip("/")
HEP_API_KEY = os.getenv("HEP_MUSIC_API_KEY", "").strip()
CONNECT_TIMEOUT = 15
REQUEST_TIMEOUT = 240


class HepMusicError(RuntimeError):
    """A safe, classified Hep.gg API error."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message or "Hep.gg request failed")
        self.status_code = status_code
        self.provider = "hep.gg"


def _require_key() -> str:
    # Read lazily because bot.py calls load_dotenv() after importing handlers.
    key = (os.getenv("HEP_MUSIC_API_KEY") or HEP_API_KEY).strip()
    if not key:
        raise HepMusicError(0, "HEP_MUSIC_API_KEY is not configured")
    return key


def _base_url() -> str:
    return (os.getenv("HEP_MUSIC_BASE_URL") or HEP_BASE_URL).rstrip("/")


def _headers() -> dict[str, str]:
    return {"X-API-Key": _require_key(), "User-Agent": "MuichiroMusic/1.0"}


def _timeout() -> aiohttp.ClientTimeout:
    return aiohttp.ClientTimeout(total=REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT, sock_read=180)


def _error_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        for key in ("error", "message", "details", "hint"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:400]
        data = payload.get("data")
        if isinstance(data, dict):
            return _error_message(data, fallback)
    return fallback


async def _raise_response_error(response: aiohttp.ClientResponse) -> None:
    body = await response.read()
    message = f"Hep.gg returned HTTP {response.status}"
    if body:
        try:
            import json
            payload = json.loads(body.decode("utf-8", errors="replace"))
            message = _error_message(payload, message)
        except Exception:
            # Do not echo arbitrary upstream HTML or large error bodies to users/logs.
            message = message
    raise HepMusicError(response.status, message)


def _unwrap_search(payload: Any) -> list[dict[str, Any]]:
    """Accept the documented search response and common envelope variants."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("results", "tracks", "items", "matches", "songs"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            found = _unwrap_search(value)
            if found:
                return found

    data = payload.get("data")
    if data is not None:
        found = _unwrap_search(data)
        if found:
            return found

    if any(payload.get(k) for k in ("isrc", "ISRC", "title", "name")):
        return [payload]
    return []


def _candidate_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _duration_seconds(item: dict[str, Any]) -> int | None:
    raw = _candidate_value(item, "duration", "duration_seconds", "length")
    if raw is None:
        raw = item.get("duration_ms")
        if raw is not None:
            try:
                return max(1, int(float(raw) / 1000))
            except (TypeError, ValueError):
                return None
    try:
        if isinstance(raw, str) and ":" in raw:
            parts = [int(part) for part in raw.strip().split(":")]
            if 2 <= len(parts) <= 3 and all(part >= 0 for part in parts):
                value = parts[-1] + 60 * parts[-2]
                if len(parts) == 3:
                    value += 3600 * parts[0]
                return value if value > 0 else None
        value = int(float(raw))
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _content_filename(response: aiohttp.ClientResponse) -> str | None:
    disposition = response.headers.get("Content-Disposition", "")
    if not disposition:
        return None
    try:
        msg = email.message.Message()
        msg["content-disposition"] = disposition
        filename = msg.get_filename()
        return unquote(filename) if filename else None
    except Exception:
        match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)', disposition, re.I)
        return unquote(match.group(1)) if match else None


def _metadata_from_response(response: aiohttp.ClientResponse, fallback: str) -> tuple[str, str, int | None, str | None, str | None]:
    title = response.headers.get("x-track-title") or ""
    artist = response.headers.get("x-track-artist") or "Unknown Artist"
    duration = response.headers.get("x-track-duration")
    try:
        duration_value = int(float(duration)) if duration else None
    except (TypeError, ValueError):
        duration_value = None

    filename = _content_filename(response)
    if not title and filename:
        stem = Path(filename).stem.strip()
        title = stem or fallback
        if " - " in stem:
            possible_artist, possible_title = stem.split(" - ", 1)
            if possible_artist.strip() and possible_title.strip():
                artist, title = possible_artist.strip(), possible_title.strip()
    if not title:
        title = fallback
    album = response.headers.get("x-track-album") or None
    artwork = response.headers.get("x-track-artwork") or None
    return title, artist, duration_value, album, artwork


def _probe_duration(path: Path) -> int | None:
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, timeout=12, check=True)
        value = float(result.stdout.strip())
        return max(1, int(round(value))) if value > 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _ensure_mp3(path: Path) -> Path:
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, timeout=12, check=True)
        if result.stdout.strip().lower() == "mp3":
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    converted = path.with_name("track-converted.mp3")
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-vn", "-codec:a", "libmp3lame", "-q:a", "2", str(converted)], capture_output=True, timeout=180, check=True)
        if not converted.is_file() or converted.stat().st_size < 1024:
            raise RuntimeError("FFmpeg produced an empty MP3")
        path.unlink(missing_ok=True)
        return converted
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        converted.unlink(missing_ok=True)
        raise HepMusicError(500, "Hep.gg response could not be converted to MP3") from exc


async def _download_binary(endpoint: str, params: dict[str, str], fallback_title: str) -> dict[str, Any]:
    headers = _headers()
    root = Path(tempfile.mkdtemp(prefix="muichiro_hep_"))
    output = root / "track.mp3"
    try:
        timeout = _timeout()
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(f"{_base_url()}{endpoint}", params=params) as response:
                if response.status != 200:
                    await _raise_response_error(response)
                content_type = response.headers.get("Content-Type", "").lower()
                if "json" in content_type or "text/html" in content_type or "video/" in content_type:
                    body = await response.read()
                    try:
                        import json
                        payload = json.loads(body.decode("utf-8", errors="replace"))
                    except Exception:
                        payload = {}
                    raise HepMusicError(response.status, _error_message(payload, "Hep.gg did not return an MP3 audio file"))
                title, artist, duration, album, artwork = _metadata_from_response(response, fallback_title)
                written = 0
                with output.open("wb") as file:
                    async for chunk in response.content.iter_chunked(256 * 1024):
                        if chunk:
                            file.write(chunk)
                            written += len(chunk)
                if written < 1024:
                    raise HepMusicError(500, "Hep.gg returned an empty or incomplete audio file")
        output = await asyncio.to_thread(_ensure_mp3, output)
        if not duration:
            duration = await asyncio.to_thread(_probe_duration, output)
        return {
            "media_path": str(output),
            "title": title,
            "artist": artist,
            "duration": duration,
            "album": album,
            "thumbnail": artwork,
            "provider": "hep_media" if endpoint == "/media" else "hep_library",
        }
    except HepMusicError:
        _remove_tree(root)
        raise
    except asyncio.TimeoutError as exc:
        _remove_tree(root)
        raise HepMusicError(0, "Hep.gg media request timed out") from exc
    except aiohttp.ClientError as exc:
        _remove_tree(root)
        raise HepMusicError(0, f"Hep.gg network request failed: {type(exc).__name__}") from exc
    except Exception:
        _remove_tree(root)
        raise


def _remove_tree(root: Path) -> None:
    try:
        for item in root.iterdir():
            if item.is_file():
                item.unlink(missing_ok=True)
        root.rmdir()
    except OSError:
        pass


async def _search_library(query: str) -> dict[str, Any]:
    headers = _headers()
    timeout = aiohttp.ClientTimeout(total=35, connect=CONNECT_TIMEOUT, sock_read=25)
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(f"{_base_url()}/search", params={"q": query}) as response:
                if response.status != 200:
                    await _raise_response_error(response)
                try:
                    payload = await response.json(content_type=None)
                except Exception as exc:
                    raise HepMusicError(response.status, "Hep.gg returned an unreadable search response") from exc
    except HepMusicError:
        raise
    except asyncio.TimeoutError as exc:
        raise HepMusicError(0, "Hep.gg search timed out") from exc
    except aiohttp.ClientError as exc:
        raise HepMusicError(0, f"Hep.gg network request failed: {type(exc).__name__}") from exc

    results = _unwrap_search(payload)
    if not results:
        raise HepMusicError(404, "No matching track was found in the Hep.gg music library")

    item = results[0]
    isrc = str(_candidate_value(item, "isrc", "ISRC", "isrc_code") or "").strip().upper()
    title = str(_candidate_value(item, "title", "name", "track_name") or query).strip()
    artist_value = _candidate_value(item, "artist", "artists", "artist_name", "performer")
    if isinstance(artist_value, list):
        artist_value = ", ".join(str(x.get("name", x)) if isinstance(x, dict) else str(x) for x in artist_value)
    artist = str(artist_value or "Unknown Artist").strip()
    if not re.fullmatch(r"[A-Z0-9]{12}", isrc):
        # A URL in a search result can still be handed to the unified media endpoint.
        url = _candidate_value(item, "url", "webpage_url", "link")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            media = await _download_binary("/media", {"url": url, "format": "audio"}, title)
            return {**media, "id": None, "webpage_url": url, "thumbnail": None, "query": query}
        raise HepMusicError(404, "Hep.gg search returned no downloadable track identifier")

    thumbnail = _candidate_value(item, "thumbnail", "artwork", "cover", "image", "cover_url")
    if isinstance(thumbnail, dict):
        thumbnail = _candidate_value(thumbnail, "url", "src")
    if not thumbnail:
        thumbnail = f"{_base_url()}/artwork/{isrc}"

    album = _candidate_value(item, "album", "album_name", "release")
    return {
        "id": isrc,
        "isrc": isrc,
        "provider": "hep_library",
        "title": title,
        "artist": artist,
        "album": str(album).strip() if album else None,
        "webpage_url": f"hep-library://{isrc}",
        "thumbnail": str(thumbnail) if thumbnail else None,
        "duration": _duration_seconds(item),
        "stream_url": None,
        "query": query,
    }


async def _resolve_with_annie(target: str) -> dict[str, Any]:
    """Download through Annie; its published API does not document a metadata/search endpoint."""
    path = await annie.prepare_audio(target)
    raw = getattr(annie, "last_metadata", {}) or {}
    def pick(*keys):
        for key in keys:
            value = raw.get(key)
            if value not in (None, ""):
                return value
        return None
    title = str(pick("title", "name", "track_title") or target)
    artist = str(pick("artist", "performer", "uploader") or "Unknown Artist")
    duration = _duration_seconds(raw) if isinstance(raw, dict) else None
    album = pick("album", "collection")
    thumbnail = pick("thumbnail", "thumbnail_url", "cover", "cover_url")
    try:
        def probe():
            completed = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", path],
                capture_output=True, text=True, timeout=15, check=True,
            )
            import json
            return json.loads(completed.stdout or "{}")
        data = await asyncio.to_thread(probe)
        fmt = data.get("format") or {}
        try:
            duration = max(1, int(float(fmt.get("duration") or 0)))
        except (TypeError, ValueError):
            duration = None
        tags = {str(k).lower(): str(v) for k, v in (fmt.get("tags") or {}).items()}
        title = tags.get("title") or title
        artist = tags.get("artist") or tags.get("album_artist") or artist
        album = tags.get("album")
    except Exception:
        log.debug("Annie media metadata probe unavailable", exc_info=True)
    return {
        "title": title, "artist": artist, "duration": duration,
        "album": album, "thumbnail": thumbnail, "media_path": path,
        "provider": "annie", "webpage_url": target, "query": target,
        "id": None, "isrc": None, "stream_url": None,
    }


async def resolve(query: str) -> dict[str, Any]:
    target = query.strip()
    if not target:
        raise ValueError("Empty music query")
    provider = get_music_provider()
    if provider == "annie":
        return await _resolve_with_annie(target)
    if target.startswith(("http://", "https://")):
        media = await _download_binary("/media", {"url": target, "format": "audio"}, "Requested track")
        return {
            **media,
            "id": None,
            "isrc": None,
            "webpage_url": target,
            "thumbnail": media.get("thumbnail"),
            "stream_url": None,
            "query": target,
        }
    return await _search_library(target)


async def download_audio(info: dict[str, Any]) -> str:
    existing = info.get("media_path")
    if existing and Path(existing).is_file():
        return str(existing)

    provider = info.get("provider") or "hep_library"
    if provider == "annie":
        path = await annie.prepare_audio(str(info.get("query") or info.get("webpage_url") or ""))
        info["media_path"] = path
        return path
    if provider == "hep_media":
        url = info.get("webpage_url") or info.get("source_url") or info.get("query")
        if not url:
            raise HepMusicError(400, "No media URL was provided")
        result = await _download_binary("/media", {"url": str(url), "format": "audio"}, str(info.get("title") or "Requested track"))
    else:
        isrc = str(info.get("isrc") or info.get("id") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{12}", isrc):
            raise HepMusicError(404, "Hep.gg track identifier is missing or invalid")
        result = await _download_binary("/download", {"isrc": isrc, "quality": "320"}, str(info.get("title") or "Requested track"))

    path = result.get("media_path")
    if not path:
        raise HepMusicError(500, "Hep.gg did not prepare an audio file")
    # The Track object is updated by the caller if API metadata was richer.
    previous_thumbnail = info.get("thumbnail")
    previous_album = info.get("album")
    info.update(result)
    if not info.get("thumbnail"):
        info["thumbnail"] = previous_thumbnail
    if not info.get("album"):
        info["album"] = previous_album
    return str(path)


def cleanup_media(path: str | None) -> None:
    if not path:
        return
    p = Path(path)
    try:
        if p.exists():
            p.unlink()
        parent = p.parent
        if parent.name.startswith(("muichiro_hep_", "muichiro_seek_")):
            try:
                parent.rmdir()
            except OSError:
                pass
    except OSError:
        pass
