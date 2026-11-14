import os
import tempfile
from urllib.parse import quote

import aiohttp


class AnnieAPIError(RuntimeError):
    def __init__(self, status_code: int, retry_after: int | None = None):
        self.status_code = int(status_code)
        self.retry_after = retry_after
        message = f"Annie API returned HTTP {self.status_code}"
        if self.status_code == 429 and retry_after:
            message += f"; retry after {retry_after} seconds"
        super().__init__(message)


class AnnieAPI:
    def __init__(self):
        self.base = os.getenv(
            "ANNIE_BASE_URL",
            "https://api.alonexraj.shop",
        ).rstrip("/")
        self.api_key = os.getenv("ANNIE_API_KEY", "").strip()
        self.last_metadata = {}

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
            total=300, connect=15, sock_read=60
        )
        headers = {"User-Agent": "MuichiroMusic/2.0"}

        async with aiohttp.ClientSession(
            timeout=timeout, headers=headers
        ) as session:
            async with session.get(
                url, allow_redirects=True
            ) as response:
                if response.status >= 400:
                    retry = response.headers.get("Retry-After")
                    try:
                        retry = int(retry) if retry else None
                    except (TypeError, ValueError):
                        retry = None
                    raise AnnieAPIError(response.status, retry)
                content_type = (
                    response.headers.get("Content-Type") or ""
                ).lower()

                if "json" in content_type:
                    payload = await response.json(content_type=None)
                    self.last_metadata = payload if isinstance(payload, dict) else {}
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
                        if media.status >= 400:
                            retry = media.headers.get("Retry-After")
                            try:
                                retry = int(retry) if retry else None
                            except (TypeError, ValueError):
                                retry = None
                            raise AnnieAPIError(media.status, retry)
                        return await self._save_response(media)

                self.last_metadata = {}
                return await self._save_response(response)

    async def _save_response(self, response):
        content_type = (
            response.headers.get("Content-Type") or ""
        ).lower()

        suffix = ".mp3"
        if "ogg" in content_type or "opus" in content_type:
            suffix = ".ogg"
        elif "m4a" in content_type or "mp4" in content_type:
            suffix = ".m4a"
        elif "webm" in content_type:
            suffix = ".webm"

        fd, path = tempfile.mkstemp(
            prefix="muichiro_music_", suffix=suffix
        )
        os.close(fd)

        try:
            with open(path, "wb") as output:
                async for chunk in response.content.iter_chunked(
                    1024 * 256
                ):
                    if chunk:
                        output.write(chunk)

            if os.path.getsize(path) == 0:
                raise RuntimeError("Annie returned an empty audio file")

            return path
        except Exception:
            try:
                os.remove(path)
            except OSError:
                pass
            raise


annie = AnnieAPI()
