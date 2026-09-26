import asyncio
import io
import logging
import os
import subprocess
import tempfile
import time
import uuid
from html import escape

import aiohttp
from telegram import InputFile, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from . import runtime
from .annie import annie
from .manager import player_manager
from .metadata import resolve
from .models import Track
from .ui import mode_keyboard, player_keyboard, queue_keyboard

log = logging.getLogger(__name__)
pending: dict[str, tuple[Track, float]] = {}
PENDING_TTL = 15 * 60


def _cleanup_pending():
    cutoff = time.monotonic() - PENDING_TTL
    for token, (_, created) in list(pending.items()):
        if created < cutoff:
            pending.pop(token, None)


async def _download_thumbnail(url: str):
    if not url:
        return None
    raw = None
    try:
        timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=12)
        headers = {"User-Agent": "Mozilla/5.0 MuichiroMusic/2.0"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as response:
                if response.status == 200:
                    raw = await response.read()
        if not raw:
            return None

        # Telegram photo uploads are most reliable with a real JPEG file.
        if raw.startswith(b"\xff\xd8\xff"):
            fd, path = tempfile.mkstemp(prefix="muichiro_thumb_", suffix=".jpg")
            os.close(fd)
            with open(path, "wb") as f: f.write(raw)
            return path

        # Convert PNG/WebP/etc. without adding Pillow to the project.
        fd, src_path = tempfile.mkstemp(prefix="muichiro_thumb_src_")
        os.close(fd)
        fd, jpg_path = tempfile.mkstemp(prefix="muichiro_thumb_", suffix=".jpg")
        os.close(fd)
        with open(src_path, "wb") as f: f.write(raw)
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-loglevel", "error", "-i", src_path,
                "-frames:v", "1", "-vf", "scale=600:600:force_original_aspect_ratio=decrease",
                "-q:v", "3", jpg_path,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            _, err = await proc.communicate()
            if proc.returncode == 0 and os.path.getsize(jpg_path) > 0:
                return jpg_path
            log.warning("Thumbnail conversion failed: %s", err.decode(errors="ignore"))
        finally:
            try: os.remove(src_path)
            except OSError: pass
            if not os.path.exists(jpg_path):
                try: os.remove(jpg_path)
                except OSError: pass
    except Exception as exc:
        log.warning("Thumbnail download failed: %s", exc)
    return None


def _now_text(state):
    track = state.current
    return (
        "🎧 <b>𝗡𝗢𝗪 𝗣𝗟𝗔𝗬𝗜𝗡𝗚</b>\n\n"
        f"🎵 <b>{escape(track.title)}</b>\n"
        f"👤 {escape(track.requested_name)}\n"
        f"📋 Queue: <b>{len(state.queue)}</b>"
    )


async def _send_now_playing(bot, chat_id, state, old_message=None):
    text = _now_text(state)
    keyboard = player_keyboard(state.paused)
    thumb_path = await _download_thumbnail(state.current.thumbnail)
    try:
        # Do NOT edit a text message into a photo. Telegram clients/API can
        # reject that transition, which was why the VC thumbnail disappeared.
        if old_message:
            try: await old_message.delete()
            except Exception: pass

        if thumb_path:
            message = await bot.send_photo(
                chat_id=chat_id,
                photo=thumb_path,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        else:
            message = await bot.send_message(
                chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        state.control_message_id = message.message_id
        return message
    finally:
        if thumb_path:
            try: os.remove(thumb_path)
            except OSError: pass


async def _start_track(chat_id: int, track: Track, replacing=False):
    state = player_manager.get(chat_id)
    previous = state.current
    state.transition = replacing
    if replacing:
        state.ignore_stream_end_until = asyncio.get_running_loop().time() + 6.0
    state.current = track
    state.paused = False
    try:
        if not track.media_path or not os.path.exists(track.media_path):
            track.media_path = await annie.prepare_audio(track.source_url or track.query)
        await runtime.voice.play(chat_id, track.media_path)
    except Exception:
        if track.media_path and track.media_path != getattr(previous, "media_path", None):
            try: os.remove(track.media_path)
            except OSError: pass
            track.media_path = None
        state.current = previous
        state.paused = False if previous is None else state.paused
        raise
    finally:
        state.transition = False
    return state


def _ffprobe_has_audio(path: str) -> bool:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _convert_to_mp3(path: str) -> str:
    fd, out = tempfile.mkstemp(prefix="muichiro_audio_", suffix=".mp3")
    os.close(fd)
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", path, "-vn", "-map", "0:a:0",
             "-c:a", "libmp3lame", "-b:a", "192k", out],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180,
        )
        if result.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1024:
            raise RuntimeError(result.stderr.strip() or "FFmpeg could not create an audio track")
        return out
    except Exception:
        try: os.remove(out)
        except OSError: pass
        raise


async def _send_audio(query, track, update):
    audio_path = None
    normalized = None
    try:
        audio_path = await annie.prepare_audio(track.source_url or query)
        if not audio_path or not os.path.exists(audio_path):
            raise RuntimeError("Annie did not return a valid audio file")
        if os.path.getsize(audio_path) < 1024:
            raise RuntimeError("Annie returned an empty audio file")

        # Telegram gets a known-good MP3 with an actual audio stream. No thumb.
        if not _ffprobe_has_audio(audio_path):
            raise RuntimeError("Downloaded media contains no audio track")
        normalized = await asyncio.to_thread(_convert_to_mp3, audio_path)

        await update.effective_message.reply_audio(
            audio=normalized,
            title=track.title,
            performer=track.artist or "Unknown Artist",
            duration=track.duration if track.duration else None,
        )
    finally:
        for path in (normalized, audio_path):
            if path and path != normalized or (path and path == normalized):
                try: os.remove(path)
                except OSError: pass


async def advance_to_next(chat_id: int, bot=None, old_message=None):
    state = player_manager.get(chat_id)
    old_track = state.current
    next_track = player_manager.pop_next(chat_id)
    if not next_track:
        await runtime.voice.leave(chat_id)
        state.current = None; state.paused = False
        if old_track and old_track.media_path:
            try: os.remove(old_track.media_path)
            except OSError: pass
        return False
    await _start_track(chat_id, next_track, replacing=True)
    if old_track and old_track.media_path and old_track.media_path != next_track.media_path:
        try: os.remove(old_track.media_path)
        except OSError: pass
    if bot:
        await _send_now_playing(bot, chat_id, state, old_message=old_message)
    return True


async def _make_track(update, query):
    info = await resolve(query)
    return Track(
        query=query, title=info.get("title") or query,
        requested_by=update.effective_user.id if update.effective_user else 0,
        requested_name=update.effective_user.full_name if update.effective_user else "Unknown",
        source_url=info.get("webpage_url") or query,
        artist=info.get("artist") or "Unknown Artist", thumbnail=info.get("thumbnail"),
        duration=int(info["duration"]) if info.get("duration") else None,
    )


async def play_command(update, context):
    message = update.effective_message
    if not message: return
    query = " ".join(context.args).strip()
    if not query:
        await message.reply_text("🎙 <b>Usage</b>\n<code>/play song name</code>", parse_mode=ParseMode.HTML); return
    searching = await message.reply_text("🔎 <b>Finding your track for VC…</b>", parse_mode=ParseMode.HTML)
    try:
        track = await _make_track(update, query); chat_id = update.effective_chat.id
        async with player_manager.lock(chat_id):
            state = player_manager.get(chat_id)
            if state.current is not None:
                position = player_manager.enqueue(chat_id, track)
                await searching.edit_text("➕ <b>𝗔𝗗𝗗𝗘𝗗 𝗧𝗢 𝗩𝗖 𝗤𝗨𝗘𝗨𝗘</b>\n\n" f"🎵 <b>{escape(track.title)}</b>\n" f"📍 Position: <b>#{position}</b>\n" f"📋 Waiting: <b>{len(state.queue)}</b>", parse_mode=ParseMode.HTML); return
            await _start_track(chat_id, track)
            await _send_now_playing(context.bot, chat_id, state, old_message=searching)
    except Exception as exc:
        log.exception("VC playback failed")
        try: await searching.edit_text("❌ <b>𝗩𝗖 𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗙𝗔𝗜𝗟𝗘𝗗</b>\n\n" f"<code>{escape(type(exc).__name__ + ': ' + str(exc))}</code>", parse_mode=ParseMode.HTML)
        except Exception: pass


async def audio_command(update, context):
    message = update.effective_message
    if not message: return
    query = " ".join(context.args).strip()
    if not query:
        await message.reply_text("🎧 <b>Usage</b>\n<code>/audio song name</code>", parse_mode=ParseMode.HTML); return
    searching = await message.reply_text("🔎 <b>Finding your audio…</b>", parse_mode=ParseMode.HTML)
    try:
        track = await _make_track(update, query)
        await _send_audio(query, track, update)
        try: await searching.delete()
        except Exception: pass
    except Exception as exc:
        try: await searching.edit_text("❌ <b>Audio delivery failed.</b>\n" f"<code>{escape(type(exc).__name__ + ': ' + str(exc))}</code>", parse_mode=ParseMode.HTML)
        except Exception: pass


async def callback(update, context):
    call = update.callback_query
    if not call: return
    data = call.data or ""
    if data.startswith("music:mode:"):
        _, _, mode, token = data.split(":", 3); item = pending.pop(token, None)
        if not item:
            await call.answer("This playback request expired.", show_alert=True); return
        track, _ = item; chat_id = call.message.chat.id if call.message else None
        if mode == "cancel":
            await call.answer("✕ Playback selection cancelled.", show_alert=True)
            try: await call.message.delete()
            except Exception: pass
            return
        if mode == "audio":
            await call.answer("🎧 Preparing the audio file…", show_alert=True)
            try: await _send_audio(track.query, track, update)
            except Exception as exc: await call.message.reply_text("❌ <b>Audio delivery failed.</b>\n" f"<code>{escape(str(exc))}</code>", parse_mode=ParseMode.HTML)
            return
        if mode != "vc" or chat_id is None:
            await call.answer("❌ Unknown playback mode.", show_alert=True); return
        await call.answer("🎙 Starting VC playback…", show_alert=True)
        async with player_manager.lock(chat_id):
            state = player_manager.get(chat_id)
            if state.current is not None:
                position = player_manager.enqueue(chat_id, track)
                try: await call.message.edit_text("➕ <b>𝗔𝗗𝗗𝗘𝗗 𝗧𝗢 𝗩𝗖 𝗤𝗨𝗘𝗨𝗘</b>\n\n" f"🎵 <b>{escape(track.title)}</b>\n" f"📍 Position: <b>#{position}</b>", parse_mode=ParseMode.HTML)
                except Exception: pass
                return
            try:
                await _start_track(chat_id, track)
                await _send_now_playing(context.bot, chat_id, state, old_message=call.message)
            except Exception as exc:
                state.current = None; state.paused = False
                try: await call.message.edit_text("❌ <b>𝗩𝗖 𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗙𝗔𝗜𝗟𝗘𝗗</b>\n" f"<code>{escape(str(exc))}</code>", parse_mode=ParseMode.HTML)
                except Exception: pass
        return

    if not data.startswith("music:player:"): return
    action = data.split(":", 2)[2]; chat_id = call.message.chat.id
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        if action == "pause_resume":
            if not state.current: await call.answer("Nothing is playing.", show_alert=True); return
            if state.paused: await runtime.voice.resume(chat_id); state.paused=False; await call.answer("▶️ Resumed")
            else: await runtime.voice.pause(chat_id); state.paused=True; await call.answer("⏸ Paused")
            try: await call.message.edit_reply_markup(reply_markup=player_keyboard(state.paused))
            except Exception: pass
            return
        if action == "skip":
            if not state.current: await call.answer("Nothing is playing.", show_alert=True); return
            try: has_next = await advance_to_next(chat_id, bot=context.bot, old_message=call.message); await call.answer("⏭ Skipped" if has_next else "⏹ Queue finished")
            except Exception as exc: await call.answer("Could not start next track.", show_alert=True)
            return
        if action == "queue":
            await call.answer("📋 Queue")
            if not state.queue: text="📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\nQueue is empty."
            else:
                text="📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\n"+"\n".join(f"<b>{i:02}</b> · {escape(t.title)}" for i,t in enumerate(state.queue[:15],1))
            try: await call.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=queue_keyboard())
            except Exception: pass
            return
        if action == "now":
            if not state.current: await call.answer("Nothing is playing.", show_alert=True); return
            await call.answer("🎵 Now playing")
            await _send_now_playing(context.bot, chat_id, state, old_message=call.message); return
        if action == "stop":
            state.transition=True; state.ignore_stream_end_until=asyncio.get_running_loop().time()+6.0
            try: await runtime.voice.leave(chat_id)
            finally:
                paths=[]
                if state.current and state.current.media_path: paths.append(state.current.media_path)
                paths.extend(t.media_path for t in state.queue if t.media_path)
                state.current=None; state.queue.clear(); state.paused=False; state.transition=False
                for path in paths:
                    if path:
                        try: os.remove(path)
                        except OSError: pass
            await call.answer("⏹ Stopped")
            try: await call.message.edit_text("⏹ <b>𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗦𝗧𝗢𝗣𝗣𝗘𝗗</b>", parse_mode=ParseMode.HTML)
            except Exception: pass


