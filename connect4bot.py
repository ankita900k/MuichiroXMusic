# ============================================================
# 🔴 MUICHIRO • CONNECT FOUR BOT
# ============================================================

import asyncio
import html
import math
import random

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


# ============================================================
# GAME STORAGE
# ============================================================

connect4_games = {}


# ============================================================
# CONSTANTS
# ============================================================

ROWS = 6
COLS = 7

EMPTY = 0
PLAYER = 1
BOT = 2

DIFFICULTIES = {
    "easy": {
        "name": "Easy",
        "emoji": "🟢",
        "depth": 1,
    },

    "normal": {
        "name": "Normal",
        "emoji": "🟡",
        "depth": 3,
    },

    "hard": {
        "name": "Hard",
        "emoji": "🔴",
        "depth": 5,
    },
}


# ============================================================
# PLAYER MENTION
# ============================================================

def player_mention(user_id, name):

    safe_name = html.escape(
        name or "Player"
    )

    return (
        f'<a href="tg://user?id={user_id}">'
        f'{safe_name}</a>'
    )


# ============================================================
# GAME KEY
# ============================================================

def get_game_key(chat, user):

    # --------------------------------------------------------
    # Group / supergroup:
    # One game per group.
    # --------------------------------------------------------

    if chat.type in (
        "group",
        "supergroup"
    ):

        return (
            "group",
            chat.id
        )

    # --------------------------------------------------------
    # Private chat:
    # One game per user.
    # --------------------------------------------------------

    return (
        "pm",
        user.id
    )


# ============================================================
# CREATE BOARD
# ============================================================

def create_board():

    return [
        [EMPTY for _ in range(COLS)]
        for _ in range(ROWS)
    ]


# ============================================================
# COPY BOARD
# ============================================================

def copy_board(board):

    return [
        row.copy()
        for row in board
    ]


# ============================================================
# BOARD TEXT
# ============================================================

def board_text(board):

    lines = []

    for row in board:

        cells = []

        for cell in row:

            if cell == PLAYER:

                cells.append("🔴")

            elif cell == BOT:

                cells.append("🟡")

            else:

                cells.append("⚪")

        lines.append(
            " ".join(cells)
        )

    lines.append(
        "1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣"
    )

    return "\n".join(lines)


# ============================================================
# COLUMN KEYBOARD
# ============================================================

def game_keyboard(
    game_key,
    board,
    enabled=True
):

    key_text = "|".join(
        str(x)
        for x in game_key
    )

    rows = []

    # --------------------------------------------------------
    # Column buttons
    # --------------------------------------------------------

    column_row = []

    for col in range(COLS):

        # Full column
        if board[0][col] != EMPTY:

            label = "🚫"

        else:

            label = str(col + 1)

        if enabled:

            column_row.append(
                InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"c4m|{key_text}|{col}"
                    )
                )
            )

        else:

            column_row.append(
                InlineKeyboardButton(
                    label,
                    callback_data="c4disabled"
                )
            )

    rows.append(column_row)

    # --------------------------------------------------------
    # End button
    # --------------------------------------------------------

    rows.append(
        [
            InlineKeyboardButton(
                "🛑 End Game",
                callback_data=(
                    f"c4end|{key_text}"
                )
            )
        ]
    )

    return InlineKeyboardMarkup(rows)


# ============================================================
# DIFFICULTY KEYBOARD
# ============================================================

def difficulty_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "🟢 𝐄𝐚𝐬𝐲",
                    callback_data="c4difficulty:easy",
                    style="success"
                )
            ],

            [
                InlineKeyboardButton(
                    "🟡 𝐍𝐨𝐫𝐦𝐚𝐥",
                    callback_data="c4difficulty:normal",
                    style="primary"
                )
            ],

            [
                InlineKeyboardButton(
                    "🔴 𝐇𝐚𝐫𝐝",
                    callback_data="c4difficulty:hard",
                    style="danger"
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data="c4cancelsetup"
                )
            ]

        ]
    )


# ============================================================
# GAME TEXT
# ============================================================

