import asyncio
import io
import logging
import os
import time
from html import escape

import aiohttp
from telegram import InputFile, Update
from telegram.constants import ParseMode
from telegram.error import TimedOut
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from . import runtime
from .downloader import HepMusicError, cleanup_media, download_audio, resolve
from .manager import player_manager
from .models import Track
from .ui import player_keyboard

log = logging.getLogger(__name__)

REWIND_SECONDS = 10
FORWARD_SECONDS = 10
TRACKER_INTERVAL = 3


def _format_time(seconds: float | int | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _message_missing(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(x in text for x in ("message to edit not found", "message not found", "message_id_invalid", "have no access"))


def _friendly_music_error(exc: BaseException, action: str) -> str:
    """Map provider/Telegram failures to distinct, safe chat replies."""
    detail = str(exc).lower()
    markers = (
        "user_banned_in_channel", "user was kicked", "user_banned", "banned from the chat",
        "banned from the channel", "kicked from the supergroup", "kicked from the group",
        "participant_id_invalid", "user_restricted",
    )
    if any(marker in detail for marker in markers):
        return (
            "⚠️ <b>Muichiro assistant is banned in your chat.</b>\n"
            "Please resolve the ban first, then try playback again."
        )
    if any(marker in detail for marker in ("chat_admin_required", "chat_write_forbidden", "channel_private", "user_not_participant", "peer_id_invalid", "not a participant", "not a member")):
        return (
            "⚠️ <b>Muichiro assistant cannot access this chat or voice chat.</b>\n"
            "Please add/unban the assistant and check its group/voice-chat permissions, then try again."
        )
    if isinstance(exc, HepMusicError):
        status = getattr(exc, "status_code", 0)
        if "hep_music_api_key is not configured" in detail:
            return "⚙️ <b>Muichiro music API isn't configured.</b>\nPlease inform the owner @nyxluciferx02."
        if status == 401:
            return "🔑 <b>Hep.gg rejected Muichiro's API key.</b>\nPlease inform the owner @nyxluciferx02."
        if status == 404:
            return "🔎 <b>Hep.gg couldn't find this track.</b>\nTry another song or a supported public media link."
        if status == 422:
            return "🚫 <b>Hep.gg couldn't fetch this media.</b>\nIt may be unavailable or restricted. Please try another track."
        if status == 400:
            return "🔗 <b>Hep.gg couldn't use this link.</b>\nTry a supported public video/audio link or search by song name."
        return "⚠️ <b>Playback failed on Hep.gg.</b>\nPlease try again later or inform the owner @nyxluciferx02."
    if "sign in to confirm you're not a bot" in detail or "confirm you're not a bot" in detail:
        return "⚠️ <b>The music source rejected this request.</b>\nTry a supported public link or another track."
    if "unsupported url" in detail:
        return "❌ <b>Unsupported music link.</b>\nTry a supported public link or search by song name."
    if "timed out" in detail or "timeout" in detail:
        return f"⏳ <b>{action} timed out.</b>\nPlease try again later or inform the owner @nyxluciferx02."
    if "forbidden" in detail or "voice chat" in detail or "group call" in detail or "join the voice chat" in detail:
        return (
            "⚠️ <b>Muichiro assistant couldn't access the voice chat.</b>\n"
            "Please make sure the assistant is in the group and allowed to join the voice chat."
        )
    return f"⚠️ <b>{action} failed.</b>\nPlease try again later or inform the owner @nyxluciferx02."


async def _report_failure(message, status_message, text: str):
    """Edit the status reply when possible, otherwise send a fresh reply."""
    if status_message:
        try:
            await status_message.edit_text(text, parse_mode=ParseMode.HTML)
            return
        except Exception:
            pass
    if message:
        try:
            await message.reply_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            log.debug("Could not send user-facing music failure reply", exc_info=True)


def _position(state) -> float:
    if not state.current:
        return 0.0
    if state.paused:
        return max(0.0, state.paused_position)
    if not state.started_at:
        return max(0.0, state.position_offset)
    return max(0.0, state.position_offset + (asyncio.get_running_loop().time() - state.started_at))


def _now_text(state) -> str:
    track = state.current
    if not track:
        return "🎵 <b>Nothing is playing.</b>"
    return (
        "🎧 <b>𝗡𝗢𝗪 𝗣𝗟𝗔𝗬𝗜𝗡𝗚</b>\n\n"
        f"🎵 <b>{escape(track.title)}</b>\n"
        f"🎤 {escape(track.artist or 'Unknown Artist')}\n"
        f"👤 {escape(track.requested_name)}\n"
        f"📋 Queue: <b>{len(state.queue)}</b>"
    )


async def _edit_player_keyboard(bot, chat_id: int, state):
    message_id = state.control_message_id
    if not message_id or not state.current:
        return False
    keyboard = player_keyboard(state.paused, _position(state), state.current.duration)
    async with player_manager.ui_lock(chat_id):
        if state.control_message_id != message_id:
            return False
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
            return True
        except Exception as exc:
            if _message_missing(exc):
                state.control_message_id = None
                state.control_is_photo = False
                return False
            if "not modified" not in str(exc).lower():
                log.debug("Player keyboard refresh failed for %s: %s", chat_id, exc)
            return False


async def _tracker_loop(bot, chat_id: int, generation: int):
    try:
        while True:
            await asyncio.sleep(TRACKER_INTERVAL)
            state = player_manager.get(chat_id)
            if state.ui_generation != generation or not state.current:
                return
            await _edit_player_keyboard(bot, chat_id, state)
    except asyncio.CancelledError:
        return
    except Exception:
        log.exception("Music tracker stopped unexpectedly in chat %s", chat_id)


def _start_tracker(bot, chat_id: int, state):
    state.ui_generation += 1
    generation = state.ui_generation
    old = state.ui_task
    if old and not old.done():
        old.cancel()
    state.ui_task = asyncio.create_task(_tracker_loop(bot, chat_id, generation), name=f"music-tracker-{chat_id}")


async def _stop_tracker(state):
    state.ui_generation += 1
    task = state.ui_task
    state.ui_task = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _download_thumbnail(url: str | None):
    if not url:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=10, connect=4, sock_read=6)
        async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.read()
                    if data:
                        return io.BytesIO(data)
    except Exception:
        pass
    return None


async def _send_now_playing(bot, chat_id, state, replace_message=None):
    text = _now_text(state)
    keyboard = player_keyboard(state.paused, _position(state), state.current.duration if state.current else None)
    thumb = await _download_thumbnail(state.current.thumbnail if state.current else None)

    if replace_message:
        try:
            if thumb:
                thumb.seek(0)
                await replace_message.edit_media(
                    media=__import__('telegram').InputMediaPhoto(media=InputFile(thumb, filename='cover.jpg'), caption=text, parse_mode=ParseMode.HTML),
                    reply_markup=keyboard,
                )
            else:
                await replace_message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            state.control_message_id = replace_message.message_id
            state.control_is_photo = bool(thumb)
            _start_tracker(bot, chat_id, state)
            return replace_message
        except Exception:
            pass

    if thumb:
        thumb.seek(0)
        msg = await bot.send_photo(chat_id=chat_id, photo=InputFile(thumb, filename="cover.jpg"), caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        state.control_is_photo = True
    else:
        msg = await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        state.control_is_photo = False
    state.control_message_id = msg.message_id
    _start_tracker(bot, chat_id, state)
    return msg


async def _is_chat_admin(bot, chat_id: int, user_id: int) -> bool:
    try:
        chat = await bot.get_chat(chat_id)
        if getattr(chat, "type", "") not in ("group", "supergroup"):
            return True
        member = await bot.get_chat_member(chat_id, user_id)
        return getattr(member, "status", "") in ("administrator", "creator")
    except Exception:
        return False


async def _require_music_admin(update, context) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    if await _is_chat_admin(context.bot, chat.id, user.id):
        return True
    message = update.effective_message
    if message:
        await message.reply_text("🔒 <b>Admin-only music control.</b>\nOnly group admins can control playback.", parse_mode=ParseMode.HTML)
    return False


async def _require_callback_admin(call, context) -> bool:
    if not call.from_user or not call.message:
        return False
    chat_id = call.message.chat.id
    if await _is_chat_admin(context.bot, chat_id, call.from_user.id):
        return True
    await call.answer("🔒 Only group admins can control playback.", show_alert=True)
    return False


async def _make_track(update: Update, query: str) -> Track:
    info = await resolve(query)
    return Track(
        query=query,
        title=info.get("title") or query,
        requested_by=update.effective_user.id if update.effective_user else 0,
        requested_name=update.effective_user.full_name if update.effective_user else "Unknown",
        source_url=info.get("webpage_url") or query,
        artist=info.get("artist") or "Unknown Artist",
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        source_stream_url=info.get("stream_url"),
        video_id=info.get("id"),
        media_path=info.get("media_path"),
        provider=info.get("provider") or "hep_library",
        isrc=info.get("isrc"),
    )


async def _prepare_track(track: Track):
    if track.media_path and os.path.exists(track.media_path):
        return track.media_path
    info = {
        "webpage_url": track.source_url,
        "query": track.query,
        "title": track.title,
        "id": track.video_id,
        "isrc": track.isrc,
        "provider": track.provider,
        "media_path": track.media_path,
    }
    track.media_path = await download_audio(info)
    track.title = info.get("title") or track.title
    track.artist = info.get("artist") or track.artist
    track.duration = info.get("duration") or track.duration
    track.thumbnail = info.get("thumbnail") or track.thumbnail
    return track.media_path


async def _start_track(chat_id: int, track: Track, replacing=False, bot=None):
    state = player_manager.get(chat_id)
    previous = state.current
    state.transition = replacing
    if replacing:
        state.ignore_stream_end_until = asyncio.get_running_loop().time() + 5.0
    state.current = track
    state.paused = False
    state.position_offset = 0.0
    state.paused_position = 0.0
    state.started_at = 0.0
    state.playback_path = None

    try:
        # If a queued track was preloaded, reuse the exact file.
        preload = state.preload_task
        if preload and state.preload_for is track and not preload.done():
            try:
                await preload
            except Exception:
                pass
        state.preload_task = None
        state.preload_for = None
        await _prepare_track(track)
        state.playback_path = track.media_path
        await runtime.voice.play(chat_id, track.media_path)
        state.started_at = asyncio.get_running_loop().time()
    except Exception:
        cleanup_media(track.media_path)
        track.media_path = None
        state.playback_path = None
        state.current = previous
        raise
    finally:
        state.transition = False
    return state


async def _preload(track: Track):
    if track.media_path and os.path.exists(track.media_path):
        return
    try:
        await _prepare_track(track)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.debug("Preload failed for %s", track.title, exc_info=True)


def _schedule_preload(chat_id: int):
    state = player_manager.get(chat_id)
    if not state.queue:
        return
    existing = state.preload_task
    if existing and not existing.done():
        return
    state.preload_for = state.queue[0]
    state.preload_task = asyncio.create_task(_preload(state.preload_for), name=f"music-preload-{chat_id}")


async def _send_audio(update, track: Track):
    path = None
    try:
        path = await _prepare_track(track)
        # Hep.gg search results may omit duration; probe the actual media for Telegram metadata.
        if not track.duration and path:
            try:
                import subprocess
                probe = await asyncio.to_thread(
                    subprocess.run,
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
                    capture_output=True, text=True, timeout=12, check=True,
                )
                track.duration = max(1, int(round(float(probe.stdout.strip()))))
            except Exception:
                log.debug("Could not probe duration for /audio track", exc_info=True)
        await update.get_bot().send_audio(
            chat_id=update.effective_chat.id,
            audio=path,
            title=track.title,
            performer=track.artist or "Unknown Artist",
            duration=track.duration,
            connect_timeout=20,
            write_timeout=180,
            read_timeout=180,
            pool_timeout=20,
        )
    except TimedOut:
        await asyncio.sleep(0.5)
        await update.get_bot().send_audio(
            chat_id=update.effective_chat.id,
            audio=path,
            title=track.title,
            performer=track.artist or "Unknown Artist",
            duration=track.duration,
            connect_timeout=20,
            write_timeout=240,
            read_timeout=240,
            pool_timeout=20,
        )
    finally:
        cleanup_media(path)
        track.media_path = None


async def _advance(chat_id: int, bot):
    state = player_manager.get(chat_id)
    old = state.current
    old_path = state.playback_path or (old.media_path if old else None)
    next_track = player_manager.pop_next(chat_id)
    if not next_track:
        await runtime.voice.leave(chat_id)
        await _stop_tracker(state)
        state.current = None
        state.paused = False
        state.playback_path = None
        cleanup_media(old_path)
        return False

    await _start_track(chat_id, next_track, replacing=True, bot=bot)
    cleanup_media(old_path)
    await _send_now_playing(bot, chat_id, state)
    _schedule_preload(chat_id)
    return True


async def _relative_seek(chat_id: int, delta: float):
    state = player_manager.get(chat_id)
    track = state.current
    if not track or not track.media_path:
        raise RuntimeError("Current track is unavailable")
    duration = float(track.duration or 0)
    if duration <= 0:
        raise RuntimeError("Track duration is unavailable")
    current = _position(state)
    target = max(0.0, min(duration - 0.5, current + delta))
    if abs(target - current) < 0.5:
        return

    # Build a fresh segment. FFmpeg remains installed for this lightweight
    # relative seek only; normal playback/downloads do not transcode.
    import tempfile
    fd, candidate = tempfile.mkstemp(prefix="muichiro_seek_", suffix=".mp3")
    os.close(fd)
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-v", "error", "-ss", f"{target:.2f}", "-i", track.media_path,
        "-map", "0:a:0", "-vn", "-c:a", "copy", "-avoid_negative_ts", "make_zero", candidate,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0 or not os.path.exists(candidate) or os.path.getsize(candidate) < 1024:
        cleanup_media(candidate)
        raise RuntimeError(err.decode(errors="ignore").strip() or "Seek failed")

    old_playback = state.playback_path or track.media_path
    was_paused = state.paused
    state.transition = True
    state.ignore_stream_end_until = asyncio.get_running_loop().time() + 5.0
    try:
        await runtime.voice.play(chat_id, candidate)
        state.playback_path = candidate
        state.position_offset = target
        state.paused_position = target
        state.started_at = asyncio.get_running_loop().time()
        if was_paused:
            await runtime.voice.pause(chat_id)
    except Exception:
        cleanup_media(candidate)
        raise
    finally:
        state.transition = False
    if old_playback and old_playback != track.media_path and old_playback != candidate:
        cleanup_media(old_playback)


async def _stop(chat_id: int, bot):
    state = player_manager.get(chat_id)
    state.transition = True
    state.ignore_stream_end_until = asyncio.get_running_loop().time() + 5.0
    paths = [state.playback_path, state.current.media_path if state.current else None]
    paths.extend(t.media_path for t in state.queue)
    try:
        await runtime.voice.leave(chat_id)
    finally:
        await _stop_tracker(state)
        preload = state.preload_task
        state.preload_task = None
        state.preload_for = None
        if preload and not preload.done():
            preload.cancel()
        state.current = None
        state.queue.clear()
        state.paused = False
        state.playback_path = None
        state.position_offset = 0.0
        state.paused_position = 0.0
        state.started_at = 0.0
        state.transition = False
        for path in paths:
            cleanup_media(path)


def _queue_text(state):
    if not state.queue:
        return "📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\nQueue is empty."
    lines = [f"<b>{i:02}</b> · {escape(t.title)} — {escape(t.requested_name)}" for i, t in enumerate(state.queue[:20], 1)]
    return "📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\n" + "\n".join(lines)


async def play_command(update, context):
    message = update.effective_message
    if not message:
        return
    query = " ".join(context.args).strip()
    if not query:
        await message.reply_text("🎙 <b>Usage</b>\n<code>/play song name</code>", parse_mode=ParseMode.HTML)
        return
    status = await message.reply_text("🔎 <b>Finding your track…</b>", parse_mode=ParseMode.HTML)
    try:
        track = await _make_track(update, query)
        chat_id = update.effective_chat.id
        async with player_manager.lock(chat_id):
            state = player_manager.get(chat_id)
            if state.current:
                pos = player_manager.enqueue(chat_id, track)
                _schedule_preload(chat_id)
                await status.edit_text(
                    f"➕ <b>Queued</b> · <b>{escape(track.title)}</b>\n📍 Position: <b>#{pos}</b>\n📋 Waiting: <b>{len(state.queue)}</b>",
                    parse_mode=ParseMode.HTML,
                )
                return
            await _start_track(chat_id, track, bot=context.bot)
            await _send_now_playing(context.bot, chat_id, state, replace_message=status)
    except Exception as exc:
        log.exception("VC playback failed")
        await _report_failure(message, status, _friendly_music_error(exc, "Playback"))


async def audio_command(update, context):
    message = update.effective_message
    if not message:
        return
    query = " ".join(context.args).strip()
    if not query:
        await message.reply_text("🎧 <b>Usage</b>\n<code>/audio song name</code>", parse_mode=ParseMode.HTML)
        return
    status = await message.reply_text("⚡ <b>Preparing audio…</b>", parse_mode=ParseMode.HTML)
    try:
        track = await _make_track(update, query)
        await _send_audio(update, track)
        try:
            await status.delete()
        except Exception:
            pass
    except Exception as exc:
        log.exception("Audio delivery failed")
        await _report_failure(message, status, _friendly_music_error(exc, "Audio delivery"))


async def queue_command(update, context):
    state = player_manager.get(update.effective_chat.id)
    await update.effective_message.reply_text(_queue_text(state), parse_mode=ParseMode.HTML)


async def now_command(update, context):
    state = player_manager.get(update.effective_chat.id)
    if not state.current:
        await update.effective_message.reply_text("🎵 Nothing is playing.")
        return
    # Do not replace or edit the player card. It already contains the live tracker.
    await update.effective_message.reply_text(_now_text(state), parse_mode=ParseMode.HTML)


async def skip_command(update, context):
    if not await _require_music_admin(update, context):
        return
    chat_id = update.effective_chat.id
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        if not state.current:
            await update.effective_message.reply_text("Nothing is playing.")
            return
        try:
            ok = await _advance(chat_id, context.bot)
            await update.effective_message.reply_text("⏭ <b>Skipped.</b>" if ok else "⏹ <b>Queue finished.</b>", parse_mode=ParseMode.HTML)
        except Exception as exc:
            log.exception("Skip failed")
            await update.effective_message.reply_text(_friendly_music_error(exc, "Skip"), parse_mode=ParseMode.HTML)


async def pause_command(update, context):
    if not await _require_music_admin(update, context):
        return
    chat_id = update.effective_chat.id
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        if not state.current:
            await update.effective_message.reply_text("Nothing is playing.")
            return
        state.paused_position = _position(state)
        await runtime.voice.pause(chat_id)
        state.paused = True
        await _edit_player_keyboard(context.bot, chat_id, state)


async def resume_command(update, context):
    if not await _require_music_admin(update, context):
        return
    chat_id = update.effective_chat.id
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        if not state.current:
            await update.effective_message.reply_text("Nothing is playing.")
            return
        state.position_offset = state.paused_position
        state.started_at = asyncio.get_running_loop().time()
        await runtime.voice.resume(chat_id)
        state.paused = False
        await _edit_player_keyboard(context.bot, chat_id, state)


async def stop_command(update, context):
    if not await _require_music_admin(update, context):
        return
    chat_id = update.effective_chat.id
    async with player_manager.lock(chat_id):
        await _stop(chat_id, context.bot)
    await update.effective_message.reply_text("⏹ <b>Playback stopped.</b>", parse_mode=ParseMode.HTML)


async def callback(update, context):
    call = update.callback_query
    if not call or not call.message:
        return
    data = call.data or ""
    if not data.startswith("music:player:"):
        await call.answer()
        return
    action = data.split(":", 2)[2]
    chat_id = call.message.chat.id

    if action == "noop":
        await call.answer("🎧 Live playback tracker")
        return

    if action in {"pause_resume", "skip", "stop", "rewind", "forward"}:
        if not await _require_callback_admin(call, context):
            return

    if action == "queue":
        state = player_manager.get(chat_id)
        await call.answer("📋 Queue")
        await context.bot.send_message(chat_id=chat_id, text=_queue_text(state), parse_mode=ParseMode.HTML)
        return

    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        if action == "pause_resume":
            if not state.current:
                await call.answer("Nothing is playing.", show_alert=True)
                return
            if state.paused:
                state.position_offset = state.paused_position
                state.started_at = asyncio.get_running_loop().time()
                await runtime.voice.resume(chat_id)
                state.paused = False
                await call.answer("▶️ Resumed")
            else:
                state.paused_position = _position(state)
                await runtime.voice.pause(chat_id)
                state.paused = True
                await call.answer("⏸️ Paused")
            await _edit_player_keyboard(context.bot, chat_id, state)
            return

        if action == "skip":
            if not state.current:
                await call.answer("Nothing is playing.", show_alert=True)
                return
            try:
                ok = await _advance(chat_id, context.bot)
                await call.answer("⏭ Skipped" if ok else "⏹ Queue finished")
            except Exception as exc:
                log.exception("Callback skip failed")
                await call.answer("Could not start next track.", show_alert=True)
                try:
                    await context.bot.send_message(chat_id=chat_id, text=_friendly_music_error(exc, "Playback"), parse_mode=ParseMode.HTML)
                except Exception:
                    log.debug("Could not send callback failure explanation", exc_info=True)
            return

        if action == "stop":
            await _stop(chat_id, context.bot)
            await call.answer("⏹ Stopped")
            try:
                await call.message.delete()
            except Exception:
                pass
            return

        if action in {"rewind", "forward"}:
            if not state.current:
                await call.answer("Nothing is playing.", show_alert=True)
                return
            try:
                await _relative_seek(chat_id, -REWIND_SECONDS if action == "rewind" else FORWARD_SECONDS)
                await call.answer("⏪ 10 seconds" if action == "rewind" else "⏩ 10 seconds")
                await _edit_player_keyboard(context.bot, chat_id, state)
            except Exception:
                log.exception("Relative seek failed")
                await call.answer("Seek failed.", show_alert=True)
            return

        if action == "now":
            await call.answer("🎧 Player is already showing the current track")
            return

    await call.answer()


def get_handlers():
    return [
        CommandHandler("play", play_command),
        CommandHandler("audio", audio_command),
        CommandHandler("queue", queue_command),
        CommandHandler("now", now_command),
        CommandHandler("skip", skip_command),
        CommandHandler("pause", pause_command),
        CommandHandler("resume", resume_command),
        CommandHandler("stop", stop_command),
        CallbackQueryHandler(callback, pattern=r"^music:"),
    ]


async def on_stream_end(chat_id: int, bot):
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        now = asyncio.get_running_loop().time()
        if state.transition or now < state.ignore_stream_end_until or not state.current:
            return
        try:
            await _advance(chat_id, bot)
        except Exception as exc:
            log.exception("Failed to auto-play next track in chat %s", chat_id)
            cleanup_media(state.playback_path)
            state.current = None
            state.paused = False
            state.playback_path = None
            try:
                await bot.send_message(chat_id=chat_id, text=_friendly_music_error(exc, "Playback"), parse_mode=ParseMode.HTML)
            except Exception:
                log.debug("Could not send auto-next failure explanation", exc_info=True)
