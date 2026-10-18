# ==========================================
# 🎮 TIC-TAC-TOE
# ==========================================

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import ContextTypes


# ==========================================
# ACTIVE GAMES
# ==========================================

tic_tac_toe_games = {}


# ==========================================
# USER MENTION
# ==========================================

def mention_user(user):

    name = user.full_name or "Player"

    # Escape HTML
    name = (
        name
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    if user.username:
        return f"@{user.username}"

    return (
        f'<a href="tg://user?id={user.id}">'
        f'{name}'
        f'</a>'
    )


# ==========================================
# BOARD
# ==========================================

def create_board(game_id, board):

    keyboard = []

    for row in range(3):

        buttons = []

        for column in range(3):

            position = row * 3 + column

            symbol = board[position]

            if not symbol:
                symbol = "⬜"

            buttons.append(
                InlineKeyboardButton(
                    symbol,
                    callback_data=(
                        f"ttt_move:"
                        f"{game_id}:"
                        f"{position}"
                    )
                )
            )

        keyboard.append(buttons)

    keyboard.append([
        InlineKeyboardButton(
            "🛑 Cancel Game",
            callback_data=f"ttt_cancel:{game_id}"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


# ==========================================
# CHECK WINNER
# ==========================================

def check_winner(board):

    winning_combinations = [

        # Rows
        (0, 1, 2),
        (3, 4, 5),
        (6, 7, 8),

        # Columns
        (0, 3, 6),
        (1, 4, 7),
        (2, 5, 8),

        # Diagonal
        (0, 4, 8),
        (2, 4, 6)
    ]

    for a, b, c in winning_combinations:

        if (
            board[a]
            and board[a] == board[b]
            and board[a] == board[c]
        ):

            return board[a]

    return None


# ==========================================
# DRAW CHECK
# ==========================================

def is_draw(board):

    return all(board)


# ==========================================
# BOARD TEXT
# ==========================================

def board_text(board):

    rows = []

    for row in range(3):

        start = row * 3

        rows.append(
            " ".join(
                board[start:start + 3]
                [i] or "⬜"
                for i in range(3)
            )
        )

    return "\n".join(rows)


# ==========================================
# FIND ACTIVE GAME
# ==========================================

def player_has_game(chat_id, user_id):

    for game in tic_tac_toe_games.values():

        if game["chat_id"] != chat_id:
            continue

        if user_id in [
            game["player_x"],
            game["player_o"]
        ]:

            return True

    return False


# ==========================================
# /TTT
# ==========================================

async def ttt_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    # ==========================================
    # GROUP ONLY
    # ==========================================

    if chat.type not in [
        "group",
        "supergroup"
    ]:

        await update.message.reply_text(
            "🎮 Tic-Tac-Toe can only be played "
            "in groups."
        )

        return

    # ==========================================
    # ALREADY PLAYING
    # ==========================================

    if player_has_game(
        chat.id,
        user.id
    ):

        await update.message.reply_text(
            "🎮 You're already in an active "
            "Tic-Tac-Toe game!"
        )

        return

    # ==========================================
    # CREATE GAME ID
    # ==========================================

    game_id = (
        f"{chat.id}_"
        f"{user.id}_"
        f"{update.message.message_id}"
    )

    # ==========================================
    # CREATE GAME
    # ==========================================

    tic_tac_toe_games[game_id] = {

        "chat_id": chat.id,

        "creator": user.id,

        "player_x": user.id,

        "player_o": None,

        "player_x_user": user,

        "player_o_user": None,

        "board": [""] * 9,

        "turn": user.id,

        "started": False
    }

    # ==========================================
    # START MESSAGE
    # ==========================================

    creator = mention_user(user)

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🎮 Join Game",
                callback_data=f"ttt_join:{game_id}"
            ),

            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=f"ttt_cancel:{game_id}"
            )
        ]

    ])

    await update.message.reply_text(

        "🎮 <b>TIC-TAC-TOE</b>\n\n"

        f"👤 {creator} wants to play!\n\n"

        "❌ They will play as <b>X</b>\n"
        "⭕ The opponent will play as <b>O</b>\n\n"

        "👇 Someone join the game!",

        parse_mode="HTML",

        reply_markup=keyboard
    )


# ==========================================
# CALLBACK HANDLER
# ==========================================

