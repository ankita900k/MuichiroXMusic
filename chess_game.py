# ==========================================
# ♟️ MUICHIRO CHESS
# ==========================================

import html

import chess
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


# ==========================================
# ACTIVE GAMES
# ==========================================

chess_games = {}


# ==========================================
# PIECE SYMBOLS
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

def player_mention(user_id, name):

    safe_name = html.escape(
        name or "Player"
    )

    return (
        f'<a href="tg://user?id={user_id}">'
        f'{safe_name}</a>'
    )


# ==========================================
# SQUARE NAME
# ==========================================

def square_name(square):

    return chess.square_name(square).upper()


# ==========================================
# LATEST MOVE TEXT
# ==========================================

def latest_move_text(board):

    if not board.move_stack:
        return "🎯 <b>Latest Move:</b> None"

    move = board.peek()

    from_square = chess.square_name(
        move.from_square
    ).upper()

    to_square = chess.square_name(
        move.to_square
    ).upper()

    move_text = f"{from_square} → {to_square}"

    if move.promotion:

        promotion_names = {
            chess.QUEEN: "Queen",
            chess.ROOK: "Rook",
            chess.BISHOP: "Bishop",
            chess.KNIGHT: "Knight",
        }

        promotion_name = promotion_names.get(
            move.promotion,
            ""
        )

        if promotion_name:
            move_text += (
                f" = {promotion_name}"
            )

    return (
        f"🎯 <b>Latest Move:</b> "
        f"<code>{move_text}</code>"
    )


# ==========================================
# BOARD DISPLAY
# ==========================================

def board_text(board):

    lines = []

    for rank in range(7, -1, -1):

        row = []

        for file in range(8):

            square = chess.square(
                file,
                rank
            )

            piece = board.piece_at(square)

            if piece:
                row.append(
                    PIECES.get(
                        piece.symbol(),
                        "?"
                    )
                )
            else:
                # Empty square
                row.append("▫️")

        lines.append(
            f"<b>{rank + 1}</b> "
            + " ".join(row)
        )

    lines.append("")
    lines.append(
        "　A  B  C  D  E  F  G  H"
    )

    return "\n".join(lines)


# ==========================================
# CHESS BOARD KEYBOARD
# ==========================================

def chess_board_keyboard(
    chat_id,
    selected=None
):

    rows = []

    for rank in range(7, -1, -1):

        row = []

        for file in range(8):

            square = chess.square(
                file,
                rank
            )

            piece = chess.Board().piece_at(square)

            # Button label is replaced later
            # by board state in callback builder.
            label = square_name(square)

            if selected == square:
                label = f"🟢 {label}"

            row.append(
                InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"chess_move:"
                        f"{chat_id}:"
                        f"{square}"
                    )
                )
            )

        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                "❌ End Game",
                callback_data=(
                    f"chess_cancel:{chat_id}"
                )
            )
        ]
    )

    return InlineKeyboardMarkup(rows)


# ==========================================
# BOARD KEYBOARD WITH PIECES
# ==========================================

def build_board_keyboard(
    chat_id,
    board,
    selected=None
):

    rows = []

    for rank in range(7, -1, -1):

        row = []

        for file in range(8):

            square = chess.square(
                file,
                rank
            )

            piece = board.piece_at(square)

            if piece:

                label = PIECES.get(
                    piece.symbol(),
                    "?"
                )

            else:

                # Use different symbols to make
                # empty squares easier to see.
                if (file + rank) % 2 == 0:
                    label = "▫️"
                else:
                    label = "◽"

            if selected == square:

                label = f"🟢{label}"

            row.append(
                InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"chess_move:"
                        f"{chat_id}:"
                        f"{square}"
                    )
                )
            )

        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                "❌ End Game",
                callback_data=(
                    f"chess_cancel:{chat_id}"
                )
            )
        ]
    )

    return InlineKeyboardMarkup(rows)


# ==========================================
# GAME TEXT
# ==========================================

