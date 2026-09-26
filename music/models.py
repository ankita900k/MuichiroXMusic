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
    control_message_id: Optional[int] = None
    transition: bool = False
    ignore_stream_end_until: float = 0.0
