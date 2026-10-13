# Muichiro Music — Hep.gg provider

Muichiro uses Hep.gg Music API for music search and MP3 delivery.

## Render environment

Add `HEP_MUSIC_API_KEY` with the key from your Hep.gg Music dashboard. Do not commit the real key to GitHub. The optional `HEP_MUSIC_BASE_URL` defaults to `https://music.jakeypri.me`.

## Commands

- `/play song name` searches the Hep.gg music library and plays the MP3 through the existing PyTgCalls voice layer.
- `/play https://...` sends a supported public media URL to Hep.gg's unified `/media` endpoint.
- `/audio song name` sends the resolved MP3 to Telegram.
- `/queue`, `/now`, `/skip`, `/pause`, `/resume`, and `/stop` retain the existing queue and player controls.

Song-name searches use Hep.gg's library search; supported media URLs use the unified downloader. A track may be unavailable if the provider cannot find or fetch it. Hep.gg errors are translated into distinct user-facing replies.

FFmpeg remains installed for seeking/media handling.
