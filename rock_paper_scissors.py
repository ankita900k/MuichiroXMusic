# ==========================================
# ROCK PAPER SCISSORS
# ==========================================

from html import escape
import html
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import ContextTypes


# ==========================================
# ACTIVE RPS GAMES
# ==========================================

rps_games = {}


# ==========================================
# MOVES
# ==========================================

RPS_EMOJIS = {
    "rock": "✊",
    "paper": "📄",
    "scissors": "✂️"
}


# ==========================================
# WIN RULES
# ==========================================

WIN_RULES = {
    "rock": "scissors",
    "paper": "rock",
    "scissors": "paper"
}


# ==========================================
# JOIN KEYBOARD
# ==========================================

def rps_join_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎮 Join Game",
                callback_data="rps_join"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="rps_cancel"
            )
        ]
    ])


# ==========================================
# MOVE KEYBOARD
# ==========================================

def rps_move_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✊ Rock",
                callback_data="rps_move:rock"
            ),
            InlineKeyboardButton(
                "📄 Paper",
                callback_data="rps_move:paper"
            ),
            InlineKeyboardButton(
                "✂️ Scissors",
                callback_data="rps_move:scissors"
            )
        ]
    ])


# ==========================================
# NEXT ROUND KEYBOARD
# ==========================================

def rps_next_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "▶️ Next Round",
                callback_data="rps_next"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ End Game",
                callback_data="rps_cancel"
            )
        ]
    ])


# ==========================================
# /RPS COMMAND
# ==========================================

async def rps_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat

    if not chat:
        return

    # --------------------------------------
    # GROUP ONLY
    # --------------------------------------

    if chat.type not in [
        "group",
        "supergroup"
    ]:

        await update.message.reply_text(
            "❌ This game can only be played in groups."
        )

        return

    chat_id = chat.id

    # --------------------------------------
    # EXISTING GAME
    # --------------------------------------

    if chat_id in rps_games:

        await update.message.reply_text(
            "🎮 A Rock Paper Scissors game "
            "is already running here!\n"
            "Use /endrps for ending it."
        )

        return

    user = update.effective_user

    if not user:
        return

    player_name = escape(
        user.full_name or "Player"
    )

    # --------------------------------------
    # CREATE GAME
    # --------------------------------------

    rps_games[chat_id] = {

        "player1": user.id,
        "player1_name": player_name,

        "player2": None,
        "player2_name": None,

        "moves": {},

        "score": {
            user.id: 0
        },

        "round": 1,

        "message_id": None,

        "waiting_message_id": None
    }

    # --------------------------------------
    # SEND GAME
    # --------------------------------------

    message = await update.message.reply_text(

        "✊📄✂️ <b>ROCK PAPER SCISSORS</b>\n\n"

        f"❌ <b>{player_name}</b> "
        "created the game!\n\n"

        "🎮 Waiting for another player...\n"
        "Tap <b>Join Game</b> to play.",

        parse_mode="HTML",

        reply_markup=rps_join_keyboard()
    )

    rps_games[chat_id][
        "message_id"
    ] = message.message_id


# ==========================================
# CALLBACK HANDLER
# ==========================================

