from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def mode_keyboard(token: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎧 𝗔𝗨𝗗𝗜𝗢",
                callback_data=f"music:mode:audio:{token}",
            ),
            InlineKeyboardButton(
                "🎙 𝗩𝗖",
                callback_data=f"music:mode:vc:{token}",
            ),
        ],
        [
            InlineKeyboardButton(
                "✕ 𝗖𝗔𝗡𝗖𝗘𝗟",
                callback_data=f"music:mode:cancel:{token}",
            )
        ],
    ])


def player_keyboard(paused: bool):
    pause_text = "▶️ 𝗥𝗘𝗦𝗨𝗠𝗘" if paused else "⏸ 𝗣𝗔𝗨𝗦𝗘"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                pause_text,
                callback_data="music:player:pause_resume",
            ),
            InlineKeyboardButton(
                "⏭ 𝗦𝗞𝗜𝗣",
                callback_data="music:player:skip",
            ),
        ],
        [
            InlineKeyboardButton(
                "📋 𝗤𝗨𝗘𝗨𝗘",
                callback_data="music:player:queue",
            ),
            InlineKeyboardButton(
                "🎵 𝗡𝗢𝗪",
                callback_data="music:player:now",
            ),
        ],
        [
            InlineKeyboardButton(
                "⏹ 𝗦𝗧𝗢𝗣",
                callback_data="music:player:stop",
            )
        ],
    ])


def queue_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⏭ 𝗦𝗞𝗜𝗣",
                callback_data="music:player:skip",
            ),
            InlineKeyboardButton(
                "⏹ 𝗦𝗧𝗢𝗣",
                callback_data="music:player:stop",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎵 𝗡𝗢𝗪 𝗣𝗟𝗔𝗬𝗜𝗡𝗚",
                callback_data="music:player:now",
            )
        ],
    ])