def build_game_text(game):

    difficulty = DIFFICULTIES[
        game["difficulty"]
    ]

    difficulty_name = difficulty["name"]
    difficulty_emoji = difficulty["emoji"]

    board = game["board"]

    player_id = game["player_id"]
    player_name = game["player_name"]

    # --------------------------------------------------------
    # Turn text
    # --------------------------------------------------------

    if game["turn"] == PLAYER:

        turn_text = (
            "🔴 <b>Your turn</b>\n"
            f"👤 {player_mention(player_id, player_name)}"
        )

    else:

        turn_text = (
            "🟡 <b>Muichiro is thinking...</b>"
        )

    return (
        "🔴 <b>𝐌𝐔𝐈𝐂𝐇𝐈𝐑𝐎 • 𝐂𝐎𝐍𝐍𝐄𝐂𝐓 𝟒</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        f"👤 <b>Player:</b> "
        f"{player_mention(player_id, player_name)}\n"

        f"🤖 <b>Muichiro:</b> 🟡\n"

        f"{difficulty_emoji} <b>Difficulty:</b> "
        f"{difficulty_name}\n\n"

        f"{board_text(board)}\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"

        f"{turn_text}\n\n"

        "🎮 <i>Choose a column to drop your piece.</i>"
    )


# ============================================================
# DROP PIECE
# ============================================================

def drop_piece(
    board,
    column,
    piece
):

    if column < 0 or column >= COLS:

        return None

    # Column already full
    if board[0][column] != EMPTY:

        return None

    for row in range(
        ROWS - 1,
        -1,
        -1
    ):

        if board[row][column] == EMPTY:

            board[row][column] = piece

            return row

    return None


# ============================================================
# AVAILABLE COLUMNS
# ============================================================

def available_columns(board):

    return [
        col
        for col in range(COLS)
        if board[0][col] == EMPTY
    ]


# ============================================================
# WIN DETECTION
# ============================================================

def check_winner(
    board,
    piece
):

    # --------------------------------------------------------
    # Horizontal
    # --------------------------------------------------------

    for row in range(ROWS):

        for col in range(COLS - 3):

            if all(
                board[row][col + i] == piece
                for i in range(4)
            ):

                return True

    # --------------------------------------------------------
    # Vertical
    # --------------------------------------------------------

    for row in range(ROWS - 3):

        for col in range(COLS):

            if all(
                board[row + i][col] == piece
                for i in range(4)
            ):

                return True

    # --------------------------------------------------------
    # Diagonal \
    # --------------------------------------------------------

    for row in range(ROWS - 3):

        for col in range(COLS - 3):

            if all(
                board[row + i][col + i] == piece
                for i in range(4)
            ):

                return True

    # --------------------------------------------------------
    # Diagonal /
    # --------------------------------------------------------

    for row in range(3, ROWS):

        for col in range(COLS - 3):

            if all(
                board[row - i][col + i] == piece
                for i in range(4)
            ):

                return True

    return False


# ============================================================
# DRAW
# ============================================================

def is_draw(board):

    return len(
        available_columns(board)
    ) == 0


# ============================================================
# WINDOW SCORE
# ============================================================

def evaluate_window(
    window,
    piece
):

    opponent = (
        PLAYER
        if piece == BOT
        else BOT
    )

    score = 0

    count_piece = window.count(piece)
    count_empty = window.count(EMPTY)
    count_opponent = window.count(opponent)

    # Four
    if count_piece == 4:

        score += 100000

    # Three + empty
    elif count_piece == 3 and count_empty == 1:

        score += 100

    # Two + two empty
    elif count_piece == 2 and count_empty == 2:

        score += 10

    # Opponent danger
    if count_opponent == 3 and count_empty == 1:

        score -= 80

    return score


# ============================================================
# POSITION SCORE
# ============================================================

def evaluate_board(board):

    score = 0

    # --------------------------------------------------------
    # Center preference
    # --------------------------------------------------------

    center_col = COLS // 2

    center_values = [
        board[row][center_col]
        for row in range(ROWS)
    ]

    score += (
        center_values.count(BOT) * 6
    )

    score -= (
        center_values.count(PLAYER) * 6
    )

    # --------------------------------------------------------
    # Horizontal
    # --------------------------------------------------------

    for row in range(ROWS):

        for col in range(COLS - 3):

            window = [
                board[row][col + i]
                for i in range(4)
            ]

            score += evaluate_window(
                window,
                BOT
            )

            score -= evaluate_window(
                window,
                PLAYER
            )

    # --------------------------------------------------------
    # Vertical
    # --------------------------------------------------------

    for row in range(ROWS - 3):

        for col in range(COLS):

            window = [
                board[row + i][col]
                for i in range(4)
            ]

            score += evaluate_window(
                window,
                BOT
            )

            score -= evaluate_window(
                window,
                PLAYER
            )

    # --------------------------------------------------------
    # Diagonal \
    # --------------------------------------------------------

    for row in range(ROWS - 3):

        for col in range(COLS - 3):

            window = [
                board[row + i][col + i]
                for i in range(4)
            ]

            score += evaluate_window(
                window,
                BOT
            )

            score -= evaluate_window(
                window,
                PLAYER
            )

    # --------------------------------------------------------
    # Diagonal /
    # --------------------------------------------------------

    for row in range(3, ROWS):

        for col in range(COLS - 3):

            window = [
                board[row - i][col + i]
                for i in range(4)
            ]

            score += evaluate_window(
                window,
                BOT
            )

            score -= evaluate_window(
                window,
                PLAYER
            )

    return score


