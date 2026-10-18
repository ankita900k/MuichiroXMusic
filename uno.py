# ==========================================
# 🎮 MUICHIRO UNO
# Professional Telegram UNO Game
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

uno_games = {}


# ==========================================
# UNO COLORS
# ==========================================

UNO_COLORS = [
    "red",
    "yellow",
    "green",
    "blue",
]

COLOR_ICON = {
    "red": "🔴",
    "yellow": "🟡",
    "green": "🟢",
    "blue": "🔵",
    "wild": "🌈",
}

COLOR_NAME = {
    "red": "🔴 Red",
    "yellow": "🟡 Yellow",
    "green": "🟢 Green",
    "blue": "🔵 Blue",
}


# ==========================================
# CARD DISPLAY
# ==========================================

def card_text(card):

    color = card["color"]
    value = card["value"]

    if color == "wild":

        if value == "wild":
            return "🌈 Wild"

        if value == "+4":
            return "🌈 +4"

    icon = COLOR_ICON.get(
        color,
        "🃏"
    )

    value_display = {
        "skip": "⛔ Skip",
        "reverse": "🔄 Reverse",
        "+2": "➕2",
    }.get(
        value,
        value
    )

    return f"{icon} {value_display}"


# ==========================================
# PLAYER MENTION
# ==========================================

def player_mention(
    user_id,
    name
):

    name = str(name)

    name = (
        name
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    return (
        f'<a href="tg://user?id={user_id}">'
        f'{name}'
        f'</a>'
    )


# ==========================================
# PM CHECK
# ==========================================

async def has_started_bot(
    context,
    user_id
):

    try:

        await context.bot.get_chat(
            user_id
        )

        return True

    except Exception:

        return False


# ==========================================
# CREATE UNO DECK
# ==========================================

def create_deck():

    deck = []

    for color in UNO_COLORS:

        # One zero
        deck.append({
            "color": color,
            "value": "0"
        })

        # Two of 1-9
        for number in range(1, 10):

            deck.append({
                "color": color,
                "value": str(number)
            })

            deck.append({
                "color": color,
                "value": str(number)
            })

        # Two Skip
        for _ in range(2):

            deck.append({
                "color": color,
                "value": "skip"
            })

        # Two Reverse
        for _ in range(2):

            deck.append({
                "color": color,
                "value": "reverse"
            })

        # Two +2
        for _ in range(2):

            deck.append({
                "color": color,
                "value": "+2"
            })

    # Four Wild
    for _ in range(4):

        deck.append({
            "color": "wild",
            "value": "wild"
        })

    # Four +4
    for _ in range(4):

        deck.append({
            "color": "wild",
            "value": "+4"
        })

    random.shuffle(deck)

    return deck


# ==========================================
# REFILL DECK
# ==========================================

def refill_deck(game):

    if len(game["discard"]) <= 1:
        return

    top_card = game["discard"][-1]

    new_deck = game["discard"][:-1]

    random.shuffle(new_deck)

    game["deck"] = new_deck

    game["discard"] = [
        top_card
    ]


# ==========================================
# DRAW ONE
# ==========================================

def draw_card(game):

    if not game["deck"]:
        refill_deck(game)

    if not game["deck"]:
        return None

    return game["deck"].pop()


# ==========================================
# CURRENT PLAYER
# ==========================================

def get_current_player(game):

    players = game["players"]

    if not players:
        return None

    return players[
        game["turn"]
    ]


# ==========================================
# ADVANCE TURN
# ==========================================

def advance_turn(
    game,
    steps=1
):

    players = game["players"]

    if not players:
        return

    game["turn"] = (
        game["turn"]
        + (
            game["direction"]
            * steps
        )
    ) % len(players)


# ==========================================
# CARD IS LEGAL
# ==========================================

def is_card_playable(
    card,
    game
):

    top_card = game["discard"][-1]

    current_color = (
        game["current_color"]
    )

    # Wild cards
    if card["color"] == "wild":

        # +4 follows UNO's basic rule:
        # only playable when player has
        # no card matching current color.
        if card["value"] == "+4":

            hand = game["hands"].get(
                game["players"][
                    game["turn"]
                ],
                []
            )

            for hand_card in hand:

                if (
                    hand_card["color"]
                    == current_color
                ):

                    return False

        return True

    # Match active color
    if card["color"] == current_color:
        return True

    # Match value
    if (
        card["value"]
        == top_card["value"]
    ):
        return True

    return False


# ==========================================
# GAME STATUS TEXT
# ==========================================

def build_player_counts(game):

    lines = []

    for player_id in game["players"]:

        name = game["names"].get(
            player_id,
            "Player"
        )

        count = len(
            game["hands"].get(
                player_id,
                []
            )
        )

        if count == 1:
            count_text = "🔥 UNO!"
        else:
            count_text = f"🃏 {count}"

        lines.append(
            f"• {player_mention(player_id, name)} "
            f"— <b>{count_text}</b>"
        )

    return "\n".join(lines)


# ==========================================
# BUILD GROUP GAME MESSAGE
# ==========================================

def build_game_text(game):
    """Build the professional UNO game status message."""

    current_player = game["players"][game["turn"]]
    current_name = game["names"].get(
        current_player,
        "Unknown Player"
    )

    top_card = (
        game["discard"][-1]
        if game.get("discard")
        else None
    )

    current_color = game.get("current_color")

    color_name = COLOR_NAME.get(
        current_color,
        current_color or "Unknown"
    )

    return (
        "🎮 <b>MUICHIRO • UNO</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"🃏 <b>Top Card:</b> "
        f"{card_text(top_card)}\n\n"

        f"🎨 <b>Color:</b> "
        f"{color_name}\n\n"

        "📊 <b>CARDS REMAINING</b>\n"
        f"{build_player_counts(game)}\n\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        f"🎯 <b>Turn:</b> "
        f"{player_mention(current_player, current_name)}\n\n"

        f"👑 {player_mention(current_player, current_name)}, "
        "<b>it's your turn!</b>\n"
        "📩 Check your cards in DM."
    )

# ==========================================
# GAME KEYBOARD
# ==========================================

def game_keyboard(
    game
):

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🃏 My Cards",
                callback_data=(
                    f"uno_hand:"
                    f"{game['chat_id']}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🛑 End Game",
                callback_data=(
                    f"uno_end:"
                    f"{game['chat_id']}"
                )
            )
        ]

    ])


