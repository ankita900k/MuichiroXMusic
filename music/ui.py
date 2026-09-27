from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def mode_keyboard(token: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎧 𝗔𝗨𝗗𝗜𝗢", callback_data=f"music:mode:audio:{token}"),
            InlineKeyboardButton("🎙 𝗩𝗖", callback_data=f"music:mode:vc:{token}"),
        ],
        [InlineKeyboardButton("✕ 𝗖𝗔𝗡𝗖𝗘𝗟", callback_data=f"music:mode:cancel:{token}")],
    ])


def _progress_buttons(position: float, duration: int | None):
    if not duration or duration <= 0:
        return [[InlineKeyboardButton("🔘  --:--  /  --:--", callback_data="music:player:seek_menu")]]

    ratio = min(1.0, max(0.0, position / duration))
    # Eight compact, tappable segments give the familiar premium-player
    # timeline while keeping the keyboard usable on small phones.
    parts = 8
    current = min(parts - 1, int(ratio * parts))
    row = []
    for i in range(parts):
        icon = "●" if i == current else "─"
        row.append(
            InlineKeyboardButton(
                icon,
                callback_data=f"music:player:seek:{i}:{parts}",
            )
        )
    return [row]


def _time_button(position: float, duration: int | None):
    def fmt(seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    if duration and duration > 0:
        return InlineKeyboardButton(
            f"⏱ {fmt(position)} / {fmt(duration)}",
            callback_data="music:player:seek_menu",
        )
    return InlineKeyboardButton("⏱ --:-- / --:--", callback_data="music:player:seek_menu")


def player_keyboard(paused: bool, position: float = 0.0, duration: int | None = None):
    pause_text = "▶️ 𝗥𝗘𝗦𝗨𝗠𝗘" if paused else "⏸ 𝗣𝗔𝗨𝗦𝗘"
    rows = _progress_buttons(position, duration)
    rows.append([_time_button(position, duration)])
    rows.extend([
        [
            InlineKeyboardButton("⏪ 10s", callback_data="music:player:seek_rel:-10"),
            InlineKeyboardButton(pause_text, callback_data="music:player:pause_resume"),
            InlineKeyboardButton("10s ⏩", callback_data="music:player:seek_rel:10"),
        ],
        [
            InlineKeyboardButton("⏭ 𝗦𝗞𝗜𝗣", callback_data="music:player:skip"),
            InlineKeyboardButton("📋 𝗤𝗨𝗘𝗨𝗘", callback_data="music:player:queue"),
            InlineKeyboardButton("⏹", callback_data="music:player:stop"),
        ],
    ])
    return InlineKeyboardMarkup(rows)


def seek_keyboard(position: float, duration: int | None):
    def fmt(seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    row1 = [
        InlineKeyboardButton("−30s", callback_data="music:player:seek_rel:-30"),
        InlineKeyboardButton("−10s", callback_data="music:player:seek_rel:-10"),
        InlineKeyboardButton("+10s", callback_data="music:player:seek_rel:10"),
        InlineKeyboardButton("+30s", callback_data="music:player:seek_rel:30"),
    ]
    row2 = [
        InlineKeyboardButton("◀ 10%", callback_data="music:player:seek_pct:10"),
        InlineKeyboardButton("25%", callback_data="music:player:seek_pct:25"),
        InlineKeyboardButton("50%", callback_data="music:player:seek_pct:50"),
        InlineKeyboardButton("75% ▶", callback_data="music:player:seek_pct:75"),
    ]
    row3 = [InlineKeyboardButton(f"⏱ {fmt(position)} / {fmt(duration or 0)}", callback_data="music:player:seek_menu")]
    row4 = [InlineKeyboardButton("↩️ 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗣𝗟𝗔𝗬𝗘𝗥", callback_data="music:player:now")]
    return InlineKeyboardMarkup([row1, row2, row3, row4])


def queue_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏭ 𝗦𝗞𝗜𝗣", callback_data="music:player:skip"),
            InlineKeyboardButton("⏹ 𝗦𝗧𝗢𝗣", callback_data="music:player:stop"),
        ],
        [InlineKeyboardButton("🎵 𝗡𝗢𝗪 𝗣𝗟𝗔𝗬𝗜𝗡𝗚", callback_data="music:player:now")],
    ])
