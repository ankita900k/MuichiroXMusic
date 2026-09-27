import asyncio

from .models import PlayerState, Track


class PlayerManager:
    def __init__(self):
        self.players: dict[int, PlayerState] = {}
        self.locks: dict[int, asyncio.Lock] = {}
        self.ui_locks: dict[int, asyncio.Lock] = {}

    def get(self, chat_id: int) -> PlayerState:
        return self.players.setdefault(chat_id, PlayerState())

    def lock(self, chat_id: int) -> asyncio.Lock:
        return self.locks.setdefault(chat_id, asyncio.Lock())

    def ui_lock(self, chat_id: int) -> asyncio.Lock:
        return self.ui_locks.setdefault(chat_id, asyncio.Lock())

    def enqueue(self, chat_id: int, track: Track) -> int:
        state = self.get(chat_id)
        state.queue.append(track)
        return len(state.queue)

    def pop_next(self, chat_id: int) -> Track | None:
        state = self.get(chat_id)
        return state.queue.pop(0) if state.queue else None

    def clear(self, chat_id: int):
        self.get(chat_id).queue.clear()

    def active_chats(self):
        return list(self.players.keys())


player_manager = PlayerManager()