# ==========================================
# GAME TEXT
# ==========================================

def build_game_text(game):

    board = game["board"]

    white_id = game["white"]
    black_id = game["black"]

    white_name = game["names"].get(
        white_id,
        "Player"
    )

    black_name = game["names"].get(
        black_id,
        "Player"
    )

    if board.turn == chess.WHITE:

        turn_id = white_id
        turn_name = white_name
        turn_piece = "♔"
        turn_color = "White"

    else:

        turn_id = black_id
        turn_name = black_name
        turn_piece = "♚"
        turn_color = "Black"

    selected = game.get(
        "selected_square"
    )

    # ======================================
    # LATEST MOVE
    # ======================================

    latest_move = latest_move_text(
        board
    )

    text = (
        "♟️ <b>MUICHIRO • CHESS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"⚪ <b>White:</b> "
        f"{player_mention(white_id, white_name)}\n"

        f"⚫ <b>Black:</b> "
        f"{player_mention(black_id, black_name)}\n\n"

        f"{board_text(board)}\n\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"{latest_move}\n\n"

        f"{turn_piece} <b>{turn_color}'s turn:</b> "
        f"{player_mention(turn_id, turn_name)}\n\n"

        "🎮 Tap your piece, then tap "
        "the destination square."
    )

    if selected is not None:

        text += (
            f"\n\n🟢 Selected: "
            f"<b>{square_name(selected)}</b>"
        )

    return text


# ==========================================
# /chess
# ==========================================

