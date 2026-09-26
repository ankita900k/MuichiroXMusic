import json
import logging
import re
from urllib.parse import quote_plus

import aiohttp

log = logging.getLogger(__name__)


def _video_id(value: str):
    value = value.strip()
    match = re.search(
        r"(?:v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        value,
    )
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    return None


def _direct_metadata(query: str):
    video_id = _video_id(query)
    if not video_id:
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    return {
        "id": video_id,
        "title": query,
        "webpage_url": url,
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "duration": None,
    }


def _extract_search_result(html: str, query: str):
    marker = "var ytInitialData = "
    start = html.find(marker)
    if start < 0:
        marker = "ytInitialData = "
        start = html.find(marker)
    if start < 0:
        return None

    start += len(marker)
    end = html.find(";</script>", start)
    if end < 0:
        end = html.find(";</", start)
    if end < 0:
        return None

    try:
        data = json.loads(html[start:end])
    except Exception:
        return None

    def walk(obj):
        if isinstance(obj, dict):
            renderer = obj.get("videoRenderer")
            if isinstance(renderer, dict) and renderer.get("videoId"):
                yield renderer
            for value in obj.values():
                yield from walk(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from walk(value)

    for item in walk(data):
        vid = item.get("videoId")
        title_runs = (item.get("title") or {}).get("runs") or []
        title = "".join(r.get("text", "") for r in title_runs).strip() or query
        length = (item.get("lengthText") or {}).get("simpleText")
        duration = None
        if length:
            try:
                parts = [int(x) for x in length.split(":")]
                if len(parts) == 2:
                    duration = parts[0] * 60 + parts[1]
                elif len(parts) == 3:
                    duration = parts[0] * 3600 + parts[1] * 60 + parts[2]
            except Exception:
                pass

        return {
            "id": vid,
            "title": title,
            "webpage_url": f"https://www.youtube.com/watch?v={vid}",
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "duration": duration,
        }

    return None


async def resolve(query: str):
    direct = _direct_metadata(query)
    if direct:
        return direct

    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    timeout = aiohttp.ClientTimeout(total=8, connect=3, sock_read=5)
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        async with aiohttp.ClientSession(
            timeout=timeout, headers=headers
        ) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    html = await response.text(errors="ignore")
                    found = _extract_search_result(html, query)
                    if found:
                        return found
    except Exception as exc:
        log.info("YouTube metadata lookup skipped for %r: %s", query, exc)

    return {
        "title": query,
        "webpage_url": query,
        "thumbnail": None,
        "duration": None,
        "id": None,
    }
