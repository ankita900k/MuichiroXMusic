import asyncio
import io
import logging
import os
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from html import escape

import aiohttp
from telegram import InlineKeyboardMarkup, InputFile, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from . import runtime
from .annie import annie
from .manager import player_manager
from .metadata import resolve
from .models import Track
from .ui import mode_keyboard, player_keyboard, queue_keyboard, seek_keyboard
from .security import safe_exception, user_error_message

log = logging.getLogger(__name__)
pending: dict[str, tuple[Track, float]] = {}
PENDING_TTL = 15 * 60


def _message_missing(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in (
        "message to edit not found",
        "message to delete not found",
        "message not found",
        "message_id_invalid",
        "have no access to the message",
    ))


def _cleanup_pending():
    cutoff = time.monotonic() - PENDING_TTL
    for token, (_, created) in list(pending.items()):
        if created < cutoff:
            pending.pop(token, None)


def _format_time(seconds: float | int | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _now_text(state):
    track = state.current
    if not track:
        return "🎵 <b>Nothing is playing.</b>"

    position = state.position(asyncio.get_running_loop().time())
    duration = track.duration
    progress = f"{_format_time(position)} / {_format_time(duration)}"

    return (
        "🎧 <b>𝗡𝗢𝗪 𝗣𝗟𝗔𝗬𝗜𝗡𝗚</b>\n\n"
        f"🎵 <b>{escape(track.title)}</b>\n"
        f"🎤 {escape(track.artist or 'Unknown Artist')}\n"
        f"👤 {escape(track.requested_name)}\n"
        f"⏱ <b>{progress}</b>\n"
        f"📋 Queue: <b>{len(state.queue)}</b>"
    )


async def _edit_control_message(bot, chat_id: int, state, text=None, keyboard=None):
    """Edit the existing player message without re-uploading its artwork."""
    message_id = state.control_message_id
    if not message_id:
        return False

    if text is None:
        text = _now_text(state)
    if keyboard is None:
        position = state.position(asyncio.get_running_loop().time())
        duration = state.current.duration if state.current else None
        keyboard = player_keyboard(state.paused, position, duration)

    async with player_manager.ui_lock(chat_id):
        # A callback may have replaced the player while this edit was waiting.
        if state.control_message_id != message_id:
            return False
        try:
            if state.control_is_photo:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            return True
        except Exception as exc:
            # The player message can be deleted manually or by Telegram/admins.
            # Treat that as stale UI, not as a playback failure. The next UI
            # refresh/command will create a fresh player message.
            if _message_missing(exc):
                state.control_message_id = None
                state.control_is_photo = False
                return False
            # Telegram returns "message is not modified" frequently when the
            # ticker lands on the same rendered second. Ignore it.
            if "not modified" not in str(exc).lower():
                log.debug("Player UI edit failed in %s: %s", chat_id, safe_exception(exc))
            return False


async def _stop_ui_task(state):
    task = state.ui_task
    state.ui_task = None
    state.ui_generation += 1
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _player_ui_loop(bot, chat_id: int, generation: int):
    """Low-frequency progress ticker.

    Playback itself never waits for this task. It only edits the existing
    Telegram player message, so fancy UI cannot delay PyTgCalls.
    """
    try:
        while True:
            await asyncio.sleep(5.0)
            state = player_manager.get(chat_id)
            if state.ui_generation != generation or not state.current:
                return

            position = state.position(asyncio.get_running_loop().time())
            duration = state.current.duration
            keyboard = player_keyboard(state.paused, position, duration)
            await _edit_control_message(bot, chat_id, state, keyboard=keyboard)
    except asyncio.CancelledError:
        return
    except Exception as exc:
        log.error("Player UI ticker failed for chat %s (%s)", chat_id, safe_exception(exc))


def _start_ui_task(bot, chat_id: int, state):
    state.ui_generation += 1
    generation = state.ui_generation
    old = state.ui_task
    if old and not old.done():
        old.cancel()
    state.ui_task = asyncio.create_task(
        _player_ui_loop(bot, chat_id, generation),
        name=f"music-ui-{chat_id}",
    )


async def _send_now_playing(bot, chat_id, state, old_message=None, force_new=False):
    """Create a fresh player card when a new track starts.

    The player card belongs to one track only. During the same track we edit
    its caption/buttons, but a completed track is never transformed into the
    next track's card. This keeps artwork and metadata visually consistent.
    """
    text = _now_text(state)
    position = state.position(asyncio.get_running_loop().time())
    keyboard = player_keyboard(
        state.paused,
        position,
        state.current.duration if state.current else None,
    )

    if force_new:
        # The caller has already marked the previous card as completed.
        state.control_message_id = None
        state.control_is_photo = False

    if state.control_message_id is None:
        if old_message and not force_new:
            try:
                await old_message.delete()
            except Exception:
                pass

        message = None
        if state.current and state.current.thumbnail:
            try:
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=state.current.thumbnail,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                state.control_is_photo = True
            except Exception as exc:
                log.debug("Remote thumbnail send failed: %s", safe_exception(exc))

        if message is None:
            message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
            state.control_is_photo = False

        state.control_message_id = message.message_id
    else:
        edited = await _edit_control_message(bot, chat_id, state, text=text, keyboard=keyboard)
        if not edited and state.control_message_id is None:
            return await _send_now_playing(bot, chat_id, state, old_message=None, force_new=False)

    _start_ui_task(bot, chat_id, state)
    return state.control_message_id


async def _mark_track_completed(bot, chat_id, state, track):
    """Freeze the current track's player card as a completed card."""
    message_id = state.control_message_id
    if not message_id:
        return

    duration = _format_time(track.duration)
    text = (
        "✅ <b>𝗧𝗥𝗔𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗</b>\n\n"
        f"🎵 <b>{escape(track.title)}</b>\n"
        f"🎤 {escape(track.artist or 'Unknown Artist')}\n"
        f"⏱ <b>{duration}</b>\n"
        f"👤 {escape(track.requested_name)}"
    )

    async with player_manager.ui_lock(chat_id):
        if state.control_message_id != message_id:
            return
        try:
            if state.control_is_photo:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([]),
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([]),
                )
        except Exception as exc:
            if not _message_missing(exc) and "not modified" not in str(exc).lower():
                log.debug("Could not mark completed player card: %s", safe_exception(exc))

    state.control_message_id = None
    state.control_is_photo = False


