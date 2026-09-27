from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Track:
    query: str
    title: str
    requested_by: int
    requested_name: str
    source_url: str
    artist: str = "Unknown Artist"
    thumbnail: Optional[str] = None
    duration: Optional[int] = None
    media_path: Optional[str] = None


@dataclass
class PlayerState:
    queue: list[Track] = field(default_factory=list)
    current: Optional[Track] = None
    paused: bool = False

    # Telegram player message.
    control_message_id: Optional[int] = None
    control_is_photo: bool = False

    # Playback clock. These are monotonic-time based so wall-clock changes
    # cannot make the progress bar jump.
    started_at: float = 0.0
    position_offset: float = 0.0
    paused_position: float = 0.0

    # Temporary file currently fed to PyTgCalls. Normally this is the
    # original downloaded file; after seeking it can be a short segment.
    playback_path: Optional[str] = None

    transition: bool = False
    ignore_stream_end_until: float = 0.0
    ui_task: object = None
    preload_task: object = None
    preload_for: Optional[Track] = None
    ui_generation: int = 0

    def position(self, now: float) -> float:
        if not self.current:
            return 0.0
        if self.paused:
            return max(0.0, self.paused_position)
        return max(0.0, self.position_offset + max(0.0, now - self.started_at))
