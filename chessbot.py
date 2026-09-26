# ==========================================
# ♟️ MUICHIRO CHESS BOT
# User vs Stockfish
# ==========================================

import os
import html
import asyncio
import shutil

import chess
import chess.engine

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.constants import ParseMode

from telegram.ext import ContextTypes

from telegram.error import BadRequest

# ======================================
# STOCKFISH PATH DETECTION
# ======================================

def get_stockfish_path():

    # Environment variable (optional override)
    env_path = os.getenv("STOCKFISH_PATH")

    if env_path and os.path.isfile(env_path):
        return env_path

    # Automatically search PATH
    path = shutil.which("stockfish")

    if path:
        return path

    # Common Linux / Docker paths
    possible_paths = [
        "/usr/games/stockfish",
        "/usr/bin/stockfish",
        "/usr/local/bin/stockfish",
    ]

    for path in possible_paths:

        if os.path.isfile(path):
            return path

    # Windows fallback for local testing
    possible_windows_paths = [
        "stockfish.exe",
        r"C:\stockfish\stockfish.exe",
    ]

    for path in possible_windows_paths:

        if os.path.isfile(path):
            return path

    return None


STOCKFISH_PATH = get_stockfish_path()

print(
    f"♟️ Stockfish path detected: {STOCKFISH_PATH}"
)



# ==========================================
# ACTIVE GAMES
# ==========================================

chessbot_games = {}


# ==========================================
# DIFFICULTIES
# ==========================================

DIFFICULTIES = {

    "easy": {
        "name": "🟢 Easy",
        "depth": 1,
    },

    "normal": {
        "name": "🟡 Normal",
        "depth": 3,
    },

    "hard": {
        "name": "🔴 Hard",
        "depth": 13,
    },

}


# ==========================================
# CHESS PIECES
# ==========================================

PIECES = {

    "P": "♙",
    "N": "♘",
    "B": "♗",
    "R": "♖",
    "Q": "♕",
    "K": "♔",

    "p": "♟",
    "n": "♞",
    "b": "♝",
    "r": "♜",
    "q": "♛",
    "k": "♚",

}


# ==========================================
# PLAYER MENTION
# ==========================================

def player_mention(
    user_id,
    name
):

    safe_name = html.escape(
        name or "Player"
    )

    return (
        f'<a href="tg://user?id={user_id}">'
        f'{safe_name}</a>'
    )


# ==========================================
# GAME KEY
# ==========================================

def game_key(chat_id):

    return chat_id


# ==========================================
# BOARD ORIENTATION
# ==========================================

def board_orientation(
    user_color
):

    if user_color == chess.WHITE:

        return (
            range(7, -1, -1),
            range(8),
            "A  B  C  D  E  F  G  H"
        )

    return (
        range(8),
        range(7, -1, -1),
        "H  G  F  E  D  C  B  A"
    )


# ==========================================
# BOARD TEXT
# ==========================================

def board_text(
    board,
    user_color
):

    ranks, files, file_labels = (
        board_orientation(
            user_color
        )
    )

    lines = []

    for rank in ranks:

        row = []

        for file in files:

            square = chess.square(
                file,
                rank
            )

            piece = board.piece_at(
                square
            )

            if piece:

                symbol = PIECES.get(
                    piece.symbol(),
                    "?"
                )

            else:

                symbol = "▫️"

            row.append(symbol)

        lines.append(
            f"<b>{rank + 1}</b> "
            + " ".join(row)
        )

    lines.append(
        f"   {file_labels}"
    )

    return "\n".join(lines)


# ==========================================
# BOARD BUTTONS
# ==========================================