async def _ensure_assistant_in_group(bot, chat_id: int):
    """Join the Pyrogram assistant automatically when it is missing.

    The bot must have permission to invite users via link. The invite is
    generated for this specific group and limited to one member, so no
    permanent invite URL is required in the environment.
    """
    voice = runtime.voice
    if voice is None:
        raise RuntimeError("Music voice layer is not initialized")

    # If the assistant is already present, avoid creating an unnecessary link.
    try:
        member = await voice.client.get_chat_member(chat_id, "me")
        status = getattr(member, "status", "")
        if status not in {"left", "kicked", "banned"}:
            await voice._warm_dialog_cache(chat_id)
            return
    except Exception:
        pass

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=chat_id,
            name="Music assistant",
            expire_date=datetime.now(timezone.utc) + timedelta(minutes=5),
            member_limit=1,
        )
    except Exception as exc:
        raise RuntimeError(
            "The bot could not create an invite link for the music assistant. "
            "Make sure the bot is an administrator with permission to invite users via link."
        ) from exc

    try:
        await voice.ensure_joined(chat_id, invite.invite_link)
    finally:
        # A one-member/short-lived link is already constrained; revoke it when
        # possible so it is not left around after the assistant joins.
        try:
            await bot.revoke_chat_invite_link(chat_id, invite.invite_link)
        except Exception:
            pass