# ============================================================
# MINIMAX
# ============================================================

def minimax(
    board,
    depth,
    maximizing
):

    valid_columns = available_columns(
        board
    )

    bot_win = check_winner(
        board,
        BOT
    )

    player_win = check_winner(
        board,
        PLAYER
    )

    if bot_win:

        return (
            None,
            1_000_000 + depth
        )

    if player_win:

        return (
            None,
            -1_000_000 - depth
        )

    if depth == 0 or not valid_columns:

        return (
            None,
            evaluate_board(board)
        )

    # --------------------------------------------------------
    # Bot
    # --------------------------------------------------------

    if maximizing:

        best_score = -math.inf
        best_columns = []

        # Center first
        ordered = sorted(
            valid_columns,
            key=lambda x: abs(3 - x)
        )

        for col in ordered:

            test_board = copy_board(
                board
            )

            drop_piece(
                test_board,
                col,
                BOT
            )

            _, score = minimax(
                test_board,
                depth - 1,
                False
            )

            if score > best_score:

                best_score = score
                best_columns = [col]

            elif score == best_score:

                best_columns.append(col)

        if best_columns:

            return (
                random.choice(
                    best_columns
                ),
                best_score
            )

        return (
            random.choice(
                valid_columns
            ),
            best_score
        )

    # --------------------------------------------------------
    # Player
    # --------------------------------------------------------

    else:

        best_score = math.inf
        best_column = valid_columns[0]

        ordered = sorted(
            valid_columns,
            key=lambda x: abs(3 - x)
        )

        for col in ordered:

            test_board = copy_board(
                board
            )

            drop_piece(
                test_board,
                col,
                PLAYER
            )

            _, score = minimax(
                test_board,
                depth - 1,
                True
            )

            if score < best_score:

                best_score = score
                best_column = col

        return (
            best_column,
            best_score
        )


# ============================================================
# EASY BOT
# ============================================================

def easy_move(board):

    valid = available_columns(
        board
    )

    if not valid:

        return None

    return random.choice(
        valid
    )


# ============================================================
# NORMAL BOT
# ============================================================

def normal_move(board):

    valid = available_columns(
        board
    )

    if not valid:

        return None

    # --------------------------------------------------------
    # First: WIN
    # --------------------------------------------------------

    for col in valid:

        test = copy_board(
            board
        )

        drop_piece(
            test,
            col,
            BOT
        )

        if check_winner(
            test,
            BOT
        ):

            return col

    # --------------------------------------------------------
    # Second: BLOCK
    # --------------------------------------------------------

    for col in valid:

        test = copy_board(
            board
        )

        drop_piece(
            test,
            col,
            PLAYER
        )

        if check_winner(
            test,
            PLAYER
        ):

            return col

    # --------------------------------------------------------
    # Otherwise minimax
    # --------------------------------------------------------

    col, _ = minimax(
        board,
        2,
        True
    )

    if col is not None:

        return col

    return random.choice(
        valid
    )


# ============================================================
# HARD BOT
# ============================================================

def hard_move(board):

    valid = available_columns(
        board
    )

    if not valid:

        return None

    col, _ = minimax(
        board,
        DIFFICULTIES["hard"]["depth"],
        True
    )

    if col is None:

        return random.choice(
            valid
        )

    return col


# ============================================================
# CHOOSE BOT MOVE
# ============================================================

async def choose_bot_move(
    board,
    difficulty
):

    if difficulty == "easy":

        return easy_move(
            board
        )

    if difficulty == "normal":

        return normal_move(
            board
        )

    if difficulty == "hard":

        # ----------------------------------------------------
        # Minimax is CPU work.
        # Run it outside the async event loop.
        # ----------------------------------------------------

        return await asyncio.to_thread(
            hard_move,
            copy_board(board)
        )

    return easy_move(
        board
    )


