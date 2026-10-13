# ============================================================
# DEMON SLAYER MYSTERY HUNT
# Muichiro Telegram Bot
# ============================================================

import asyncio
import random
import time
import os
import html

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes
)

from database import db, cursor, USE_POSTGRES


# ============================================================
# CONFIGURATION
# ============================================================

OWNER_ID = 6608396796
STORE_CHANNEL_LINK = "https://t.me/muichiroUpdates/30"

HUNT_DURATION = 600
MIN_HUNT_INTERVAL = 3600
MAX_HUNT_INTERVAL = 7200

GOLDEN_HUNT_CHANCE = 0.25

ACTIVE_HUNTS = {}
RECENTLY_ENDED = {}

hunt_tasks = {}

db_lock = asyncio.Lock()


# ============================================================
# SAFE DATABASE ROLLBACK
# ============================================================

async def safe_db_rollback():
    try:
        async with db_lock:
            db.rollback()
    except Exception:
        pass


# ============================================================
# PREMIUM MESSAGE FORMATTING
# ============================================================


def hunt_quote(text):
    """Create a compact Telegram HTML blockquote for key hunt details."""
    return f"<blockquote>{text.strip()}</blockquote>"


def hunt_divider():
    """Keep message separators subtle instead of using oversized boxes."""
    return "<b>──────────────</b>"


# ============================================================
# CHARACTER ROSTER
# ============================================================

CHARACTERS = [

    {
        "name": "Tanjiro Kamado",
        "aliases": [
            "tanjiro",
            "tanjiro kamado",
            "kamado tanjiro"
        ],
        "image": "assets/demon_hunt/tanjiro.jpeg",
        "difficulty": "easy",
        "hint": "He carries a <b>heavy responsibility</b> while protecting someone precious.",
        "final_hint": "His younger sister is <b>Nezuko Kamado</b>.",
        "reward": 60,
    },

    {
        "name": "Nezuko Kamado",
        "aliases": [
            "nezuko",
            "nezuko kamado",
            "kamado nezuko"
        ],
        "image": "assets/demon_hunt/nezuko.jpeg",
        "difficulty": "easy",
        "hint": "She spends much of her journey inside a <b>wooden box</b>.",
        "final_hint": "She is the <b>younger sister of Tanjiro</b>.",
        "reward": 60,
    },

    {
        "name": "Zenitsu Agatsuma",
        "aliases": [
            "zenitsu",
            "zenitsu agatsuma",
            "agatsuma zenitsu"
        ],
        "image": "assets/demon_hunt/zenitsu.jpeg",
        "difficulty": "easy",
        "hint": "His greatest strength appears when his <b>fear fades away</b>.",
        "final_hint": "He is a master of <b>Thunder Breathing</b>.",
        "reward": 70,
    },

    {
        "name": "Inosuke Hashibira",
        "aliases": [
            "inosuke",
            "inosuke hashibira",
            "hashibira inosuke"
        ],
        "image": "assets/demon_hunt/inosuke.jpeg",
        "difficulty": "easy",
        "hint": "A wild fighter who prefers <b>instinct over strategy</b>.",
        "final_hint": "He created his own <b>Beast Breathing</b> style.",
        "reward": 70,
    },

    {
        "name": "Giyu Tomioka",
        "aliases": [
            "giyu",
            "giyu tomioka",
            "tomioka",
            "tomioka giyu"
        ],
        "image": "assets/demon_hunt/giyu.jpeg",
        "difficulty": "medium",
        "hint": "He is known for his <b>calm and distant nature</b>.",
        "final_hint": "He is the <b>Water Hashira</b>.",
        "reward": 100,
    },

    {
        "name": "Shinobu Kocho",
        "aliases": [
            "shinobu",
            "shinobu kocho",
            "kocho",
            "kocho shinobu"
        ],
        "image": "assets/demon_hunt/shinobu.jpeg",
        "difficulty": "medium",
        "hint": "Her fighting style relies heavily on <b>speed and poison</b>.",
        "final_hint": "She is the <b>Insect Hashira</b>.",
        "reward": 100,
    },

    {
        "name": "Mitsuri Kanroji",
        "aliases": [
            "mitsuri",
            "mitsuri kanroji",
            "kanroji",
            "kanroji mitsuri"
        ],
        "image": "assets/demon_hunt/mitsuri.jpeg",
        "difficulty": "medium",
        "hint": "Her unusual physical abilities make her <b>far stronger than she looks</b>.",
        "final_hint": "She is the <b>Love Hashira</b>.",
        "reward": 110,
    },

    {
        "name": "Obanai Iguro",
        "aliases": [
            "obanai",
            "obanai iguro",
            "iguro",
            "iguro obanai"
        ],
        "image": "assets/demon_hunt/obanai.jpeg",
        "difficulty": "hard",
        "hint": "A <b>white snake</b> is rarely far from him.",
        "final_hint": "He is the <b>Serpent Hashira</b>.",
        "reward": 140,
    },

    {
        "name": "Sanemi Shinazugawa",
        "aliases": [
            "sanemi",
            "sanemi shinazugawa",
            "shinazugawa",
            "shinazugawa sanemi"
        ],
        "image": "assets/demon_hunt/sanemi.jpeg",
        "difficulty": "hard",
        "hint": "His temper is as fierce as his <b>fighting spirit</b>.",
        "final_hint": "He is the <b>Wind Hashira</b>.",
        "reward": 140,
    },

    {
        "name": "Muichiro Tokito",
        "aliases": [
            "muichiro",
            "muichiro tokito",
            "tokito",
            "tokito muichiro"
        ],
        "image": "assets/demon_hunt/muichiro.jpeg",
        "difficulty": "hard",
        "hint": "His thoughts once drifted away like <b>mist</b>.",
        "final_hint": "He is the <b>Mist Hashira</b>.",
        "reward": 160,
    },

    {
        "name": "Kyojuro Rengoku",
        "aliases": [
            "rengoku",
            "kyojuro",
            "kyojuro rengoku",
            "rengoku kyojuro"
        ],
        "image": "assets/demon_hunt/rengoku.jpeg",
        "difficulty": "medium",
        "hint": "His determination burns with an <b>unshakable spirit</b>.",
        "final_hint": "He is the <b>Flame Hashira</b>.",
        "reward": 120,
    },

    {
        "name": "Gyomei Himejima",
        "aliases": [
            "gyomei",
            "gyomei himejima",
            "himejima",
            "himejima gyomei"
        ],
        "image": "assets/demon_hunt/gyomei.jpeg",
        "difficulty": "legendary",
        "hint": "His immense strength is matched by a <b>deep sense of compassion</b>.",
        "final_hint": "He is the <b>Stone Hashira</b>.",
        "reward": 200,
    },

    {
        "name": "Tengen Uzui",
        "aliases": [
            "tengen",
            "tengen uzui",
            "uzui",
            "uzui tengen"
        ],
        "image": "assets/demon_hunt/tengen.jpeg",
        "difficulty": "medium",
        "hint": "For him, ordinary is never enough — everything must be <b>flashy</b>.",
        "final_hint": "He is the <b>Sound Hashira</b>.",
        "reward": 110,
    },
]


# ============================================================
# STORE ITEMS
# ============================================================

STORE_ITEMS = {

    1: {
        "name": "Elite Slayer Badge",
        "emoji": "🎖️",
        "price": 500,
        "type": "badge",
        "description": "A badge for rising Demon Slayers.",
    },

    2: {
        "name": "Mist Badge",
        "emoji": "🌫️",
        "price": 1000,
        "type": "badge",
        "description": "A rare badge inspired by the Mist Hashira.",
    },

    3: {
        "name": "Flame Badge",
        "emoji": "🔥",
        "price": 1500,
        "type": "badge",
        "description": "A fiery badge for fearless hunters.",
    },

    4: {
        "name": "Hashira Badge",
        "emoji": "👑",
        "price": 2500,
        "type": "badge",
        "description": "A prestigious Hashira profile badge.",
    },

    5: {
        "name": "Lucky Charm",
        "emoji": "🍀",
        "price": 1000,
        "type": "collectible",
        "description": "A special collectible for your inventory.",
    },

    6: {
        "name": "Slayer Katana",
        "emoji": "⚔️",
        "price": 10000,
        "type": "collectible",
        "description": "A legendary profile collectible.",
    },

    7: {
        "name": "Golden Relic",
        "emoji": "🌟",
        "price": 5000,
        "type": "collectible",
        "description": "An extremely rare Demon Slayer relic.",
    },

    8: {
        "name": "Diamond Crest",
        "emoji": "💎",
        "price": 15000,
        "type": "badge",
        "description": "A premium badge for elite collectors.",
    },

    9: {
        "name": "Golden Hashira Crest",
        "emoji": "🏵️",
        "price": 25000,
        "type": "badge",
        "description": "A prestigious golden profile crest.",
    },

    10: {
        "name": "Legendary Slayer Relic",
        "emoji": "✨",
        "price": 50000,
        "type": "collectible",
        "description": "The ultimate collectible of the Corps.",
    },
}


# ============================================================
# PURCHASE ACHIEVEMENTS
# ============================================================

PURCHASE_ACHIEVEMENTS = [

    (1, 0, "🛍️ First Purchase"),

    (0, 2500, "💰 Collector"),

    (0, 10000, "💎 Big Spender"),

    (0, 25000, "🔥 Elite Collector"),

    (0, 50000, "👑 Golden Hashira"),

    (0, 100000, "🌟 Legendary Collector"),

]


# ============================================================
# HUNT ACHIEVEMENTS
# ============================================================