def board_keyboard(
    game,
    selected=None
):

    chat_id = game["chat_id"]

    board = game["board"]

    user_color = game["user_color"]

    ranks, files, _ = (
        board_orientation(
            user_color
        )
    )

    keyboard = []

    for rank in ranks:

        row = []

        for file in files:

            square = chess.square(
                file,
                rank
            )

            piece = board.piece_at(
                square
            )

            if piece:

                label = PIECES.get(
                    piece.symbol(),
                    "?"
                )

            else:

                if (file + rank) % 2 == 0:

                    label = "▫️"

                else:

                    label = "◽"

            if selected == square:

                label = "🟢" + label

            row.append(
                InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"cb_move:"
                        f"{chat_id}:"
                        f"{square}"
                    )
                )
            )

        keyboard.append(row)

    keyboard.append(
        [
            InlineKeyboardButton(
                "🏳️ Resign",
                callback_data=(
                    f"cb_resign:{chat_id}"
                )
            ),

            InlineKeyboardButton(
                "❌ End Game",
                callback_data=(
                    f"cb_cancel:{chat_id}"
                )
            ),
        ]
    )

    return InlineKeyboardMarkup(
        keyboard
    )


# ==========================================
# DIFFICULTY BUTTONS
# ==========================================

def difficulty_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "🟢 Easy",
                    callback_data="cb_diff:easy"
                )
            ],

            [
                InlineKeyboardButton(
                    "🟡 Normal",
                    callback_data="cb_diff:normal"
                )
            ],

            [
                InlineKeyboardButton(
                    "🔴 Hard",
                    callback_data="cb_diff:hard"
                )
            ],

        ]
    )


# ==========================================
# COLOR BUTTONS
# ==========================================

def color_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "⚪ Play White",
                    callback_data="cb_color:white"
                ),

                InlineKeyboardButton(
                    "⚫ Play Black",
                    callback_data="cb_color:black"
                ),
            ]

        ]
    )


# ==========================================
# PROMOTION BUTTONS
# ==========================================

def promotion_keyboard(
    chat_id
):

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "♕ Queen",
                    callback_data=(
                        f"cb_promo:{chat_id}:q"
                    )
                ),

                InlineKeyboardButton(
                    "♖ Rook",
                    callback_data=(
                        f"cb_promo:{chat_id}:r"
                    )
                ),
            ],

            [
                InlineKeyboardButton(
                    "♗ Bishop",
                    callback_data=(
                        f"cb_promo:{chat_id}:b"
                    )
                ),

                InlineKeyboardButton(
                    "♘ Knight",
                    callback_data=(
                        f"cb_promo:{chat_id}:n"
                    )
                ),
            ],

        ]
    )


# ==========================================
# RESULT BUTTONS
# ==========================================

def result_keyboard(
    game
):

    chat_id = game["chat_id"]

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "🔄 Rematch",
                    callback_data=(
                        f"cb_rematch:{chat_id}"
                    )
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Close",
                    callback_data=(
                        f"cb_close:{chat_id}"
                    )
                )
            ],

        ]
    )


# ==========================================
# GAME TEXT
# ==========================================

def game_text(
    game
):

    board = game["board"]

    user_id = game["user_id"]

    user_name = game["user_name"]

    difficulty = game["difficulty"]

    user_color = game["user_color"]

    # ======================================
    # LATEST MOVE
    # ======================================

    last_move = game.get(
        "last_move"
    )

    if last_move:

        last_move_text = (
            f"{last_move[:2]} → {last_move[2:4]}"
        )

        # Show promotion piece if present
        if len(last_move) > 4:

            last_move_text += (
                f"={last_move[4].upper()}"
            )

    else:

        last_move_text = "No moves yet"

    # ======================================
    # PLAYER SIDES
    # ======================================

    if user_color == chess.WHITE:

        user_side = "⚪ White"

        bot_side = "⚫ Black"

    else:

        user_side = "⚫ Black"

        bot_side = "⚪ White"

    # ======================================
    # TURN TEXT
    # ======================================

    if board.turn == user_color:

        turn_text = (
            f"👤 <b>{html.escape(user_name)}</b>, "
            "it's your turn!"
        )

    else:

        turn_text = (
            "🤖 <b>Muichiro</b> is thinking..."
        )

    check_text = ""

    if board.is_check():

        check_text = (
            "\n\n⚠️ <b>CHECK!</b>"
        )

    return (

        "♟️ <b>MUICHIRO • CHESS BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"👤 <b>You:</b> "
        f"{player_mention(user_id, user_name)}\n"

        f"🤖 <b>Muichiro:</b> "
        f"{difficulty}\n\n"

        f"⚪ <b>White:</b> "
        f"{'You' if user_color == chess.WHITE else 'Muichiro'}\n"

        f"⚫ <b>Black:</b> "
        f"{'You' if user_color == chess.BLACK else 'Muichiro'}\n\n"

        f"🎯 <b>Your side:</b> "
        f"{user_side}\n"

        f"🤖 <b>Bot side:</b> "
        f"{bot_side}\n\n"

        f"📜 <b>Latest Move:</b> "
        f"<code>{last_move_text}</code>\n\n"

        f"{board_text(board, user_color)}\n\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"{turn_text}"

        f"{check_text}"

    )


