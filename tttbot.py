# ==========================================
# 🎮 MUICHIRO • TIC TAC TOE BOT
# ==========================================

import random

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

tttbot_games = {}


# ==========================================
# DIFFICULTIES
# ==========================================

TTT_DIFFICULTIES = {
    "easy": {
        "name": "🟢 Easy",
    },
    "normal": {
        "name": "🟡 Normal",
    },
    "hard": {
        "name": "🔴 Hard",
    },
}


# ==========================================
# PLAYER MENTION
# ==========================================

def ttt_mention(user_id, name):

    return (
        f'<a href="tg://user?id={user_id}">'
        f'{name}</a>'
    )


# ==========================================
# WINNING COMBINATIONS
# ==========================================

WINNING_LINES = [

    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),

    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),

    (0, 4, 8),
    (2, 4, 6),

]


# ==========================================
# CHECK WINNER
# ==========================================

def ttt_winner(board):

    for a, b, c in WINNING_LINES:

        if (
            board[a] != ""
            and board[a] == board[b]
            and board[b] == board[c]
        ):

            return board[a]

    return None


# ==========================================
# CHECK DRAW
# ==========================================

def ttt_draw(board):

    return (
        ttt_winner(board) is None
        and all(board)
    )


# ==========================================
# BOARD TEXT
# ==========================================

def ttt_board_text(board):

    symbols = []

    for cell in board:

        if cell == "X":
            symbols.append("❌")

        elif cell == "O":
            symbols.append("⭕")

        else:
            symbols.append("▫️")

    return (
        f"{symbols[0]} {symbols[1]} {symbols[2]}\n"
        f"{symbols[3]} {symbols[4]} {symbols[5]}\n"
        f"{symbols[6]} {symbols[7]} {symbols[8]}"
    )


# ==========================================
# BOARD BUTTONS
# ==========================================

def ttt_keyboard(game):

    chat_id = game["chat_id"]

    board = game["board"]

    buttons = []

    for i in range(9):

        if board[i] == "X":

            text = "❌"

        elif board[i] == "O":

            text = "⭕"

        else:

            text = str(i + 1)

        buttons.append(
            InlineKeyboardButton(
                text,
                callback_data=(
                    f"tttb_move:{chat_id}:{i}"
                )
            )
        )

    keyboard = [

        buttons[0:3],
        buttons[3:6],
        buttons[6:9],

        [
            InlineKeyboardButton(
                "❌ End Game",
                callback_data=(
                    f"tttb_end:{chat_id}"
                )
            )
        ],

    ]

    return InlineKeyboardMarkup(
        keyboard
    )


# ==========================================
# DIFFICULTY KEYBOARD
# ==========================================

def ttt_difficulty_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "🟢 Easy",
                    callback_data="tttb_diff:easy"
                )
            ],

            [
                InlineKeyboardButton(
                    "🟡 Normal",
                    callback_data="tttb_diff:normal"
                )
            ],

            [
                InlineKeyboardButton(
                    "🔴 Hard",
                    callback_data="tttb_diff:hard"
                )
            ],

        ]
    )


# ==========================================
# SYMBOL KEYBOARD
# ==========================================

def ttt_symbol_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "❌ Play X",
                    callback_data="tttb_symbol:X"
                ),

                InlineKeyboardButton(
                    "⭕ Play O",
                    callback_data="tttb_symbol:O"
                ),
            ]

        ]
    )


# ==========================================
# RESULT KEYBOARD
# ==========================================

def ttt_result_keyboard(chat_id):

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "🔄 Rematch",
                    callback_data=(
                        f"tttb_rematch:{chat_id}"
                    )
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Close",
                    callback_data=(
                        f"tttb_close:{chat_id}"
                    )
                )
            ],

        ]
    )


# ==========================================
# GAME TEXT
# ==========================================