ACHIEVEMENTS = [

    (1, "🥉 Rookie Slayer"),

    (5, "🥈 Demon Hunter"),

    (15, "🥇 Elite Slayer"),

    (30, "⚔️ Hashira Candidate"),

    (50, "👑 Legendary Hashira"),

]


# ============================================================
# DATABASE SETUP
# ============================================================

async def setup_hunt_database():

    async with db_lock:

        try:

            # ------------------------------------------------
            # PLAYER ECONOMY
            # ------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS slayer_points (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    points BIGINT DEFAULT 0,
                    hunts_won INTEGER DEFAULT 0,
                    total_guesses INTEGER DEFAULT 0,
                    correct_guesses INTEGER DEFAULT 0,
                    win_streak INTEGER DEFAULT 0,
                    best_streak INTEGER DEFAULT 0,
                    is_bot BOOLEAN DEFAULT FALSE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Existing installations
            cursor.execute("""
                ALTER TABLE slayer_points
                ADD COLUMN IF NOT EXISTS is_bot BOOLEAN DEFAULT FALSE
            """)


            # ------------------------------------------------
            # GROUP REGISTRATION
            # ------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS demon_hunt_groups (
                    chat_id BIGINT PRIMARY KEY,
                    chat_title TEXT,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_hunts INTEGER DEFAULT 0,
                    total_guesses INTEGER DEFAULT 0
                )
            """)


            # ------------------------------------------------
            # HUNT HISTORY
            # ------------------------------------------------

            if USE_POSTGRES:

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS demon_hunt_history (
                        id BIGSERIAL PRIMARY KEY,
                        chat_id BIGINT,
                        character_name TEXT,
                        winner_id BIGINT,
                        winner_name TEXT,
                        reward INTEGER DEFAULT 0,
                        total_guesses INTEGER DEFAULT 0,
                        golden BOOLEAN DEFAULT FALSE,
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE SEQUENCE IF NOT EXISTS
                    demon_hunt_history_id_seq
                """)

                cursor.execute("""
                    ALTER TABLE demon_hunt_history
                    ALTER COLUMN id
                    SET DEFAULT
                    nextval('demon_hunt_history_id_seq')
                """)

                cursor.execute("""
                    ALTER SEQUENCE demon_hunt_history_id_seq
                    OWNED BY demon_hunt_history.id
                """)

                cursor.execute("""
                    SELECT setval(
                        'demon_hunt_history_id_seq',
                        COALESCE(
                            (SELECT MAX(id)
                             FROM demon_hunt_history),
                            0
                        ) + 1,
                        false
                    )
                """)

            else:

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS demon_hunt_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER,
                        character_name TEXT,
                        winner_id INTEGER,
                        winner_name TEXT,
                        reward INTEGER DEFAULT 0,
                        total_guesses INTEGER DEFAULT 0,
                        golden BOOLEAN DEFAULT FALSE,
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)


            # ------------------------------------------------
            # HUNT ACHIEVEMENTS
            # ------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS slayer_achievements (
                    user_id BIGINT,
                    achievement TEXT,
                    earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, achievement)
                )
            """)


            # ------------------------------------------------
            # STORE INVENTORY
            # ------------------------------------------------

            if USE_POSTGRES:

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS
                    slayer_inventory (
                        user_id BIGINT,
                        item_id INTEGER,
                        quantity INTEGER DEFAULT 1,
                        purchased_at TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, item_id)
                    )
                """)

            else:

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS
                    slayer_inventory (
                        user_id INTEGER,
                        item_id INTEGER,
                        quantity INTEGER DEFAULT 1,
                        purchased_at TIMESTAMP
                        DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, item_id)
                    )
                """)


            # ------------------------------------------------
            # STORE STATS
            # ------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS slayer_store_stats (
                    user_id BIGINT PRIMARY KEY,
                    total_spent BIGINT DEFAULT 0,
                    purchase_count INTEGER DEFAULT 0,
                    updated_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
                )
            """)


            # ------------------------------------------------
            # PROFILE SETTINGS
            # ------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS slayer_profile (
                    user_id BIGINT PRIMARY KEY,
                    equipped_badge INTEGER,
                    updated_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
                )
            """)

            db.commit()

            print("⚔️ Demon Slayer Hunt database ready!")

        except Exception as e:

            print(
                f"❌ Hunt database setup error: {e}"
            )

            try:
                db.rollback()
            except Exception:
                pass

# ============================================================
# HTMAL USER TAG
# ============================================================

def get_user_html_tag(user):
    if user.username:
        return (
            f'<a href="tg://user?id={user.id}">'
            f'@{html.escape(user.username)}'
            f'</a>'
        )

    name = html.escape(
        user.first_name or "Unknown User"
    )

    return (
        f'<a href="tg://user?id={user.id}">'
        f'{name}'
        f'</a>'
    )
# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_answer(text):

    if not text:
        return ""

    return " ".join(
        text.lower().strip().split()
    )


# ============================================================
# VALID REAL USER
# ============================================================

def is_valid_hunt_user(update, user=None):

    if not update:
        return False

    message = update.effective_message

    if not message:
        return False

    if getattr(message, "sender_chat", None):
        return False

    if user is None:
        user = update.effective_user

    if not user:
        return False

    if user.is_bot:
        return False

    return True


# ============================================================
# ANONYMOUS USER MESSAGE
# ============================================================

async def reject_anonymous_user(update):

    if not update.effective_message:
        return

    await update.effective_message.reply_text(
        "⚠️ <b>You are not a user.</b>\n\n"
        "Demon Hunt is only available to real Telegram users.",
        parse_mode=ParseMode.HTML
    )


# ============================================================
# REGISTER GROUP
# ============================================================

async def track_hunt_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_chat:
        return

    chat = update.effective_chat

    if chat.type not in ["group", "supergroup"]:
        return

    try:

        async with db_lock:

            cursor.execute("""
                INSERT INTO demon_hunt_groups
                (
                    chat_id,
                    chat_title,
                    last_activity
                )
                VALUES (%s, %s, CURRENT_TIMESTAMP)

                ON CONFLICT (chat_id)
                DO UPDATE SET
                    chat_title = EXCLUDED.chat_title,
                    last_activity = CURRENT_TIMESTAMP
            """, (
                chat.id,
                chat.title or "Unknown Group"
            ))

            db.commit()

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"⚠️ Hunt group tracking error: {e}"
        )


# ============================================================
# REGISTERED GROUPS
# ============================================================

async def get_registered_groups():

    try:

        async with db_lock:

            cursor.execute("""
                SELECT chat_id
                FROM demon_hunt_groups
            """)

            rows = cursor.fetchall()

        return [
            row[0]
            for row in rows
        ]

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Error getting hunt groups: {e}"
        )

        return []


# ============================================================
# ENSURE PLAYER
# ============================================================

async def ensure_player(user):

    if not user:
        return False

    if user.is_bot:
        return False

    username = (
        f"@{user.username}"
        if user.username
        else None
    )

    full_name = user.full_name

    try:

        async with db_lock:

            cursor.execute("""
                INSERT INTO slayer_points
                (
                    user_id,
                    username,
                    full_name,
                    points,
                    hunts_won,
                    total_guesses,
                    correct_guesses,
                    win_streak,
                    best_streak,
                    is_bot
                )
                VALUES
                (
                    %s, %s, %s,
                    0, 0, 0, 0, 0, 0, FALSE
                )

                ON CONFLICT (user_id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name,
                    is_bot = FALSE
            """, (
                user.id,
                username,
                full_name
            ))

            db.commit()

        return True

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Player creation error: {e}"
        )

        return False


# ============================================================
# HUNT ACHIEVEMENTS
# ============================================================

async def check_achievements(
    user_id,
    wins
):

    new_achievements = []

    try:

        async with db_lock:

            for required_wins, achievement in ACHIEVEMENTS:

                if wins >= required_wins:

                    cursor.execute("""
                        SELECT 1
                        FROM slayer_achievements
                        WHERE user_id = %s
                        AND achievement = %s
                    """, (
                        user_id,
                        achievement
                    ))

                    if cursor.fetchone():
                        continue

                    cursor.execute("""
                        INSERT INTO slayer_achievements
                        (
                            user_id,
                            achievement
                        )
                        VALUES (%s, %s)
                    """, (
                        user_id,
                        achievement
                    ))

                    new_achievements.append(
                        achievement
                    )

            db.commit()

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Achievement error: {e}"
        )

    return new_achievements


# ============================================================
# STORE ACHIEVEMENTS
# ============================================================

async def check_store_achievements(
    user_id,
    purchase_count,
    total_spent
):

    new_achievements = []

    try:

        async with db_lock:

            for required_purchases, required_spent, achievement in PURCHASE_ACHIEVEMENTS:

                purchase_ok = (
                    required_purchases == 0
                    or purchase_count >= required_purchases
                )

                spent_ok = (
                    required_spent == 0
                    or total_spent >= required_spent
                )

                if not (
                    purchase_ok
                    and spent_ok
                ):
                    continue

                cursor.execute("""
                    SELECT 1
                    FROM slayer_achievements
                    WHERE user_id = %s
                    AND achievement = %s
                """, (
                    user_id,
                    achievement
                ))

                if cursor.fetchone():
                    continue

                cursor.execute("""
                    INSERT INTO slayer_achievements
                    (
                        user_id,
                        achievement
                    )
                    VALUES (%s, %s)
                """, (
                    user_id,
                    achievement
                ))

                new_achievements.append(
                    achievement
                )

            db.commit()

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Store achievement error: {e}"
        )

    return new_achievements


# ============================================================
# REWARD CALCULATION
# ============================================================

def calculate_reward(
    base_reward,
    attempts,
    golden=False
):

    if attempts <= 1:
        multiplier = 1.0

    elif attempts <= 3:
        multiplier = 0.80

    elif attempts <= 5:
        multiplier = 0.60

    elif attempts <= 8:
        multiplier = 0.45

    else:
        multiplier = 0.30

    reward = int(
        base_reward * multiplier
    )

    if golden:
        reward *= 2

    return max(
        reward,
        10
    )


# ============================================================
# START HUNT
# ============================================================

async def start_demon_hunt(
    bot,
    chat_id
):

    if chat_id in ACTIVE_HUNTS:
        return False

    character = random.choice(
        CHARACTERS
    )

    golden = (
        random.random()
        < GOLDEN_HUNT_CHANCE
    )

    hunt_id = (
        f"{chat_id}_{int(time.time())}"
    )

    now = time.time()

    hunt_data = {

        "hunt_id": hunt_id,

        "character": character,

        "started_at": now,

        "ends_at": (
            now + HUNT_DURATION
        ),

        "guesses": {},

        "total_guesses": 0,

        "wrong_answers": set(),

        "last_guess_time": {},

        "solved": False,

        "golden": golden,

        "hint_tasks": [],
    }

    ACTIVE_HUNTS[chat_id] = hunt_data


    if golden:

        caption = (
            "🌟 <b>𝗚𝗢𝗟𝗗𝗘𝗡 𝗗𝗘𝗠𝗢𝗡 𝗛𝗨𝗡𝗧 𝗗𝗥𝗢𝗣𝗣𝗘𝗗!</b>\n\n"
            + hunt_quote(
                "A legendary Demon has fallen.\n"
                "Find the Slayer who defeated it.\n\n"
                "💎 <b>REWARD:</b> 2× Slayer Points\n"
                "⌁ <b>GUESS:</b> <code>/g &lt;name&gt;</code>\n"
                "⏳ <b>TIME LIMIT:</b> 10 Minutes"
            )
            + "\n\n<b>Double Rewards. One Winner.</b>"
        )

    else:

        caption = (
            "📦 <b>𝗡𝗘𝗪 𝗗𝗘𝗠𝗢𝗡 𝗛𝗨𝗡𝗧 𝗗𝗥𝗢𝗣𝗣𝗘𝗗!</b>\n\n"
            + hunt_quote(
                "A Demon has fallen, but its Slayer remains unknown.\n\n"
                "💎 <b>REWARD:</b> Slayer Points\n"
                "⌁ <b>GUESS:</b> <code>/g &lt;name&gt;</code>\n"
                "⏳ <b>TIME LIMIT:</b> 10 Minutes"
            )
            + "\n\n<b>Study carefully. Think fast.</b>\n"
            "⌁ First correct guess claims the reward."
        )


    try:

        image_path = character["image"]

        if not os.path.exists(image_path):
            raise FileNotFoundError(
                f"Image not found: {image_path}"
            )

        with open(
            image_path,
            "rb"
        ) as photo_file:

            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_file,
                caption=caption,
                parse_mode="HTML"
            )

        print(
            f"⚔️ Hunt started: "
            f"{character['name']} -> {chat_id}"
        )

    except Exception as e:

        print(
            f"❌ Could not start hunt "
            f"in {chat_id}: {e}"
        )

        ACTIVE_HUNTS.pop(
            chat_id,
            None
        )

        return False


    # --------------------------------------------------------
    # Group stats
    # --------------------------------------------------------

    try:

        async with db_lock:

            cursor.execute("""
                UPDATE demon_hunt_groups
                SET total_hunts =
                    total_hunts + 1
                WHERE chat_id = %s
            """, (
                chat_id,
            ))

            db.commit()

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"⚠️ Group hunt stat error: {e}"
        )


    # --------------------------------------------------------
    # Hint tasks
    # --------------------------------------------------------

    hint_tasks = [

        asyncio.create_task(
            send_hint(
                bot,
                chat_id,
                hunt_id,
                180,
                1
            )
        ),

        asyncio.create_task(
            send_hint(
                bot,
                chat_id,
                hunt_id,
                360,
                2
            )
        ),

        asyncio.create_task(
            send_hint(
                bot,
                chat_id,
                hunt_id,
                480,
                3
            )
        ),

        asyncio.create_task(
            end_hunt_after_timeout(
                bot,
                chat_id,
                hunt_id
            )
        ),
    ]

    hunt_data["hint_tasks"] = hint_tasks

    return True


# ============================================================
# HINT SYSTEM
# ============================================================

async def send_hint(
    bot,
    chat_id,
    hunt_id,
    delay,
    hint_number
):

    try:

        await asyncio.sleep(
            delay
        )

        hunt = ACTIVE_HUNTS.get(
            chat_id
        )

        if not hunt:
            return

        if hunt["hunt_id"] != hunt_id:
            return

        if hunt["solved"]:
            return

        character = hunt["character"]


        if hint_number == 1:

            first_letter = (
                character["name"][0]
            )

            text = (
                "💡 <b>𝗛𝗜𝗡𝗧 #𝟭 𝗨𝗡𝗟𝗢𝗖𝗞𝗘𝗗!</b>\n\n"
                + hunt_quote(
                    "The Slayer's name starts with: <b>"
                    + html.escape(first_letter)
                    + "</b>\n\n"
                    "⌁ <b>GUESS:</b> <code>/g &lt;name&gt;</code>"
                )
                + "\n𝗞𝗲𝗲𝗽 𝗵𝘂𝗻𝘁𝗶𝗻𝗴..."
            )

        elif hint_number == 2:

            text = (
                "💡 <b>𝗛𝗜𝗡𝗧 #𝟮 𝗨𝗡𝗟𝗢𝗖𝗞𝗘𝗗!</b>\n\n"
                + hunt_quote(
                    character["hint"]
                    + "\n\n⌁ <b>GUESS:</b> <code>/g &lt;name&gt;</code>"
                )
                + "\n𝗧𝗵𝗲 𝗺𝘆𝘀𝘁𝗲𝗿𝘆 𝗶𝘀 𝗴𝗲𝘁𝘁𝗶𝗻𝗴 𝗰𝗹𝗼𝘀𝗲𝗿..."
            )

        else:

            text = (
                "✨ <b>𝗙𝗜𝗡𝗔𝗟 𝗛𝗜𝗡𝗧 𝗨𝗡𝗟𝗢𝗖𝗞𝗘𝗗!</b>\n\n"
                + hunt_quote(
                    character["final_hint"]
                    + "\n\n⌁ <b>LAST CHANCE:</b> <code>/g &lt;name&gt;</code>"
                )
                + "\n<b>Choose wisely.</b>"
            )

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML
        )

    except asyncio.CancelledError:
        return

    except Exception as e:

        print(
            f"❌ Hint error: {e}"
        )


# ============================================================
# TIMEOUT
# ============================================================

async def end_hunt_after_timeout(
    bot,
    chat_id,
    hunt_id
):

    try:

        await asyncio.sleep(
            HUNT_DURATION
        )

        hunt = ACTIVE_HUNTS.get(
            chat_id
        )

        if not hunt:
            return

        if hunt["hunt_id"] != hunt_id:
            return

        if hunt["solved"]:
            return

        hunt["solved"] = True

        character = hunt["character"]

        await bot.send_message(

            chat_id=chat_id,

            text=(
                "🌫️ <b>𝗧𝗛𝗘 𝗛𝗨𝗡𝗧 𝗛𝗔𝗦 𝗘𝗡𝗗𝗘𝗗...</b>\n\n"
                + hunt_quote(
                    "💨 The Slayer disappeared into the mist before anyone could identify them.\n\n"
                    "⚔️ <b>The Answer:</b> <code>"
                    + html.escape(character["name"])
                    + "</code>"
                )
                + "\n\n💔 No Slayer Points were awarded.\n\n"
                + hunt_divider()
                + "\n🌙 Another demon may appear when you least expect it..."
            ),

            parse_mode=ParseMode.HTML
        )

        await finish_hunt(
            chat_id,
            hunt
        )

    except asyncio.CancelledError:
        return

    except Exception as e:

        print(
            f"❌ Hunt timeout error: {e}"
        )


# ============================================================
# FINISH HUNT
# ============================================================

async def finish_hunt(
    chat_id,
    hunt
):

    ACTIVE_HUNTS.pop(
        chat_id,
        None
    )

    RECENTLY_ENDED[chat_id] = (
        time.time() + 300
    )

    current_task = (
        asyncio.current_task()
    )

    for task in hunt.get(
        "hint_tasks",
        []
    ):

        if (
            task != current_task
            and not task.done()
        ):
            task.cancel()


# ============================================================
# GUESS COMMAND
# ============================================================

async def guess_(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if getattr(
        update.message,
        "sender_chat",
        None
    ):

        await reject_anonymous_user(
            update
        )

        return

    if not update.effective_user:
        return

    user = update.effective_user

    if user.is_bot:
        return

    chat = update.effective_chat

    if not chat:
        return

    if chat.type not in [
        "group",
        "supergroup"
    ]:

        await update.message.reply_text(
            "⚠️ 𝗧𝗵𝗲 𝗗𝗲𝗺𝗼𝗻 𝗛𝘂𝗻𝘁 "
            "can only be played in groups."
        )

        return


    hunt = ACTIVE_HUNTS.get(
        chat.id
    )

    if not hunt:

        recently_ended = (
            RECENTLY_ENDED.get(
                chat.id
            )
        )

        if (
            recently_ended
            and recently_ended > time.time()
        ):

            await update.message.reply_text(
                "⚠️ <b>𝗧𝗛𝗘 𝗛𝗨𝗡𝗧 𝗜𝗦 𝗢𝗩𝗘𝗥!</b>\n\n"
                "🌫️ This mystery has already ended.\n"
                "Wait for the next demon to appear... ⚔️",
                parse_mode=ParseMode.HTML
            )

        else:

            await update.message.reply_text(
                "🌙 <b>𝗡𝗢 𝗔𝗖𝗧𝗜𝗩𝗘 𝗛𝗨𝗡𝗧</b>\n\n"
                "No demon has appeared yet.\n"
                "Stay alert... the next hunt can begin anytime. ⚔️",
                parse_mode=ParseMode.HTML
            )

        return


    if not context.args:

        await update.message.reply_text(
            "⚠️ <b>𝗨𝗦𝗔𝗚𝗘:</b>\n\n"
            "<code>/g &lt;Demon Slayer's name&gt;</code>",
            parse_mode=ParseMode.HTML
        )

        return


    answer = normalize_answer(
        " ".join(context.args)
    )


    user_guesses = hunt[
        "guesses"
    ].setdefault(
        user.id,
        set()
    )


    if answer in user_guesses:

        await update.message.reply_text(
            "🔁 You've already tried that answer!"
        )

        return


    user_guesses.add(
        answer
    )

    hunt["total_guesses"] += 1


    await ensure_player(
        user
    )


    try:

        async with db_lock:

            cursor.execute("""
                UPDATE slayer_points
                SET
                    total_guesses =
                        total_guesses + 1,
                    updated_at =
                        CURRENT_TIMESTAMP
                WHERE user_id = %s
                AND is_bot = FALSE
            """, (
                user.id,
            ))

            cursor.execute("""
                UPDATE demon_hunt_groups
                SET total_guesses =
                    total_guesses + 1
                WHERE chat_id = %s
            """, (
                chat.id,
            ))

            db.commit()

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"⚠️ Guess stat error: {e}"
        )


    aliases = [

        normalize_answer(alias)

        for alias in hunt[
            "character"
        ]["aliases"]

    ]


    if answer not in aliases:

        wrong_messages = [

            "❌ <b>Wrong guess!</b>\n\n"
            "🌫️ The mist remains silent... "
            "Try again, Slayer! ⚔️",

            "❌ <b>Not quite!</b>\n\n"
            "🌙 That doesn't seem to be "
            "the mysterious Slayer.",

            "❌ <b>Incorrect!</b>\n\n"
            "⚔️ The Demon Slayer Corps "
            "records no match. Keep hunting!",

            "❌ <b>Wrong answer!</b>\n\n"
            "🌟 Don't give up, hunter. "
            "Study the clues carefully!",
        ]

        try:

            await update.message.reply_text(
                random.choice(
                    wrong_messages
                ),
                parse_mode=ParseMode.HTML
            )

        except Exception as e:

            print(
                f"❌ Wrong guess message error: {e}"
            )

        return


    if hunt["solved"]:
        return

    hunt["solved"] = True

    attempts = len(
        user_guesses
    )

    character = hunt[
        "character"
    ]

    reward = calculate_reward(
        character["reward"],
        attempts,
        hunt["golden"]
    )


    await award_winner(
        user=user,
        reward=reward
    )


    wins = 0
    streak = 0
    best_streak = 0

    try:

        async with db_lock:

            cursor.execute("""
                SELECT
                    hunts_won,
                    win_streak,
                    best_streak
                FROM slayer_points
                WHERE user_id = %s
                AND is_bot = FALSE
            """, (
                user.id,
            ))

            row = cursor.fetchone()

            if row:

                wins = row[0]
                streak = row[1]
                best_streak = row[2]

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Winner stat fetch error: {e}"
        )


    new_achievements = (
        await check_achievements(
            user.id,
            wins
        )
    )


    # --------------------------------------------------------
    # SAVE HISTORY
    # --------------------------------------------------------

    try:

        async with db_lock:

            cursor.execute("""
                INSERT INTO demon_hunt_history
                (
                    chat_id,
                    character_name,
                    winner_id,
                    winner_name,
                    reward,
                    total_guesses,
                    golden
                )
                VALUES
                (
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
            """, (

                chat.id,
                character["name"],
                user.id,
                user.full_name,
                reward,
                hunt["total_guesses"],
                hunt["golden"]

            ))

            db.commit()

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"⚠️ Hunt history error: {e}"
        )


    achievement_text = ""

    if new_achievements:

        achievement_text = (
            "\n\n🏅 <b>𝗡𝗘𝗪 𝗔𝗖𝗛𝗜𝗘𝗩𝗘𝗠𝗘𝗡𝗧!</b>\n"
            + "\n".join(
                f"✨ {html.escape(a)}"
                for a in new_achievements
            )
        )


    golden_text = ""

    if hunt["golden"]:

        golden_text = (
            "\n🌟 <b>GOLDEN HUNT BONUS ×2!</b>"
        )


    try:

        await update.message.reply_text(

            (
                "🏆⚔️ <b>𝗗𝗘𝗠𝗢𝗡 𝗦𝗟𝗔𝗬𝗘𝗥 𝗜𝗗𝗘𝗡𝗧𝗜𝗙𝗜𝗘𝗗!</b>\n\n"
                + hunt_quote(
                    "👑 <b>Hunter:</b> " + user.mention_html() + "\n"
                    "⚔️ <b>Slayer:</b> " + html.escape(character["name"]) + "\n"
                    f"🎯 <b>Attempts:</b> {attempts}\n"
                    f"💎 <b>Reward:</b> +{reward} Slayer Points\n"
                    f"🔥 <b>Win Streak:</b> {streak}"
                )
                + golden_text
                + achievement_text
                + "\n\n"
                + hunt_divider()
                + "\n<i>The Demon Slayer Corps recognizes your knowledge! 🌙⚔️</i>"
            ),

            parse_mode=ParseMode.HTML
        )

    except Exception as e:

        print(
            f"❌ Winner message error: {e}"
        )


    await finish_hunt(
        chat.id,
        hunt
    )


# ============================================================
# AWARD WINNER
# ============================================================

async def award_winner(
    user,
    reward
):

    if not await ensure_player(user):
        return False

    try:

        async with db_lock:

            cursor.execute("""
                UPDATE slayer_points
                SET
                    points =
                        points + %s,

                    hunts_won =
                        hunts_won + 1,

                    correct_guesses =
                        correct_guesses + 1,

                    win_streak =
                        win_streak + 1,

                    best_streak =
                        CASE
                            WHEN win_streak + 1
                                > best_streak
                            THEN win_streak + 1
                            ELSE best_streak
                        END,

                    updated_at =
                        CURRENT_TIMESTAMP

                WHERE user_id = %s
                AND is_bot = FALSE
            """, (
                reward,
                user.id
            ))

            db.commit()

        return True

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Award error: {e}"
        )

        return False


# ============================================================
# STORE HELPER — PLAYER STATS
# ============================================================

async def get_store_stats(user_id):

    try:

        async with db_lock:

            cursor.execute("""
                SELECT
                    total_spent,
                    purchase_count
                FROM slayer_store_stats
                WHERE user_id = %s
            """, (
                user_id,
            ))

            row = cursor.fetchone()

        if not row:
            return 0, 0

        return (
            row[0] or 0,
            row[1] or 0
        )

    except Exception as e:

        print(
            f"❌ Store stats error: {e}"
        )

        return 0, 0


# ============================================================
# STORE HELPER — INVENTORY
# ============================================================

async def get_inventory(user_id):

    try:

        async with db_lock:

            cursor.execute("""
                SELECT
                    item_id,
                    quantity
                FROM slayer_inventory
                WHERE user_id = %s
                ORDER BY item_id
            """, (
                user_id,
            ))

            return cursor.fetchall()

    except Exception as e:

        print(
            f"❌ Inventory error: {e}"
        )

        return []


# ============================================================
# STORE HELPER — EQUIPPED BADGE
# ============================================================

async def get_equipped_badge(user_id):

    try:

        async with db_lock:

            cursor.execute("""
                SELECT equipped_badge
                FROM slayer_profile
                WHERE user_id = %s
            """, (
                user_id,
            ))

            row = cursor.fetchone()

        if not row:
            return None

        return row[0]

    except Exception as e:

        print(
            f"❌ Equipped badge error: {e}"
        )

        return None


# ============================================================
# /STORE
# ============================================================

async def store_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if getattr(
        update.message,
        "sender_chat",
        None
    ):

        await reject_anonymous_user(
            update
        )

        return

    user = update.effective_user

    if not user:
        return

    if user.is_bot:
        return

    await ensure_player(
        user
    )

    try:

        async with db_lock:

            cursor.execute(
                """
                SELECT points
                FROM slayer_points
                WHERE user_id = %s
                AND is_bot = FALSE
                """,
                (
                    user.id,
                )
            )

            row = cursor.fetchone()

        coins = (
            row[0]
            if row
            else 0
        )
        user_mention = (
    f'<a href="tg://user?id={user.id}">'
    f'{html.escape(user.first_name or "Hunter")}'
    f'</a>'
)
    except Exception as e:

        print(
            f"❌ Store balance error: {e}"
        )

        return

    # --------------------------------------------------------
    # STORE BUTTONS
    # --------------------------------------------------------

    keyboard = [

        [
            InlineKeyboardButton(
                "🛍️  Vɪᴇᴡ Fᴜʟʟ Sᴛᴏʀᴇ",
                url=STORE_CHANNEL_LINK
            )
        ],

        [
            InlineKeyboardButton(
                "🎒  Iɴᴠᴇɴᴛᴏʀʏ",
                callback_data="slayer_inventory"
            ),

            InlineKeyboardButton(
                "🎖️  Eǫᴜɪᴘ Bᴀᴅɢᴇ",
                callback_data="slayer_equip_help"
            )
        ]

    ]

    reply_markup = InlineKeyboardMarkup(
        keyboard
    )

    # --------------------------------------------------------
    # SHORT STORE MESSAGE
    # --------------------------------------------------------

    text = (
        "╭━━━〔 🏪 <b>𝗦𝗟𝗔𝗬𝗘𝗥 𝗦𝗧𝗢𝗥𝗘</b> 〕━━━╮\n\n"
        f"👤{user_mention}\n"
        f"💎 <b>Your Coins:</b> "
        f"{coins:,}\n\n"

        "✨ Explore the complete Hunter Store "
        "and discover all available rewards, "
        "badges and exclusive items.\n"

        "🛍️ <b>Tap below to open the full Store.</b>\n"

        "⚔️ <i>Earn coins. Collect rewards. "
        "Build your legacy.</i>\n\n"

        "╰━━━━━━━━━━━━━━━━━━━━╯"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def store_button_callback(update, context):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    user = query.from_user

    if not user or user.is_bot:
        return

    # ==================================================
    # 🎒 INVENTORY
    # ==================================================

    if query.data == "slayer_inventory":

        await ensure_player(user)

        inventory = await get_inventory(user.id)
        total_spent, purchase_count = await get_store_stats(user.id)
        equipped_badge = await get_equipped_badge(user.id)

        lines = []

        if inventory:
            for item_id, quantity in inventory:

                item = STORE_ITEMS.get(item_id)

                if not item:
                    continue

                name = html.escape(item["name"])
                emoji = item["emoji"]

                equipped_text = ""

                if (
                    item.get("type") == "badge"
                    and equipped_badge == item_id
                ):
                    equipped_text = "  ◈ <b>EQUIPPED</b>"

                lines.append(
                    f"│ {emoji} <b>{name}</b>\n"
                    f"│    └─ x{quantity}{equipped_text}"
                )

        if not lines:
            inventory_text = (
                "│\n"
                "│ 📦 <i>Your inventory is empty.</i>\n"
                "│\n"
                "│ Visit the Slayer Store to get your first item!"
            )
        else:
            inventory_text = "\n".join(lines)

        # Equipped badge display
        if equipped_badge:
            equipped_item = STORE_ITEMS.get(equipped_badge)

            if equipped_item:
                equipped_name = html.escape(
                    equipped_item["name"]
                )

                equipped_display = (
                    f"{equipped_item['emoji']} "
                    f"<b>{equipped_name}</b>"
                )
            else:
                equipped_display = "❔ Unknown Badge"
        else:
            equipped_display = "None"
        user_mention = (
    f'<a href="tg://user?id={user.id}">'
    f'{html.escape(user.first_name or "Hunter")}'
    f'</a>'
)
        text = (
            "╭━━━〔 🎒 <b>𝗬𝗢𝗨𝗥 𝗜𝗡𝗩𝗘𝗡𝗧𝗢𝗥𝗬</b> 〕━━━╮\n"
            f"│👤 {user_mention} \n"
            f"{inventory_text}\n"
            "│\n"
            "├──────────────────\n"
            f"│ 🎖️ <b>Equipped Badge:</b>\n"
            f"│ {equipped_display}\n"
            "│\n"
            f"│ 🛍️ <b>Purchases:</b> {purchase_count:,}\n"
            f"│ 💎 <b>Total Spent:</b> {total_spent:,} coins\n"
            "│\n"
            "╰──────────────────"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "↩️ Bᴀᴄᴋ Tᴏ Sᴛᴏʀᴇ",
                    callback_data="slayer_store"
                )
            ],
            [
                InlineKeyboardButton(
                    "🎖️ Eǫᴜɪᴘ Bᴀᴅɢᴇ",
                    callback_data="slayer_equip_help"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return

    # ==================================================
    # 🎖️ EQUIP BADGE HELP
    # ==================================================

    if query.data == "slayer_equip_help":

        text = (
            "╭━━━〔 🎖️ <b>𝗘𝗤𝗨𝗜𝗣 𝗕𝗔𝗗𝗚𝗘</b> 〕━━━╮\n"
            "│\n"
            "│ Equip any badge you own using\n"
            "│ its Store item ID.\n"
            "│\n"
            "│ 📝 <b>Example:</b>\n"
            "│ <code>/equipbadge 4</code>\n"
            "│\n"
            "│ Your equipped badge will appear\n"
            "│ on your Slayer Profile.\n"
            "│\n"
            "╰──────────────────"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "↩️ Bᴀᴄᴋ Tᴏ Iɴᴠᴇɴᴛᴏʀʏ",
                    callback_data="slayer_inventory"
                )
            ],
            [
                InlineKeyboardButton(
                    "🏪 Sᴛᴏʀᴇ",
                    callback_data="slayer_store"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return

    # ==================================================
    # 🏪 BACK TO STORE
    # ==================================================

    if query.data == "slayer_store":

        # Get current coins
        await ensure_player(user)

        try:
            if USE_POSTGRES:
                cursor.execute(
                    """
                    SELECT points
                    FROM slayer_points
                    WHERE user_id = %s
                    AND is_bot = FALSE
                    """,
                    (user.id,)
                )
            else:
                cursor.execute(
                    """
                    SELECT points
                    FROM slayer_points
                    WHERE user_id = ?
                    AND is_bot = FALSE
                    """,
                    (user.id,)
                )

            row = cursor.fetchone()
            coins = row[0] if row else 0
            user_mention = (
                f'<a href="tg://user?id={user.id}">'
                f'{html.escape(user.first_name or "Hunter")}'
                f'</a>')
        except Exception:
            safe_db_rollback()
            coins = 0
            

        text = (
            "╭━━━〔 🏪 <b>𝗦𝗟𝗔𝗬𝗘𝗥 𝗦𝗧𝗢𝗥𝗘</b> 〕━━━╮\n"
            f"│ 👤 {user_mention}\n"
            f"│ 💎 <b>Your Coins:</b> {coins:,}\n"
            "│\n"
            "│ 🛍️ <b>Full Store:</b>\n"
            "│ View all items, prices & details\n"
            "│ in our Updates Channel.\n"
            "│\n"
            "╰──────────────────"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🛍️ Vɪᴇᴡ Fᴜʟʟ Sᴛᴏʀᴇ",
                    url=STORE_CHANNEL_LINK
                )
            ],
            [
                InlineKeyboardButton(
                    "🎒 Iɴᴠᴇɴᴛᴏʀʏ",
                    callback_data="slayer_inventory"
                ),
                InlineKeyboardButton(
                    "🎖️ Eǫᴜɪᴘ Bᴀᴅɢᴇ",
                    callback_data="slayer_equip_help"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return

# ============================================================
# /BUY
# ============================================================

async def buy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if getattr(
        update.message,
        "sender_chat",
        None
    ):

        await reject_anonymous_user(
            update
        )

        return

    user = update.effective_user

    if not user or user.is_bot:
        return

    if not context.args:

        await update.message.reply_text(
            "🛒 <b>Usage:</b>\n"
            "<code>/buy &lt;item id&gt;</code>\n\n"
            "Example: <code>/buy 4</code>",
            parse_mode=ParseMode.HTML
        )

        return

    try:
        item_id = int(
            context.args[0]
        )
    except ValueError:

        await update.message.reply_text(
            "⚠️ Invalid item ID.\n"
            "Use <code>/store</code> to view the available items.",
            parse_mode=ParseMode.HTML
        )

        return


    item = STORE_ITEMS.get(
        item_id
    )

    if not item:

        await update.message.reply_text(
            "❌ <b>Item not found.</b>\n\n"
            "Use <code>/store</code> to view available items.",
            parse_mode=ParseMode.HTML
        )

        return


    await ensure_player(user)


    new_spent = 0
    new_count = 0

    try:

        async with db_lock:

            # ----------------------------------------------
            # Get current balance
            # ----------------------------------------------

            cursor.execute("""
                SELECT points
                FROM slayer_points
                WHERE user_id = %s
                AND is_bot = FALSE
            """, (
                user.id,
            ))

            balance_row = cursor.fetchone()

            if not balance_row:
                db.rollback()
                return

            balance = (
                balance_row[0] or 0
            )

            price = item["price"]

            if balance < price:

                db.rollback()

                await update.message.reply_text(
                    "💎 <b>Not enough Slayer Points.</b>\n\n"
                    f"💰 Required: <b>{price:,}</b>\n"
                    f"💎 Available: <b>{balance:,}</b>\n"
                    f"📉 Missing: <b>{price - balance:,}</b>",
                    parse_mode=ParseMode.HTML
                )

                return


            # ----------------------------------------------
            # Deduct coins
            # ----------------------------------------------

            cursor.execute("""
                UPDATE slayer_points
                SET
                    points = points - %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                AND is_bot = FALSE
                AND points >= %s
            """, (
                price,
                user.id,
                price
            ))


            # ----------------------------------------------
            # Inventory
            # ----------------------------------------------

            cursor.execute("""
                INSERT INTO slayer_inventory
                (
                    user_id,
                    item_id,
                    quantity
                )
                VALUES (%s, %s, 1)

                ON CONFLICT (user_id, item_id)
                DO UPDATE SET
                    quantity =
                        slayer_inventory.quantity + 1
            """, (
                user.id,
                item_id
            ))


            # ----------------------------------------------
            # Store statistics
            # ----------------------------------------------

            cursor.execute("""
                INSERT INTO slayer_store_stats
                (
                    user_id,
                    total_spent,
                    purchase_count
                )
                VALUES (%s, %s, 1)

                ON CONFLICT (user_id)
                DO UPDATE SET
                    total_spent =
                        slayer_store_stats.total_spent + EXCLUDED.total_spent,

                    purchase_count =
                        slayer_store_stats.purchase_count + 1,

                    updated_at =
                        CURRENT_TIMESTAMP
            """, (
                user.id,
                price
            ))


            # ----------------------------------------------
            # Read updated store stats
            # ----------------------------------------------

            cursor.execute("""
                SELECT
                    total_spent,
                    purchase_count
                FROM slayer_store_stats
                WHERE user_id = %s
            """, (
                user.id,
            ))

            stats_row = cursor.fetchone()

            if stats_row:

                new_spent = (
                    stats_row[0] or 0
                )

                new_count = (
                    stats_row[1] or 0
                )


            db.commit()

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Purchase error: {e}"
        )

        await update.message.reply_text(
            "❌ Purchase failed.\n"
            "Your Slayer Points were not changed.",
            parse_mode=ParseMode.HTML
        )

        return


    # --------------------------------------------------------
    # Store achievements
    # --------------------------------------------------------

    new_achievements = (
        await check_store_achievements(
            user.id,
            new_count,
            new_spent
        )
    )


    achievement_text = ""

    if new_achievements:

        achievement_text = (
            "\n\n🏆 <b>NEW STORE ACHIEVEMENT!</b>\n"
            + "\n".join(
                f"✨ {html.escape(a)}"
                for a in new_achievements
            )
        )


    remaining = balance - item["price"]


    await update.message.reply_text(

        f"""
🛍️ <b>𝗣𝗨𝗥𝗖𝗛𝗔𝗦𝗘 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘!</b>

{item["emoji"]} <b>{html.escape(item["name"])}</b>
<i>{html.escape(item["description"])}</i>

💎 <b>Spent:</b> {item["price"]:,}
💰 <b>Remaining:</b> {remaining:,}

🎒 <b>Purchase Count:</b> {new_count}
💎 <b>Total Spent:</b> {new_spent:,}
{achievement_text}

<i>Your collection grows stronger. ⚔️</i>
""",

        parse_mode=ParseMode.HTML
    )


# ============================================================
# /INVENTORY
# ============================================================

async def inventory_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if getattr(
        update.message,
        "sender_chat",
        None
    ):

        await reject_anonymous_user(
            update
        )

        return

    user = update.effective_user

    if not user or user.is_bot:
        return

    await ensure_player(user)

    inventory = await get_inventory(
        user.id
    )

    total_spent, purchase_count = (
        await get_store_stats(
            user.id
        )
    )

    equipped_badge = (
        await get_equipped_badge(
            user.id
        )
    )


    if not inventory:

        await update.message.reply_text(
            "🎒 <b>𝗦𝗟𝗔𝗬𝗘𝗥 𝗜𝗡𝗩𝗘𝗡𝗧𝗢𝗥𝗬</b>\n\n"
            "Your collection is empty.\n\n"
            "Visit <code>/store</code> to begin collecting.",
            parse_mode=ParseMode.HTML
        )

        return


    lines = []

    for item_id, quantity in inventory:

        item = STORE_ITEMS.get(
            item_id
        )

        if not item:
            continue

        equipped = (
            "  ◈ <b>EQUIPPED</b>"
            if equipped_badge == item_id
            else ""
        )

        lines.append(
            f"{item['emoji']} "
            f"<b>{html.escape(item['name'])}</b>"
            f" ×{quantity}{equipped}\n"
            f"   <code>ID: {item_id}</code>"
        )


    await update.message.reply_text(

        f"""
╭━━〔 🎒 <b>𝗦𝗟𝗔𝗬𝗘𝗥 𝗜𝗡𝗩𝗘𝗡𝗧𝗢𝗥𝗬</b> 〕━━╮

👤 <b>Hunter:</b> {user.mention_html()}

"""
        + "\n\n".join(lines)
        + f"""

━━━━━━━━━━━━━━━━━━━━
🛍️ <b>Purchases:</b> {purchase_count}
💎 <b>Total Spent:</b> {total_spent:,}

🎖️ <b>Equip a badge:</b>
<code>/equipbadge &lt;item id&gt;</code>

╰━━━━━━━━━━━━━━━━━━━━╯
""",

        parse_mode=ParseMode.HTML
    )


# ============================================================
# /EQUIPBADGE
# ============================================================

async def equip_badge_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if getattr(
        update.message,
        "sender_chat",
        None
    ):

        await reject_anonymous_user(
            update
        )

        return

    user = update.effective_user

    if not user or user.is_bot:
        return

    if not context.args:

        await update.message.reply_text(
            "🎖️ <b>Usage:</b>\n"
            "<code>/equipbadge &lt;item id&gt;</code>\n\n"
            "Example: <code>/equipbadge 4</code>",
            parse_mode=ParseMode.HTML
        )

        return


    try:
        item_id = int(
            context.args[0]
        )
    except ValueError:

        await update.message.reply_text(
            "⚠️ Invalid badge ID.",
            parse_mode=ParseMode.HTML
        )

        return


    item = STORE_ITEMS.get(
        item_id
    )

    if not item:

        await update.message.reply_text(
            "❌ Item not found.",
            parse_mode=ParseMode.HTML
        )

        return


    if item["type"] != "badge":

        await update.message.reply_text(
            "⚠️ That item is not a profile badge.",
            parse_mode=ParseMode.HTML
        )

        return


    try:

        async with db_lock:

            cursor.execute("""
                SELECT quantity
                FROM slayer_inventory
                WHERE user_id = %s
                AND item_id = %s
            """, (
                user.id,
                item_id
            ))

            row = cursor.fetchone()

            if not row:

                await update.message.reply_text(
                    "🔒 <b>You don't own this badge.</b>\n\n"
                    "Purchase it from <code>/store</code> first.",
                    parse_mode=ParseMode.HTML
                )

                return


            cursor.execute("""
                INSERT INTO slayer_profile
                (
                    user_id,
                    equipped_badge
                )
                VALUES (%s, %s)

                ON CONFLICT (user_id)
                DO UPDATE SET
                    equipped_badge = EXCLUDED.equipped_badge,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                user.id,
                item_id
            ))

            db.commit()

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Equip badge error: {e}"
        )

        return


    await update.message.reply_text(

        f"""
🎖️ <b>𝗕𝗔𝗗𝗚𝗘 𝗘𝗤𝗨𝗜𝗣𝗣𝗘𝗗!</b>

{item["emoji"]} <b>{html.escape(item["name"])}</b>

Your new badge will now appear
on your Slayer Profile.

⚔️ <i>Wear your rank with pride.</i>
""",

        parse_mode=ParseMode.HTML
    )


