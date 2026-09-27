import asyncio
import io
import logging
import os
import time
import uuid
from html import escape

import aiohttp
from telegram import InputFile, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

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

    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.read()
                    if data:
                        return io.BytesIO(data)
    except Exception:
        pass

    return None


def _now_text(state):
    track = state.current
    return (
        "🎧 <b>𝗡𝗢𝗪 𝗣𝗟𝗔𝗬𝗜𝗡𝗚</b>\n\n"
        f"🎵 <b>{escape(track.title)}</b>\n"
        f"👤 {escape(track.requested_name)}\n"
        f"📋 Queue: <b>{len(state.queue)}</b>"
    )


async def _send_now_playing(
    bot,
    chat_id,
    state,
    old_message=None,
):
    text = _now_text(state)
    keyboard = player_keyboard(state.paused)
    thumb = await _download_thumbnail(state.current.thumbnail)

    if old_message:
        try:
            if thumb:
                thumb.seek(0)
                await old_message.edit_media(
                    media=InputMediaPhoto(
                        media=thumb,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    )
                )
                await old_message.edit_reply_markup(
                    reply_markup=keyboard
                )
                return old_message

            await old_message.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
            return old_message
        except Exception:
            pass

    if thumb:
        thumb.seek(0)
        message = await bot.send_photo(
            chat_id=chat_id,
            photo=InputFile(thumb, filename="thumbnail.jpg"),
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    else:
        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    state.control_message_id = message.message_id
    return message


async def _start_track(chat_id: int, track: Track, replacing=False):
    state = player_manager.get(chat_id)
    previous = state.current
    state.transition = replacing

    if replacing:
        state.ignore_stream_end_until = (
            asyncio.get_running_loop().time() + 6.0
        )

    state.current = track
    state.paused = False

    try:
        if not track.media_path or not os.path.exists(track.media_path):
            track.media_path = await annie.prepare_audio(
                track.source_url or track.query
            )

        await runtime.voice.play(chat_id, track.media_path)
    except Exception:
        if track.media_path and track.media_path != getattr(
            previous, "media_path", None
        ):
            try:
                os.remove(track.media_path)
            except OSError:
                pass
            track.media_path = None

        state.current = previous
        state.paused = False if previous is None else state.paused
        raise
    finally:
        state.transition = False

    return state


async def advance_to_next(
    chat_id: int,
    bot=None,
    old_message=None,
):
    state = player_manager.get(chat_id)
    old_track = state.current
    next_track = player_manager.pop_next(chat_id)

    if not next_track:
        await runtime.voice.leave(chat_id)
        state.current = None
        state.paused = False

        if old_track and old_track.media_path:
            try:
                os.remove(old_track.media_path)
            except OSError:
                pass

        return False

    await _start_track(chat_id, next_track, replacing=True)

    if old_track and old_track.media_path:
        if old_track.media_path != next_track.media_path:
            try:
                os.remove(old_track.media_path)
            except OSError:
                pass

    if bot:
        await _send_now_playing(
            bot,
            chat_id,
            state,
            old_message=old_message,
        )

    return True


async def _make_track(update: Update, query: str) -> Track:
    info = await resolve(query)
    duration = info.get("duration")

    return Track(
        query=query,
        title=info.get("title") or query,
        requested_by=(
            update.effective_user.id
            if update.effective_user
            else 0
        ),
        requested_name=(
            update.effective_user.full_name
            if update.effective_user
            else "Unknown"
        ),
        source_url=info.get("webpage_url") or query,
        artist=info.get("artist") or "Unknown Artist",
        thumbnail=info.get("thumbnail"),
        duration=int(duration) if duration else None,
    )


async def _is_chat_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    """Return True when the requesting user is a group administrator/owner."""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception as exc:
        log.warning(
            "Could not verify music control permission for %s/%s: %s",
            chat_id,
            user_id,
            type(exc).__name__,
        )
        return False


async def _require_music_admin(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    reply=None,
) -> bool:
    """Allow playback-changing music controls only to group admins."""
    if await _is_chat_admin(context, chat_id, user_id):
        return True

    message = (
        "🔒 <b>Admin-only music control</b>\n\n"
        "Only group admins can pause, resume, skip, seek or stop playback."
    )

    if reply is not None:
        try:
            await reply(message, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    return False


async def _ensure_vc_peer(chat_id: int):
    """Resolve the Telegram supergroup in the Pyrogram user session first.

    PyTgCalls can raise `Peer id invalid` when its Pyrogram client has not
    resolved the -100... peer yet.  Resolving it here keeps the existing
    VoiceChat/PyTgCalls playback path unchanged.
    """
    voice = runtime.voice
    if voice is None:
        raise RuntimeError("Music voice layer is not initialized")

    client = getattr(voice, "client", None)
    if client is None:
        raise RuntimeError("Pyrogram music client is not available")

    try:
        await client.resolve_peer(chat_id)
    except Exception as exc:
        log.warning("Could not resolve VC peer %s: %s", chat_id, exc)
        raise


async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Play a track directly in the voice chat."""
    message = update.effective_message
    if not message:
        return

    query = " ".join(context.args).strip()
    if not query:
        await message.reply_text(
            "🎙 <b>Usage</b>\n<code>/play song name</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    searching = await message.reply_text(
        "🔎 <b>Finding your track for VC…</b>",
        parse_mode=ParseMode.HTML,
    )

    try:
        track = await _make_track(update, query)
        chat_id = update.effective_chat.id

        async with player_manager.lock(chat_id):
            state = player_manager.get(chat_id)

            if state.current is not None:
                position = player_manager.enqueue(chat_id, track)
                try:
                    await searching.edit_text(
                        "➕ <b>𝗔𝗗𝗗𝗘𝗗 𝗧𝗢 𝗩𝗖 𝗤𝗨𝗘𝗨𝗘</b>\n\n"
                        f"🎵 <b>{escape(track.title)}</b>\n"
                        f"📍 Position: <b>#{position}</b>\n"
                        f"📋 Waiting: <b>{len(state.queue)}</b>",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
                return

            await _ensure_vc_peer(chat_id)
            await _start_track(chat_id, track)

            await _send_now_playing(
                context.bot,
                chat_id,
                state,
                old_message=searching,
            )

    except Exception as exc:
        log.exception("VC playback failed")
        try:
            await searching.edit_text(
                "❌ <b>𝗩𝗖 𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗙𝗔𝗜𝗟𝗘𝗗</b>\n\n"
                f"<code>{escape(type(exc).__name__ + ': ' + str(exc))}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await message.reply_text(
                "❌ <b>VC playback failed.</b>\n"
                f"<code>{escape(str(exc))}</code>",
                parse_mode=ParseMode.HTML,
            )


async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a track as Telegram audio, independently from VC playback."""
    message = update.effective_message
    if not message:
        return

    query = " ".join(context.args).strip()
    if not query:
        await message.reply_text(
            "🎧 <b>Usage</b>\n<code>/audio song name</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    searching = await message.reply_text(
        "🔎 <b>Finding your audio…</b>",
        parse_mode=ParseMode.HTML,
    )

    try:
        track = await _make_track(update, query)
        await _send_audio(query, track, update)
        try:
            await searching.delete()
        except Exception:
            pass
    except Exception as exc:
        try:
            await searching.edit_text(
                "❌ <b>Audio delivery failed.</b>\n"
                f"<code>{escape(type(exc).__name__ + ': ' + str(exc))}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await message.reply_text(
                "❌ <b>Audio delivery failed.</b>\n"
                f"<code>{escape(str(exc))}</code>",
                parse_mode=ParseMode.HTML,
            )


async def _send_audio(query, track, update):
    # Keep the original working Telegram/Annie audio delivery path.
    # Telegram fetches the Annie audio URL directly instead of using a
    # locally downloaded temporary file.
    thumb = await _download_thumbnail(track.thumbnail)
    kwargs = {
        "audio": annie.audio_url(track.source_url or query),
        "title": track.title,
        "performer": track.artist or "Unknown Artist",
    }
    if track.duration:
        kwargs["duration"] = track.duration
    if thumb:
        thumb.seek(0)
        # Telegram requires an actual JPEG thumbnail for audio messages.
        kwargs["thumbnail"] = InputFile(thumb, filename="thumbnail.jpg")

    await update.effective_message.reply_audio(**kwargs)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    call = update.callback_query
    if not call:
        return

    data = call.data or ""

    if data.startswith("music:mode:"):
        _, _, mode, token = data.split(":", 3)
        item = pending.pop(token, None)

        if not item:
            await call.answer(
                "This playback request expired.",
                show_alert=True,
            )
            return

        track, _ = item
        chat_id = call.message.chat.id if call.message else None

        if mode == "cancel":
            await call.answer(
                "✕ Playback selection cancelled.",
                show_alert=True,
            )
            try:
                await call.message.delete()
            except Exception:
                pass
            return

        if mode == "audio":
            await call.answer(
                "🎧 Audio selected. Preparing the audio file…",
                show_alert=True,
            )
            try:
                await _send_audio(track.query, track, update)
            except Exception as exc:
                await call.message.reply_text(
                    "❌ <b>Audio playback failed.</b>\n"
                    f"<code>{escape(str(exc))}</code>",
                    parse_mode=ParseMode.HTML,
                )
            return

        if mode != "vc" or chat_id is None:
            await call.answer(
                "❌ Unknown playback mode.",
                show_alert=True,
            )
            return

        await call.answer(
            "🎙 VC selected. Starting playback in the voice chat…",
            show_alert=True,
        )

        async with player_manager.lock(chat_id):
            state = player_manager.get(chat_id)

            if state.current is not None:
                position = player_manager.enqueue(chat_id, track)
                await call.answer(
                    f"➕ Added to the queue at position #{position}.",
                    show_alert=True,
                )
                try:
                    await call.message.edit_text(
                        "➕ <b>𝗔𝗗𝗗𝗘𝗗 𝗧𝗢 𝗤𝗨𝗘𝗨𝗘</b>\n\n"
                        f"🎵 <b>{escape(track.title)}</b>\n"
                        f"📍 Position: <b>#{position}</b>\n"
                        f"📋 Waiting: <b>{len(state.queue)}</b>",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
                return

            try:
                await _ensure_vc_peer(chat_id)
                await _start_track(chat_id, track)
                await _send_now_playing(
                    context.bot,
                    chat_id,
                    state,
                    old_message=call.message,
                )
            except Exception as exc:
                state.current = None
                state.paused = False
                try:
                    await call.message.edit_text(
                        "❌ <b>𝗩𝗖 𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗙𝗔𝗜𝗟𝗘𝗗</b>\n\n"
                        f"<code>{escape(type(exc).__name__ + ': ' + str(exc))}</code>",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
            return

    if not data.startswith("music:player:"):
        return

    action = data.split(":", 2)[2]
    chat_id = call.message.chat.id

    # Playback-changing controls are admin-only. Informational controls
    # such as Queue/Now remain available to everyone.
    protected_actions = {
        "pause_resume",
        "skip",
        "stop",
        "seek",
        "rewind",
        "forward",
        "previous",
        "shuffle",
        "repeat",
        "volume",
    }

    if action in protected_actions:
        user = call.from_user
        if not user or not await _require_music_admin(
            context,
            chat_id,
            user.id,
        ):
            await call.answer(
                "🔒 Music controls are restricted to group admins.",
                show_alert=True,
            )
            return

    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)

        if action == "pause_resume":
            if not state.current:
                await call.answer(
                    "Nothing is playing.",
                    show_alert=True,
                )
                return

            if state.paused:
                await runtime.voice.resume(chat_id)
                state.paused = False
                await call.answer("▶️ Resumed")
            else:
                await runtime.voice.pause(chat_id)
                state.paused = True
                await call.answer("⏸ Paused")

            try:
                await call.message.edit_reply_markup(
                    reply_markup=player_keyboard(state.paused)
                )
            except Exception:
                pass
            return

        if action == "skip":
            if not state.current:
                await call.answer(
                    "Nothing is playing.",
                    show_alert=True,
                )
                return

            try:
                has_next = await advance_to_next(
                    chat_id,
                    bot=context.bot,
                    old_message=call.message,
                )
                await call.answer(
                    "⏭ Skipped"
                    if has_next
                    else "⏹ Queue finished"
                )
            except Exception as exc:
                state.current = None
                state.paused = False
                await call.answer(
                    "Could not start next track.",
                    show_alert=True,
                )
                try:
                    await call.message.edit_text(
                        "❌ <b>Next track failed.</b>\n"
                        f"<code>{escape(str(exc))}</code>",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
            return

        if action == "queue":
            await call.answer(
                "📋 Opening the current music queue…",
                show_alert=True,
            )
            if not state.queue:
                text = "📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\nQueue is empty."
            else:
                lines = [
                    f"<b>{i:02}</b> · {escape(t.title)}"
                    for i, t in enumerate(state.queue[:15], 1)
                ]
                text = "📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\n" + "\n".join(lines)
                if len(state.queue) > 15:
                    text += (
                        f"\n\n… and <b>{len(state.queue)-15}</b> more."
                    )

            try:
                await call.message.edit_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=queue_keyboard(),
                )
            except Exception:
                pass
            return

        if action == "now":
            if not state.current:
                await call.answer(
                    "Nothing is playing.",
                    show_alert=True,
                )
                return

            await call.answer(
                "🎵 Showing the currently playing track…",
                show_alert=True,
            )
            await _send_now_playing(
                context.bot,
                chat_id,
                state,
                old_message=call.message,
            )
            return

        if action == "stop":
            state.transition = True
            state.ignore_stream_end_until = (
                asyncio.get_running_loop().time() + 6.0
            )

            try:
                await runtime.voice.leave(chat_id)
            finally:
                paths = []
                if state.current and state.current.media_path:
                    paths.append(state.current.media_path)
                paths.extend(
                    t.media_path
                    for t in state.queue
                    if t.media_path
                )

                state.current = None
                state.queue.clear()
                state.paused = False
                state.transition = False

                for path in paths:
                    if path:
                        try:
                            os.remove(path)
                        except OSError:
                            pass

            await call.answer("⏹ Stopped")
            try:
                await call.message.edit_text(
                    "⏹ <b>𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗦𝗧𝗢𝗣𝗣𝗘𝗗</b>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    state = player_manager.get(update.effective_chat.id)
    if not state.queue:
        await message.reply_text(
            "📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\nQueue is empty.",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = [
        f"<b>{i:02}</b> · {escape(t.title)} — "
        f"{escape(t.requested_name)}"
        for i, t in enumerate(state.queue[:20], 1)
    ]
    extra = (
        f"\n\n… and <b>{len(state.queue)-20}</b> more."
        if len(state.queue) > 20
        else ""
    )
    await message.reply_text(
        "📋 <b>𝗤𝗨𝗘𝗨𝗘</b>\n\n" + "\n".join(lines) + extra,
        parse_mode=ParseMode.HTML,
    )


async def now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message:
        return

    state = player_manager.get(update.effective_chat.id)
    if not state.current:
        await update.effective_message.reply_text(
            "🎵 Nothing is playing."
        )
        return

    await _send_now_playing(
        context.bot,
        update.effective_chat.id,
        state,
        old_message=None,
    )


async def skip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    user = update.effective_user
    if not user:
        return

    if not await _require_music_admin(
        context,
        update.effective_chat.id,
        user.id,
        reply=message.reply_text,
    ):
        return

    chat_id = update.effective_chat.id
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        if not state.current:
            await message.reply_text("Nothing is playing.")
            return

        try:
            if await advance_to_next(
                chat_id,
                bot=context.bot,
            ):
                await message.reply_text(
                    "⏭ <b>Skipped to the next track.</b>",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await message.reply_text(
                    "⏹ <b>Queue finished.</b>",
                    parse_mode=ParseMode.HTML,
                )
        except Exception as exc:
            state.current = None
            state.paused = False
            await message.reply_text(
                "❌ <b>Could not start next track.</b>\n"
                f"<code>{escape(str(exc))}</code>",
                parse_mode=ParseMode.HTML,
            )


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    user = update.effective_user
    if not user:
        return

    if not await _require_music_admin(
        context,
        update.effective_chat.id,
        user.id,
        reply=message.reply_text,
    ):
        return

    chat_id = update.effective_chat.id
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        if not state.current:
            await message.reply_text("Nothing is playing.")
            return

        await runtime.voice.pause(chat_id)
        state.paused = True
        await _send_now_playing(
            context.bot,
            chat_id,
            state,
            old_message=None,
        )


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    user = update.effective_user
    if not user:
        return

    if not await _require_music_admin(
        context,
        update.effective_chat.id,
        user.id,
        reply=message.reply_text,
    ):
        return

    chat_id = update.effective_chat.id
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        if not state.current:
            await message.reply_text("Nothing is playing.")
            return

        await runtime.voice.resume(chat_id)
        state.paused = False
        await _send_now_playing(
            context.bot,
            chat_id,
            state,
            old_message=None,
        )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    user = update.effective_user
    if not user:
        return

    if not await _require_music_admin(
        context,
        update.effective_chat.id,
        user.id,
        reply=message.reply_text,
    ):
        return

    chat_id = update.effective_chat.id
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        state.transition = True
        state.ignore_stream_end_until = (
            asyncio.get_running_loop().time() + 6.0
        )

        try:
            await runtime.voice.leave(chat_id)
        finally:
            paths = []
            if state.current and state.current.media_path:
                paths.append(state.current.media_path)
            paths.extend(
                t.media_path for t in state.queue if t.media_path
            )

            state.current = None
            state.queue.clear()
            state.paused = False
            state.transition = False

            for path in paths:
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

        await message.reply_text(
            "⏹ <b>𝗣𝗟𝗔𝗬𝗕𝗔𝗖𝗞 𝗦𝗧𝗢Ｐ𝗣𝗘𝗗</b>",
            parse_mode=ParseMode.HTML,
        )


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
        CallbackQueryHandler(
            callback,
            pattern=r"^music:",
        ),
    ]


async def on_stream_end(chat_id: int, bot):
    async with player_manager.lock(chat_id):
        state = player_manager.get(chat_id)
        now = asyncio.get_running_loop().time()

        if state.transition or now < state.ignore_stream_end_until:
            log.info(
                "Ignored transition stream-end event for chat %s",
                chat_id,
            )
            return

        if state.current is None:
            return

        try:
            if await advance_to_next(chat_id, bot=bot):
                log.info(
                    "Auto-played next queued track in chat %s",
                    chat_id,
                )
            else:
                log.info("Queue finished in chat %s", chat_id)
        except Exception:
            log.exception(
                "Failed to auto-play next track in chat %s",
                chat_id,
            )
            state.current = None
            state.paused = False
