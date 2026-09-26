# ==========================================
# 🎯 MUICHIRO CONNECT 4
# ==========================================

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from html import escape


# ==========================================
# ACTIVE GAMES
# ==========================================

connect4_games = {}


# ==========================================
# GAME SETTINGS
# ==========================================

ROWS = 6
COLS = 7

EMPTY = "⚪"
RED = "🔴"
YELLOW = "🟡"


# ==========================================
# PLAYER MENTION
# ==========================================

def player_mention(user_id, name):
    safe_name = escape(name or "Player")

    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'


# ==========================================
# CREATE EMPTY BOARD
# ==========================================

def create_board():

    return [
        [EMPTY for _ in range(COLS)]
        for _ in range(ROWS)
    ]


# ==========================================
# BOARD DISPLAY
# ==========================================

def board_text(board):

    lines = []

    for row in board:
        lines.append(" ".join(row))

    lines.append("")
    lines.append("1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣")

    return "\n".join(lines)


# ==========================================
# CHECK WIN
# ==========================================

def check_win(board, row, col, piece):

    directions = [
        (0, 1),   # Horizontal
        (1, 0),   # Vertical
        (1, 1),   # Diagonal \
        (1, -1),  # Diagonal /
    ]

    for dr, dc in directions:

        count = 1

        # Forward
        r = row + dr
        c = col + dc

        while (
            0 <= r < ROWS
            and 0 <= c < COLS
            and board[r][c] == piece
        ):
            count += 1
            r += dr
            c += dc

        # Backward
        r = row - dr
        c = col - dc

        while (
            0 <= r < ROWS
            and 0 <= c < COLS
            and board[r][c] == piece
        ):
            count += 1
            r -= dr
            c -= dc

        if count >= 4:
            return True

    return False


# ==========================================
# CHECK DRAW
# ==========================================

def check_draw(board):

    return all(
        board[0][col] != EMPTY
        for col in range(COLS)
    )


# ==========================================
# COLUMN BUTTONS
# ==========================================