async def _preload_track(track: Track):
    """Download the next queued track in the background.

    Playback never waits for this task. If it finishes before the current
    track ends, the next transition can start immediately from disk.
    """
    if track.media_path and os.path.exists(track.media_path):
        return
    try:
        track.media_path = await annie.prepare_audio(track.source_url or track.query)
        log.debug("Preloaded queued track: %s", track.title)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.debug("Background preload failed for %s: %s", track.title, exc)


def _schedule_preload(chat_id: int):
    state = player_manager.get(chat_id)
    if not state.queue:
        return
    # Keep one background preload per chat. The task is intentionally not
    # awaited by the command/callback path.
    existing = getattr(state, "preload_task", None)
    if existing and not existing.done():
        return
    state.preload_for = state.queue[0]
    state.preload_task = asyncio.create_task(
        _preload_track(state.preload_for),
        name=f"music-preload-{chat_id}",
    )


async def _refresh_track_source(track: Track):
    """Re-resolve a track after a temporary/stale audio-service 404."""
    info = await resolve(track.query)
    source = info.get("webpage_url") or track.source_url or track.query
    if source:
        track.source_url = source
    if info.get("title"):
        track.title = info["title"]
    if info.get("artist"):
        track.artist = info["artist"]
    if info.get("thumbnail"):
        track.thumbnail = info["thumbnail"]
    if info.get("duration"):
        try:
            track.duration = int(info["duration"])
        except (TypeError, ValueError):
            pass