# ============================================================
# /CONNECT4BOT
# ============================================================

async def connect4bot_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:

        return

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:

        return

    game_key = get_game_key(
        chat,
        user
    )

    # --------------------------------------------------------
    # Already playing
    # --------------------------------------------------------

    if game_key in connect4_games:

        await update.message.reply_text(

            "🔴 <b>CONNECT FOUR</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"

            "⚠️ You already have an active "
            "Connect Four game.\n\n"

            "Finish it or press <b>End Game</b> "
            "before starting another one.",

            parse_mode=ParseMode.HTML
        )

        return

    # --------------------------------------------------------
    # Setup state
    # --------------------------------------------------------

    connect4_games[game_key] = {

        "setup": True,

        "chat_id": chat.id,

        "player_id": user.id,

        "player_name": user.full_name,

        "difficulty": None,

        "board": None,

        "turn": None,

        "message_id": None,

        "busy": False,
    }

    # --------------------------------------------------------
    # Difficulty selector
    # --------------------------------------------------------

    msg = await update.message.reply_text(

        "🔴 <b>𝐌𝐔𝐈𝐂𝐇𝐈𝐑𝐎 • 𝐂𝐎𝐍𝐍𝐄𝐂𝐓 𝟒</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        "🎮 <b>New Game</b>\n\n"

        f"👤 Player: "
        f"{player_mention(user.id, user.full_name)}\n\n"

        "⚔️ Choose your difficulty:\n\n"

        "🟢 <b>Easy</b>\n"
        "<i>Relaxed • Mostly random</i>\n\n"

        "🟡 <b>Normal</b>\n"
        "<i>Wins when possible • Blocks threats</i>\n\n"

        "🔴 <b>Hard</b>\n"
        "<i>Strategic • Minimax AI</i>\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"

        "🧠 <i>How well can you beat Muichiro?</i>",

        parse_mode=ParseMode.HTML,

        reply_markup=difficulty_keyboard()
    )

    connect4_games[
        game_key
    ]["message_id"] = msg.message_id


# ============================================================
# CALLBACK HANDLER
# ============================================================