# ==========================================
# UPDATE GROUP GAME MESSAGE
# ==========================================

async def update_game_message(
    context,
    game
):

    message_id = game.get(
        "message_id"
    )

    if not message_id:
        return

    try:

        await context.bot.edit_message_text(

            chat_id=game["chat_id"],

            message_id=message_id,

            text=build_game_text(game),

            parse_mode=ParseMode.HTML,

            reply_markup=game_keyboard(
                game
            )
        )

    except Exception as e:

        print(
            f"⚠️ UNO group update error: {e}"
        )


# ==========================================
# SEND / UPDATE PLAYER HAND
# ==========================================

async def send_player_hand(
    context,
    game,
    player_id
):

    hand = game["hands"].get(
        player_id,
        []
    )

    top_card = (
        game["discard"][-1]
        if game["discard"]
        else None
    )

    top_text = (
        card_text(top_card)
        if top_card
        else "None"
    )

    current_color = COLOR_NAME.get(
        game["current_color"],
        game["current_color"]
    )

    keyboard = []

    # ======================================
    # CARD BUTTONS
    # ======================================

    for index, card in enumerate(hand):

        keyboard.append([

            InlineKeyboardButton(

                card_text(card),

                callback_data=(
                    f"uno_card:"
                    f"{game['chat_id']}:"
                    f"{index}"
                )
            )

        ])

    # ======================================
    # DRAW
    # ======================================

    keyboard.append([

        InlineKeyboardButton(
            "🃏 Draw Card",
            callback_data=(
                f"uno_draw:"
                f"{game['chat_id']}"
            )
        )

    ])

    text = (

        "🃏 <b>YOUR UNO HAND</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"🔝 <b>Top Card:</b> "
        f"{top_text}\n"

        f"🎨 <b>Current Color:</b> "
        f"{current_color}\n\n"

        f"🃏 <b>Your Cards:</b> "
        f"{len(hand)}\n\n"

        "👇 <b>Select a card</b>\n\n"

        "🚫 Illegal cards will be rejected."
    )

    try:

        message_id = game[
            "dm_messages"
        ].get(player_id)

        if message_id:

            try:

                await context.bot.edit_message_text(

                    chat_id=player_id,

                    message_id=message_id,

                    text=text,

                    parse_mode=ParseMode.HTML,

                    reply_markup=InlineKeyboardMarkup(
                        keyboard
                    )
                )

                return

            except Exception:
                pass

        msg = await context.bot.send_message(

            chat_id=player_id,

            text=text,

            parse_mode=ParseMode.HTML,

            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        game[
            "dm_messages"
        ][player_id] = msg.message_id

    except Exception as e:

        print(
            f"⚠️ UNO DM error "
            f"for {player_id}: {e}"
        )


# ==========================================
# /UNO
# ==========================================

async def uno_command(
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
            "🎮 UNO can only be played in groups."
        )

        return

    # ======================================
    # CREATOR PM CHECK
    # ======================================

    if not await has_started_bot(
        context,
        user.id
    ):

        bot_username = (
            context.bot.username
        )

        await update.message.reply_text(

            "⚠️ <b>START MUICHIRO FIRST</b>\n\n"

            f"📩 @{bot_username}\n\n"

            "Start me in PM and then use "
            "<code>/uno</code> again.",

            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # GAME ALREADY EXISTS
    # ======================================

    if chat.id in uno_games:

        await update.message.reply_text(

            "🎮 <b>UNO MATCH ALREADY RUNNING</b>\n\n"

            "👥 Join the current match "
            "or wait for it to finish.\n\n"

            "🛑 Players can use "
            "<code>/enduno</code> "
            "if the game needs to be stopped.",

            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # CREATE GAME
    # ======================================

    game = {

        "chat_id": chat.id,

        "creator": user.id,

        "players": [
            user.id
        ],

        "names": {
            user.id: user.full_name
        },

        "hands": {},

        "deck": create_deck(),

        "discard": [],

        "turn": 0,

        "direction": 1,

        "current_color": None,

        "started": False,

        "message_id": None,

        "dm_messages": {}
    }

    uno_games[
        chat.id
    ] = game

    # ======================================
    # WAITING MESSAGE
    # ======================================

    keyboard = [

        [

            InlineKeyboardButton(
                "🚀 Start Me",
                url=(
                    f"https://t.me/"
                    f"{context.bot.username}"
                    "?start=uno"
                )
            )

        ],

        [

            InlineKeyboardButton(
                "🎮 Join UNO",
                callback_data=(
                    f"uno_join:{chat.id}"
                )
            )

        ],

        [

            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=(
                    f"uno_cancel:{chat.id}"
                )
            )

        ]

    ]

    msg = await update.message.reply_text(

        "🎮 <b>ＭＵＩＣＨＩＲＯ • UNO</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "✨ <b>NEW MATCH CREATED!</b>\n\n"

        f"👑 <b>Creator:</b> {player_mention(user.id, user.full_name)}\n\n"

        "👥 <b>Players:</b> 1 / 10\n"
        "🃏 <b>Minimum:</b> 2 players\n\n"

        "⚠️ <b>Important</b>\n"
        "Everyone must start Muichiro in PM "
        "before joining.\n\n"

        "👇 <b>Waiting for players...</b>",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )

    game[
        "message_id"
    ] = msg.message_id


# ==========================================
# UNO CALLBACK ROUTER
# ==========================================

async def uno_callback(
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

    if data.startswith(
        "uno_join:"
    ):

        await handle_uno_join(
            query,
            context
        )

        return

    # ======================================
    # START
    # ======================================

    if data.startswith(
        "uno_start:"
    ):

        await handle_uno_start(
            query,
            context
        )

        return

    # ======================================
    # CANCEL
    # ======================================

    if data.startswith(
        "uno_cancel:"
    ):

        await handle_uno_cancel(
            query,
            context
        )

        return

    # ======================================
    # PLAY CARD
    # ======================================

    if data.startswith(
        "uno_card:"
    ):

        parts = data.split(":")

        if len(parts) != 3:
            await query.answer()
            return

        chat_id = int(parts[1])
        index = int(parts[2])

        await play_uno_card(
            query,
            context,
            chat_id,
            index
        )

        return

    # ======================================
    # CHOOSE COLOR
    # ======================================

    if data.startswith(
        "uno_color:"
    ):

        parts = data.split(":")

        if len(parts) != 4:
            await query.answer()
            return

        chat_id = int(parts[1])
        index = int(parts[2])
        color = parts[3]

        await choose_uno_color(
            query,
            context,
            chat_id,
            index,
            color
        )

        return

    # ======================================
    # DRAW
    # ======================================

    if data.startswith(
        "uno_draw:"
    ):

        chat_id = int(
            data.split(":")[1]
        )

        await draw_uno_card(
            query,
            context,
            chat_id
        )

        return

    # ======================================
    # MY HAND
    # ======================================

    if data.startswith(
        "uno_hand:"
    ):

        chat_id = int(
            data.split(":")[1]
        )

        game = uno_games.get(
            chat_id
        )

        if not game:

            await query.answer(
                "❌ This game has ended.",
                show_alert=True
            )

            return

        user_id = query.from_user.id

        if user_id not in game["players"]:

            await query.answer(
                "❌ You aren't in this game.",
                show_alert=True
            )

            return

        await query.answer(
            "📩 Check your DM!"
        )

        await send_player_hand(
            context,
            game,
            user_id
        )

        return

    # ======================================
    # END GAME BUTTON
    # ======================================

    if data.startswith(
        "uno_end:"
    ):

        chat_id = int(
            data.split(":")[1]
        )

        game = uno_games.get(
            chat_id
        )

        if not game:

            await query.answer(
                "❌ Game already ended.",
                show_alert=True
            )

            return

        if query.from_user.id not in game["players"]:

            await query.answer(
                "🚫 Only UNO players can end this game.",
                show_alert=True
            )

            return

        uno_games.pop(
            chat_id,
            None
        )

        await query.answer(
            "🛑 UNO ended."
        )

        try:

            await query.edit_message_text(

                "🛑 <b>UNO MATCH ENDED</b>\n\n"

                "The match was stopped by a player.\n"
                "Thanks for playing! 🎮",

                parse_mode=ParseMode.HTML
            )

        except Exception:
            pass


# ==========================================
# JOIN GAME
# ==========================================

async def handle_uno_join(
    query,
    context
):

    await query.answer()

    chat_id = int(
        query.data.split(":")[1]
    )

    game = uno_games.get(
        chat_id
    )

    if not game:

        await query.answer(
            "❌ This UNO game has ended.",
            show_alert=True
        )

        return

    user = query.from_user

    # Already joined
    if user.id in game["players"]:

        await query.answer(
            "✅ You are already in the game!",
            show_alert=True
        )

        return

    # ======================================
    # PM CHECK
    # ======================================

    if not await has_started_bot(
        context,
        user.id
    ):

        await query.answer(

            "⚠️ Start Muichiro in PM first!",
            show_alert=True
        )

        return

    # ======================================
    # LIMIT
    # ======================================

    if len(game["players"]) >= 10:

        await query.answer(
            "❌ This game is full!",
            show_alert=True
        )

        return

    # ======================================
    # ADD PLAYER
    # ======================================

    game["players"].append(
        user.id
    )

    game["names"][
        user.id
    ] = user.full_name

    await query.answer(
        "🎮 You joined UNO!"
    )

    # ======================================
    # WAITING UI
    # ======================================

    keyboard = [

        [

            InlineKeyboardButton(
                "🎮 Join UNO",
                callback_data=(
                    f"uno_join:{chat_id}"
                )
            )

        ],

        [

            InlineKeyboardButton(
                "▶️ Start Game",
                callback_data=(
                    f"uno_start:{chat_id}"
                )
            )

        ],

        [

            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=(
                    f"uno_cancel:{chat_id}"
                )
            )

        ]

    ]
    players_text = "\n".join(
    f"• {player_mention(pid, game['names'].get(pid, 'Player'))}"
    for pid in game["players"]
)
    await query.edit_message_text(

        "🎮 <b>ＭＵＩＣＨＩＲＯ • UNO</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "✨ <b>MATCH LOBBY</b>\n\n"

        f"👥 <b>Players:</b> "
        f"{len(game['players'])} / 10\n\n"

        f"{players_text}\n\n"

        "⚠️ Everyone must start "
        "Muichiro in PM.\n\n"

        "👇 Waiting for more players...",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ==========================================
# START GAME
# ==========================================

async def handle_uno_start(
    query,
    context
):

    await query.answer()

    chat_id = int(
        query.data.split(":")[1]
    )

    game = uno_games.get(
        chat_id
    )

    if not game:
        return

    if query.from_user.id != game["creator"]:

        await query.answer(
            "🚫 Only the creator can start UNO.",
            show_alert=True
        )

        return

    if len(game["players"]) < 2:

        await query.answer(
            "❌ You need at least 2 players.",
            show_alert=True
        )

        return

    # ======================================
    # START
    # ======================================

    game["started"] = True

    # Deal 7 cards
    for player_id in game["players"]:

        game["hands"][player_id] = []

        for _ in range(7):

            card = draw_card(game)

            if card:
                game["hands"][
                    player_id
                ].append(card)

    # ======================================
    # FIRST CARD
    # ======================================

    while True:

        first = draw_card(game)

        if not first:
            break

        # Start with a normal colored card
        if first["color"] != "wild":
            break

        game["deck"].insert(
            0,
            first
        )

        random.shuffle(
            game["deck"]
        )

    game["discard"].append(
        first
    )

    game["current_color"] = (
        first["color"]
    )

    # ======================================
    # FIRST PLAYER
    # ======================================

    game["turn"] = 0

    # ======================================
    # START MESSAGE
    # ======================================

    await query.edit_message_text(

        build_game_text(game),

        parse_mode=ParseMode.HTML,

        reply_markup=game_keyboard(
            game
        )
    )

    # ======================================
    # SEND DM TO EVERY PLAYER
    # ======================================

    for player_id in game["players"]:

        await send_player_hand(
            context,
            game,
            player_id
        )

    # ======================================
    # GROUP TURN UPDATE
    # ======================================

    await update_game_message(
        context,
        game
    )


# ==========================================
# CANCEL GAME
# ==========================================

async def handle_uno_cancel(
    query,
    context
):

    await query.answer()

    chat_id = int(
        query.data.split(":")[1]
    )

    game = uno_games.get(
        chat_id
    )

    if not game:
        return

    if query.from_user.id != game["creator"]:

        await query.answer(
            "🚫 Only the creator can cancel.",
            show_alert=True
        )

        return

    uno_games.pop(
        chat_id,
        None
    )

    await query.edit_message_text(

        "❌ <b>UNO MATCH CANCELLED</b>\n\n"

        "The creator cancelled the match.\n"
        "Maybe next time! 🎮",

        parse_mode=ParseMode.HTML
    )


# ==========================================
# PLAY CARD
# ==========================================

async def play_uno_card(
    query,
    context,
    chat_id,
    card_index
):

    game = uno_games.get(
        chat_id
    )

    if not game:

        await query.answer(
            "❌ This game has ended.",
            show_alert=True
        )

        return

    user_id = query.from_user.id

    # ======================================
    # PLAYER CHECK
    # ======================================

    if user_id not in game["players"]:

        await query.answer(
            "🚫 You are not part of this UNO game.",
            show_alert=True
        )

        return

    # ======================================
    # TURN CHECK
    # ======================================

    if get_current_player(game) != user_id:

        await query.answer(
            "⏳ It's not your turn!",
            show_alert=True
        )

        return

    hand = game["hands"].get(
        user_id,
        []
    )

    if (
        card_index < 0
        or card_index >= len(hand)
    ):

        await query.answer(
            "❌ This card is no longer available.",
            show_alert=True
        )

        return

    card = hand[card_index]

    # ======================================
    # LEGAL MOVE
    # ======================================

    if not is_card_playable(
        card,
        game
    ):

        await query.answer(

            "🚫 Illegal move!\n\n"
            "Match the current color, "
            "symbol/number, or use a valid Wild.",

            show_alert=True
        )

        return

    # ======================================
    # WILD
    # ======================================

    if card["color"] == "wild":

        keyboard = [

            [

                InlineKeyboardButton(
                    "🔴 Red",
                    callback_data=(
                        f"uno_color:"
                        f"{chat_id}:"
                        f"{card_index}:"
                        f"red"
                    )
                ),

                InlineKeyboardButton(
                    "🟡 Yellow",
                    callback_data=(
                        f"uno_color:"
                        f"{chat_id}:"
                        f"{card_index}:"
                        f"yellow"
                    )
                )

            ],

            [

                InlineKeyboardButton(
                    "🟢 Green",
                    callback_data=(
                        f"uno_color:"
                        f"{chat_id}:"
                        f"{card_index}:"
                        f"green"
                    )
                ),

                InlineKeyboardButton(
                    "🔵 Blue",
                    callback_data=(
                        f"uno_color:"
                        f"{chat_id}:"
                        f"{card_index}:"
                        f"blue"
                    )
                )

            ]

        ]

        await query.answer()

        await query.edit_message_text(

            "🌈 <b>CHOOSE A COLOR</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "🎨 Select the color that "
            "the next player must follow.",

            parse_mode=ParseMode.HTML,

            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    # ======================================
    # NORMAL CARD
    # ======================================

    await finish_card(
        query,
        context,
        game,
        card_index,
        card,
        card["color"]
    )


# ==========================================
# CHOOSE WILD COLOR
# ==========================================

async def choose_uno_color(
    query,
    context,
    chat_id,
    card_index,
    chosen_color
):

    game = uno_games.get(
        chat_id
    )

    if not game:

        await query.answer(
            "❌ Game ended.",
            show_alert=True
        )

        return

    user_id = query.from_user.id

    if get_current_player(game) != user_id:

        await query.answer(
            "⏳ It's not your turn.",
            show_alert=True
        )

        return

    if chosen_color not in UNO_COLORS:

        await query.answer(
            "❌ Invalid color.",
            show_alert=True
        )

        return

    hand = game["hands"].get(
        user_id,
        []
    )

    if (
        card_index < 0
        or card_index >= len(hand)
    ):

        await query.answer(
            "❌ Card no longer exists.",
            show_alert=True
        )

        return

    card = hand[card_index]

    if card["color"] != "wild":

        await query.answer(
            "❌ That's not a Wild card.",
            show_alert=True
        )

        return

    await finish_card(
        query,
        context,
        game,
        card_index,
        card,
        chosen_color
    )


# ==========================================
# FINISH PLAYED CARD
# ==========================================

async def finish_card(
    query,
    context,
    game,
    card_index,
    card,
    selected_color
):

    user_id = query.from_user.id

    hand = game["hands"].get(
        user_id,
        []
    )

    # ======================================
    # REMOVE CARD
    # ======================================

    hand.pop(card_index)

    game["discard"].append(
        card
    )

    game["current_color"] = (
        selected_color
    )

    # ======================================
    # WIN
    # ======================================

    if len(hand) == 0:

        name = game["names"].get(
            user_id,
            "Player"
        )

        try:

            await query.edit_message_text(

                "🏆 <b>YOU WON UNO!</b>\n\n"

                "🎉 You played your final card!\n"
                "🔥 Congratulations!",

                parse_mode=ParseMode.HTML
            )

        except Exception:
            pass

        try:

            await context.bot.send_message(

                chat_id=game["chat_id"],

                text=(

                    "🏆 <b>UNO WINNER!</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n\n"

                    f"👑 {player_mention(user_id, name)}\n\n"
                    "🎉 Played their final card!\n"
                    "🔥 GG everyone!"

                ),

                parse_mode=ParseMode.HTML
            )

        except Exception:
            pass

        uno_games.pop(
            game["chat_id"],
            None
        )

        return

    # ======================================
    # SPECIAL CARD
    # ======================================

    value = card["value"]

    if value == "skip":

        advance_turn(
            game,
            2
        )

    elif value == "reverse":

        game["direction"] *= -1

        if len(game["players"]) == 2:

            advance_turn(
                game,
                2
            )

        else:

            advance_turn(
                game,
                1
            )

    elif value == "+2":

        advance_turn(
            game,
            1
        )

        target = get_current_player(
            game
        )

        for _ in range(2):

            drawn = draw_card(
                game
            )

            if drawn:

                game["hands"][
                    target
                ].append(drawn)

        advance_turn(
            game,
            1
        )

    elif value == "+4":

        advance_turn(
            game,
            1
        )

        target = get_current_player(
            game
        )

        for _ in range(4):

            drawn = draw_card(
                game
            )

            if drawn:

                game["hands"][
                    target
                ].append(drawn)

        advance_turn(
            game,
            1
        )

    else:

        advance_turn(
            game,
            1
        )

    await query.answer(
        f"✅ Played {card_text(card)}"
    )

    # ======================================
    # REFRESH CURRENT PLAYER DM
    # ======================================

    await send_player_hand(
        context,
        game,
        user_id
    )

    # ======================================
    # NEXT PLAYER DM
    # ======================================

    next_player = get_current_player(
        game
    )

    await send_player_hand(
        context,
        game,
        next_player
    )

    # ======================================
    # GROUP UPDATE
    # ======================================

    await update_game_message(
        context,
        game
    )


# ==========================================
# DRAW CARD
# ==========================================

async def draw_uno_card(
    query,
    context,
    chat_id
):

    game = uno_games.get(
        chat_id
    )

    if not game:

        await query.answer(
            "❌ Game ended.",
            show_alert=True
        )

        return

    user_id = query.from_user.id

    if get_current_player(game) != user_id:

        await query.answer(
            "⏳ It's not your turn!",
            show_alert=True
        )

        return

    card = draw_card(
        game
    )

    if not card:

        await query.answer(
            "❌ No cards available.",
            show_alert=True
        )

        return

    game["hands"][
        user_id
    ].append(card)

    await query.answer(
        f"🃏 Drew {card_text(card)}"
    )

    # ======================================
    # REFRESH HAND
    # ======================================

    await send_player_hand(
        context,
        game,
        user_id
    )

    # ======================================
    # AUTO TURN
    # ======================================

    # Player can play the drawn card
    # if legal.
    if is_card_playable(
        card,
        game
    ):

        try:

            await context.bot.send_message(

                chat_id=user_id,

                text=(

                    "🃏 <b>CARD DRAWN</b>\n\n"

                    f"You drew "
                    f"<b>{card_text(card)}</b>.\n\n"

                    "✅ You can play it if you want."
                ),

                parse_mode=ParseMode.HTML
            )

        except Exception:
            pass

        return

    # Not playable -> next turn
    advance_turn(
        game,
        1
    )

    next_player = get_current_player(
        game
    )

    await send_player_hand(
        context,
        game,
        next_player
    )

    await update_game_message(
        context,
        game
    )


# ==========================================
# /ENDUNO
# ==========================================

async def enduno_command(
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
            "❌ UNO can only be ended in a group."
        )

        return

    game = uno_games.get(
        chat.id
    )

    if not game:

        await update.message.reply_text(
            "❌ No active UNO game."
        )

        return

    # ======================================
    # PLAYER ONLY
    # ======================================

    if user.id not in game["players"]:

        await update.message.reply_text(

            "🚫 <b>You aren't playing UNO.</b>\n\n"

            "Only players in the current match "
            "can use /enduno.",

            parse_mode=ParseMode.HTML
        )

        return

    # ======================================
    # DELETE GAME
    # ======================================

    uno_games.pop(
        chat.id,
        None
    )

    # ======================================
    # DELETE GAME MESSAGE
    # ======================================

    message_id = game.get(
        "message_id"
    )

    if message_id:

        try:

            await context.bot.delete_message(

                chat_id=chat.id,

                message_id=message_id
            )

        except Exception as e:

            print(
                f"⚠️ Could not delete UNO "
                f"game message: {e}"
            )

    # ======================================
    # END MESSAGE
    # ======================================

    await update.message.reply_text(

        "🛑 <b>UNO MATCH ENDED</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"👤 Ended by "
        f"{player_mention(user.id, user.full_name)}\n\n"
            
        "🎮 The match has been stopped.",

        parse_mode=ParseMode.HTML
    )