# ==========================================
# STOCKFISH
# ==========================================

def stockfish_move(
    board,
    depth
):

    engine = None

    try:

        engine = (
            chess.engine.SimpleEngine
            .popen_uci(
                STOCKFISH_PATH
            )
        )

        result = engine.play(
            board,
            chess.engine.Limit(
                depth=depth
            )
        )

        return result.move

    finally:

        if engine:

            try:
                engine.quit()

            except Exception:
                pass


# ==========================================
# ASYNC STOCKFISH
# ==========================================

async def get_bot_move(
    board,
    depth
):

    return await asyncio.to_thread(
        stockfish_move,
        board.copy(),
        depth
    )


# ==========================================
# /CHESSBOT
# ==========================================

async def chessbot_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:

        return

    chat = update.effective_chat

    user = update.effective_user

    if not chat or not user:

        return

    key = game_key(
        chat.id
    )

    if key in chessbot_games:

        await update.message.reply_text(

            "♟️ <b>CHESS BOT GAME "
            "ALREADY RUNNING!</b>\n\n"

            "Finish the current match first "
            "or use <b>/endchessbot</b>.",

            parse_mode=ParseMode.HTML
        )

        return

    await update.message.reply_text(

        "♟️ <b>MUICHIRO • CHESS BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "🤖 <b>Choose your difficulty</b>\n\n"

        "🟢 <b>Easy</b> — Casual opponent\n"
        "🟡 <b>Normal</b> — Balanced opponent\n"
        "🔴 <b>Hard</b> — Strong opponent\n\n"

        "👇 Select a difficulty:",

        parse_mode=ParseMode.HTML,

        reply_markup=difficulty_keyboard()
    )


# ==========================================
# CALLBACK HANDLER
# ==========================================