# ============================================================
# GET ACHIEVEMENTS
# ============================================================

async def get_user_achievements(
    user_id
):

    try:

        async with db_lock:

            cursor.execute("""
                SELECT achievement
                FROM slayer_achievements
                WHERE user_id = %s
                ORDER BY earned_at DESC
            """, (
                user_id,
            ))

            rows = cursor.fetchall()

        return [
            row[0]
            for row in rows
        ]

    except Exception as e:

        print(
            f"❌ Achievement fetch error: {e}"
        )

        return []

# ============================================================
# GLOBAL RANK HELPER
# ============================================================

async def get_global_rank(user_id):
    """Return the player's global rank based on points, then wins."""

    try:
        async with db_lock:
            cursor.execute("""
                SELECT points, hunts_won
                FROM slayer_points
                WHERE user_id = %s
                AND is_bot = FALSE
            """, (
                user_id,
            ))

            player_row = cursor.fetchone()

            if not player_row:
                return None

            points = player_row[0] or 0
            wins = player_row[1] or 0

            cursor.execute("""
                SELECT COUNT(*)
                FROM slayer_points
                WHERE is_bot = FALSE
                AND (
                    points > %s
                    OR (
                        points = %s
                        AND hunts_won > %s
                    )
                )
            """, (
                points,
                points,
                wins,
            ))

            row = cursor.fetchone()

        return (row[0] if row else 0) + 1

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Global rank error: {e}"
        )

        return None