async def rps_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    chat = query.message.chat

    if not chat:
        return

    chat_id = chat.id

    user = query.from_user

    data = query.data

    # ======================================
    # GET GAME
    # ======================================

    game = rps_games.get(chat_id)

    if not game:

        try:
            await query.answer(
                "❌ There is no active game.",
                show_alert=True
            )
        except Exception:
            pass

        return

    # ======================================
    # JOIN GAME
    # ======================================

    if data == "rps_join":

        # Creator cannot join themselves
        if user.id == game["player1"]:

            await query.answer(
                "😂 You already created this game!",
                show_alert=True
            )

            return

        # Game already has 2 players
        if game["player2"]:

            await query.answer(
                "❌ This game already has 2 players.",
                show_alert=True
            )

            return

        player2_name = escape(
            user.full_name or "Player"
        )

        # ----------------------------------
        # ADD PLAYER 2
        # ----------------------------------

        game["player2"] = user.id
        game["player2_name"] = player2_name

        game["score"][user.id] = 0

        # ----------------------------------
        # SHOW MOVE BUTTONS
        # ----------------------------------

        try:

            await query.message.edit_text(

                "✊📄✂️ <b>ROCK PAPER SCISSORS</b>\n\n"

                f"❌ <b>{game['player1_name']}</b>\n"
                f"⭕ <b>{player2_name}</b>\n\n"

                "🏆 <b>Best of 3</b>\n"
                "First player to reach 2 wins wins the match!\n\n"

                "🎮 <b>Round 1</b>\n\n"
                "Choose your move!",

                parse_mode="HTML",

                reply_markup=rps_move_keyboard()
            )

        except Exception as e:

            print(
                f"⚠️ RPS join error: {e}"
            )

        return

    # ======================================
    # CANCEL GAME
    # ======================================

    if data == "rps_cancel":

        # Only players can cancel
        if user.id not in [
            game["player1"],
            game["player2"]
        ]:

            await query.answer(
                "❌ You are not part of this game.",
                show_alert=True
            )

            return

        # ----------------------------------
        # DELETE WAITING MESSAGE
        # ----------------------------------

        waiting_id = game.get(
            "waiting_message_id"
        )

        if waiting_id:

            try:

                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=waiting_id
                )

            except Exception:
                pass

        # ----------------------------------
        # REMOVE GAME
        # ----------------------------------

        rps_games.pop(
            chat_id,
            None
        )

        try:

            await query.message.edit_text(

                "❌ <b>Rock Paper Scissors ended.</b>\n\n"
                "🎮 Start a new match with /rps",

                parse_mode="HTML"
            )

        except Exception as e:

            print(
                f"⚠️ RPS cancel error: {e}"
            )

        return

    # ======================================
    # NEXT ROUND
    # ======================================

    if data == "rps_next":

        # Only players
        if user.id not in [
            game["player1"],
            game["player2"]
        ]:

            await query.answer(
                "❌ You are not a player.",
                show_alert=True
            )

            return

        # ----------------------------------
        # PREPARE NEW ROUND
        # ----------------------------------

        game["round"] += 1

        game["moves"] = {}

        game["waiting_message_id"] = None

        # ----------------------------------
        # SAFETY
        # ----------------------------------

        if game["round"] > 3:

            await query.message.edit_text(
                "❌ This match has already ended.\n\n"
                "🎮 Start a new match with /rps",
                parse_mode="HTML"
            )

            rps_games.pop(
                chat_id,
                None
            )

            return

        # ----------------------------------
        # SHOW NEXT ROUND
        # ----------------------------------

        try:

            await query.message.edit_text(

                "✊📄✂️ <b>ROCK PAPER SCISSORS</b>\n\n"

                f"❌ <b>{game['player1_name']}</b>\n"
                f"⭕ <b>{game['player2_name']}</b>\n\n"

                "🏆 <b>Best of 3</b>\n\n"

                f"🎮 <b>Round {game['round']}</b>\n\n"

                "Choose your move!",

                parse_mode="HTML",

                reply_markup=rps_move_keyboard()
            )

        except Exception as e:

            print(
                f"⚠️ RPS next round error: {e}"
            )

        return

    # ======================================
    # MOVE
    # ======================================

    if data.startswith("rps_move:"):

        # ----------------------------------
        # ONLY PLAYERS
        # ----------------------------------

        if user.id not in [
            game["player1"],
            game["player2"]
        ]:

            await query.answer(
                "❌ You are not playing this game.",
                show_alert=True
            )

            return

        # ----------------------------------
        # NEED SECOND PLAYER
        # ----------------------------------

        if not game["player2"]:

            await query.answer(
                "⏳ Waiting for another player.",
                show_alert=True
            )

            return

        # ----------------------------------
        # GET MOVE
        # ----------------------------------

        move = data.split(
            ":",
            1
        )[1]

        if move not in RPS_EMOJIS:

            await query.answer(
                "❌ Invalid move.",
                show_alert=True
            )

            return

        # ----------------------------------
        # ALREADY MOVED
        # ----------------------------------

        if user.id in game["moves"]:

            await query.answer(
                "🔒 You already locked your move!",
                show_alert=True
            )

            return

        # ----------------------------------
        # SAVE MOVE
        # ----------------------------------

        game["moves"][user.id] = move

        print(
            f"🎮 RPS move | "
            f"user={user.full_name} | "
            f"move={move} | "
            f"round={game['round']}"
        )

        await query.answer(
            f"{RPS_EMOJIS[move]} Move locked!"
        )

        # ==================================
        # ONLY ONE PLAYER MOVED
        # ==================================

        if len(game["moves"]) == 1:

            waiting_message = (
                await query.message.reply_text(

                    f"🔒 <b>{escape(user.full_name)}</b> "
                    "has locked in their move!\n\n"

                    "⏳ Waiting for the other player...",

                    parse_mode="HTML"
                )
            )

            game[
                "waiting_message_id"
            ] = waiting_message.message_id

            return

        # ==================================
        # BOTH PLAYERS MOVED
        # ==================================

        if len(game["moves"]) == 2:

            p1 = game["player1"]
            p2 = game["player2"]

            move1 = game["moves"].get(p1)
            move2 = game["moves"].get(p2)

            # ----------------------------------
            # DELETE WAITING MESSAGE
            # ----------------------------------

            waiting_id = game.get(
                "waiting_message_id"
            )

            if waiting_id:

                try:

                    await context.bot.delete_message(
                        chat_id=chat_id,
                        message_id=waiting_id
                    )

                except Exception as e:

                    print(
                        f"⚠️ Waiting message "
                        f"delete error: {e}"
                    )

                game[
                    "waiting_message_id"
                ] = None

            # ----------------------------------
            # DETERMINE ROUND RESULT
            # ----------------------------------

            round_winner = None

            if move1 == move2:

                result = (
                    "🤝 <b>It's a draw!</b>"
                )

            elif WIN_RULES[move1] == move2:

                round_winner = p1

                game["score"][p1] += 1

                result = (
                    f"🏆 <b>{game['player1_name']}</b> "
                    "wins the round!"
                )

            else:

                round_winner = p2

                game["score"][p2] += 1

                result = (
                    f"🏆 <b>{game['player2_name']}</b> "
                    "wins the round!"
                )

            # ----------------------------------
            # CURRENT SCORE
            # ----------------------------------

            score1 = game["score"].get(
                p1,
                0
            )

            score2 = game["score"].get(
                p2,
                0
            )

            # ==================================
            # ROUND RESULT
            # ==================================

            result_text = (

                "✊📄✂️ "
                "<b>ROCK PAPER SCISSORS</b>\n\n"

                f"🎮 <b>Round {game['round']}</b>\n\n"

                f"❌ <b>{game['player1_name']}</b> → "
                f"{RPS_EMOJIS[move1]} "
                f"{move1.title()}\n"

                f"⭕ <b>{game['player2_name']}</b> → "
                f"{RPS_EMOJIS[move2]} "
                f"{move2.title()}\n\n"

                f"{result}\n\n"

                "📊 <b>Score</b>\n"

                f"❌ {game['player1_name']} — {score1}\n"
                f"⭕ {game['player2_name']} — {score2}"
            )

            # ==================================
            # MATCH END CHECK
            # ==================================

            match_finished = False
            match_winner = None

            # Someone reached 2 wins
            if score1 >= 2:

                match_finished = True
                match_winner = p1

            elif score2 >= 2:

                match_finished = True
                match_winner = p2

            # ----------------------------------
            # ROUND 3 COMPLETED
            # ----------------------------------

            elif game["round"] >= 3:

                match_finished = True

                if score1 > score2:

                    match_winner = p1

                elif score2 > score1:

                    match_winner = p2

                else:

                    match_winner = None

            # ==================================
            # MATCH FINISHED
            # ==================================

            if match_finished:

                if match_winner == p1:

                    final_result = (
                        f"🏆 <b>MATCH OVER!</b>\n\n"
                        f"👑 <b>{game['player1_name']}</b> "
                        "wins the match!"
                    )

                elif match_winner == p2:

                    final_result = (
                        f"🏆 <b>MATCH OVER!</b>\n\n"
                        f"👑 <b>{game['player2_name']}</b> "
                        "wins the match!"
                    )

                else:

                    final_result = (
                        "🤝 <b>MATCH DRAW!</b>\n\n"
                        "Nobody won the match!"
                    )

                result_text += (
                    "\n\n"
                    f"{final_result}\n\n"
                    "🎮 Start a new match with /rps"
                )

                # ----------------------------------
                # REMOVE ACTIVE GAME
                # ----------------------------------

                rps_games.pop(
                    chat_id,
                    None
                )

                # ----------------------------------
                # SHOW FINAL RESULT
                # ----------------------------------

                try:

                    await query.message.edit_text(
                        result_text,
                        parse_mode="HTML"
                    )

                except Exception as e:

                    print(
                        f"⚠️ RPS final result error: {e}"
                    )

                return

            # ==================================
            # NEXT ROUND
            # ==================================

            try:

                await query.message.edit_text(

                    result_text,

                    parse_mode="HTML",

                    reply_markup=rps_next_keyboard()
                )

            except Exception as e:

                print(
                    f"⚠️ RPS result error: {e}"
                )

            return