async def connect4bot_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:

        return

    data = query.data or ""

    # ========================================================
    # DISABLED
    # ========================================================

    if data == "c4disabled":

        await query.answer(
            "⏳ Please wait for Muichiro's move."
        )

        return

    # ========================================================
    # CANCEL SETUP
    # ========================================================

    if data == "c4cancelsetup":

        user = query.from_user

        # Find setup game belonging to this user.
        game_key = None

        for key, game in connect4_games.items():

            if (
                game.get("setup")
                and game.get("player_id")
                == user.id
            ):

                game_key = key
                break

        if game_key is None:

            await query.answer(
                "❌ Game setup expired.",
                show_alert=True
            )

            return

        del connect4_games[
            game_key
        ]

        await query.answer(
            "❌ Game cancelled."
        )

        await query.edit_message_text(

            "❌ <b>CONNECT FOUR CANCELLED</b>\n\n"
            "No game was started.",

            parse_mode=ParseMode.HTML
        )

        return

    # ========================================================
    # DIFFICULTY
    # ========================================================

    if data.startswith(
        "c4difficulty:"
    ):

        difficulty = data.split(
            ":",
            1
        )[1]

        if difficulty not in DIFFICULTIES:

            await query.answer(
                "❌ Invalid difficulty.",
                show_alert=True
            )

            return

        user = query.from_user

        game_key = None
        game = None

        # ----------------------------------------------------
        # Find this user's setup game.
        # ----------------------------------------------------

        for key, existing_game in connect4_games.items():

            if (
                existing_game.get("setup")
                and existing_game.get("player_id")
                == user.id
            ):

                game_key = key
                game = existing_game
                break

        if game is None:

            await query.answer(
                "❌ This game setup has expired.",
                show_alert=True
            )

            return

        # ----------------------------------------------------
        # Start actual game
        # ----------------------------------------------------

        game["setup"] = False
        game["difficulty"] = difficulty
        game["board"] = create_board()
        game["turn"] = PLAYER
        game["busy"] = False

        difficulty_info = DIFFICULTIES[
            difficulty
        ]

        await query.answer(
            f"{difficulty_info['name']} mode selected!"
        )

        await query.edit_message_text(

            build_game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=game_keyboard(
                game_key,
                game["board"],
                enabled=True
            )
        )

        return

    # ========================================================
    # END GAME
    # ========================================================

    if data.startswith("c4end|"):

        try:

            key_text = data.split(
                "|",
                1
            )[1]

            key_parts = key_text.split(
                "|"
            )

            if key_parts[0] == "group":

                game_key = (
                    "group",
                    int(key_parts[1])
                )

            else:

                game_key = (
                    "pm",
                    int(key_parts[1])
                )

        except (
            ValueError,
            IndexError
        ):

            await query.answer(
                "❌ Invalid game.",
                show_alert=True
            )

            return

        game = connect4_games.get(
            game_key
        )

        if game is None:

            await query.answer(
                "❌ This game has already ended.",
                show_alert=True
            )

            return

        user = query.from_user

        # ----------------------------------------------------
        # Only player can end
        # ----------------------------------------------------

        if user.id != game["player_id"]:

            await query.answer(
                "🚫 Only the player can end this game.",
                show_alert=True
            )

            return

        del connect4_games[
            game_key
        ]

        await query.answer(
            "🛑 Game ended."
        )

        await query.edit_message_text(

            "🛑 <b>CONNECT FOUR ENDED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"

            f"👤 Ended by "
            f"{player_mention(user.id, user.full_name)}\n\n"

            "🎮 Start a new game with "
            "<b>/connect4bot</b>.",

            parse_mode=ParseMode.HTML
        )

        return

    # ========================================================
    # MOVE
    # ========================================================

    if data.startswith("c4m|"):

        try:

            parts = data.split("|")

            # c4m | group/pm | id | column
            game_type = parts[1]
            game_id = int(parts[2])
            column = int(parts[3])

            game_key = (
                game_type,
                game_id
            )

        except (
            ValueError,
            IndexError
        ):

            await query.answer(
                "❌ Invalid move.",
                show_alert=True
            )

            return

        game = connect4_games.get(
            game_key
        )

        if game is None:

            await query.answer(
                "❌ This game no longer exists.",
                show_alert=True
            )

            return

        user = query.from_user

        # ====================================================
        # ONLY PLAYER
        # ====================================================

        if user.id != game["player_id"]:

            await query.answer(
                "🚫 This isn't your game.",
                show_alert=True
            )

            return

        # ====================================================
        # SETUP CHECK
        # ====================================================

        if game.get("setup"):

            await query.answer(
                "⚠️ Choose a difficulty first.",
                show_alert=True
            )

            return

        # ====================================================
        # BUSY CHECK
        # ====================================================

        if game.get("busy"):

            await query.answer(
                "⏳ Muichiro is thinking...",
                show_alert=True
            )

            return

        # ====================================================
        # TURN CHECK
        # ====================================================

        if game["turn"] != PLAYER:

            await query.answer(
                "⏳ It's Muichiro's turn.",
                show_alert=True
            )

            return

        board = game["board"]

        # ====================================================
        # COLUMN RANGE
        # ====================================================

        if column < 0 or column >= COLS:

            await query.answer(
                "❌ Invalid column.",
                show_alert=True
            )

            return

        # ====================================================
        # FULL COLUMN
        # ====================================================

        if board[0][column] != EMPTY:

            await query.answer(
                "🚫 That column is full!",
                show_alert=True
            )

            return

        # ====================================================
        # LOCK GAME
        # ====================================================

        game["busy"] = True

        # ====================================================
        # PLAYER MOVE
        # ====================================================

        row = drop_piece(
            board,
            column,
            PLAYER
        )

        if row is None:

            game["busy"] = False

            await query.answer(
                "🚫 Illegal move!",
                show_alert=True
            )

            return

        # ====================================================
        # PLAYER WIN
        # ====================================================

        if check_winner(
            board,
            PLAYER
        ):

            del connect4_games[
                game_key
            ]

            await query.answer(
                "🏆 You won!"
            )

            await query.edit_message_text(

                "🏆 <b>𝐂𝐎𝐍𝐍𝐄𝐂𝐓 𝟒 • 𝐘𝐎𝐔 𝐖𝐈𝐍!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"

                f"👑 Winner: "
                f"{player_mention(user.id, user.full_name)}\n\n"

                f"{board_text(board)}\n\n"

                "🔥 <b>FOUR IN A ROW!</b>\n"
                "🎉 GG!",

                parse_mode=ParseMode.HTML
            )

            return

        # ====================================================
        # PLAYER DRAW
        # ====================================================

        if is_draw(board):

            del connect4_games[
                game_key
            ]

            await query.answer(
                "🤝 Draw!"
            )

            await query.edit_message_text(

                "🤝 <b>𝐂𝐎𝐍𝐍𝐄𝐂𝐓 𝟒 • 𝐃𝐑𝐀𝐖</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"

                f"{board_text(board)}\n\n"

                "⚖️ <b>The board is full.</b>\n"
                "Nobody managed four in a row.",

                parse_mode=ParseMode.HTML
            )

            return

        # ====================================================
        # PLAYER MOVE DISPLAY
        # ====================================================

        game["turn"] = BOT

        await query.answer(
            "🔴 Move played!"
        )

        await query.edit_message_text(

            build_game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=game_keyboard(
                game_key,
                board,
                enabled=False
            )
        )

        # ====================================================
        # BOT THINKING
        # ====================================================

        await asyncio.sleep(
            0.35
        )

        bot_column = await choose_bot_move(
            board,
            game["difficulty"]
        )

        # ----------------------------------------------------
        # Safety check
        # ----------------------------------------------------

        if (
            bot_column is None
            or bot_column not in available_columns(board)
        ):

            valid = available_columns(
                board
            )

            if not valid:

                del connect4_games[
                    game_key
                ]

                await query.edit_message_text(

                    "🤝 <b>CONNECT 4 • DRAW</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"

                    f"{board_text(board)}",

                    parse_mode=ParseMode.HTML
                )

                return

            bot_column = random.choice(
                valid
            )

        # ====================================================
        # BOT MOVE
        # ====================================================

        drop_piece(
            board,
            bot_column,
            BOT
        )

        # ====================================================
        # BOT WIN
        # ====================================================

        if check_winner(
            board,
            BOT
        ):

            del connect4_games[
                game_key
            ]

            await query.edit_message_text(

                "🤖 <b>𝐂𝐎𝐍𝐍𝐄𝐂𝐓 𝟒 • 𝐌𝐔𝐈𝐂𝐇𝐈𝐑𝐎 𝐖𝐈𝐍𝐒!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"

                f"👤 Player: "
                f"{player_mention(user.id, user.full_name)}\n\n"

                f"{board_text(board)}\n\n"

                "🟡 <b>FOUR IN A ROW!</b>\n\n"

                "😎 Muichiro got you this time!",

                parse_mode=ParseMode.HTML
            )

            return

        # ====================================================
        # BOT DRAW
        # ====================================================

        if is_draw(board):

            del connect4_games[
                game_key
            ]

            await query.edit_message_text(

                "🤝 <b>𝐂𝐎𝐍𝐍𝐄𝐂𝐓 𝟒 • 𝐃𝐑𝐀𝐖</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"

                f"{board_text(board)}\n\n"

                "⚖️ <b>No moves remain.</b>\n"
                "That was a close game!",

                parse_mode=ParseMode.HTML
            )

            return

        # ====================================================
        # BACK TO PLAYER
        # ====================================================

        game["turn"] = PLAYER
        game["busy"] = False

        # ====================================================
        # FINAL BOARD UPDATE
        # ====================================================

        try:

            await query.edit_message_text(

                build_game_text(game),

                parse_mode=ParseMode.HTML,

                reply_markup=game_keyboard(
                    game_key,
                    board,
                    enabled=True
                )
            )

        except Exception as e:

            print(
                f"❌ Connect4 board update error: {e}"
            )

            game["busy"] = False

        return


# ============================================================
# /ENDCONNECT4BOT
# ============================================================

async def endconnect4bot_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:

        return

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:

        return

    game_key = get_game_key(
        chat,
        user
    )

    game = connect4_games.get(
        game_key
    )

    if game is None:

        await update.message.reply_text(
            "❌ There is no active "
            "Connect Four Bot game."
        )

        return

    # --------------------------------------------------------
    # Only player
    # --------------------------------------------------------

    if user.id != game["player_id"]:

        await update.message.reply_text(

            "🚫 <b>Only the player in the "
            "current game can end it.</b>",

            parse_mode=ParseMode.HTML
        )

        return

    del connect4_games[
        game_key
    ]

    await update.message.reply_text(

        "🛑 <b>CONNECT FOUR BOT ENDED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        f"👤 Ended by "
        f"{player_mention(user.id, user.full_name)}\n\n"

        "🎮 The current game has been stopped.",

        parse_mode=ParseMode.HTML
    )