def ttt_game_text(game):

    player_symbol = game["player_symbol"]

    bot_symbol = game["bot_symbol"]

    if game["turn"] == "player":

        turn = (
            "👤 <b>Your turn!</b>\n"
            "👇 Choose a square."
        )

    else:

        turn = (
            "🤖 <b>Muichiro's turn...</b>"
        )

    return (

        "🎮 <b>MUICHIRO • TIC TAC TOE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"👤 <b>You:</b> "
        f"{ttt_mention(game['user_id'], game['user_name'])}\n"

        f"❌/⭕ <b>Your symbol:</b> "
        f"{player_symbol}\n"

        f"🤖 <b>Bot:</b> "
        f"{bot_symbol}\n\n"

        f"🎯 <b>Difficulty:</b> "
        f"{game['difficulty']}\n\n"

        f"{ttt_board_text(game['board'])}\n\n"

        "━━━━━━━━━━━━━━━━━━\n"

        f"{turn}"

    )


# ==========================================
# EMPTY MOVES
# ==========================================

def available_moves(board):

    return [
        i
        for i, cell in enumerate(board)
        if cell == ""
    ]


# ==========================================
# EASY BOT
# ==========================================

def easy_move(board):

    return random.choice(
        available_moves(board)
    )


# ==========================================
# NORMAL BOT
# ==========================================

def normal_move(
    board,
    bot_symbol,
    player_symbol
):

    moves = available_moves(board)

    if not moves:
        return None

    # Try to win
    for move in moves:

        test = board[:]

        test[move] = bot_symbol

        if ttt_winner(test) == bot_symbol:

            return move

    # Block player
    for move in moves:

        test = board[:]

        test[move] = player_symbol

        if ttt_winner(test) == player_symbol:

            return move

    # Take center
    if 4 in moves:

        return 4

    # Take corner
    corners = [
        x for x in [0, 2, 6, 8]
        if x in moves
    ]

    if corners:

        return random.choice(
            corners
        )

    return random.choice(
        moves
    )


# ==========================================
# MINIMAX
# ==========================================

def minimax(
    board,
    bot_symbol,
    player_symbol,
    maximizing
):

    winner = ttt_winner(board)

    if winner == bot_symbol:
        return 1

    if winner == player_symbol:
        return -1

    if ttt_draw(board):
        return 0

    moves = available_moves(board)

    if maximizing:

        best_score = -999

        for move in moves:

            board[move] = bot_symbol

            score = minimax(
                board,
                bot_symbol,
                player_symbol,
                False
            )

            board[move] = ""

            best_score = max(
                best_score,
                score
            )

        return best_score

    else:

        best_score = 999

        for move in moves:

            board[move] = player_symbol

            score = minimax(
                board,
                bot_symbol,
                player_symbol,
                True
            )

            board[move] = ""

            best_score = min(
                best_score,
                score
            )

        return best_score


# ==========================================
# HARD BOT
# ==========================================

def hard_move(
    board,
    bot_symbol,
    player_symbol
):

    best_score = -999

    best_moves = []

    for move in available_moves(board):

        board[move] = bot_symbol

        score = minimax(
            board,
            bot_symbol,
            player_symbol,
            False
        )

        board[move] = ""

        if score > best_score:

            best_score = score

            best_moves = [move]

        elif score == best_score:

            best_moves.append(move)

    return random.choice(
        best_moves
    )


# ==========================================
# BOT MOVE
# ==========================================

def get_ttt_bot_move(game):

    board = game["board"]

    difficulty = game[
        "difficulty_key"
    ]

    bot_symbol = game[
        "bot_symbol"
    ]

    player_symbol = game[
        "player_symbol"
    ]

    if difficulty == "easy":

        return easy_move(board)

    if difficulty == "normal":

        return normal_move(
            board,
            bot_symbol,
            player_symbol
        )

    return hard_move(
        board,
        bot_symbol,
        player_symbol
    )


# ==========================================
# /TTTBOT
# ==========================================

