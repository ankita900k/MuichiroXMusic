import logging
import os
from pathlib import Path

from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls import filters as tg_filters
from pytgcalls.types import AudioQuality, MediaStream, StreamEnded

from .security import safe_exception

log = logging.getLogger(__name__)


class VoiceChat:
    def __init__(self, api_id: int, api_hash: str, session_string: str):
        if not api_id or not api_hash:
            raise RuntimeError("API_ID/API_HASH are not configured")
        if not session_string:
            raise RuntimeError(
                "SESSION_STRING is empty. A Pyrogram user session is required."
            )

        self.client = Client(
            "muichiro_music_vc",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
        )
        self.calls = PyTgCalls(self.client)
        self.on_ended = None
        self.started = False
        self._dialogs_warmed = False
        self._joined_groups: set[int] = set()

    async def start(self):
        if self.started:
            return

        await self.client.start()
        me = await self.client.get_me()
        log.info(
            "Music VC assistant connected: @%s (%s)",
            me.username or "no_username",
            me.id,
        )

        # PyTgCalls ultimately asks Pyrogram to resolve the group ID.  On a
        # fresh Render restart, Pyrogram's local peer cache can be empty even
        # though the assistant is already a member of the group.  Loading the
        # dialogs once repopulates that cache and prevents:
        #   ValueError: Peer id invalid: -100...
        await self._warm_dialog_cache()

        await self.calls.start()
        self.started = True

    async def _warm_dialog_cache(self, target_chat_id: int | None = None):
        if self._dialogs_warmed and target_chat_id is None:
            return

        found = target_chat_id is None
        try:
            async for dialog in self.client.get_dialogs():
                if target_chat_id is not None and dialog.chat:
                    if dialog.chat.id == target_chat_id:
                        found = True
                        break
        except Exception as exc:
            log.warning("Could not warm Pyrogram peer cache (%s)", safe_exception(exc))
            if target_chat_id is None:
                return

        if target_chat_id is None:
            self._dialogs_warmed = True
        elif found:
            log.debug("Pyrogram peer cache contains chat %s", target_chat_id)

    async def _ensure_peer_cached(self, chat_id: int):
        # Fast path: if Pyrogram already knows this peer, nothing else is
        # needed.  Do not expose resolve_peer() to the caller or swallow a
        # bad peer ID; PyTgCalls will perform the final resolution itself.
        try:
            await self.client.resolve_peer(chat_id)
            return
        except (KeyError, ValueError):
            pass

        # Fresh sessions commonly need this after a Render restart.
        await self._warm_dialog_cache(chat_id)

        try:
            await self.client.resolve_peer(chat_id)
        except (KeyError, ValueError) as exc:
            raise RuntimeError(
                "The music assistant cannot resolve this group. "
                "Make sure the assistant account is a member of the group "
                "and has access to its voice chat, then try /play again."
            ) from exc

    async def ensure_joined(self, chat_id: int, invite_link: str):
        """Ensure the Pyrogram assistant is a member of the target group.

        The invite link is created dynamically by the Telegram bot for the
        current group, so no permanent invite link needs to be stored.
        """
        if not invite_link:
            raise RuntimeError("No invite link was provided for the assistant")

        # Fast path: once this group has been verified during this process,
        # avoid a Telegram membership lookup for every queued track.
        if chat_id in self._joined_groups:
            return False

        # Check membership first. This also warms Pyrogram's peer cache when
        # the assistant is already present.
        try:
            member = await self.client.get_chat_member(chat_id, "me")
            status = getattr(member, "status", "")
            if status not in {"left", "kicked", "banned"}:
                await self._warm_dialog_cache(chat_id)
                self._joined_groups.add(chat_id)
                return False
        except Exception as exc:
            log.debug("Assistant membership check for %s failed (%s)", chat_id, safe_exception(exc))

        log.info("Assistant is not in %s; joining with the generated invite link", chat_id)
        try:
            await self.client.join_chat(invite_link)
        except Exception as exc:
            # It may have joined between the membership check and join call.
            try:
                member = await self.client.get_chat_member(chat_id, "me")
                status = getattr(member, "status", "")
                if status not in {"left", "kicked", "banned"}:
                    await self._warm_dialog_cache(chat_id)
                    self._joined_groups.add(chat_id)
                    return True
            except Exception:
                pass
            raise RuntimeError(
                "The music assistant could not join this group using the generated invite link."
            ) from None

        # Force the joined group's peer into the local cache before PyTgCalls.
        await self._warm_dialog_cache(chat_id)
        self._joined_groups.add(chat_id)
        return True

    async def play(self, chat_id: int, path: str):
        if not self.started:
            raise RuntimeError("Music voice layer is not started")
        if not path or not os.path.exists(path):
            raise ValueError("Prepared audio file is missing")

        await self._ensure_peer_cached(chat_id)

        stream = MediaStream(
            str(Path(path).resolve()),
            AudioQuality.HIGH,
            video_flags=MediaStream.Flags.IGNORE,
        )
        await self.calls.play(chat_id, stream)

    async def pause(self, chat_id: int):
        await self.calls.pause(chat_id)

    async def resume(self, chat_id: int):
        await self.calls.resume(chat_id)

    async def leave(self, chat_id: int):
        try:
            await self.calls.leave_call(chat_id)
        except Exception as exc:
            log.warning("Music VC leave failed for %s (%s)", chat_id, safe_exception(exc))

    def register_stream_end(self, callback):
        self.on_ended = callback

        @self.calls.on_update(tg_filters.stream_end())
        async def _stream_end(_, update: StreamEnded):
            if self.on_ended:
                await self.on_ended(update.chat_id)

    async def stop(self):
        for chat_id in list(self._active_chat_ids()):
            await self.leave(chat_id)

        try:
            await self.client.stop()
        except Exception:
            pass

        self.started = False
        self._dialogs_warmed = False
        self._joined_groups.clear()

    def _active_chat_ids(self):
        try:
            from .manager import player_manager
            return player_manager.active_chats()
        except Exception:
            return []