# ============================================================
# /BALANCE
# ============================================================

async def balance_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    # Anonymous/channel identity
    if getattr(
        update.message,
        "sender_chat",
        None
    ):
        await reject_anonymous_user(
            update
        )
        return

    # Default target = command sender
    user = update.effective_user

    if not user or user.is_bot:
        return

    # If replying to someone, show their balance
    if update.message.reply_to_message:
        replied_user = (
            update.message.reply_to_message.from_user
        )

        if not replied_user:
            return

        if replied_user.is_bot:
            await update.message.reply_text(
                "🤖 <i>Muichiro ignores bots.</i>",
                parse_mode=ParseMode.HTML
            )
            return

        user = replied_user

    await ensure_player(user)

    points = 0

    try:
        async with db_lock:
            cursor.execute("""
                SELECT points
                FROM slayer_points
                WHERE user_id = %s
                AND is_bot = FALSE
            """, (
                user.id,
            ))

            row = cursor.fetchone()

        if row:
            points = row[0] or 0

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Balance error: {e}"
        )
        return

    # --------------------------------------------------------
    # Global rank
    # --------------------------------------------------------

    global_rank = await get_global_rank(
        user.id
    )

    rank_text = (
        f"#{global_rank:,}"
        if global_rank is not None
        else "—"
    )

    # --------------------------------------------------------
    # Equipped badge
    # --------------------------------------------------------

    equipped_badge = await get_equipped_badge(
        user.id
    )

    badge_text = "None"

    if equipped_badge:
        badge = STORE_ITEMS.get(
            equipped_badge
        )

        if badge:
            badge_text = (
                f"{badge['emoji']} "
                f"{html.escape(badge['name'])}"
            )

    # --------------------------------------------------------
    # Achievement
    # --------------------------------------------------------

    achievements = await get_user_achievements(
        user.id
    )

    achievement = (
        achievements[0]
        if achievements
        else "🌱 New Recruit"
    )
    user_tag= get_user_html_tag(user)

    await update.message.reply_text(
        f"""
╭━━━〔 💎 <b>𝗦𝗟𝗔𝗬𝗘𝗥 𝗕𝗔𝗟𝗔𝗡𝗖𝗘</b> 〕━━━╮

👤 <b>User:</b> {user_tag}
💎 <b>Points:</b> {points:,}
🌍 <b>Global Rank:</b> {rank_text}

🏆 <b>Achievement:</b>
{html.escape(achievement)}

🎖️ <b>Equipped Badge:</b>
{badge_text}

╰━━━━━━━━━━━━━━━━━━━━╯

<i>Your progress at a glance. ⚔️</i>
""",
        parse_mode=ParseMode.HTML
    )