async def chessbot_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:

        return

    data = query.data or ""


    # ======================================
    # DIFFICULTY
    # ======================================

    if data.startswith("cb_diff:"):

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

        if not query.message:

            return

        chat = query.message.chat

        user = query.from_user

        key = game_key(
            chat.id
        )

        if key in chessbot_games:

            await query.answer(
                "♟️ A game is already running.",
                show_alert=True
            )

            return

        await query.answer()

        chessbot_games[key] = {

            "chat_id": chat.id,

            "user_id": user.id,

            "user_name": user.full_name,

            "difficulty": (
                DIFFICULTIES[
                    difficulty
                ]["name"]
            ),

            "difficulty_key": difficulty,

            "depth": (
                DIFFICULTIES[
                    difficulty
                ]["depth"]
            ),

            "user_color": None,

            "board": None,

            "selected_square": None,

            "pending_promotion": None,

            "last_move": None,

            "message_id": (
                query.message.message_id
            ),

        }

        await query.edit_message_text(

            "♟️ <b>MUICHIRO • CHESS BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            f"🤖 <b>Difficulty:</b> "
            f"{DIFFICULTIES[difficulty]['name']}\n\n"

            "🎨 <b>Choose your side</b>\n\n"

            "⚪ <b>White</b> — You move first\n"
            "⚫ <b>Black</b> — Muichiro moves first\n\n"

            "👇 Select your color:",

            parse_mode=ParseMode.HTML,

            reply_markup=color_keyboard()
        )

        return


    # ======================================
    # COLOR
    # ======================================

    if data.startswith("cb_color:"):

        color = data.split(
            ":",
            1
        )[1]

        if color not in [
            "white",
            "black"
        ]:

            await query.answer(
                "❌ Invalid color.",
                show_alert=True
            )

            return

        if not query.message:

            return

        chat = query.message.chat

        user = query.from_user

        key = game_key(
            chat.id
        )

        game = chessbot_games.get(
            key
        )

        if not game:

            await query.answer(
                "❌ Game setup expired.",
                show_alert=True
            )

            return

        if game["user_id"] != user.id:

            await query.answer(
                "🚫 Only the player who "
                "started this game can choose.",
                show_alert=True
            )

            return

        if color == "white":

            game["user_color"] = (
                chess.WHITE
            )

        else:

            game["user_color"] = (
                chess.BLACK
            )

        game["board"] = chess.Board()

        game["selected_square"] = None

        game["pending_promotion"] = None

        await query.answer(
            "♟️ Game starting!"
        )

        await query.edit_message_text(

            game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=board_keyboard(
                game
            )
        )

        # ==================================
        # BOT MOVES FIRST IF USER IS BLACK
        # ==================================

        if game["user_color"] == chess.BLACK:

            await bot_turn(
                query,
                game
            )

        return


    # ======================================
    # MOVE
    # ======================================

    if data.startswith("cb_move:"):

        try:

            parts = data.split(":")

            chat_id = int(
                parts[1]
            )

            square = int(
                parts[2]
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

        game = chessbot_games.get(
            chat_id
        )

        if not game:

            await query.answer(
                "❌ This game no longer exists.",
                show_alert=True
            )

            return

        user = query.from_user

        if user.id != game["user_id"]:

            await query.answer(
                "🚫 This isn't your game.",
                show_alert=True
            )

            return

        board = game["board"]

        if board is None:

            await query.answer(
                "❌ Game has not started.",
                show_alert=True
            )

            return

        # ==================================
        # BOT TURN
        # ==================================

        if board.turn != game["user_color"]:

            await query.answer(
                "🤖 It's Muichiro's turn!",
                show_alert=True
            )

            return

        selected = game.get(
            "selected_square"
        )

        # ==================================
        # SELECT PIECE
        # ==================================

        if selected is None:

            piece = board.piece_at(
                square
            )

            if piece is None:

                await query.answer(
                    "❌ There is no piece there.",
                    show_alert=True
                )

                return

            if piece.color != game["user_color"]:

                await query.answer(
                    "🚫 That's not your piece!",
                    show_alert=True
                )

                return

            game[
                "selected_square"
            ] = square

            await query.answer(
                f"Selected "
                f"{chess.square_name(square).upper()}"
            )

            await query.edit_message_text(

                game_text(game),

                parse_mode=ParseMode.HTML,

                reply_markup=board_keyboard(
                    game,
                    selected=square
                )
            )

            return

        # ==================================
        # DESELECT
        # ==================================

        if selected == square:

            game[
                "selected_square"
            ] = None

            await query.answer(
                "Selection cancelled."
            )

            await query.edit_message_text(

                game_text(game),

                parse_mode=ParseMode.HTML,

                reply_markup=board_keyboard(
                    game
                )
            )

            return

        piece = board.piece_at(
            selected
        )

        # ==================================
        # PROMOTION
        # ==================================

        is_promotion = (

            piece is not None

            and piece.piece_type
            == chess.PAWN

            and chess.square_rank(square)
            in [0, 7]
        )

        if is_promotion:

            test_move = chess.Move(
                selected,
                square,
                promotion=chess.QUEEN
            )

            if test_move not in board.legal_moves:

                game[
                    "selected_square"
                ] = None

                await query.answer(
                    "🚫 Illegal move!",
                    show_alert=True
                )

                await query.edit_message_text(

                    game_text(game),

                    parse_mode=ParseMode.HTML,

                    reply_markup=board_keyboard(
                        game
                    )
                )

                return

            game[
                "pending_promotion"
            ] = (
                selected,
                square
            )

            await query.answer()

            await query.edit_message_text(

                game_text(game)
                + "\n\n"
                "👑 <b>Choose your promotion:</b>",

                parse_mode=ParseMode.HTML,

                reply_markup=promotion_keyboard(
                    chat_id
                )
            )

            return

        # ==================================
        # NORMAL MOVE
        # ==================================

        move = chess.Move(
            selected,
            square
        )

        if move not in board.legal_moves:

            await query.answer(
                "🚫 Illegal move!",
                show_alert=True
            )

            return

        game[
            "selected_square"
        ] = None

        game["last_move"] = move.uci()

        board.push(
            move
        )

        await query.answer(
            "✅ Move played!"
        )

        # ==================================
        # GAME OVER
        # ==================================

        if await finish_if_game_over(
            query,
            game
        ):

            return

        await query.edit_message_text(

            game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=board_keyboard(
                game
            )
        )

        await bot_turn(
            query,
            game
        )

        return


    # ======================================
    # PROMOTION
    # ======================================

    if data.startswith("cb_promo:"):

        try:

            parts = data.split(":")

            chat_id = int(
                parts[1]
            )

            promotion_letter = parts[2]

        except (
            ValueError,
            IndexError
        ):

            await query.answer(
                "❌ Invalid promotion.",
                show_alert=True
            )

            return

        game = chessbot_games.get(
            chat_id
        )

        if not game:

            await query.answer(
                "❌ Game no longer exists.",
                show_alert=True
            )

            return

        if query.from_user.id != game["user_id"]:

            await query.answer(
                "🚫 This isn't your game.",
                show_alert=True
            )

            return

        pending = game.get(
            "pending_promotion"
        )

        if not pending:

            await query.answer(
                "❌ No promotion pending.",
                show_alert=True
            )

            return

        promotion_map = {

            "q": chess.QUEEN,

            "r": chess.ROOK,

            "b": chess.BISHOP,

            "n": chess.KNIGHT,

        }

        promotion_piece = (
            promotion_map.get(
                promotion_letter
            )
        )

        if not promotion_piece:

            await query.answer(
                "❌ Invalid piece.",
                show_alert=True
            )

            return

        from_square, to_square = (
            pending
        )

        move = chess.Move(
            from_square,
            to_square,
            promotion=promotion_piece
        )

        if move not in game["board"].legal_moves:

            await query.answer(
                "🚫 Illegal promotion.",
                show_alert=True
            )

            return

        game[
            "pending_promotion"
        ] = None

        game[
            "selected_square"
        ] = None

        game["last_move"] = move.uci()

        game["board"].push(
            move
        )

        await query.answer(
            "👑 Promotion complete!"
        )

        if await finish_if_game_over(
            query,
            game
        ):

            return

        await query.edit_message_text(

            game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=board_keyboard(
                game
            )
        )

        await bot_turn(
            query,
            game
        )

        return


    # ======================================
    # RESIGN
    # ======================================

    if data.startswith("cb_resign:"):

        try:

            chat_id = int(
                data.split(":")[1]
            )

        except (
            ValueError,
            IndexError
        ):

            return

        game = chessbot_games.get(
            chat_id
        )

        if not game:

            await query.answer(
                "Game already ended.",
                show_alert=True
            )

            return

        if query.from_user.id != game["user_id"]:

            await query.answer(
                "🚫 This isn't your game.",
                show_alert=True
            )

            return

        chessbot_games.pop(
            chat_id,
            None
        )

        await query.answer(
            "🏳️ You resigned."
        )

        await query.edit_message_text(

            "🏳️ <b>YOU RESIGNED</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "🤖 <b>Muichiro wins!</b>\n\n"

            "Better luck next game! 😎",

            parse_mode=ParseMode.HTML
        )

        return


    # ======================================
    # END GAME BUTTON
    # ======================================

    if data.startswith("cb_cancel:"):

        try:

            chat_id = int(
                data.split(":")[1]
            )

        except (
            ValueError,
            IndexError
        ):

            return

        game = chessbot_games.get(
            chat_id
        )

        if not game:

            await query.answer(
                "Game already ended.",
                show_alert=True
            )

            return

        if query.from_user.id != game["user_id"]:

            await query.answer(
                "🚫 Only the player who "
                "started this game can end it.",
                show_alert=True
            )

            return

        chessbot_games.pop(
            chat_id,
            None
        )

        await query.answer(
            "🛑 Game ended."
        )

        await query.edit_message_text(

            "🛑 <b>CHESS BOT GAME ENDED</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "The match has been stopped.\n\n"

            "♟️ Use <b>/chessbot</b> "
            "to start a new game.",

            parse_mode=ParseMode.HTML
        )

        return


    # ======================================
    # REMATCH
    # ======================================

    if data.startswith("cb_rematch:"):

        try:

            chat_id = int(
                data.split(":")[1]
            )

        except (
            ValueError,
            IndexError
        ):

            return

        await query.answer()

        await query.edit_message_text(

            "♟️ <b>NEW CHESS BOT MATCH</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "🤖 <b>Choose your difficulty:</b>",

            parse_mode=ParseMode.HTML,

            reply_markup=difficulty_keyboard()
        )

        return


    # ======================================
    # CLOSE
    # ======================================

    if data.startswith("cb_close:"):

        await query.answer()

        await query.edit_message_text(

            "♟️ <b>Chess Bot match closed.</b>\n\n"

            "Use <b>/chessbot</b> to play again.",

            parse_mode=ParseMode.HTML
        )

        return


# ==========================================
# BOT TURN
# ==========================================

async def bot_turn(
    query,
    game
):

    chat_id = game["chat_id"]

    # ======================================
    # CHECK GAME EXISTS
    # ======================================

    if chat_id not in chessbot_games:
        return

    board = game.get("board")

    if board is None:
        return

    if board.is_game_over():
        return

    # ======================================
    # PREVENT DOUBLE BOT TURN
    # ======================================

    if game.get("bot_thinking", False):
        return

    game["bot_thinking"] = True

    try:

        # ======================================
        # GET STOCKFISH MOVE
        # ======================================

        move = await get_bot_move(
            board,
            game["depth"]
        )

    except Exception as error:

        print(
            "❌ ChessBot Stockfish error:",
            error
        )

        game["bot_thinking"] = False

        try:

            await query.edit_message_text(

                "❌ <b>CHESS ENGINE ERROR</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "🤖 Stockfish could not make a move.\n\n"
                "Please check the Stockfish installation "
                "and engine path.",

                parse_mode=ParseMode.HTML
            )

        except Exception as edit_error:

            print(
                "❌ Error showing engine message:",
                edit_error
            )

        chessbot_games.pop(
            chat_id,
            None
        )

        return

    # ======================================
    # GAME MAY HAVE ENDED WHILE THINKING
    # ======================================

    if chat_id not in chessbot_games:
        return

    if move is None:

        game["bot_thinking"] = False

        return

    # ======================================
    # MAKE BOT MOVE
    # ======================================

    try:

        # Save latest Stockfish move
        game["last_move"] = move.uci()

        board.push(
            move
        )

    except Exception as error:

        print(
            "❌ Error making bot move:",
            error
        )

        game["bot_thinking"] = False

        return

    game["bot_thinking"] = False

    # ======================================
    # CHECK GAME OVER
    # ======================================

    if await finish_if_game_over(
        query,
        game
    ):

        return

    # ======================================
    # UPDATE BOARD AFTER REAL MOVE
    # ======================================

    try:

        await query.edit_message_text(

            game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=board_keyboard(
                game
            )
        )

    except Exception as error:

        # Ignore harmless Telegram error
        if "Message is not modified" not in str(error):

            print(
                "❌ Error updating chess board:",
                error
            )

# ==========================================
# GAME OVER
# ==========================================

async def finish_if_game_over(
    query,
    game
):

    board = game["board"]

    chat_id = game["chat_id"]

    # ======================================
    # CHECKMATE
    # ======================================

    if board.is_checkmate():

        winner_color = not board.turn

        if winner_color == game["user_color"]:

            winner = (
                "👑 <b>Winner:</b> "
                + player_mention(
                    game["user_id"],
                    game["user_name"]
                )
            )

            result = (
                "🎉 You defeated Muichiro!"
            )

            title = (
                "🏆 <b>CHECKMATE!</b>"
            )

        else:

            winner = (
                "🤖 <b>Winner:</b> Muichiro"
            )

            result = (
                "🤖 Muichiro wins this game!"
            )

            title = (
                "💀 <b>CHECKMATE!</b>"
            )

        await query.edit_message_text(

            f"{title}\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            f"{winner}\n\n"

            f"{result}\n\n"

            f"{board_text(board, game['user_color'])}\n\n"

            "♟️ <b>Game over.</b>",

            parse_mode=ParseMode.HTML,

            reply_markup=result_keyboard(
                game
            )
        )

        chessbot_games.pop(
            chat_id,
            None
        )

        return True

    # ======================================
    # STALEMATE
    # ======================================

    if board.is_stalemate():

        await query.edit_message_text(

            "🤝 <b>STALEMATE!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "⚖️ No legal moves remain.\n"
            "The game is a draw.\n\n"

            f"{board_text(board, game['user_color'])}\n\n"

            "♟️ <b>Good game!</b>",

            parse_mode=ParseMode.HTML,

            reply_markup=result_keyboard(
                game
            )
        )

        chessbot_games.pop(
            chat_id,
            None
        )

        return True

    # ======================================
    # INSUFFICIENT MATERIAL
    # ======================================

    if board.is_insufficient_material():

        await query.edit_message_text(

            "🤝 <b>DRAW!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "♟️ Neither side has enough "
            "material to checkmate.\n\n"

            f"{board_text(board, game['user_color'])}",

            parse_mode=ParseMode.HTML,

            reply_markup=result_keyboard(
                game
            )
        )

        chessbot_games.pop(
            chat_id,
            None
        )

        return True

    # ======================================
    # FIFTY MOVE RULE
    # ======================================

    if board.is_fifty_moves():

        await query.edit_message_text(

            "🤝 <b>DRAW!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "⚖️ The fifty-move rule "
            "has been reached.\n\n"

            f"{board_text(board, game['user_color'])}",

            parse_mode=ParseMode.HTML,

            reply_markup=result_keyboard(
                game
            )
        )

        chessbot_games.pop(
            chat_id,
            None
        )

        return True

    # ======================================
    # FIVEFOLD REPETITION
    # ======================================

    if board.is_fivefold_repetition():

        await query.edit_message_text(

            "🤝 <b>DRAW!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "🔄 The position occurred "
            "five times.\n\n"

            f"{board_text(board, game['user_color'])}",

            parse_mode=ParseMode.HTML,

            reply_markup=result_keyboard(
                game
            )
        )

        chessbot_games.pop(
            chat_id,
            None
        )

        return True

    return False


# ==========================================
# /ENDCHESSBOT
# ==========================================

async def endchessbot_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:

        return

    chat = update.effective_chat

    user = update.effective_user

    if not chat or not user:

        return

    key = game_key(
        chat.id
    )

    game = chessbot_games.get(
        key
    )

    if not game:

        await update.message.reply_text(

            "❌ There is no active "
            "Chess Bot game."
        )

        return

    if game["user_id"] != user.id:

        await update.message.reply_text(

            "🚫 <b>Only the player who "
            "started this game can end it.</b>",

            parse_mode=ParseMode.HTML
        )

        return

    chessbot_games.pop(
        key,
        None
    )

    mention = player_mention(
        user.id,
        user.full_name
    )

    await update.message.reply_text(

        "🛑 <b>CHESS BOT GAME ENDED</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"👤 <b>Ended by:</b> {mention}\n\n"

        "♟️ Start another game with "
        "<b>/chessbot</b>.",

        parse_mode=ParseMode.HTML
    )

print(f"♟️ Stockfish path detected: {STOCKFISH_PATH}")