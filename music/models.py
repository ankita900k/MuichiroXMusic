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
    source_stream_url: Optional[str] = None
    video_id: Optional[str] = None
    provider: str = "hep_library"
    isrc: Optional[str] = None
    album: Optional[str] = None


@dataclass
class PlayerState:
    queue: list[Track] = field(default_factory=list)
    current: Optional[Track] = None
    paused: bool = False
    control_message_id: Optional[int] = None
    control_is_photo: bool = False
    transition: bool = False
    ignore_stream_end_until: float = 0.0
    started_at: float = 0.0
    position_offset: float = 0.0
    paused_position: float = 0.0
    ui_task: object | None = None
    ui_generation: int = 0
    playback_path: Optional[str] = None
    preload_task: object | None = None
    preload_for: Optional[Track] = None
    loop_infinite: bool = False
    loop_remaining: int = 0