async def _start_track(chat_id: int, track: Track, replacing=False, bot=None):
    state = player_manager.get(chat_id)
    previous = state.current
    previous_playback_path = state.playback_path

    state.transition = replacing
    if replacing:
        state.ignore_stream_end_until = asyncio.get_running_loop().time() + 6.0
    state.current = track
    state.paused = False
    state.position_offset = 0.0
    state.paused_position = 0.0
    state.started_at = asyncio.get_running_loop().time()
    state.playback_path = None

    try:
        if bot is not None:
            await _ensure_assistant_in_group(bot, chat_id)

        # If this track was already being downloaded in the background,
        # await that exact task instead of starting a duplicate download.
        preload = state.preload_task
        if (not track.media_path or not os.path.exists(track.media_path)) and preload and state.preload_for is track:
            try:
                await preload
            except Exception:
                pass
            state.preload_task = None
            state.preload_for = None

        if not track.media_path or not os.path.exists(track.media_path):
            try:
                track.media_path = await annie.prepare_audio(track.source_url or track.query)
            except RuntimeError as exc:
                # The audio service can return 404 when a previously resolved
                # source has gone stale. Resolve the query again once instead
                # of immediately killing VC playback.
                if "HTTP 404" not in str(exc):
                    raise
                log.info("Audio source returned 404 for %r; re-resolving", track.query)
                track.media_path = None
                await _refresh_track_source(track)
                track.media_path = await annie.prepare_audio(track.source_url or track.query)

        state.playback_path = track.media_path
        await runtime.voice.play(chat_id, track.media_path)
        state.started_at = asyncio.get_running_loop().time()
    except Exception:
        if track.media_path and track.media_path != getattr(previous, "media_path", None):
            try:
                os.remove(track.media_path)
            except OSError:
                pass
            track.media_path = None
        state.playback_path = previous_playback_path
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

        # Do NOT use effective_message.reply_audio() here. That creates a
        # Telegram reply relationship with the original command message.
        # If that message was deleted/expired/inaccessible, Telegram raises
        # "BadRequest: Message to be replied not found" and audio delivery
        # fails even though the audio itself is valid. Send directly to the
        # chat instead.
        chat = update.effective_chat
        if not chat:
            raise RuntimeError("Audio destination chat is unavailable")

        await update.get_bot().send_audio(
            chat_id=chat.id,
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
    old_playback_path = state.playback_path
    next_track = player_manager.pop_next(chat_id)

    if old_track and bot:
        await _stop_ui_task(state)
        await _mark_track_completed(bot, chat_id, state, old_track)

    if not next_track:
        await runtime.voice.leave(chat_id)
        state.current = None
        state.paused = False
        state.playback_path = None
        state.position_offset = 0.0
        state.paused_position = 0.0

        for path in (old_playback_path, old_track.media_path if old_track else None):
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
        return False

    try:
        await _start_track(chat_id, next_track, replacing=True, bot=bot)
    except Exception:
        # The old card has already been safely frozen as completed. Do not
        # overwrite it with an error player card.
        raise

    for path in (old_playback_path, old_track.media_path if old_track else None):
        if path and path != next_track.media_path and path != state.playback_path:
            try:
                os.remove(path)
            except OSError:
                pass

    if bot:
        await _send_now_playing(bot, chat_id, state, force_new=True)
    _schedule_preload(chat_id)
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
                _schedule_preload(chat_id)
                await searching.edit_text("➕ <b>𝗔𝗗𝗗𝗘𝗗 𝗧𝗢 𝗩𝗖 𝗤𝗨𝗘𝗨𝗘</b>\n\n" f"🎵 <b>{escape(track.title)}</b>\n" f"📍 Position: <b>#{position}</b>\n" f"📋 Waiting: <b>{len(state.queue)}</b>", parse_mode=ParseMode.HTML); return
            await _start_track(chat_id, track, bot=context.bot)
            await _send_now_playing(context.bot, chat_id, state, old_message=searching)
    except Exception as exc:
        log.error("VC playback failed (%s)", safe_exception(exc))
        try: await searching.edit_text("❌ <b>𝗩𝗖 𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗙𝗔𝗜𝗟𝗘𝗗</b>\n\nPlease try again in a moment.", parse_mode=ParseMode.HTML)
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
        log.error("Audio delivery failed (%s)", safe_exception(exc))
        try: await searching.edit_text("❌ <b>Audio delivery failed.</b>\nPlease try again in a moment.", parse_mode=ParseMode.HTML)
        except Exception: pass


async def _seek_to(chat_id: int, target: float):
    """Seek by restarting the current local audio from a small FFmpeg segment.

    The normal playback path never invokes FFmpeg for seeking. This keeps
    startup fast; FFmpeg is used only when the user explicitly taps seek.
    """
    state = player_manager.get(chat_id)
    track = state.current
    if not track or not track.media_path or not os.path.exists(track.media_path):
        raise RuntimeError("The current audio file is no longer available")

    duration = float(track.duration or 0)
    if duration <= 0:
        raise RuntimeError("This track has no known duration, so it cannot be seeked")

    target = max(0.0, min(float(target), max(0.0, duration - 0.5)))
    old_playback = state.playback_path or track.media_path
    new_path = None

    if target <= 0.5:
        new_path = track.media_path
    else:
        suffix = os.path.splitext(track.media_path)[1] or ".mp3"
        fd, candidate = tempfile.mkstemp(prefix="muichiro_seek_", suffix=suffix)
        os.close(fd)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{target:.3f}",
            "-i", track.media_path,
            "-map", "0:a:0", "-vn",
            "-c:a", "copy",
            "-avoid_negative_ts", "make_zero",
            candidate,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()

        if proc.returncode != 0 or not os.path.exists(candidate) or os.path.getsize(candidate) < 1024:
            try:
                os.remove(candidate)
            except OSError:
                pass
            fd, candidate = tempfile.mkstemp(prefix="muichiro_seek_", suffix=".mp3")
            os.close(fd)
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-v", "error",
                "-ss", f"{target:.3f}",
                "-i", track.media_path,
                "-map", "0:a:0", "-vn",
                "-c:a", "libmp3lame", "-b:a", "192k",
                candidate,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err = await proc.communicate()

        if proc.returncode != 0 or not os.path.exists(candidate) or os.path.getsize(candidate) < 1024:
            try:
                os.remove(candidate)
            except OSError:
                pass
            raise RuntimeError(err.decode(errors="ignore").strip() or "FFmpeg seek failed")
        new_path = candidate

    was_paused = state.paused
    state.transition = True
    state.ignore_stream_end_until = asyncio.get_running_loop().time() + 5.0
    try:
        await runtime.voice.play(chat_id, new_path)
        state.playback_path = new_path
        state.position_offset = target
        state.paused_position = target
        state.started_at = asyncio.get_running_loop().time()
        state.paused = was_paused
        if was_paused:
            await runtime.voice.pause(chat_id)
    except Exception:
        if new_path != track.media_path and new_path:
            try:
                os.remove(new_path)
            except OSError:
                pass
        raise
    finally:
        state.transition = False

    if old_playback and old_playback != track.media_path and old_playback != new_path:
        try:
            os.remove(old_playback)
        except OSError:
            pass

    return target


async def callback(update, context):
    call = update.callback_query
    if not call:
        return

    data = call.data or ""

    if data.startswith("music:mode:"):
        _, _, mode, token = data.split(":", 3)
        item = pending.pop(token, None)
        if not item:
            await call.answer("This playback request expired.", show_alert=True)
            return

        track, _ = item
        chat_id = call.message.chat.id if call.message else None

        if mode == "cancel":
            await call.answer("✕ Playback selection cancelled.", show_alert=True)
            try:
                await call.message.delete()
            except Exception:
                pass
            return

        if mode == "audio":
            await call.answer("🎧 Preparing the audio file…", show_alert=True)
            try:
                await _send_audio(track.query, track, update)
            except Exception as exc:
                log.error("Callback audio delivery failed (%s)", safe_exception(exc))
                await call.message.reply_text(
                    "❌ <b>Audio delivery failed.</b>\nPlease try again in a moment.",
                    parse_mode=ParseMode.HTML,
                )
            return

        if mode != "vc" or chat_id is None:
            await call.answer("❌ Unknown playback mode.", show_alert=True)
            return

        await call.answer("🎙 Starting VC playback…")
        async with player_manager.lock(chat_id):
            state = player_manager.get(chat_id)
            if state.current is not None:
                position = player_manager.enqueue(chat_id, track)
                _schedule_preload(chat_id)
                await call.message.edit_text(
                    "➕ <b>𝗔𝗗𝗗𝗘𝗗 𝗧𝗢 𝗩𝗖 𝗤𝗨𝗘𝗨𝗘</b>\n\n"
                    f"🎵 <b>{escape(track.title)}</b>\n"
                    f"📍 Position: <b>#{position}</b>",
                    parse_mode=ParseMode.HTML,
                )
                return

            try:
                await _start_track(chat_id, track, bot=context.bot)
                # Reuse the new persistent player message. The mode selector is
                # transient and can safely be removed.
                await _send_now_playing(context.bot, chat_id, state, old_message=call.message)
            except Exception as exc:
                state.current = None
                state.paused = False
                try:
                    await call.message.edit_text(
                        "❌ <b>𝗩𝗖 𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗙𝗔𝗜𝗟𝗘𝗗</b>\nPlease try again in a moment.",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
        return

    if not data.startswith("music:player:") or not call.message:
        return

    action = data.split(":", 2)[2]
    chat_id = call.message.chat.id

    # Seek operations are intentionally outside the main player lock while
    # FFmpeg runs. This keeps other chats and Telegram callbacks responsive.
    if action == "seek_menu":
        state = player_manager.get(chat_id)
        if not state.current:
            await call.answer("Nothing is playing.", show_alert=True)
            return
        position = state.position(asyncio.get_running_loop().time())
        await call.answer("🎚 Seek")
        try:
            await _edit_control_message(
                context.bot,
                chat_id,
                state,
                text=_now_text(state),
                keyboard=seek_keyboard(position, state.current.duration),
            )
        except Exception:
            pass
        return

    if action.startswith("seek:"):
        try:
            _, segment, total = action.split(":")
            fraction = (int(segment) + 0.5) / int(total)
        except Exception:
            await call.answer("Invalid seek position.", show_alert=True)
            return

        state = player_manager.get(chat_id)
        if not state.current or not state.current.duration:
            await call.answer("Track duration is unavailable.", show_alert=True)
            return

        await call.answer("🎚 Seeking…")
        try:
            async with player_manager.lock(chat_id):
                target = state.current.duration * fraction
                await _seek_to(chat_id, target)
                position = state.position(asyncio.get_running_loop().time())
                await _edit_control_message(
                    context.bot, chat_id, state,
                    keyboard=player_keyboard(False, position, state.current.duration),
                )
        except Exception as exc:
            await call.answer(f"Seek failed: {type(exc).__name__}", show_alert=True)
        return

    if action.startswith("seek_pct:"):
        try:
            percent = float(action.split(":")[1])
        except Exception:
            await call.answer("Invalid seek position.", show_alert=True)
            return
        state = player_manager.get(chat_id)
        if not state.current or not state.current.duration:
            await call.answer("Track duration is unavailable.", show_alert=True)
            return

        await call.answer("🎚 Seeking…")
        try:
            async with player_manager.lock(chat_id):
                await _seek_to(chat_id, state.current.duration * percent / 100.0)
                position = state.position(asyncio.get_running_loop().time())
                await _edit_control_message(
                    context.bot, chat_id, state,
                    keyboard=player_keyboard(state.paused, position, state.current.duration),
                )
        except Exception as exc:
            await call.answer(f"Seek failed: {type(exc).__name__}", show_alert=True)
        return

    if action.startswith("seek_rel:"):
        try:
            delta = float(action.split(":")[1])
        except Exception:
            await call.answer("Invalid seek amount.", show_alert=True)
            return
        state = player_manager.get(chat_id)
        if not state.current or not state.current.duration:
            await call.answer("Track duration is unavailable.", show_alert=True)
            return

        await call.answer("🎚 Seeking…")
        try:
            async with player_manager.lock(chat_id):
                current_position = state.position(asyncio.get_running_loop().time())
                await _seek_to(chat_id, current_position + delta)
                position = state.position(asyncio.get_running_loop().time())
                await _edit_control_message(
                    context.bot, chat_id, state,
                    keyboard=player_keyboard(state.paused, position, state.current.duration),
                )
        except Exception as exc:
            await call.answer(f"Seek failed: {type(exc).__name__}", show_alert=True)
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
                state.paused_position = state.position(asyncio.get_running_loop().time())
                await runtime.voice.pause(chat_id)
                state.paused = True
                await call.answer("⏸ Paused")

            position = state.position(asyncio.get_running_loop().time())
            await _edit_control_message(
                context.bot, chat_id, state,
                keyboard=player_keyboard(state.paused, position, state.current.duration),
            )
            return

        if action == "skip":
            if not state.current:
                await call.answer("Nothing is playing.", show_alert=True)
                return
            try:
                has_next = await advance_to_next(
                    chat_id, bot=context.bot, old_message=call.message
                )
                await call.answer("⏭ Skipped" if has_next else "⏹ Queue finished")
            except Exception:
                await call.answer("Could not start next track.", show_alert=True)
            return

        if action == "queue":
            await call.answer("📋 Queue")
            if not state.queue:
                text = "📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\nQueue is empty."
            else:
                items = []
                for i, t in enumerate(state.queue[:12], 1):
                    title = t.title
                    if len(title) > 55:
                        title = title[:52] + "…"
                    items.append(f"<b>{i:02}</b> · {escape(title)}")
                text = "📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\n" + "\n".join(items)
            await _edit_control_message(
                context.bot, chat_id, state, text=text, keyboard=queue_keyboard()
            )
            return

        if action == "now":
            if not state.current:
                await call.answer("Nothing is playing.", show_alert=True)
                return
            await call.answer("🎵 Now playing")
            position = state.position(asyncio.get_running_loop().time())
            await _edit_control_message(
                context.bot,
                chat_id,
                state,
                text=_now_text(state),
                keyboard=player_keyboard(state.paused, position, state.current.duration),
            )
            return

        if action == "stop":
            state.transition = True
            state.ignore_stream_end_until = asyncio.get_running_loop().time() + 6.0

            old_paths = []
            if state.current and state.current.media_path:
                old_paths.append(state.current.media_path)
            if state.playback_path:
                old_paths.append(state.playback_path)
            old_paths.extend(t.media_path for t in state.queue if t.media_path)

            try:
                await runtime.voice.leave(chat_id)
            finally:
                await _stop_ui_task(state)
                preload = state.preload_task
                state.preload_task = None
                state.preload_for = None
                if preload and not preload.done():
                    preload.cancel()
                # Keep the message ID long enough to turn the player into a
                # clean stopped state instead of deleting/reposting it.
                state.current = None
                state.queue.clear()
                state.paused = False
                state.playback_path = None
                state.position_offset = 0.0
                state.paused_position = 0.0
                await _edit_control_message(
                    context.bot,
                    chat_id,
                    state,
                    text="⏹ <b>𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗦𝗧𝗢𝗣𝗣𝗘𝗗</b>",
                    keyboard=InlineKeyboardMarkup([]),
                )
                state.control_message_id = None
                state.control_is_photo = False
                state.transition = False

                for path in old_paths:
                    if path:
                        try:
                            os.remove(path)
                        except OSError:
                            pass

            await call.answer("⏹ Stopped")
            return


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
        except Exception as exc:
            log.error("Could not start next track (%s)", safe_exception(exc))
            await message.reply_text("❌ <b>Could not start next track.</b>\nPlease try again in a moment.",parse_mode=ParseMode.HTML)


async def pause_command(update, context):
    message = update.effective_message
    if not message:
        return
    chat_id = update.effective_chat.id
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        if not state.current:
            await message.reply_text("Nothing is playing.")
            return
        state.paused_position = state.position(asyncio.get_running_loop().time())
        await runtime.voice.pause(chat_id)
        state.paused = True
        position = state.position(asyncio.get_running_loop().time())
        await _edit_control_message(
            context.bot, chat_id, state,
            keyboard=player_keyboard(True, position, state.current.duration),
        )


async def resume_command(update, context):
    message = update.effective_message
    if not message:
        return
    chat_id = update.effective_chat.id
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        if not state.current:
            await message.reply_text("Nothing is playing.")
            return
        state.position_offset = state.paused_position
        state.started_at = asyncio.get_running_loop().time()
        await runtime.voice.resume(chat_id)
        state.paused = False
        position = state.position(asyncio.get_running_loop().time())
        await _edit_control_message(
            context.bot, chat_id, state,
            keyboard=player_keyboard(False, position, state.current.duration),
        )


async def stop_command(update, context):
    message = update.effective_message
    if not message:
        return
    chat_id = update.effective_chat.id

    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        state.transition = True
        state.ignore_stream_end_until = asyncio.get_running_loop().time() + 6.0

        paths = []
        if state.current and state.current.media_path:
            paths.append(state.current.media_path)
        if state.playback_path:
            paths.append(state.playback_path)
        paths.extend(t.media_path for t in state.queue if t.media_path)

        try:
            await runtime.voice.leave(chat_id)
        finally:
            await _stop_ui_task(state)
            preload = state.preload_task
            state.preload_task = None
            state.preload_for = None
            if preload and not preload.done():
                preload.cancel()
            state.current = None
            state.queue.clear()
            state.paused = False
            state.playback_path = None

            await _edit_control_message(
                context.bot,
                chat_id,
                state,
                text="⏹ <b>𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗦𝗧𝗢𝗣𝗣𝗘𝗗</b>",
                keyboard=InlineKeyboardMarkup([]),
            )
            state.control_message_id = None
            state.control_is_photo = False
            state.transition = False

            for path in paths:
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

        await message.reply_text("⏹ <b>𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗦𝗧𝗢𝗣𝗣𝗘𝗗</b>", parse_mode=ParseMode.HTML)


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
        except Exception as exc:
            log.error("Failed to auto-play next track in chat %s (%s)", chat_id, safe_exception(exc))
            state.current=None
