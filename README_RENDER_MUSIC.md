# Muichiro All-in-One — Music + Render setup

This version keeps the existing `python-telegram-bot` application and adds the
music/VC system from the MuichiroXMusic project without introducing aiogram.

## Music features

- `/play <song name or YouTube URL>`
- AUDIO / VC selection
- Per-group queue
- Concurrent `/play` requests are queued
- Automatic next-track playback
- `/queue`
- `/now`
- `/skip`
- `/pause`
- `/resume`
- `/stop`
- Inline player buttons
- YouTube thumbnail on Now Playing
- Local temporary audio files for VC playback
- yt-dlp with EJS + Deno support (no cookies or browser sessions)
- Pyrogram user session + PyTgCalls for Telegram voice chats

## Does it need a virtual environment?

### Local computer
A virtual environment is recommended, but not strictly required.

Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Then create `.env` from `.env.example` and fill in the required values.

### Render
No, you do **not** create or upload a virtual environment to Render.
Render creates the Python runtime for the service and installs the packages
from `requirements.txt`. The project pins Python to 3.13.5 using
`.python-version`.

Render's native runtime already includes FFmpeg, which the music playback
layer needs.

## Render Web Service

Use a Render **Web Service with Docker runtime** so Render builds the included
`Dockerfile`. The image installs FFmpeg, Deno, and the `unzip` dependency required
by the Deno installer. The included `render.yaml` points to this Dockerfile.

No commands need to be typed into Render's shell. Push the changed files to the
connected GitHub branch and redeploy. If an existing service was created as a
native Python service, changing `render.yaml` alone may not change that service's
runtime; check the service's Runtime setting and use Docker for this build.

### Required environment variables

```text
BOT_TOKEN
GROQ_API_KEY
DATABASE_URL
API_KEY
API_ID
API_HASH
SESSION_STRING
WEBHOOK_URL
WEBHOOK_SECRET
```

Set `WEBHOOK_URL` to the public URL of the Render service, for example:

```text
https://your-service-name.onrender.com
```

The code also accepts Render's `RENDER_EXTERNAL_URL` automatically if
`WEBHOOK_URL` is not set.

## Important for VC playback

The bot account and the music assistant are different Telegram clients:

1. `python-telegram-bot` handles normal bot updates.
2. Pyrogram uses `SESSION_STRING` for the user account that joins voice chats.
3. PyTgCalls streams the prepared audio into the group call.

The music assistant account must be able to join/manage the group's voice chat.

For continuous music playback, use a Render service that stays running.
A service that sleeps/stops will also stop the music process.

## Security

Do not put API keys or session strings into source files or Git.
Use Render Environment Variables.

If a secret was previously hard-coded in an older copy of the project, rotate
that secret and use the new value only as an environment variable.

## Database note

The existing project falls back to `database.db` (SQLite) when `DATABASE_URL`
is not set. Render filesystems are ephemeral, so SQLite data can disappear
after restarts/redeploys. For persistent bot data, provide a PostgreSQL
`DATABASE_URL`.