async def chess_command(
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
            "♟️ <b>Chess can only be played "
            "in groups.</b>",
            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # EXISTING GAME
    # ======================================

    if chat.id in chess_games:

        await update.message.reply_text(
            "♟️ <b>A Chess game is already "
            "running!</b>\n\n"
            "👥 Join the current match "
            "or wait until it ends.",
            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # CREATE GAME
    # ======================================

    chess_games[chat.id] = {

        "chat_id": chat.id,

        "creator": user.id,

        "players": [
            user.id
        ],

        "white": user.id,

        "black": None,

        "names": {
            user.id: user.full_name
        },

        "board": chess.Board(),

        "selected_square": None,

        "message_id": None,

        "started": False
    }

    keyboard = [

        [
            InlineKeyboardButton(
                "♟️ Join Chess",
                callback_data=(
                    f"chess_join:{chat.id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=(
                    f"chess_cancel:{chat.id}"
                )
            )
        ]

    ]

    msg = await update.message.reply_text(

        "♟️ <b>MUICHIRO • CHESS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "✨ <b>NEW MATCH CREATED!</b>\n\n"

        f"👑 <b>Creator:</b> "
        f"{player_mention(user.id, user.full_name)}\n\n"

        f"⚪ <b>White:</b> "
        f"{player_mention(user.id, user.full_name)}\n"

        "⚫ <b>Black:</b> Waiting...\n\n"

        "👥 <b>Players:</b> 1 / 2\n\n"

        "♟️ <b>White moves first.</b>\n\n"

        "👇 Waiting for another player...",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )

    chess_games[
        chat.id
    ]["message_id"] = msg.message_id


# ==========================================
# CALLBACK HANDLER
# ==========================================

async def chess_callback(
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

    if data.startswith("chess_join:"):

        try:

            chat_id = int(
                data.split(":")[1]
            )

        except (ValueError, IndexError):

            await query.answer(
                "❌ Invalid game.",
                show_alert=True
            )

            return

        game = chess_games.get(chat_id)

        if not game:

            await query.answer(
                "❌ This game no longer exists.",
                show_alert=True
            )

            return

        user = query.from_user

        # Already a player
        if user.id in game["players"]:

            await query.answer(
                "✅ You are already in this game!",
                show_alert=True
            )

            return

        # Game full
        if len(game["players"]) >= 2:

            await query.answer(
                "🚫 This Chess game is full.",
                show_alert=True
            )

            return

        # ==================================
        # ADD BLACK PLAYER
        # ==================================

        game["players"].append(
            user.id
        )

        game["black"] = user.id

        game["names"][user.id] = (
            user.full_name
        )

        game["started"] = True

        game["board"] = chess.Board()

        game["selected_square"] = None

        await query.answer(
            "♟️ You joined as Black!"
        )

        await query.edit_message_text(

            build_game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=build_board_keyboard(
                chat_id,
                game["board"]
            )
        )

        return

    # ======================================
    # CANCEL
    # ======================================

    if data.startswith("chess_cancel:"):

        try:

            chat_id = int(
                data.split(":")[1]
            )

        except (ValueError, IndexError):

            await query.answer(
                "❌ Invalid game.",
                show_alert=True
            )

            return

        game = chess_games.get(chat_id)

        if not game:

            await query.answer(
                "❌ This game no longer exists.",
                show_alert=True
            )

            return

        user = query.from_user

        if user.id not in game["players"]:

            await query.answer(
                "🚫 Only players in this game "
                "can end it.",
                show_alert=True
            )

            return

        del chess_games[chat_id]

        await query.answer(
            "🛑 Chess game ended."
        )

        await query.edit_message_text(

            "🛑 <b>CHESS GAME ENDED</b>\n\n"
            "The current match has been "
            "cancelled.\n\n"
            "♟️ Start another one with "
            "<b>/chess</b>.",

            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # MOVE / SQUARE SELECTION
    # ======================================

    if data.startswith("chess_move:"):

        try:

            parts = data.split(":")

            chat_id = int(parts[1])
            square = int(parts[2])

        except (ValueError, IndexError):

            await query.answer(
                "❌ Invalid move.",
                show_alert=True
            )

            return

        game = chess_games.get(chat_id)

        if not game:

            await query.answer(
                "❌ This game no longer exists.",
                show_alert=True
            )

            return

        user = query.from_user

        # ==================================
        # ONLY PLAYERS
        # ==================================

        if user.id not in game["players"]:

            await query.answer(
                "🚫 You are not a player "
                "in this game.",
                show_alert=True
            )

            return

        board = game["board"]

        # ==================================
        # CHECK WHOSE TURN
        # ==================================

        if board.turn == chess.WHITE:

            current_player = game["white"]

        else:

            current_player = game["black"]

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
        # FIRST TAP — SELECT PIECE
        # ==================================

        selected = game.get(
            "selected_square"
        )

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

            # Correct color?
            if piece.color != board.turn:

                await query.answer(
                    "🚫 That's not your piece!",
                    show_alert=True
                )

                return

            game[
                "selected_square"
            ] = square

            await query.answer(
                f"Selected {square_name(square)}"
            )

            await query.edit_message_text(

                build_game_text(game),

                parse_mode=ParseMode.HTML,

                reply_markup=build_board_keyboard(
                    chat_id,
                    board,
                    selected=square
                )
            )

            return

        # ==================================
        # SECOND TAP — DESTINATION
        # ==================================

        # Tapping same square cancels selection
        if selected == square:

            game[
                "selected_square"
            ] = None

            await query.answer(
                "Selection cancelled."
            )

            await query.edit_message_text(

                build_game_text(game),

                parse_mode=ParseMode.HTML,

                reply_markup=build_board_keyboard(
                    chat_id,
                    board
                )
            )

            return

        # ==================================
        # CREATE MOVE
        # ==================================

        move = chess.Move(
            selected,
            square
        )

        # ==================================
        # PROMOTION
        # ==================================

        piece = board.piece_at(
            selected
        )

        if (
            piece
            and piece.piece_type == chess.PAWN
            and chess.square_rank(square)
            in [0, 7]
        ):

            # Default promotion to Queen.
            # A dedicated promotion selector
            # can be added later.
            move = chess.Move(
                selected,
                square,
                promotion=chess.QUEEN
            )

        # ==================================
        # ILLEGAL MOVE
        # ==================================

        if move not in board.legal_moves:

            game[
                "selected_square"
            ] = None

            await query.answer(
                "🚫 Illegal move!",
                show_alert=True
            )

            await query.edit_message_text(

                build_game_text(game),

                parse_mode=ParseMode.HTML,

                reply_markup=build_board_keyboard(
                    chat_id,
                    board
                )
            )

            return

        # ==================================
        # MAKE MOVE
        # ==================================

        board.push(move)

        game[
            "selected_square"
        ] = None

        # ==================================
        # CHECKMATE
        # ==================================

        if board.is_checkmate():

            winner_id = user.id

            winner_name = game["names"].get(
                winner_id,
                "Player"
            )

            winner_color = (
                "White"
                if board.turn == chess.BLACK
                else "Black"
            )

            await query.answer(
                "🏆 Checkmate!"
            )

            await query.edit_message_text(

                "🏆 <b>CHECKMATE!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                f"👑 <b>Winner:</b> "
                f"{player_mention(winner_id, winner_name)}\n\n"

                f"♟️ <b>{winner_color}</b> wins!\n\n"

                f"{board_text(board)}\n\n"

                "🎉 <b>GG!</b>",

                parse_mode=ParseMode.HTML
            )

            del chess_games[chat_id]

            return

        # ==================================
        # DRAW
        # ==================================

        if board.is_stalemate():

            await query.answer(
                "🤝 Stalemate!"
            )

            await query.edit_message_text(

                "🤝 <b>CHESS DRAW!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                "⚖️ <b>Stalemate!</b>\n"
                "No legal moves remain.\n\n"

                f"{board_text(board)}",

                parse_mode=ParseMode.HTML
            )

            del chess_games[chat_id]

            return

        if board.is_insufficient_material():

            await query.answer(
                "🤝 Draw!"
            )

            await query.edit_message_text(

                "🤝 <b>CHESS DRAW!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                "♟️ Neither side has enough "
                "material to checkmate.\n\n"

                f"{board_text(board)}",

                parse_mode=ParseMode.HTML
            )

            del chess_games[chat_id]

            return

        # ==================================
        # FIFTY-MOVE / OTHER DRAW
        # ==================================

        if (
            board.is_fifty_moves()
            or board.is_seventyfive_moves()
            or board.is_fivefold_repetition()
        ):

            await query.answer(
                "🤝 Draw!"
            )

            await query.edit_message_text(

                "🤝 <b>CHESS DRAW!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                "⚖️ The game ended by draw rule.\n\n"

                f"{board_text(board)}",

                parse_mode=ParseMode.HTML
            )

            del chess_games[chat_id]

            return

        # ==================================
        # NORMAL MOVE
        # ==================================

        if board.is_check():

            status = "\n\n⚠️ <b>CHECK!</b>"

        else:

            status = ""

        await query.answer(
            "✅ Move played!"
        )

        await query.edit_message_text(

            build_game_text(game)
            + status,

            parse_mode=ParseMode.HTML,

            reply_markup=build_board_keyboard(
                chat_id,
                board
            )
        )

        return


# ==========================================
# /endchess
# ==========================================

async def endchess_command(
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
            "♟️ Chess can only be ended "
            "inside a group."
        )

        return

    game = chess_games.get(
        chat.id
    )

    if not game:

        await update.message.reply_text(
            "❌ There is no active Chess game."
        )

        return

    # ======================================
    # ONLY PLAYERS
    # ======================================

    if user.id not in game["players"]:

        await update.message.reply_text(
            "🚫 <b>Only players in the current "
            "Chess game can end it.</b>",
            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # DELETE GAME
    # ======================================

    del chess_games[
        chat.id
    ]

    await update.message.reply_text(

        "🛑 <b>CHESS GAME ENDED</b>\n\n"

        f"👤 Ended by "
        f"{player_mention(user.id, user.full_name)}\n\n"

        "♟️ The current match has been stopped.\n"
        "Start a new game with <b>/chess</b>.",

        parse_mode=ParseMode.HTML
    )