# ============================================================
# /PROFILE
# ============================================================

async def profile_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    # Anonymous/channel identity
    if getattr(
        update.message,
        "sender_chat",
        None
    ):

        await reject_anonymous_user(
            update
        )

        return

    user = update.effective_user

    if not user or user.is_bot:
        return

    # If replying to someone, show that user's profile.
    if update.message.reply_to_message:

        replied_user = (
            update.message.reply_to_message.from_user
        )

        if not replied_user:
            return

        if replied_user.is_bot:
            await update.message.reply_text(
                "🤖 <i>Muichiro ignores bots.</i>",
                parse_mode=ParseMode.HTML
            )
            return

        user = replied_user

    await ensure_player(user)

    points = 0
    wins = 0
    total_guesses = 0
    correct_guesses = 0
    streak = 0
    best_streak = 0
    global_rank = 0

    try:
        async with db_lock:
            cursor.execute("""
                SELECT
                    points,
                    hunts_won,
                    total_guesses,
                    correct_guesses,
                    win_streak,
                    best_streak
                FROM slayer_points
                WHERE user_id = %s
                AND is_bot = FALSE
            """, (
                user.id,
            ))

            row = cursor.fetchone()

            # Global rank is based on Slayer Points, with hunts won
            # used as the tie-breaker.
            cursor.execute("""
                SELECT COUNT(*)
                FROM slayer_points
                WHERE is_bot = FALSE
                AND (
                    points > %s
                    OR (
                        points = %s
                        AND hunts_won > %s
                    )
                )
            """, (
                points if row is None else row[0],
                points if row is None else row[0],
                wins if row is None else row[1],
            ))

            rank_row = cursor.fetchone()

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Profile stats error: {e}"
        )
        return

    if row:
        (
            points,
            wins,
            total_guesses,
            correct_guesses,
            streak,
            best_streak
        ) = row

    global_rank = (
        (rank_row[0] + 1)
        if rank_row
        else 1
    )

    accuracy = 0

    if total_guesses > 0:
        accuracy = round(
            (
                correct_guesses
                / total_guesses
            ) * 100,
            1
        )

    total_spent, purchase_count = (
        await get_store_stats(
            user.id
        )
    )

    inventory = await get_inventory(
        user.id
    )

    equipped_badge = (
        await get_equipped_badge(
            user.id
        )
    )

    badge_text = "None"

    if equipped_badge:
        badge = STORE_ITEMS.get(
            equipped_badge
        )

        if badge:
            badge_text = (
                f"{badge['emoji']} "
                f"{html.escape(badge['name'])}"
            )

    achievements = (
        await get_user_achievements(
            user.id
        )
    )

    achievement = (
        achievements[0]
        if achievements
        else "🌱 New Recruit"
    )

    collection_count = sum(
        quantity
        for _, quantity in inventory
    )

    achievement_lines = ""

    if achievements:
        shown = achievements[:5]

        achievement_lines = (
            "🏆 <b>Achievements:</b>\n"
            + "\n".join(
                f"• {html.escape(a)}"
                for a in shown
            )
        )

        if len(achievements) > 5:
            achievement_lines += (
                f"\n• +{len(achievements) - 5} more"
            )

    await update.message.reply_text(
        (
            "╭━━━〔 💎 <b>𝗦𝗟𝗔𝗬𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘</b> 〕━━━╮\n\n"
            + hunt_quote(
                "👤 <b>Hunter:</b>\n"
                + user.mention_html()
                + "\n\n"
                f"💎 <b>Slayer Points:</b> {points:,}\n"
                f"🌍 <b>Global Rank:</b> #{global_rank}\n"
                f"🏆 <b>Hunts Won:</b> {wins}\n"
                f"🎯 <b>Total Guesses:</b> {total_guesses}\n"
                f"📊 <b>Accuracy:</b> {accuracy}%\n\n"
                f"🔥 <b>Current Streak:</b> {streak}\n"
                f"⚡ <b>Best Streak:</b> {best_streak}\n\n"
                f"🏅 <b>Achievement Rank:</b> {html.escape(achievement)}\n"
                f"🎖️ <b>Equipped Badge:</b> {badge_text}\n\n"
                f"🛍️ <b>Store Purchases:</b> {purchase_count}\n"
                f"💰 <b>Total Spent:</b> {total_spent:,}\n"
                f"🎒 <b>Collection Items:</b> {collection_count}"
            )
            + ("\n\n" + achievement_lines if achievement_lines else "")
            + "\n\n╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "<i>Keep hunting. The Corps is watching... ⚔️</i>"
        ),
        parse_mode=ParseMode.HTML
    )


