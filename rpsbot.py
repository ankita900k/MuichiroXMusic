# ==========================================
# 🎮 MUICHIRO • RPS BOT
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

rpsbot_games = {}


# ==========================================
# MOVES
# ==========================================

RPS_MOVES = {

    "rock": "🪨",

    "paper": "📄",

    "scissors": "✂️",

}


# ==========================================
# DIFFICULTIES
# ==========================================

RPS_DIFFICULTIES = {

    "easy": "🟢 Easy",

    "normal": "🟡 Normal",

    "hard": "🔴 Hard",

}


# ==========================================
# PLAYER MENTION
# ==========================================

def rps_mention(
    user_id,
    name
):

    return (
        f'<a href="tg://user?id={user_id}">'
        f'{name}</a>'
    )


# ==========================================
# DIFFICULTY BUTTONS
# ==========================================

def rps_difficulty_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "🟢 Easy",
                    callback_data="rpsb_diff:easy"
                )
            ],

            [
                InlineKeyboardButton(
                    "🟡 Normal",
                    callback_data="rpsb_diff:normal"
                )
            ],

            [
                InlineKeyboardButton(
                    "🔴 Hard",
                    callback_data="rpsb_diff:hard"
                )
            ],

        ]
    )


# ==========================================
# MOVE BUTTONS
# ==========================================

def rps_move_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "🪨 Rock",
                    callback_data="rpsb_move:rock"
                ),

                InlineKeyboardButton(
                    "📄 Paper",
                    callback_data="rpsb_move:paper"
                ),

                InlineKeyboardButton(
                    "✂️ Scissors",
                    callback_data="rpsb_move:scissors"
                ),
            ],

            [
                InlineKeyboardButton(
                    "❌ End Game",
                    callback_data="rpsb_end"
                )
            ],

        ]
    )


# ==========================================
# RESULT BUTTONS
# ==========================================

def rps_result_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "🔄 Play Again",
                    callback_data="rpsb_again"
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Close",
                    callback_data="rpsb_close"
                )
            ],

        ]
    )


# ==========================================
# BOT MOVE
# ==========================================

def get_rps_bot_move(
    game,
    player_move
):

    difficulty = game[
        "difficulty_key"
    ]

    moves = list(
        RPS_MOVES.keys()
    )

    # ======================================
    # EASY
    # ======================================

    if difficulty == "easy":

        return random.choice(
            moves
        )

    # ======================================
    # NORMAL
    # ======================================

    if difficulty == "normal":

        # Mostly random
        # Sometimes counter player

        if random.random() < 0.5:

            counters = {

                "rock": "paper",

                "paper": "scissors",

                "scissors": "rock",

            }

            return counters[
                player_move
            ]

        return random.choice(
            moves
        )

    # ======================================
    # HARD
    # ======================================

    counters = {

        "rock": "paper",

        "paper": "scissors",

        "scissors": "rock",

    }

    # Hard counters most of the time
    if random.random() < 0.75:

        return counters[
            player_move
        ]

    return random.choice(
        moves
    )


# ==========================================
# RESULT
# ==========================================

def rps_result(
    player,
    bot
):

    if player == bot:

        return "draw"

    wins = {

        "rock": "scissors",

        "paper": "rock",

        "scissors": "paper",

    }

    if wins[player] == bot:

        return "player"

    return "bot"


# ==========================================
# GAME TEXT
# ==========================================

def rps_game_text(game):

    return (

        "🎮 <b>MUICHIRO • RPS BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"👤 <b>You:</b> "
        f"{rps_mention(game['user_id'], game['user_name'])}\n"

        f"🤖 <b>Opponent:</b> Muichiro\n\n"

        f"🎯 <b>Difficulty:</b> "
        f"{game['difficulty']}\n\n"

        "🏆 <b>Score</b>\n"

        f"👤 You: <b>{game['player_score']}</b>\n"

        f"🤖 Muichiro: <b>{game['bot_score']}</b>\n"

        f"🤝 Draws: <b>{game['draws']}</b>\n\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        "👇 <b>Choose your move!</b>"

    )


# ==========================================
# /RPSBOT
# ==========================================

async def rpsbot_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat

    user = update.effective_user

    if not chat or not user:
        return

    if chat.id in rpsbot_games:

        await update.message.reply_text(

            "🎮 <b>RPS BOT GAME ALREADY RUNNING!</b>\n\n"
            "Finish the current match first.",

            parse_mode=ParseMode.HTML
        )

        return

    await update.message.reply_text(

        "🎮 <b>MUICHIRO • RPS BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "🤖 <b>Choose your difficulty:</b>\n\n"

        "🟢 Easy — Random opponent\n"
        "🟡 Normal — Smarter opponent\n"
        "🔴 Hard — Tough opponent\n\n"

        "👇 Select a difficulty:",

        parse_mode=ParseMode.HTML,

        reply_markup=rps_difficulty_keyboard()
    )


# ==========================================
# CALLBACK
# ==========================================