async def queue_command(update, context):
    message=update.effective_message
    if not message:return
    state=player_manager.get(update.effective_chat.id)
    if not state.queue: await message.reply_text("📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\nQueue is empty.",parse_mode=ParseMode.HTML);return
    lines=[f"<b>{i:02}</b> · {escape(t.title)} — {escape(t.requested_name)}" for i,t in enumerate(state.queue[:20],1)]
    await message.reply_text("📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\n"+"\n".join(lines),parse_mode=ParseMode.HTML)


async def now_command(update, context):
    if not update.effective_message:return
    state=player_manager.get(update.effective_chat.id)
    if not state.current: await update.effective_message.reply_text("🎵 Nothing is playing.");return
    await _send_now_playing(context.bot,update.effective_chat.id,state)


async def skip_command(update, context):
    message=update.effective_message
    if not message:return
    chat_id=update.effective_chat.id
    async with player_manager.lock(chat_id):
        state=player_manager.get(chat_id)
        if not state.current: await message.reply_text("Nothing is playing.");return
        try:
            ok=await advance_to_next(chat_id,bot=context.bot)
            await message.reply_text("⏭ <b>Skipped to the next track.</b>" if ok else "⏹ <b>Queue finished.</b>",parse_mode=ParseMode.HTML)
        except Exception as exc: await message.reply_text("❌ <b>Could not start next track.</b>\n" f"<code>{escape(str(exc))}</code>",parse_mode=ParseMode.HTML)