# ============================================================
# /TOP10
# ============================================================

async def top5_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    try:

        async with db_lock:

            cursor.execute("""
                SELECT
                    sp.user_id,
                    sp.username,
                    sp.full_name,
                    sp.points,
                    sp.hunts_won,
                    sl.equipped_badge
                FROM slayer_points sp
                LEFT JOIN slayer_profile sl
                    ON sp.user_id = sl.user_id
                WHERE is_bot = FALSE
                ORDER BY
                    sp.points DESC,
                    sp.hunts_won DESC
                LIMIT 5
            """)

            rows = cursor.fetchall()

    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Top05 error: {e}"
        )

        return


    if not rows:

        await update.message.reply_text(
            "🌙 <b>𝗡𝗢 𝗦𝗟𝗔𝗬𝗘𝗥𝗦 𝗛𝗔𝗩𝗘 "
            "𝗖𝗟𝗔𝗜𝗠𝗘𝗗 𝗣𝗢𝗜𝗡𝗧𝗦 𝗬𝗘𝗧!</b>\n\n"
            "Be the first hunter to rise. ⚔️",
            parse_mode=ParseMode.HTML
        )

        return


    medals = [
        "🥇",
        "🥈",
        "🥉",
        "4️⃣",
        "5️⃣",
        
    ]


    leaderboard = []


    for index, row in enumerate(rows):

        (
            user_id,
            username,
            full_name,
            points,
            wins, 
            equipped_badge
        ) = row


        name = (
            username
            if username
            else full_name
        )

        name = html.escape(
            name or "Unknown Slayer"
        )
        badge_text = "🏅 No Badge"
        if equipped_badge:
            badge = STORE_ITEMS.get(equipped_badge)
            if badge:
                badge_text = (
                    f"{badge['emoji']}"
                    f"{html.escape(badge['name'])}"
                
                )

        leaderboard.append(

            f"{medals[index]} <b>{name}</b>\n"
            f"      {badge_text}"
            f"     💎 {points:,}"
            f"• 🏆 {wins}"

        )


    await update.message.reply_text(

        """
🏆⚔️ <b>𝗗𝗘𝗠𝗢𝗡 𝗦𝗟𝗔𝗬𝗘𝗥 𝗖𝗢𝗥𝗣𝗦</b>
<b>━━━ 𝗚𝗟𝗢𝗕𝗔𝗟 𝗥𝗔𝗡𝗞𝗜𝗡𝗚𝗦 ━━━</b>

"""
        + "\n\n".join(
            leaderboard
        )
        + """

━━━━━━━━━━━━━━━━━━━━
🌍 Rankings are shared across
every group where Muichiro hunts.

<i>Hunt. Guess. Rise. ⚔️</i>
""",

        parse_mode=ParseMode.HTML
    )


