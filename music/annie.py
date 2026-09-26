import os
import tempfile
from urllib.parse import quote

import aiohttp


class AnnieAPI:
    def __init__(self):
        self.base = os.getenv(
            "ANNIE_BASE_URL",
            "https://api.alonexraj.shop",
        ).rstrip("/")
        self.api_key = os.getenv("ANNIE_API_KEY", "").strip()

    def _url(self, query: str, media_type: str = "audio"):
        if not self.api_key:
            raise RuntimeError("ANNIE_API_KEY is not configured")
        return (
            f"{self.base}/download?url={quote(query, safe='')}"
            f"&type={media_type}"
            f"&api_key={quote(self.api_key, safe='')}"
        )

    def audio_url(self, query: str):
        return self._url(query, "audio")

    async def prepare_audio(self, query: str):
        url = self.audio_url(query)
        timeout = aiohttp.ClientTimeout(
            total=600, connect=20, sock_read=120
        )
        headers = {"User-Agent": "MuichiroMusic/2.0"}

        async with aiohttp.ClientSession(
            timeout=timeout, headers=headers
        ) as session:
            async with session.get(
                url, allow_redirects=True
            ) as response:
                response.raise_for_status()
                content_type = (
                    response.headers.get("Content-Type") or ""
                ).lower()

                if "json" in content_type:
                    payload = await response.json(content_type=None)
                    media_url = None
                    if isinstance(payload, dict):
                        for key in (
                            "url",
                            "download_url",
                            "audio_url",
                            "stream_url",
                            "link",
                        ):
                            value = payload.get(key)
                            if isinstance(value, str) and value.startswith(
                                ("http://", "https://")
                            ):
                                media_url = value
                                break

                    if not media_url:
                        raise RuntimeError(
                            "Annie returned JSON without a playable audio URL"
                        )

                    async with session.get(
                        media_url, allow_redirects=True
                    ) as media:
                        media.raise_for_status()
                        return await self._save_response(media)

                return await self._save_response(response)

    @staticmethod
    def _detect_suffix(content_type: str, head: bytes):
        ct = (content_type or "").lower()

        # Prefer the actual file signature over a generic application/octet-stream
        # header.  Some download endpoints return valid M4A/MP3 data with a
        # generic Content-Type, which previously made us save it as .mp3.
        if head.startswith(b"OggS") or "ogg" in ct or "opus" in ct:
            return ".ogg"
        if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
            return ".mp3"
        if head.startswith(b"\x1a\x45\xdf\xa3") or "webm" in ct or "matroska" in ct:
            return ".webm"
        if len(head) >= 12 and head[4:8] == b"ftyp":
            return ".m4a"
        if "m4a" in ct or "mp4" in ct or "audio/mp4" in ct:
            return ".m4a"
        if "webm" in ct:
            return ".webm"
        if "ogg" in ct or "opus" in ct:
            return ".ogg"
        return ".mp3"

    async def _save_response(self, response):
        content_type = (
            response.headers.get("Content-Type") or ""
        ).lower()

        # Read only a tiny prefix first so the final extension matches the
        # actual media container even when the server sends a generic header.
        head = await response.content.read(64)
        if not head:
            raise RuntimeError("Annie returned an empty audio response")

        suffix = self._detect_suffix(content_type, head)

        fd, path = tempfile.mkstemp(
            prefix="muichiro_music_", suffix=suffix
        )
        os.close(fd)

        try:
            with open(path, "wb") as output:
                output.write(head)
                async for chunk in response.content.iter_chunked(1024 * 256):
                    if chunk:
                        output.write(chunk)

            size = os.path.getsize(path)
            if size < 1024:
                raise RuntimeError(
                    f"Annie returned an invalid/empty audio file ({size} bytes)"
                )

            with open(path, "rb") as check:
                probe = check.read(512).lstrip().lower()

            if (
                probe.startswith(b"<html")
                or probe.startswith(b"<!doctype")
                or probe.startswith(b"{\"")
            ):
                raise RuntimeError(
                    "Annie returned an error response instead of audio"
                )

            return path
        except Exception:
            try:
                os.remove(path)
            except OSError:
                pass
            raise


annie = AnnieAPI()