async def pause_command(update, context):
    message=update.effective_message
    if not message:return
    chat_id=update.effective_chat.id
    async with player_manager.lock(chat_id):
        state=player_manager.get(chat_id)
        if not state.current: await message.reply_text("Nothing is playing.");return
        await runtime.voice.pause(chat_id); state.paused=True; await _send_now_playing(context.bot,chat_id,state)


async def resume_command(update, context):
    message=update.effective_message
    if not message:return
    chat_id=update.effective_chat.id
    async with player_manager.lock(chat_id):
        state=player_manager.get(chat_id)
        if not state.current: await message.reply_text("Nothing is playing.");return
        await runtime.voice.resume(chat_id); state.paused=False; await _send_now_playing(context.bot,chat_id,state)


async def stop_command(update, context):
    message=update.effective_message
    if not message:return
    chat_id=update.effective_chat.id
    async with player_manager.lock(chat_id):
        state=player_manager.get(chat_id); state.transition=True; state.ignore_stream_end_until=asyncio.get_running_loop().time()+6.0
        try: await runtime.voice.leave(chat_id)
        finally:
            paths=[]
            if state.current and state.current.media_path: paths.append(state.current.media_path)
            paths.extend(t.media_path for t in state.queue if t.media_path)
            state.current=None; state.queue.clear(); state.paused=False; state.transition=False
            for path in paths:
                if path:
                    try: os.remove(path)
                    except OSError: pass
        await message.reply_text("⏹ <b>𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗦𝗧𝗢𝗣𝗣𝗘𝗗</b>",parse_mode=ParseMode.HTML)


def get_handlers():
    return [
        CommandHandler("play", play_command), CommandHandler("audio", audio_command),
        CommandHandler("queue", queue_command), CommandHandler("now", now_command),
        CommandHandler("skip", skip_command), CommandHandler("pause", pause_command),
        CommandHandler("resume", resume_command), CommandHandler("stop", stop_command),
        CallbackQueryHandler(callback, pattern=r"^music:"),
    ]


async def on_stream_end(chat_id: int, bot):
    async with player_manager.lock(chat_id):
        state=player_manager.get(chat_id); now=asyncio.get_running_loop().time()
        if state.transition or now < state.ignore_stream_end_until:return
        if state.current is None:return
        try:
            await advance_to_next(chat_id,bot=bot)
        except Exception:
            log.exception("Failed to auto-play next track in chat %s",chat_id)
            state.current=None