async def ttt_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data

    if not data:
        return

    # ==========================================
    # SPLIT CALLBACK
    # ==========================================

    parts = data.split(":")

    action = parts[0]

    game_id = parts[1]

    game = tic_tac_toe_games.get(game_id)

    # ==========================================
    # GAME DOESN'T EXIST
    # ==========================================

    if not game:

        await query.answer(
            "❌ This game no longer exists.",
            show_alert=True
        )

        return

    user = query.from_user

    # ==========================================
    # JOIN GAME
    # ==========================================

    if action == "ttt_join":

        # Creator cannot join themselves
        if user.id == game["creator"]:

            await query.answer(
                "😂 You already created this game!",
                show_alert=True
            )

            return

        # Already started
        if game["started"]:

            await query.answer(
                "🎮 This game has already started!",
                show_alert=True
            )

            return

        # User already playing another game
        if player_has_game(
            game["chat_id"],
            user.id
        ):

            await query.answer(
                "🎮 You're already playing "
                "another game!",
                show_alert=True
            )

            return

        # ======================================
        # ADD PLAYER
        # ======================================

        game["player_o"] = user.id

        game["player_o_user"] = user

        game["started"] = True

        x_user = game["player_x_user"]

        o_user = game["player_o_user"]

        x_name = mention_user(x_user)

        o_name = mention_user(o_user)

        keyboard = create_board(
            game_id,
            game["board"]
        )

        await query.edit_message_text(

            "🎮 <b>TIC-TAC-TOE</b>\n\n"

            f"❌ {x_name}\n"
            f"⭕ {o_name}\n\n"

            f"👉 {x_name}'s turn!\n\n"

            "Choose a square 👇",

            parse_mode="HTML",

            reply_markup=keyboard
        )

        return

    # ==========================================
    # CANCEL GAME
    # ==========================================

    if action == "ttt_cancel":

        if user.id not in [
            game["player_x"],
            game["player_o"]
        ]:

            await query.answer(
                "👀 This isn't your game!",
                show_alert=True
            )

            return

        del tic_tac_toe_games[game_id]

        await query.edit_message_text(

            "🛑 <b>Tic-Tac-Toe cancelled.</b>\n\n"
            "Maybe next time 😎",

            parse_mode="HTML"
        )

        return

    # ==========================================
    # MOVE
    # ==========================================

    if action != "ttt_move":
        return

    position = int(parts[2])

    # ==========================================
    # PLAYER CHECK
    # ==========================================

    if user.id not in [
        game["player_x"],
        game["player_o"]
    ]:

        await query.answer(
            "👀 You're not playing this game!",
            show_alert=True
        )

        return

    # ==========================================
    # TURN CHECK
    # ==========================================

    if user.id != game["turn"]:

        await query.answer(
            "⏳ It's not your turn!",
            show_alert=True
        )

        return

    # ==========================================
    # SQUARE CHECK
    # ==========================================

    if game["board"][position]:

        await query.answer(
            "❌ That square is already taken!",
            show_alert=True
        )

        return

    # ==========================================
    # SYMBOL
    # ==========================================

    if user.id == game["player_x"]:

        symbol = "❌"

    else:

        symbol = "⭕"

    game["board"][position] = symbol

    # ==========================================
    # WINNER
    # ==========================================

    winner = check_winner(
        game["board"]
    )

    if winner:

        if winner == "❌":

            winner_user = (
                game["player_x_user"]
            )

        else:

            winner_user = (
                game["player_o_user"]
            )

        winner_name = mention_user(
            winner_user
        )

        await query.edit_message_text(

            "🏆 <b>TIC-TAC-TOE</b>\n\n"

            f"{board_text(game['board'])}\n\n"

            f"🎉 {winner_name} <b>wins!</b>\n\n"
            "🔥 GG!",

            parse_mode="HTML"
        )

        del tic_tac_toe_games[game_id]

        return

    # ==========================================
    # DRAW
    # ==========================================

    if is_draw(game["board"]):

        await query.edit_message_text(

            "🤝 <b>TIC-TAC-TOE</b>\n\n"

            f"{board_text(game['board'])}\n\n"

            "🤝 <b>It's a draw!</b>\n\n"
            "Nobody wins this time 😎",

            parse_mode="HTML"
        )

        del tic_tac_toe_games[game_id]

        return

    # ==========================================
    # NEXT TURN
    # ==========================================

    if game["turn"] == game["player_x"]:

        game["turn"] = game["player_o"]

        turn_user = game["player_o_user"]

    else:

        game["turn"] = game["player_x"]

        turn_user = game["player_x_user"]

    turn_name = mention_user(
        turn_user
    )

    # ==========================================
    # UPDATE BOARD
    # ==========================================

    keyboard = create_board(
        game_id,
        game["board"]
    )

    await query.edit_message_text(

        "🎮 <b>TIC-TAC-TOE</b>\n\n"

        f"❌ {mention_user(game['player_x_user'])}\n"
        f"⭕ {mention_user(game['player_o_user'])}\n\n"

        f"{board_text(game['board'])}\n\n"

        f"👉 {turn_name}'s turn!",

        parse_mode="HTML",

        reply_markup=keyboard
    )