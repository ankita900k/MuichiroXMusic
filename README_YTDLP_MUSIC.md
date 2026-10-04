# Muichiro Music — yt-dlp backend

The music system now uses yt-dlp instead of the retired Annie API. No cookies, browser profiles, login sessions, or `ANNIE_API_KEY` are used by the downloader.

## Music behavior

- `/play <song>` — download and play in the group voice chat
- `/audio <song>` — send the audio file to Telegram
- `/queue` — show the queue
- `/now` — show current track information without modifying the player card
- `/pause`, `/resume`, `/skip`, `/stop` — admin-only playback commands in groups
- Player buttons — admin-only playback controls
- Normal members can still use `/play` and `/audio`
- Queue additions are kept as normal Telegram messages; the player card itself is not rewritten during playback
- The player card has a live button-based tracker: `elapsed ━━━•━━━ total`
- Tracker updates edit only the inline keyboard, not the player text/caption
- Relative rewind/forward buttons use FFmpeg only when explicitly pressed
- Next queued tracks are preloaded in the background when possible
- Each new track gets its own player card/artwork

## Deployment

FFmpeg is intentionally kept in the Docker image because the player uses it for relative seek operations and media compatibility.