# ============================================================
# /HUNTSTATS
# ============================================================

async def huntstats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if getattr(
        update.message,
        "sender_chat",
        None
    ):

        await reject_anonymous_user(
            update
        )

        return

    chat = update.effective_chat

    if not chat:
        return


    if chat.type not in [
        "group",
        "supergroup"
    ]:

        await update.message.reply_text(
            "⚠️ This command only works in groups."
        )

        return


    try:

        async with db_lock:

            cursor.execute("""
                SELECT
                    total_hunts,
                    total_guesses
                FROM demon_hunt_groups
                WHERE chat_id = %s
            """, (
                chat.id,
            ))

            group_row = cursor.fetchone()


            cursor.execute("""
                SELECT
                    winner_name,
                    COUNT(*) AS wins
                FROM demon_hunt_history
                WHERE chat_id = %s
                AND winner_id IS NOT NULL
                GROUP BY winner_name
                ORDER BY wins DESC
                LIMIT 1
            """, (
                chat.id,
            ))

            best_row = cursor.fetchone()


            cursor.execute("""
                SELECT character_name
                FROM demon_hunt_history
                WHERE chat_id = %s
                ORDER BY started_at DESC
                LIMIT 1
            """, (
                chat.id,
            ))

            last_row = cursor.fetchone()


    except Exception as e:

        try:
            db.rollback()
        except Exception:
            pass

        print(
            f"❌ Hunt stats error: {e}"
        )

        return


    total_hunts = (
        group_row[0]
        if group_row
        else 0
    )

    total_guesses = (
        group_row[1]
        if group_row
        else 0
    )


    best_hunter = (

        f"{html.escape(str(best_row[0]))} "
        f"({best_row[1]} wins)"

        if best_row
        else "No winner yet"
    )


    last_hunt = (

        html.escape(
            str(last_row[0])
        )

        if last_row
        else "No completed hunts"
    )


    await update.message.reply_text(

        (
            "⚔️ <b>𝗚𝗥𝗢𝗨𝗣 𝗛𝗨𝗡𝗧 𝗦𝗧𝗔𝗧𝗦</b>\n\n"
            + hunt_quote(
                f"🏹 <b>Total Hunts:</b> {total_hunts}\n"
                f"🎯 <b>Total Guesses:</b> {total_guesses}\n\n"
                f"👑 <b>Best Hunter:</b>\n{best_hunter}\n\n"
                f"🌙 <b>Last Mystery:</b>\n{last_hunt}"
            )
            + "\n\n<i>Will this group produce the next Legendary Slayer? ⚔️</i>"
        ),

        parse_mode=ParseMode.HTML
    )