async def rpsbot_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    data = query.data or ""

    user = query.from_user

    # ======================================
    # DIFFICULTY
    # ======================================

    if data.startswith("rpsb_diff:"):

        difficulty = data.split(
            ":",
            1
        )[1]

        chat_id = query.message.chat.id

        rpsbot_games[
            chat_id
        ] = {

            "chat_id":
                chat_id,

            "user_id":
                user.id,

            "user_name":
                user.full_name,

            "difficulty_key":
                difficulty,

            "difficulty":
                RPS_DIFFICULTIES[
                    difficulty
                ],

            "player_score":
                0,

            "bot_score":
                0,

            "draws":
                0,

        }

        await query.answer()

        await query.edit_message_text(

            rps_game_text(
                rpsbot_games[
                    chat_id
                ]
            ),

            parse_mode=ParseMode.HTML,

            reply_markup=rps_move_keyboard()
        )

        return

    # ======================================
    # MOVE
    # ======================================

    if data.startswith("rpsb_move:"):

        player_move = data.split(
            ":",
            1
        )[1]

        chat_id = query.message.chat.id

        game = rpsbot_games.get(
            chat_id
        )

        if not game:

            await query.answer(
                "❌ Game no longer exists.",
                show_alert=True
            )

            return

        if user.id != game["user_id"]:

            await query.answer(
                "🚫 This isn't your game!",
                show_alert=True
            )

            return

        bot_move = get_rps_bot_move(
            game,
            player_move
        )

        result = rps_result(
            player_move,
            bot_move
        )

        if result == "player":

            game["player_score"] += 1

            title = (
                "🏆 <b>YOU WIN!</b>"
            )

            result_text = (
                "🎉 Nice move!"
            )

        elif result == "bot":

            game["bot_score"] += 1

            title = (
                "🤖 <b>MUICHIRO WINS!</b>"
            )

            result_text = (
                "😎 Muichiro got you this round!"
            )

        else:

            game["draws"] += 1

            title = (
                "🤝 <b>DRAW!</b>"
            )

            result_text = (
                "Both chose the same move!"
            )

        await query.answer()

        await query.edit_message_text(

            f"{title}\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            f"👤 <b>You:</b> "
            f"{RPS_MOVES[player_move]}\n\n"

            f"🤖 <b>Muichiro:</b> "
            f"{RPS_MOVES[bot_move]}\n\n"

            f"{result_text}\n\n"

            "🏆 <b>Score</b>\n"

            f"👤 You: "
            f"<b>{game['player_score']}</b>\n"

            f"🤖 Muichiro: "
            f"<b>{game['bot_score']}</b>\n"

            f"🤝 Draws: "
            f"<b>{game['draws']}</b>\n\n"

            "👇 <b>Play another round!</b>",

            parse_mode=ParseMode.HTML,

            reply_markup=rps_move_keyboard()
        )

        return

    # ======================================
    # END
    # ======================================

    if data == "rpsb_end":

        chat_id = query.message.chat.id

        game = rpsbot_games.get(
            chat_id
        )

        if not game:

            return

        if user.id != game["user_id"]:

            await query.answer(
                "🚫 Only the player can end this game.",
                show_alert=True
            )

            return

        rpsbot_games.pop(
            chat_id,
            None
        )

        await query.answer(
            "Game ended."
        )

        await query.edit_message_text(

            "🛑 <b>RPS BOT GAME ENDED</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            f"👤 Final score: "
            f"<b>{game['player_score']}</b>\n"

            f"🤖 Muichiro: "
            f"<b>{game['bot_score']}</b>\n\n"

            "Use <b>/rpsbot</b> to play again.",

            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # PLAY AGAIN
    # ======================================

    if data == "rpsb_again":

        await query.answer()

        await query.edit_message_text(

            "🎮 <b>RPS BOT</b>\n\n"
            "Choose your difficulty:",

            parse_mode=ParseMode.HTML,

            reply_markup=rps_difficulty_keyboard()
        )

        return

    # ======================================
    # CLOSE
    # ======================================

    if data == "rpsb_close":

        chat_id = query.message.chat.id

        rpsbot_games.pop(
            chat_id,
            None
        )

        await query.answer()

        await query.edit_message_text(

            "🎮 <b>RPS Bot closed.</b>\n\n"
            "Use <b>/rpsbot</b> to play again.",

            parse_mode=ParseMode.HTML
        )


# ==========================================
# /ENDRPSBOT
# ==========================================

async def endrpsbot_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat_id = update.effective_chat.id

    user = update.effective_user

    game = rpsbot_games.get(
        chat_id
    )

    if not game:

        await update.message.reply_text(
            "❌ No active RPS Bot game."
        )

        return

    if game["user_id"] != user.id:

        await update.message.reply_text(
            "🚫 Only the player can end this game."
        )

        return

    rpsbot_games.pop(
        chat_id,
        None
    )

    await update.message.reply_text(

        "🛑 <b>RPS BOT GAME ENDED</b>\n\n"

        f"👤 You: <b>{game['player_score']}</b>\n"
        f"🤖 Muichiro: <b>{game['bot_score']}</b>\n\n"

        "Use <b>/rpsbot</b> to play again.",

        parse_mode=ParseMode.HTML
    )