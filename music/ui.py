from telegram import InlineKeyboardButton, InlineKeyboardMarkup


_BAR = "━"
_DOT = "•"


def _format_time(seconds: float | int | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _progress_bar(position: float | int | None, duration: float | int | None, width: int = 13) -> str:
    if not duration or duration <= 0:
        return "━━━━━━━━━━━━━"
    ratio = max(0.0, min(1.0, float(position or 0) / float(duration)))
    index = min(width - 1, int(round(ratio * (width - 1))))
    return _BAR * index + _DOT + _BAR * (width - index - 1)


def player_keyboard(paused: bool, position: float | int | None = None, duration: float | int | None = None, media_type: str = "audio"):
    pause_text = "▶️" if paused else "⏸️"
    tracker = f"{_format_time(position)}  {_progress_bar(position, duration)}  {_format_time(duration)}"
    controls = [
        InlineKeyboardButton("⏹️", callback_data="music:player:stop", style="danger"),
    ]
    if media_type != "video":
        controls.append(InlineKeyboardButton("⏪", callback_data="music:player:rewind"))
    controls.append(InlineKeyboardButton(pause_text, callback_data="music:player:pause_resume", style="primary"))
    if media_type != "video":
        controls.append(InlineKeyboardButton("⏩", callback_data="music:player:forward"))
    controls.append(InlineKeyboardButton("📋", callback_data="music:player:queue"))
    rows = [[InlineKeyboardButton(tracker, callback_data="music:player:noop")], controls]
    if media_type != "video":
        rows.append([InlineKeyboardButton("♡ 𝗙𝗔𝗩𝗢𝗨𝗥𝗜𝗧𝗘", callback_data="music:player:favorite")])
    return InlineKeyboardMarkup(rows)


def queue_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎧 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗣𝗟𝗔𝗬𝗘𝗥", callback_data="music:player:now")]])


def mode_keyboard(token: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎧 𝗔𝗨𝗗𝗜𝗢", callback_data=f"music:mode:audio:{token}"),
            InlineKeyboardButton("🎙 𝗩𝗖", callback_data=f"music:mode:vc:{token}"),
        ],
        [InlineKeyboardButton("✕ 𝗖𝗔𝗡𝗖𝗘𝗟", callback_data=f"music:mode:cancel:{token}")],
    ])