# ============================================================
# /TESTHUNT
# ============================================================

async def testhunt_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if getattr(
        update.message,
        "sender_chat",
        None
    ):

        await reject_anonymous_user(
            update
        )

        return

    user = update.effective_user

    if user and user.is_bot:
        return

    chat = update.effective_chat

    if not chat:
        return

    if chat.type not in [
        "group",
        "supergroup"
    ]:

        await update.message.reply_text(
            "⚠️ This command can only be used in groups."
        )

        return


    if chat.id in ACTIVE_HUNTS:

        await update.message.reply_text(
            "⚔️ A Demon Hunt is already active!"
        )

        return


    await track_hunt_group(
        update,
        context
    )


    await update.message.reply_text(
        "⚔️ <b>TEST HUNT ACTIVATED...</b>\n\n"
        "🌙 Summoning a Demon Slayer mystery.",
        parse_mode=ParseMode.HTML
    )


    success = await start_demon_hunt(
        context.bot,
        chat.id
    )

    if not success:

        await update.message.reply_text(
            "❌ Could not start the test hunt."
        )


# ============================================================
# AUTOMATIC GROUP HUNT SCHEDULER
# ============================================================

async def group_hunt_loop(
    application,
    chat_id
):

    try:

        await asyncio.sleep(
            random.randint(10, 60)
        )

        while True:

            try:

                if chat_id in ACTIVE_HUNTS:

                    while chat_id in ACTIVE_HUNTS:

                        await asyncio.sleep(5)

                    continue


                wait_time = random.randint(
                    MIN_HUNT_INTERVAL,
                    MAX_HUNT_INTERVAL
                )


                print(
                    f"🌙 Hunt scheduled for "
                    f"{chat_id} in "
                    f"{wait_time // 60} minutes"
                )


                await asyncio.sleep(
                    wait_time
                )


                if chat_id in ACTIVE_HUNTS:
                    continue


                print(
                    f"⚔️ Starting automatic "
                    f"Demon Hunt in group "
                    f"{chat_id}"
                )


                success = await start_demon_hunt(
                    application.bot,
                    chat_id
                )


                if not success:

                    print(
                        f"⚠️ Automatic hunt "
                        f"could not start in "
                        f"{chat_id}"
                    )

                    await asyncio.sleep(
                        30
                    )

                    continue


                while chat_id in ACTIVE_HUNTS:

                    await asyncio.sleep(5)


                print(
                    f"✅ Hunt finished in "
                    f"{chat_id}. Scheduler continues."
                )


            except asyncio.CancelledError:

                raise


            except Exception as e:

                print(
                    f"❌ Hunt scheduler error "
                    f"for {chat_id}: {e}"
                )

                await asyncio.sleep(30)

    except asyncio.CancelledError:

        print(
            f"🛑 Hunt scheduler cancelled "
            f"for {chat_id}"
        )

        raise


# ============================================================
# ENSURE GROUP SCHEDULER
# ============================================================

def ensure_hunt_task(
    application,
    chat_id
):

    existing_task = (
        hunt_tasks.get(
            chat_id
        )
    )


    if existing_task:

        if not existing_task.done():
            return False

        hunt_tasks.pop(
            chat_id,
            None
        )


    task = asyncio.create_task(
        group_hunt_loop(
            application,
            chat_id
        )
    )


    hunt_tasks[chat_id] = task


    print(
        f"⚔️ Scheduler created "
        f"for group {chat_id}"
    )

    return True


# ============================================================
# MASTER HUNT SCHEDULER
# ============================================================

async def hunt_master_scheduler(
    application
):

    print(
        "🌙 Demon Hunt Master Scheduler started!"
    )


    while True:

        try:

            groups = (
                await get_registered_groups()
            )


            print(
                f"🔎 Hunt scheduler checking "
                f"{len(groups)} registered groups..."
            )


            for chat_id in groups:

                ensure_hunt_task(
                    application,
                    chat_id
                )


            dead_tasks = []


            for chat_id, task in list(
                hunt_tasks.items()
            ):

                if task.done():

                    dead_tasks.append(
                        chat_id
                    )


            for chat_id in dead_tasks:

                task = hunt_tasks.pop(
                    chat_id,
                    None
                )

                if task:

                    try:

                        task.result()

                    except asyncio.CancelledError:
                        pass

                    except Exception as e:

                        print(
                            f"⚠️ Scheduler task "
                            f"{chat_id} ended: {e}"
                        )


            await asyncio.sleep(60)


        except asyncio.CancelledError:

            print(
                "🛑 Demon Hunt Master Scheduler stopped."
            )

            break


        except Exception as e:

            print(
                f"❌ Master scheduler error: {e}"
            )

            await asyncio.sleep(30)


# ============================================================
# START HUNT SCHEDULERS
# ============================================================

# python-telegram-bot Application uses slots and does not allow arbitrary
# custom attributes. Keep the master scheduler task at module scope.
_hunt_master_task = None

async def start_hunt_schedulers(
    application
):

    await setup_hunt_database()


    global _hunt_master_task

    if _hunt_master_task is None or _hunt_master_task.done():
        _hunt_master_task = asyncio.create_task(
            hunt_master_scheduler(
                application
            )
        )


    groups = (
        await get_registered_groups()
    )


    for chat_id in groups:

        ensure_hunt_task(
            application,
            chat_id
        )


    print(
        f"⚔️ Demon Hunt Scheduler started "
        f"for {len(groups)} groups!"
    )


# ============================================================
# REGISTER NEW GROUP
# ============================================================

async def ensure_group_scheduler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await track_hunt_group(
        update,
        context
    )


    chat = update.effective_chat

    if not chat:
        return


    if chat.type not in [
        "group",
        "supergroup"
    ]:

        return


    ensure_hunt_task(
        context.application,
        chat.id
    )


# ============================================================
# CLEANUP MEMORY
# ============================================================

async def cleanup_hunt_memory():

    while True:

        try:

            now = time.time()

            expired = [

                chat_id

                for chat_id, expires_at
                in RECENTLY_ENDED.items()

                if expires_at < now

            ]


            for chat_id in expired:

                RECENTLY_ENDED.pop(
                    chat_id,
                    None
                )


            await asyncio.sleep(
                300
            )


        except asyncio.CancelledError:

            break

        except Exception as e:

            print(
                f"⚠️ Hunt cleanup error: {e}"
            )

            await asyncio.sleep(
                300
            )


# ============================================================
# INITIALIZE HUNT SYSTEM
# ============================================================

async def initialize_demon_hunt(
    application
):

    await setup_hunt_database()


    asyncio.create_task(
        cleanup_hunt_memory()
    )


    await start_hunt_schedulers(
        application
    )


    print(
        "⚔️ Demon Slayer Mystery Hunt initialized!"
    )


# ============================================================
# OWNER-ONLY GLOBAL HUNT LAUNCHER
# /startallhunts
# ============================================================

async def start_all_hunts_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if not update.effective_message:
        return

    user = update.effective_user


    if user.id != OWNER_ID:

        await update.effective_message.reply_text(
            "⛔ You don't have permission to use this command."
        )

        return


    if update.effective_chat.type != "private":

        await update.effective_message.reply_text(
            "⚠️ Use this command in my PM only."
        )

        return


    try:

        groups = (
            await get_registered_groups()
        )

    except Exception as e:

        print(
            f"❌ Failed to get registered groups: {e}"
        )

        await update.effective_message.reply_text(
            "❌ Couldn't load the registered groups."
        )

        return


    if not groups:

        await update.effective_message.reply_text(
            "⚠️ No registered groups found."
        )

        return


    started = 0
    already_active = 0
    failed = 0


    await update.effective_message.reply_text(

        "⚔️ <b>GLOBAL DEMON HUNT DEPLOYED</b>\n\n"
        f"🌙 Registered groups: <b>{len(groups)}</b>\n"
        "🔥 Launching hunts...",

        parse_mode=ParseMode.HTML
    )


    for chat_id in groups:

        if chat_id in ACTIVE_HUNTS:

            already_active += 1
            continue


        try:

            success = await start_demon_hunt(
                context.application.bot,
                chat_id
            )

            if success:
                started += 1
            else:
                failed += 1

        except Exception as e:

            failed += 1

            print(
                f"❌ Global hunt failed "
                f"for {chat_id}: {e}"
            )


    await update.effective_message.reply_text(

        "⚔️ <b>GLOBAL HUNT COMPLETE</b>\n\n"
        f"🔥 Hunts launched: <b>{started}</b>\n"
        f"⏭️ Already active: <b>{already_active}</b>\n"
        f"⚠️ Failed: <b>{failed}</b>\n\n"
        "🌙 <i>The Demon Hunt is now live across "
        "the registered realms!</i>",

        parse_mode=ParseMode.HTML
    )