# ==========================================
# /ENDRPS COMMAND
# ==========================================

async def end_rps_command(
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

    if chat.type not in ["group", "supergroup"]:

        await update.message.reply_text(
            "❌ This command can only be used in groups."
        )
        return

    chat_id = chat.id

    # ======================================
    # CHECK ACTIVE GAME
    # ======================================

    game = rps_games.get(chat_id)

    if not game:

        await update.message.reply_text(
            "🎮 There is no active RPS game here."
        )
        return

    # ======================================
    # CHECK PLAYER
    # ======================================

    player1_id = game.get("player1")
    player2_id = game.get("player2")

    if user.id not in [player1_id, player2_id]:

        await update.message.reply_text(
            "❌ Only the players of this game "
            "can end it."
        )
        return

    # ======================================
    # SAVE USER NAME
    # ======================================

    username = (
        user.full_name
        or user.username
        or "Player"
    )

    # ======================================
    # DELETE MAIN GAME MESSAGE
    # ======================================

    game_message_id = game.get(
        "game_message_id"
    )

    if game_message_id:

        try:

            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=game_message_id
            )

            print(
                "🗑️ RPS game message deleted."
            )

        except Exception as e:

            print(
                f"⚠️ Could not delete RPS "
                f"game message: {e}"
            )

    # ======================================
    # DELETE WAITING MESSAGE
    # ======================================

    waiting_message_id = game.get(
        "waiting_message_id"
    )

    if waiting_message_id:

        try:

            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=waiting_message_id
            )

            print(
                "🗑️ RPS waiting message deleted."
            )

        except Exception as e:

            print(
                f"⚠️ Could not delete RPS "
                f"waiting message: {e}"
            )

    # ======================================
    # REMOVE ACTIVE GAME
    # ======================================

    rps_games.pop(
        chat_id,
        None
    )

    # ======================================
    # SEND END MESSAGE
    # ======================================

    await update.message.reply_text(
        "🛑 <b>RPS GAME ENDED</b>\n\n"
        f"👤 Ended by <b>{html.escape(username)}</b>\n\n"
        "🎮 The current Rock Paper Scissors "
        "game has been cancelled.\n\n"
        "💡 Start a new game with /rps",
        parse_mode="HTML"
    )

    # ======================================
    # TERMINAL LOG
    # ======================================

    print(
        f"🛑 RPS game ended | "
        f"chat={chat_id} | "
        f"ended_by={user.id}"
    )