def game_keyboard(chat_id):

    buttons = []

    for col in range(COLS):

        buttons.append(
            InlineKeyboardButton(
                str(col + 1),
                callback_data=f"c4_move:{chat_id}:{col}"
            )
        )

    keyboard = [
        buttons,
        [
            InlineKeyboardButton(
                "❌ End Game",
                callback_data=f"c4_cancel:{chat_id}"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# ==========================================
# GAME MESSAGE
# ==========================================

def build_game_text(game):

    board = game["board"]

    current_index = game["turn"]

    current_player = game["players"][current_index]

    current_name = game["names"].get(
        current_player,
        "Player"
    )

    current_piece = game["pieces"][current_player]

    player1 = game["players"][0]
    player2 = game["players"][1] if len(game["players"]) > 1 else None

    player1_name = game["names"].get(
        player1,
        "Player"
    )

    player2_name = (
        game["names"].get(player2, "Player")
        if player2
        else "Waiting..."
    )

    return (
        "🎯 <b>MUICHIRO • CONNECT 4</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "🔴 "
        f"{player_mention(player1, player1_name)}\n"

        "🟡 "
        f"{player_mention(player2, player2_name)}\n\n"

        f"{board_text(board)}\n\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"🎮 <b>Turn:</b> "
        f"{player_mention(current_player, current_name)}\n"

        f"{current_piece} <b>Your move!</b>\n"
        "👇 Choose a column."
    )


# ==========================================
# /connect4
# ==========================================

async def connect4_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return

    # ======================================
    # GROUP ONLY
    # ======================================

    if chat.type not in [
        "group",
        "supergroup"
    ]:

        await update.message.reply_text(
            "🎯 <b>Connect 4 can only be played "
            "in groups.</b>",
            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # EXISTING GAME
    # ======================================

    if chat.id in connect4_games:

        await update.message.reply_text(
            "🎯 <b>Connect 4 is already running!</b>\n\n"
            "👥 Join the current match "
            "or wait until it ends.",
            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # CREATE GAME
    # ======================================

    connect4_games[chat.id] = {

        "chat_id": chat.id,

        "creator": user.id,

        "players": [
            user.id
        ],

        "names": {
            user.id: user.full_name
        },

        "pieces": {
            user.id: RED
        },

        "board": create_board(),

        "turn": 0,

        "message_id": None,

        "started": False
    }

    keyboard = [

        [
            InlineKeyboardButton(
                "🎯 Join Connect 4",
                callback_data=f"c4_join:{chat.id}"
            )
        ],

        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=f"c4_cancel:{chat.id}"
            )
        ]

    ]

    msg = await update.message.reply_text(

        "🎯 <b>MUICHIRO • CONNECT 4</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "✨ <b>NEW MATCH CREATED!</b>\n\n"

        f"👑 <b>Creator:</b> "
        f"{player_mention(user.id, user.full_name)}\n\n"

        "🔴 <b>Player 1:</b> "
        f"{player_mention(user.id, user.full_name)}\n"

        "🟡 <b>Player 2:</b> Waiting...\n\n"

        "👥 <b>Players:</b> 1 / 2\n\n"

        "🎯 Connect four of your pieces "
        "in a row to win!\n\n"

        "👇 <b>Waiting for another player...</b>",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )

    connect4_games[
        chat.id
    ]["message_id"] = msg.message_id


# ==========================================
# CALLBACK HANDLER
# ==========================================

async def connect4_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    data = query.data or ""

    # ======================================
    # JOIN
    # ======================================

    if data.startswith("c4_join:"):

        try:
            chat_id = int(
                data.split(":")[1]
            )
        except (ValueError, IndexError):
            return

        game = connect4_games.get(chat_id)

        if not game:

            await query.answer(
                "❌ This game no longer exists.",
                show_alert=True
            )

            return

        user = query.from_user

        # Already joined
        if user.id in game["players"]:

            await query.answer(
                "✅ You are already in this game!",
                show_alert=True
            )

            return

        # Game already has 2 players
        if len(game["players"]) >= 2:

            await query.answer(
                "🚫 This Connect 4 game is full.",
                show_alert=True
            )

            return

        # Add second player
        game["players"].append(
            user.id
        )

        game["names"][user.id] = (
            user.full_name
        )

        game["pieces"][user.id] = YELLOW

        game["started"] = True

        game["turn"] = 0

        await query.edit_message_text(

            build_game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=game_keyboard(
                chat_id
            )
        )

        return

    # ======================================
    # CANCEL
    # ======================================

    if data.startswith("c4_cancel:"):

        try:
            chat_id = int(
                data.split(":")[1]
            )
        except (ValueError, IndexError):
            return

        game = connect4_games.get(chat_id)

        if not game:
            return

        user = query.from_user

        if user.id not in game["players"]:

            await query.answer(
                "🚫 Only players in this game "
                "can end it.",
                show_alert=True
            )

            return

        del connect4_games[chat_id]

        await query.edit_message_text(

            "🛑 <b>CONNECT 4 CANCELLED</b>\n\n"
            "Maybe next time 😎",

            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # MOVE
    # ======================================

    if data.startswith("c4_move:"):

        try:

            parts = data.split(":")

            chat_id = int(parts[1])
            col = int(parts[2])

        except (ValueError, IndexError):

            return

        game = connect4_games.get(chat_id)

        if not game:
            return

        user = query.from_user

        # ==================================
        # ONLY PLAYERS
        # ==================================

        if user.id not in game["players"]:

            await query.answer(
                "🚫 You are not a player in this game.",
                show_alert=True
            )

            return

        # ==================================
        # CURRENT PLAYER
        # ==================================

        current_player = game["players"][
            game["turn"]
        ]

        if user.id != current_player:

            current_name = game["names"].get(
                current_player,
                "Player"
            )

            await query.answer(
                f"⏳ Wait for {current_name}'s turn!",
                show_alert=True
            )

            return

        # ==================================
        # VALID COLUMN
        # ==================================

        if col < 0 or col >= COLS:

            await query.answer(
                "❌ Invalid column.",
                show_alert=True
            )

            return

        # ==================================
        # FIND EMPTY ROW
        # ==================================

        row = None

        for r in range(
            ROWS - 1,
            -1,
            -1
        ):

            if game["board"][r][col] == EMPTY:

                row = r
                break

        # ==================================
        # COLUMN FULL
        # ==================================

        if row is None:

            await query.answer(
                "🚫 That column is full!",
                show_alert=True
            )

            return

        # ==================================
        # PLACE PIECE
        # ==================================

        piece = game["pieces"][user.id]

        game["board"][row][col] = piece

        # ==================================
        # WIN
        # ==================================

        if check_win(
            game["board"],
            row,
            col,
            piece
        ):

            name = game["names"].get(
                user.id,
                "Player"
            )

            await query.edit_message_text(

                "🏆 <b>CONNECT 4 WINNER!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                f"👑 {player_mention(user.id, name)}\n\n"

                f"{piece} <b>Connected four!</b>\n\n"

                f"{board_text(game['board'])}\n\n"

                "🎉 <b>GG everyone!</b>",

                parse_mode=ParseMode.HTML
            )

            del connect4_games[chat_id]

            return

        # ==================================
        # DRAW
        # ==================================

        if check_draw(game["board"]):

            await query.edit_message_text(

                "🤝 <b>CONNECT 4 DRAW!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                f"{board_text(game['board'])}\n\n"

                "😎 The board is completely full!\n"
                "Nobody connected four.",

                parse_mode=ParseMode.HTML
            )

            del connect4_games[chat_id]

            return

        # ==================================
        # NEXT TURN
        # ==================================

        game["turn"] = (
            game["turn"] + 1
        ) % 2

        await query.edit_message_text(

            build_game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=game_keyboard(
                chat_id
            )
        )


# ==========================================
# /endconnect4
# ==========================================

async def endconnect4_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return

    if chat.type not in [
        "group",
        "supergroup"
    ]:

        await update.message.reply_text(
            "🎯 Connect 4 can only be ended "
            "inside a group."
        )

        return

    game = connect4_games.get(
        chat.id
    )

    if not game:

        await update.message.reply_text(
            "❌ There is no active Connect 4 game."
        )

        return

    # ======================================
    # ONLY PLAYERS
    # ======================================

    if user.id not in game["players"]:

        await update.message.reply_text(
            "🚫 <b>Only players in the current "
            "Connect 4 game can end it.</b>",
            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # END GAME
    # ======================================

    del connect4_games[
        chat.id
    ]

    await update.message.reply_text(

        "🛑 <b>CONNECT 4 ENDED</b>\n\n"

        f"👤 Ended by "
        f"{player_mention(user.id, user.full_name)}\n\n"

        "🎯 The current game has been stopped.\n"
        "Start a new game with <b>/connect4</b>.",

        parse_mode=ParseMode.HTML
    )