async def tttbot_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return

    if chat.id in tttbot_games:

        await update.message.reply_text(

            "🎮 <b>TIC TAC TOE ALREADY RUNNING!</b>\n\n"

            "Finish the current match first.",

            parse_mode=ParseMode.HTML
        )

        return

    await update.message.reply_text(

        "🎮 <b>MUICHIRO • TIC TAC TOE BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "🤖 <b>Choose your difficulty:</b>\n\n"

        "🟢 Easy — Casual game\n"
        "🟡 Normal — Smarter opponent\n"
        "🔴 Hard — Unbeatable opponent\n\n"

        "👇 Select a difficulty:",

        parse_mode=ParseMode.HTML,

        reply_markup=ttt_difficulty_keyboard()
    )


# ==========================================
# CALLBACK
# ==========================================

async def tttbot_callback(
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

    if data.startswith("tttb_diff:"):

        difficulty = data.split(
            ":",
            1
        )[1]

        await query.answer()

        await query.edit_message_text(

            "🎮 <b>TIC TAC TOE</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            f"🎯 <b>Difficulty:</b> "
            f"{TTT_DIFFICULTIES[difficulty]['name']}\n\n"

            "Choose your symbol:",

            parse_mode=ParseMode.HTML,

            reply_markup=ttt_symbol_keyboard()
        )

        # Temporarily store setup
        user = query.from_user

        # Find/create setup
        for key, game in list(
            tttbot_games.items()
        ):

            if game.get(
                "user_id"
            ) == user.id:

                tttbot_games.pop(
                    key,
                    None
                )

        tttbot_games[
            query.message.chat.id
        ] = {

            "chat_id":
                query.message.chat.id,

            "user_id":
                user.id,

            "user_name":
                user.full_name,

            "difficulty_key":
                difficulty,

            "difficulty":
                TTT_DIFFICULTIES[
                    difficulty
                ]["name"],

            "setup":
                True,

        }

        return

    # ======================================
    # SYMBOL
    # ======================================

    if data.startswith("tttb_symbol:"):

        symbol = data.split(
            ":",
            1
        )[1]

        user = query.from_user

        chat_id = query.message.chat.id

        game = tttbot_games.get(
            chat_id
        )

        if not game:

            await query.answer(
                "❌ Game setup expired.",
                show_alert=True
            )

            return

        if game["user_id"] != user.id:

            await query.answer(
                "🚫 This isn't your game.",
                show_alert=True
            )

            return

        game["player_symbol"] = symbol

        game["bot_symbol"] = (
            "O"
            if symbol == "X"
            else "X"
        )

        game["board"] = [
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]

        game["setup"] = False

        if symbol == "X":

            game["turn"] = "player"

        else:

            game["turn"] = "bot"

        await query.answer(
            "🎮 Game started!"
        )

        await query.edit_message_text(

            ttt_game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=ttt_keyboard(game)
        )

        # Bot starts if player chose O
        if symbol == "O":

            move = get_ttt_bot_move(
                game
            )

            game["board"][move] = (
                game["bot_symbol"]
            )

            game["turn"] = "player"

            await query.edit_message_text(

                ttt_game_text(game),

                parse_mode=ParseMode.HTML,

                reply_markup=ttt_keyboard(game)
            )

        return

    # ======================================
    # MOVE
    # ======================================

    if data.startswith("tttb_move:"):

        try:

            parts = data.split(":")

            chat_id = int(parts[1])

            position = int(parts[2])

        except (
            ValueError,
            IndexError
        ):

            return

        game = tttbot_games.get(
            chat_id
        )

        if not game or game.get("setup"):

            return

        user = query.from_user

        if user.id != game["user_id"]:

            await query.answer(
                "🚫 This isn't your game!",
                show_alert=True
            )

            return

        if game["turn"] != "player":

            await query.answer(
                "🤖 Wait for Muichiro!",
                show_alert=True
            )

            return

        if game["board"][position] != "":

            await query.answer(
                "🚫 That square is already occupied!",
                show_alert=True
            )

            return

        # Player move
        game["board"][position] = (
            game["player_symbol"]
        )

        winner = ttt_winner(
            game["board"]
        )

        if winner:

            tttbot_games.pop(
                chat_id,
                None
            )

            await query.answer(
                "🎉 You won!"
            )

            await query.edit_message_text(

                "🏆 <b>TIC TAC TOE — YOU WIN!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                f"👑 "
                f"{ttt_mention(user.id, user.full_name)}\n\n"

                f"{ttt_board_text(game['board'])}\n\n"

                "🎉 <b>Congratulations!</b>",

                parse_mode=ParseMode.HTML,

                reply_markup=ttt_result_keyboard(
                    chat_id
                )
            )

            return

        if ttt_draw(game["board"]):

            tttbot_games.pop(
                chat_id,
                None
            )

            await query.answer(
                "🤝 Draw!"
            )

            await query.edit_message_text(

                "🤝 <b>TIC TAC TOE — DRAW!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                f"{ttt_board_text(game['board'])}\n\n"

                "Nobody won this time!",

                parse_mode=ParseMode.HTML,

                reply_markup=ttt_result_keyboard(
                    chat_id
                )
            )

            return

        game["turn"] = "bot"

        await query.edit_message_text(

            ttt_game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=ttt_keyboard(game)
        )

        # Bot move
        move = get_ttt_bot_move(
            game
        )

        game["board"][move] = (
            game["bot_symbol"]
        )

        winner = ttt_winner(
            game["board"]
        )

        if winner:

            tttbot_games.pop(
                chat_id,
                None
            )

            await query.edit_message_text(

                "🤖 <b>MUICHIRO WINS!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                f"{ttt_board_text(game['board'])}\n\n"

                "😎 Better luck next time!",

                parse_mode=ParseMode.HTML,

                reply_markup=ttt_result_keyboard(
                    chat_id
                )
            )

            return

        if ttt_draw(game["board"]):

            tttbot_games.pop(
                chat_id,
                None
            )

            await query.edit_message_text(

                "🤝 <b>TIC TAC TOE — DRAW!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"

                f"{ttt_board_text(game['board'])}",

                parse_mode=ParseMode.HTML,

                reply_markup=ttt_result_keyboard(
                    chat_id
                )
            )

            return

        game["turn"] = "player"

        await query.edit_message_text(

            ttt_game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=ttt_keyboard(game)
        )

        return

    # ======================================
    # END
    # ======================================

    if data.startswith("tttb_end:"):

        chat_id = int(
            data.split(":")[1]
        )

        game = tttbot_games.get(
            chat_id
        )

        if not game:
            return

        if query.from_user.id != game["user_id"]:

            await query.answer(
                "🚫 Only the player can end this game.",
                show_alert=True
            )

            return

        tttbot_games.pop(
            chat_id,
            None
        )

        await query.answer(
            "Game ended."
        )

        await query.edit_message_text(

            "🛑 <b>TIC TAC TOE GAME ENDED</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "Use <b>/tttbot</b> to play again.",

            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # REMATCH
    # ======================================

    if data.startswith("tttb_rematch:"):

        await query.answer()

        await query.edit_message_text(

            "🎮 <b>NEW TIC TAC TOE MATCH</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "Choose your difficulty:",

            parse_mode=ParseMode.HTML,

            reply_markup=ttt_difficulty_keyboard()
        )

        return

    # ======================================
    # CLOSE
    # ======================================

    if data.startswith("tttb_close:"):

        await query.answer()

        await query.edit_message_text(

            "🎮 <b>Tic Tac Toe closed.</b>\n\n"
            "Use <b>/tttbot</b> to play again.",

            parse_mode=ParseMode.HTML
        )


# ==========================================
# /ENDTTTBOT
# ==========================================

async def endtttbot_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat_id = update.effective_chat.id

    user = update.effective_user

    game = tttbot_games.get(
        chat_id
    )

    if not game:

        await update.message.reply_text(
            "❌ No active Tic Tac Toe game."
        )

        return

    if game["user_id"] != user.id:

        await update.message.reply_text(
            "🚫 Only the player can end this game."
        )

        return

    tttbot_games.pop(
        chat_id,
        None
    )

    await update.message.reply_text(

        "🛑 <b>TIC TAC TOE GAME ENDED</b>\n\n"
        "Use <b>/tttbot</b> to play again.",

        parse_mode=ParseMode.HTML
    )