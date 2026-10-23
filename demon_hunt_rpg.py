"""
Muichiro Demon Hunt RPG
=======================

A separate RPG system that coexists with the legacy character mystery-hunt system.
Uses its own tables and separate RPG coins; it never changes legacy Slayer Points.

Framework: python-telegram-bot v20+
Database: existing DATABASE_URL (PostgreSQL on Render) or database.db (SQLite locally).
Feature art: reuses the project's existing assets/start/start.jpeg and assets/demon_hunt portraits.
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ContextTypes

from database import DATABASE_URL, USE_POSTGRES

logger = logging.getLogger(__name__)
PREFIX = "rpg"

STANDARD_STYLES: Dict[str, Dict[str, Any]] = {
    "mist": {"name": "Mist Breathing", "emoji": "🌫️", "forms": ["Low Clouds", "Obscuring Mist", "Shifting Flow"], "image": "assets/demon_hunt/muichiro.jpeg", "power": 1.10},
    "water": {"name": "Water Breathing", "emoji": "🌊", "forms": ["Water Surface Slash", "Flowing Dance", "Ripple Thrust"], "image": "assets/demon_hunt/tanjiro.jpeg", "power": 1.00},
    "flame": {"name": "Flame Breathing", "emoji": "🔥", "forms": ["Unknowing Fire", "Rising Scorching Sun", "Flame Tiger"], "image": "assets/demon_hunt/rengoku.jpeg", "power": 1.12},
    "thunder": {"name": "Thunder Breathing", "emoji": "⚡", "forms": ["Thunderclap", "Sixfold Flash", "Godlike Speed"], "image": "assets/demon_hunt/zenitsu.jpeg", "power": 1.08},
    "wind": {"name": "Wind Breathing", "emoji": "🌪️", "forms": ["Dust Whirlwind", "Clean Storm Wind Tree", "Black Wind Mountain Mist"], "image": "assets/demon_hunt/sanemi.jpeg", "power": 1.07},
    "stone": {"name": "Stone Breathing", "emoji": "🪨", "forms": ["Serpentinite Bipolar", "Stone Skin", "Arcs of Justice"], "image": "assets/demon_hunt/gyomei.jpeg", "power": 1.13},
    "beast": {"name": "Beast Breathing", "emoji": "🐗", "forms": ["Pierce", "Slice", "Spatial Awareness"], "image": "assets/demon_hunt/inosuke.jpeg", "power": 1.04},
    "love": {"name": "Love Breathing", "emoji": "💗", "forms": ["Shivers of First Love", "Catlove Shower", "Swaying Love"], "image": "assets/demon_hunt/mitsuri.jpeg", "power": 1.06},
    "serpent": {"name": "Serpent Breathing", "emoji": "🐍", "forms": ["Winding Serpent", "Slithering Serpent", "Coil Choke"], "image": "assets/demon_hunt/obanai.jpeg", "power": 1.06},
    "sound": {"name": "Sound Breathing", "emoji": "🎵", "forms": ["Roar", "String Performance", "Resonant Slash"], "image": "assets/demon_hunt/tengen.jpeg", "power": 1.05},
    "flower": {"name": "Flower Breathing", "emoji": "🌸", "forms": ["Whirling Peach", "Honorable Shadow Plum", "Crimson Hanagoromo"], "image": "assets/demon_hunt/mitsuri.jpeg", "power": 1.03},
    "insect": {"name": "Insect Breathing", "emoji": "🦋", "forms": ["Butterfly Dance", "Dance of the Bee Sting", "Dance of the Dragonfly"], "image": "assets/demon_hunt/shinobu.jpeg", "power": 1.02},
}
LEGENDARY_STYLES = {"sun": {"name": "Sun Breathing", "emoji": "🌞", "power": 1.25}, "moon": {"name": "Moon Breathing", "emoji": "🌙", "power": 1.25}}
BOSSES = {
    "easy": {"name": "Rui", "rank": "Lower Rank", "hp": 700, "seconds": 900, "reward": 90, "exp": 35, "emoji": "🕸️"},
    "normal": {"name": "Enmu", "rank": "Lower Rank", "hp": 1600, "seconds": 1200, "reward": 180, "exp": 75, "emoji": "🌙"},
    "hard": {"name": "Akaza", "rank": "Upper Rank", "hp": 3200, "seconds": 1800, "reward": 350, "exp": 150, "emoji": "🥊"},
    "upper": {"name": "Doma", "rank": "Upper Rank", "hp": 5600, "seconds": 2400, "reward": 650, "exp": 260, "emoji": "❄️"},
    "final": {"name": "Muzan Kibutsuji", "rank": "Final Boss", "hp": 10000, "seconds": 3600, "reward": 1200, "exp": 500, "emoji": "🩸"},
}
STORE = {
    "potion": {"name": "Healing Potion", "price": 80, "emoji": "🧪", "description": "A one-use battle tonic; currently grants a small bonus to your next attack."},
    "whetstone": {"name": "Nichirin Whetstone", "price": 160, "emoji": "🪨", "description": "A training material for future equipment upgrades."},
    "armor": {"name": "Slayer Armor", "price": 400, "emoji": "🛡️", "description": "Protective Corps gear; grants a small attack bonus."},
    "katana": {"name": "Nichirin Katana", "price": 650, "emoji": "⚔️", "description": "A quality blade; grants a small attack bonus."},
    "charm": {"name": "Wisteria Charm", "price": 250, "emoji": "🪻", "description": "A collectible charm kept in your inventory."},
}
STYLE_KEYS = ", ".join(STANDARD_STYLES)


@contextmanager
def _db(immediate: bool = False):
    """Use an isolated connection so this feature does not share bot.py's global cursor."""
    if USE_POSTGRES:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect("database.db", timeout=15)
        conn.row_factory = sqlite3.Row
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.cursor()
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_dict(cursor, row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        return dict(row)
    return dict(zip([c[0] for c in cursor.description], row))


def setup_rpg_database() -> None:
    """Create only RPG-specific tables; legacy hunt tables are untouched."""
    with _db() as (_, cur):
        cur.execute("""CREATE TABLE IF NOT EXISTS rpg_profiles (
            user_id BIGINT PRIMARY KEY, username TEXT, full_name TEXT,
            style TEXT, style_finalized INTEGER DEFAULT 0, correction_used INTEGER DEFAULT 0,
            exp BIGINT DEFAULT 0, corps_rank TEXT DEFAULT 'Mizunoto',
            coins BIGINT DEFAULT 0, victories INTEGER DEFAULT 0, personal_defeats INTEGER DEFAULT 0,
            sun_defeats INTEGER DEFAULT 0, moon_defeats INTEGER DEFAULT 0,
            legendary_path TEXT DEFAULT '',
            next_attack_bonus INTEGER DEFAULT 0, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        if USE_POSTGRES:
            cur.execute("ALTER TABLE rpg_profiles ADD COLUMN IF NOT EXISTS legendary_path TEXT DEFAULT ''")
        else:
            cur.execute("PRAGMA table_info(rpg_profiles)")
            columns = {row[1] for row in cur.fetchall()}
            if "legendary_path" not in columns:
                cur.execute("ALTER TABLE rpg_profiles ADD COLUMN legendary_path TEXT DEFAULT ''")
        cur.execute("""CREATE TABLE IF NOT EXISTS rpg_style_unlocks (
            user_id BIGINT NOT NULL, style TEXT NOT NULL,
            PRIMARY KEY(user_id, style)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS rpg_raids (
            raid_id TEXT PRIMARY KEY, chat_id BIGINT NOT NULL, boss_key TEXT NOT NULL,
            boss_name TEXT NOT NULL, boss_rank TEXT NOT NULL, hp BIGINT NOT NULL,
            max_hp BIGINT NOT NULL, deadline BIGINT NOT NULL, status TEXT NOT NULL,
            message_id BIGINT, created_by BIGINT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS rpg_contributions (
            raid_id TEXT NOT NULL, user_id BIGINT NOT NULL, damage BIGINT DEFAULT 0,
            actions INTEGER DEFAULT 0, last_action BIGINT DEFAULT 0,
            PRIMARY KEY(raid_id, user_id)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS rpg_inventory (
            user_id BIGINT NOT NULL, item_key TEXT NOT NULL, quantity INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, item_key)
        )""")
        cur.execute("""CREATE INDEX IF NOT EXISTS rpg_raids_chat_status_idx ON rpg_raids(chat_id, status)""")
        cur.execute("""CREATE INDEX IF NOT EXISTS rpg_contributions_user_idx ON rpg_contributions(user_id)""")


def _ensure_profile(user, conn_cur=None):
    if user is None:
        return
    with _db() as (_, cur):
        if USE_POSTGRES:
            cur.execute("""INSERT INTO rpg_profiles(user_id, username, full_name)
                VALUES(%s, %s, %s) ON CONFLICT(user_id) DO UPDATE SET
                username=EXCLUDED.username, full_name=EXCLUDED.full_name, updated_at=CURRENT_TIMESTAMP""",
                (user.id, user.username or "", user.full_name or user.first_name or "Slayer"))
        else:
            cur.execute("""INSERT INTO rpg_profiles(user_id, username, full_name)
                VALUES(?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username, full_name=excluded.full_name, updated_at=CURRENT_TIMESTAMP""",
                (user.id, user.username or "", user.full_name or user.first_name or "Slayer"))


def _get_profile(user_id: int) -> Optional[Dict[str, Any]]:
    with _db() as (_, cur):
        cur.execute("SELECT * FROM rpg_profiles WHERE user_id = " + ("%s" if USE_POSTGRES else "?"), (user_id,))
        return _row_dict(cur, cur.fetchone())


def _expire_raid(cur, raid_id: str) -> bool:
    ph = "%s" if USE_POSTGRES else "?"
    now = int(time.time())
    cur.execute(
        "UPDATE rpg_raids SET status='failed' WHERE raid_id=" + ph + " AND status='active' AND deadline <= " + ph,
        (raid_id, now),
    )
    if cur.rowcount:
        coin_floor = "GREATEST(0, coins-10)" if USE_POSTGRES else "MAX(0, coins-10)"
        cur.execute(
            f"UPDATE rpg_profiles SET coins={coin_floor} WHERE user_id IN "
            f"(SELECT user_id FROM rpg_contributions WHERE raid_id={ph} AND damage>0)",
            (raid_id,),
        )
        return True
    return False


def _get_raid(raid_id: str) -> Optional[Dict[str, Any]]:
    with _db() as (_, cur):
        ph = "%s" if USE_POSTGRES else "?"
        cur.execute("SELECT * FROM rpg_raids WHERE raid_id = " + ph, (raid_id,))
        raid = _row_dict(cur, cur.fetchone())
        if raid and raid.get("status") == "active" and int(raid.get("deadline") or 0) <= int(time.time()):
            _expire_raid(cur, raid_id)
            raid["status"] = "failed"
        return raid


def _active_raid(chat_id: int) -> Optional[Dict[str, Any]]:
    with _db() as (_, cur):
        ph = "%s" if USE_POSTGRES else "?"
        now = int(time.time())
        cur.execute("SELECT raid_id FROM rpg_raids WHERE chat_id=" + ph + " AND status='active' AND deadline <= " + ph, (chat_id, now))
        expired = [row[0] for row in cur.fetchall()]
        for raid_id in expired:
            _expire_raid(cur, raid_id)
        cur.execute("SELECT * FROM rpg_raids WHERE chat_id = " + ph + " AND status='active' ORDER BY created_at DESC", (chat_id,))
        return _row_dict(cur, cur.fetchone())


def _upsert_contribution(cur, raid_id: str, user_id: int, damage: int, now: int) -> None:
    if USE_POSTGRES:
        cur.execute("""INSERT INTO rpg_contributions(raid_id,user_id,damage,actions,last_action)
            VALUES(%s,%s,%s,1,%s) ON CONFLICT(raid_id,user_id) DO UPDATE SET
            damage=rpg_contributions.damage+EXCLUDED.damage,
            actions=rpg_contributions.actions+1,last_action=EXCLUDED.last_action""",
            (raid_id, user_id, damage, now))
    else:
        cur.execute("""INSERT INTO rpg_contributions(raid_id,user_id,damage,actions,last_action)
            VALUES(?,?,?,1,?) ON CONFLICT(raid_id,user_id) DO UPDATE SET
            damage=damage+excluded.damage,actions=actions+1,last_action=excluded.last_action""",
            (raid_id, user_id, damage, now))


def _profile_keyboard(user_id: int, profile: Dict[str, Any]) -> InlineKeyboardMarkup:
    style = profile.get("style")
    rows = [
        [InlineKeyboardButton("⚔️ Open Personal Battle Panel", callback_data=f"{PREFIX}:panel:{user_id}")],
        [InlineKeyboardButton("🌬️ Change / Choose Style", callback_data=f"{PREFIX}:styles:{user_id}")],
    ]
    if style and not profile.get("correction_used"):
        rows.append([InlineKeyboardButton("🔄 Use Free Correction", callback_data=f"{PREFIX}:correction:{user_id}")])
    return InlineKeyboardMarkup(rows)


def _style_keyboard(user_id: int, correction: bool = False) -> InlineKeyboardMarkup:
    rows, row = [], []
    for key, item in STANDARD_STYLES.items():
        row.append(InlineKeyboardButton(f"{item['emoji']} {item['name']}", callback_data=f"{PREFIX}:{'correct' if correction else 'style'}:{user_id}:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Cancel", callback_data=f"{PREFIX}:panel:{user_id}")])
    return InlineKeyboardMarkup(rows)


def _battle_keyboard(raid_id: str, user_id: int, style: str) -> InlineKeyboardMarkup:
    st = STANDARD_STYLES.get(style, LEGENDARY_STYLES.get(style, STANDARD_STYLES["water"]))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{st['emoji']} Quick Attack", callback_data=f"{PREFIX}:act:{raid_id}:{user_id}:attack"),
         InlineKeyboardButton("🛡️ Defend", callback_data=f"{PREFIX}:act:{raid_id}:{user_id}:defend")],
        [InlineKeyboardButton("🌟 Breathing Form", callback_data=f"{PREFIX}:act:{raid_id}:{user_id}:form"),
         InlineKeyboardButton("💥 Ultimate", callback_data=f"{PREFIX}:act:{raid_id}:{user_id}:ultimate")],
        [InlineKeyboardButton("📊 Raid Status", callback_data=f"{PREFIX}:status:{raid_id}:{user_id}"),
         InlineKeyboardButton("🎒 Inventory", callback_data=f"{PREFIX}:inventory:{user_id}")],
    ])


def _raid_keyboard(raid_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Join Raid / Get My Controls", callback_data=f"{PREFIX}:join:{raid_id}")],
        [InlineKeyboardButton("📊 Refresh Raid Status", callback_data=f"{PREFIX}:status:{raid_id}:0")],
    ])


def _raid_text(raid: Dict[str, Any]) -> str:
    hp = max(0, int(raid["hp"]))
    max_hp = int(raid["max_hp"])
    ratio = hp / max_hp if max_hp else 0
    filled = max(0, min(12, round(ratio * 12)))
    bar = "🟥" * filled + "⬛" * (12 - filled)
    remaining = max(0, int(raid["deadline"]) - int(time.time()))
    mins, secs = divmod(remaining, 60)
    return (
        f"⚔️ <b>MUICHIRO • DEMON RAID</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{BOSSES.get(raid['boss_key'], {}).get('emoji', '👹')} <b>{html.escape(raid['boss_name'])}</b>\n"
        f"🏷 Rank: <b>{html.escape(raid['boss_rank'])}</b>\n"
        f"❤️ HP: <b>{hp:,}/{max_hp:,}</b>\n{bar}\n"
        f"⏳ Time remaining: <b>{mins:02d}:{secs:02d}</b>\n"
        f"📌 Status: <b>{html.escape(raid['status'].upper())}</b>\n\n"
        f"Tap <b>Join Raid</b> to receive your personal breathing-style battle panel.\n"
        f"<i>RPG coins and EXP are separate from the existing Slayer Points.</i>"
    )


def _boss_art_path(boss_key: str) -> str:
    """Return the dedicated portrait for this raid boss, with safe legacy fallbacks."""
    boss_images = {
        "easy": "rui.jpg",
        "normal": "enmu.jpg",
        "hard": "akaza.jpg",
        "upper": "doma.jpg",
        "final": "muzan.jpg",
    }
    candidates = [
        os.path.join("assets", "demon_hunt", "bosses", boss_images.get(boss_key, "")),
        os.path.join("assets", "start", "start.jpeg"),
        os.path.join("assets", "demon_hunt", "muichiro.jpeg"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return ""


async def _send_raid_card(context, chat_id: int, raid: Dict[str, Any], edit_message_id: Optional[int] = None):
    text = _raid_text(raid)
    if edit_message_id:
        try:
            await context.bot.edit_message_caption(chat_id=chat_id, message_id=edit_message_id, caption=text,
                                                   parse_mode=ParseMode.HTML, reply_markup=_raid_keyboard(raid["raid_id"]))
            return edit_message_id
        except TelegramError:
            pass
    art = _boss_art_path(raid["boss_key"])
    if art:
        with open(art, "rb") as photo:
            msg = await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=text,
                                               parse_mode=ParseMode.HTML, reply_markup=_raid_keyboard(raid["raid_id"]))
    else:
        msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                                             reply_markup=_raid_keyboard(raid["raid_id"]))
    with _db() as (_, cur):
        cur.execute("UPDATE rpg_raids SET message_id = " + ("%s" if USE_POSTGRES else "?") + " WHERE raid_id = " + ("%s" if USE_POSTGRES else "?"),
                    (msg.message_id, raid["raid_id"]))
    raid["message_id"] = msg.message_id
    return msg.message_id


async def _send_personal_panel(context, user_id: int, raid: Dict[str, Any]):
    profile = _get_profile(user_id)
    if not profile or not profile.get("style"):
        await context.bot.send_message(
            chat_id=user_id,
            text="🌬️ First choose your breathing style. All standard styles are available for your first choice.",
            reply_markup=_style_keyboard(user_id),
        )
        return
    style = profile["style"]
    st = STANDARD_STYLES.get(style, LEGENDARY_STYLES.get(style, STANDARD_STYLES["water"]))
    form_list = st.get("forms", ["Solar Slash", "Moonlit Arc", "Final Form"])
    text = (
        f"{st['emoji']} <b>{html.escape(st['name'])} • PERSONAL BATTLE PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👹 Target: <b>{html.escape(raid['boss_name'])}</b>\n"
        f"❤️ Demon HP: <b>{max(0, int(raid['hp'])):,}/{int(raid['max_hp']):,}</b>\n"
        f"🌬 Your forms: <b>{html.escape(' • '.join(form_list))}</b>\n\n"
        f"Choose an action. Each action is validated against the active raid and your Telegram ID."
    )
    art = _boss_art_path(raid["boss_key"])
    if not art:
        art = st.get("image", "")
    if art and os.path.isfile(art):
        with open(art, "rb") as photo:
            await context.bot.send_photo(chat_id=user_id, photo=photo, caption=text, parse_mode=ParseMode.HTML,
                                         reply_markup=_battle_keyboard(raid["raid_id"], user_id, style))
    else:
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML,
                                       reply_markup=_battle_keyboard(raid["raid_id"], user_id, style))


async def _notify_raid_failure(application, raid: Dict[str, Any]) -> None:
    if raid.get("message_id"):
        try:
            await application.bot.edit_message_caption(
                chat_id=raid["chat_id"], message_id=raid["message_id"],
                caption=_raid_text(raid), parse_mode=ParseMode.HTML, reply_markup=None,
            )
        except TelegramError:
            try:
                await application.bot.edit_message_text(
                    chat_id=raid["chat_id"], message_id=raid["message_id"],
                    text=_raid_text(raid), parse_mode=ParseMode.HTML, reply_markup=None,
                )
            except TelegramError:
                pass
    try:
        await application.bot.send_message(
            chat_id=raid["chat_id"],
            text=f"⏳ <b>Raid failed!</b> {html.escape(raid['boss_name'])} survived until the deadline. No victory rewards were granted; participating attackers lost 10 RPG coins.",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        logger.warning("Could not announce failed RPG raid %s", raid["raid_id"])


async def _raid_timeout_watcher(application, raid_id: str, deadline: int) -> None:
    try:
        await asyncio.sleep(max(0, int(deadline) - int(time.time())))
        raid = _get_raid(raid_id)
        if raid and raid.get("status") == "failed" and int(raid.get("deadline") or 0) <= int(time.time()):
            await _notify_raid_failure(application, raid)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("RPG raid timeout watcher failed for %s", raid_id)


def start_rpg_raid_watchers(application) -> None:
    """Restore timeout watchers for active raids after Render restarts."""
    with _db() as (_, cur):
        cur.execute("SELECT raid_id, deadline FROM rpg_raids WHERE status='active'")
        raids = cur.fetchall()
    for raid_id, deadline in raids:
        application.create_task(_raid_timeout_watcher(application, raid_id, int(deadline)))


async def launch_hunt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user:
        return
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await msg.reply_text("⚔️ Launch a group raid inside the group you want to play in.")
        return
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("administrator", "creator"):
            await msg.reply_text("Only group admins can launch a demon raid.")
            return
    except TelegramError:
        await msg.reply_text("I couldn't verify your admin status. Please try again.")
        return
    difficulty = (context.args[0].lower() if context.args else "normal")
    if difficulty not in BOSSES:
        await msg.reply_text("Usage: /launchhunt easy|normal|hard|upper|final")
        return
    existing = _active_raid(chat.id)
    if existing:
        await msg.reply_text(f"There's already an active raid against {existing['boss_name']}. Finish it before launching another.")
        return
    boss = BOSSES[difficulty]
    raid_id = uuid.uuid4().hex[:8]
    now = int(time.time())
    raid = {
        "raid_id": raid_id, "chat_id": chat.id, "boss_key": difficulty,
        "boss_name": boss["name"], "boss_rank": boss["rank"], "hp": boss["hp"],
        "max_hp": boss["hp"], "deadline": now + boss["seconds"], "status": "active",
        "message_id": None, "created_by": user.id,
    }
    with _db() as (_, cur):
        cur.execute("""INSERT INTO rpg_raids(raid_id,chat_id,boss_key,boss_name,boss_rank,hp,max_hp,deadline,status,created_by)
            VALUES(""" + (", ".join(["%s"] * 10) if USE_POSTGRES else ", ".join(["?"] * 10)) + ")",
            (raid_id, chat.id, difficulty, boss["name"], boss["rank"], boss["hp"], boss["hp"], raid["deadline"], "active", user.id))
    await _send_raid_card(context, chat.id, raid)
    context.application.create_task(_raid_timeout_watcher(context.application, raid_id, int(raid["deadline"])))


async def raid_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return
    raid = _active_raid(chat.id) if chat.type != ChatType.PRIVATE else None
    if context.args:
        raid = _get_raid(context.args[0])
    if not raid:
        await msg.reply_text("No active raid found here. An admin can start one with /launchhunt normal.")
        return
    await msg.reply_text(_raid_text(raid), parse_mode=ParseMode.HTML, reply_markup=_raid_keyboard(raid["raid_id"]))


async def breathing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    _ensure_profile(user)
    profile = _get_profile(user.id)
    if profile and profile.get("style"):
        text = (f"🌬️ Current style: <b>{html.escape(STANDARD_STYLES.get(profile['style'], LEGENDARY_STYLES.get(profile['style'], {'name': profile['style']}))['name'])}</b>\n"
                f"Free correction: <b>{'used' if profile.get('correction_used') else 'available'}</b>\n\n"
                "To unlock another standard style, use /rpgtrain <style>. Use /legendary sun or /legendary moon after 100 personal demon defeats.")
        keyboard = _profile_keyboard(user.id, profile)
        if msg.chat.type == ChatType.PRIVATE:
            await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        else:
            try:
                await context.bot.send_message(user.id, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                await msg.reply_text("📩 Check your private chat for your personal breathing-style controls.")
            except (Forbidden, TelegramError):
                await msg.reply_text("Open my private chat and press Start first, then use /breathing again.")
    else:
        try:
            await context.bot.send_message(user.id, "🌬️ Choose your starting breathing style:", reply_markup=_style_keyboard(user.id))
            if msg.chat.type != ChatType.PRIVATE:
                await msg.reply_text("📩 I sent the breathing-style picker to your private chat.")
        except (Forbidden, TelegramError):
            await msg.reply_text("Open my private chat and press Start first, then use /breathing again.")


async def rpg_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    _ensure_profile(user)
    p = _get_profile(user.id)
    if not p:
        await msg.reply_text("Profile is being initialized. Try again.")
        return
    style = p.get("style")
    style_name = STANDARD_STYLES.get(style, LEGENDARY_STYLES.get(style, {"name": "Not chosen"}))["name"] if style else "Not chosen"
    text = (
        f"🗡️ <b>SLAYER PROFILE</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"👤 {html.escape(p.get('full_name') or user.full_name)}\n"
        f"🌬 Style: <b>{html.escape(style_name)}</b>\n"
        f"🏯 Corps Rank: <b>{html.escape(p.get('corps_rank') or 'Mizunoto')}</b>\n"
        f"✨ EXP: <b>{int(p.get('exp') or 0):,}</b>\n"
        f"🪙 RPG Coins: <b>{int(p.get('coins') or 0):,}</b>\n"
        f"🏆 Raid victories: <b>{int(p.get('victories') or 0)}</b>\n"
        f"👹 Personal demon defeats: <b>{int(p.get('personal_defeats') or 0)}</b>\n"
        f"🌞 Sun path defeats: <b>{int(p.get('sun_defeats') or 0)}/100</b>\n"
        f"🌙 Moon path defeats: <b>{int(p.get('moon_defeats') or 0)}/100</b>"
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=_profile_keyboard(user.id, p))


async def rpg_store_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    _ensure_profile(user)
    p = _get_profile(user.id)
    lines = ["🛒 <b>DEMON SLAYER RPG STORE</b>", f"Your RPG coins: <b>{int(p.get('coins') or 0):,}</b>", ""]
    rows = []
    for key, item in STORE.items():
        lines.append(f"{item['emoji']} <b>{html.escape(item['name'])}</b> — {item['price']} coins\n<code>/rpgbuy {key}</code> — {html.escape(item['description'])}")
        rows.append([InlineKeyboardButton(f"{item['emoji']} {item['name']} · {item['price']}", callback_data=f"{PREFIX}:buy:{key}")])
    await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows))


async def rpg_buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    if not context.args:
        await rpg_store_command(update, context)
        return
    await _buy_item(user.id, context.args[0].lower(), msg)


async def _buy_item(user_id: int, key: str, message=None, query=None):
    if key not in STORE:
        response = "Unknown item. Use /rpgstore to see available items."
        if query:
            await query.answer(response, show_alert=True)
        elif message:
            await message.reply_text(response)
        return
    with _db() as (_, cur):
        ph = "%s" if USE_POSTGRES else "?"
        cur.execute(f"SELECT coins FROM rpg_profiles WHERE user_id={ph}", (user_id,))
        row = cur.fetchone()
        if not row:
            response = "Use /breathing first to create your RPG profile."
            if query: await query.answer(response, show_alert=True)
            elif message: await message.reply_text(response)
            return
        coins = row[0] if not hasattr(row, "keys") else row["coins"]
        item = STORE[key]
        if int(coins or 0) < item["price"]:
            response = f"You need {item['price'] - int(coins or 0)} more RPG coins."
            if query: await query.answer(response, show_alert=True)
            elif message: await message.reply_text(response)
            return
        cur.execute(f"UPDATE rpg_profiles SET coins=coins-{ph}, updated_at=CURRENT_TIMESTAMP WHERE user_id={ph}",
                    (item["price"], user_id))
        if USE_POSTGRES:
            cur.execute("""INSERT INTO rpg_inventory(user_id,item_key,quantity) VALUES(%s,%s,1)
                ON CONFLICT(user_id,item_key) DO UPDATE SET quantity=rpg_inventory.quantity+1""", (user_id, key))
        else:
            cur.execute("""INSERT INTO rpg_inventory(user_id,item_key,quantity) VALUES(?,?,1)
                ON CONFLICT(user_id,item_key) DO UPDATE SET quantity=quantity+1""", (user_id, key))
    response = f"✅ Purchased {STORE[key]['emoji']} {STORE[key]['name']} for {STORE[key]['price']} RPG coins."
    if query: await query.answer(response, show_alert=True)
    elif message: await message.reply_text(response)


async def rpg_inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    with _db() as (_, cur):
        cur.execute("SELECT item_key, quantity FROM rpg_inventory WHERE user_id = " + ("%s" if USE_POSTGRES else "?"), (user.id,))
        rows = cur.fetchall()
    if not rows:
        await msg.reply_text("🎒 Your RPG inventory is empty. Use /rpgstore to browse items.")
        return
    lines = ["🎒 <b>YOUR RPG INVENTORY</b>"]
    for row in rows:
        key, qty = row[0], row[1]
        item = STORE.get(key, {"emoji": "📦", "name": key})
        lines.append(f"{item['emoji']} {html.escape(item['name'])} × <b>{qty}</b>")
    await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def rpg_use_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    key = context.args[0].lower() if context.args else ""
    if key != "potion":
        await msg.reply_text("Usage: /rpguse potion")
        return
    with _db() as (_, cur):
        ph = "%s" if USE_POSTGRES else "?"
        cur.execute(f"SELECT quantity FROM rpg_inventory WHERE user_id={ph} AND item_key={ph}", (user.id, key))
        row = cur.fetchone()
        if not row or int(row[0]) <= 0:
            await msg.reply_text("You don't have a Healing Potion. Buy one with /rpgbuy potion.")
            return
        cur.execute(f"UPDATE rpg_inventory SET quantity=quantity-1 WHERE user_id={ph} AND item_key={ph}", (user.id, key))
        cur.execute(f"UPDATE rpg_profiles SET next_attack_bonus=next_attack_bonus+80 WHERE user_id={ph}", (user.id,))
    await msg.reply_text("🧪 Potion used! Your next RPG attack receives +80 damage.")


def _user_in_active_raid(user_id: int) -> bool:
    ph = "%s" if USE_POSTGRES else "?"
    with _db() as (_, cur):
        cur.execute(
            f"SELECT 1 FROM rpg_contributions c JOIN rpg_raids r ON r.raid_id=c.raid_id "
            f"WHERE c.user_id={ph} AND r.status='active' AND r.deadline>{ph} LIMIT 1",
            (user_id, int(time.time())),
        )
        return cur.fetchone() is not None


async def rpg_train_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    key = context.args[0].lower() if context.args else ""
    if key not in STANDARD_STYLES:
        await msg.reply_text("Usage: /rpgtrain <style>\nAvailable: " + STYLE_KEYS)
        return
    if _user_in_active_raid(user.id):
        await msg.reply_text("You cannot change or train a breathing style during an active raid.")
        return
    _ensure_profile(user)
    p = _get_profile(user.id)
    if not p or not p.get("style_finalized"):
        await msg.reply_text("Choose your first style with /breathing before training another.")
        return
    if key == p.get("style"):
        await msg.reply_text("You already have this style equipped.")
        return
    ph = "%s" if USE_POSTGRES else "?"
    with _db() as (_, cur):
        cur.execute(f"SELECT 1 FROM rpg_style_unlocks WHERE user_id={ph} AND style={ph}", (user.id, key))
        unlocked = cur.fetchone()
        if unlocked:
            cur.execute(f"UPDATE rpg_profiles SET style={ph}, updated_at=CURRENT_TIMESTAMP WHERE user_id={ph}", (key, user.id))
            result = "equipped"
        else:
            if int(p.get("coins") or 0) < 100 or int(p.get("exp") or 0) < 100:
                result = "insufficient"
            else:
                cur.execute(f"UPDATE rpg_profiles SET coins=coins-100, exp=exp-100, style={ph}, updated_at=CURRENT_TIMESTAMP WHERE user_id={ph}", (key, user.id))
                cur.execute(f"INSERT INTO rpg_style_unlocks(user_id,style) VALUES({ph},{ph})", (user.id, key))
                result = "unlocked"
    if result == "insufficient":
        await msg.reply_text("Training costs 100 RPG coins and 100 EXP. Earn them in raids first.")
    else:
        await msg.reply_text(f"🌬️ {STANDARD_STYLES[key]['emoji']} {STANDARD_STYLES[key]['name']} is now equipped.")


async def legendary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    key = context.args[0].lower() if context.args else ""
    if key not in LEGENDARY_STYLES:
        await msg.reply_text("Usage: /legendary sun or /legendary moon\\nChoose a path; its separate counter requires 100 personal raid defeats.")
        return
    _ensure_profile(user)
    p = _get_profile(user.id)
    field = "sun_defeats" if key == "sun" else "moon_defeats"
    count = int(p.get(field) or 0)
    if count >= 100:
        if _user_in_active_raid(user.id):
            await msg.reply_text("You cannot change your breathing style during an active raid.")
            return
        with _db() as (_, cur):
            cur.execute("UPDATE rpg_profiles SET style = " + ("%s" if USE_POSTGRES else "?") + " WHERE user_id = " + ("%s" if USE_POSTGRES else "?"), (key, user.id))
        await msg.reply_text(f"🌟 Legendary path unlocked and equipped: {LEGENDARY_STYLES[key]['emoji']} {LEGENDARY_STYLES[key]['name']}!")
        return
    with _db() as (_, cur):
        cur.execute("UPDATE rpg_profiles SET legendary_path = " + ("%s" if USE_POSTGRES else "?") + " WHERE user_id = " + ("%s" if USE_POSTGRES else "?"), (key, user.id))
    await msg.reply_text(
        f"{LEGENDARY_STYLES[key]['emoji']} <b>{LEGENDARY_STYLES[key]['name']} path selected.</b>\\n"
        f"Progress: <b>{count}/100</b> personal demon defeats on this path.\\n"
        "Eligible victories in group raids will advance only the path you selected. Your other legendary path keeps its own progress.",
        parse_mode=ParseMode.HTML,
    )

async def rpg_leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    with _db() as (_, cur):
        cur.execute("SELECT full_name, exp, victories, personal_defeats, coins FROM rpg_profiles ORDER BY victories DESC, exp DESC LIMIT 10")
        rows = cur.fetchall()
    if not rows:
        await msg.reply_text("No Slayers on the RPG leaderboard yet. Start with /breathing.")
        return
    lines = ["🏆 <b>MUICHIRO RPG LEADERBOARD</b>"]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. {html.escape(str(row[0] or 'Slayer'))} — 🏆 {row[2]} victories · ✨ {row[1]} EXP · 🪙 {row[4]} coins")
    await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def rpg_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    text = (
        "⚔️ <b>DEMON HUNT RPG COMMANDS</b>\n"
        "/launchhunt easy|normal|hard|upper|final — Admin: launch a group raid\n"
        "/raidstatus — View this group's active raid\n"
        "/breathing — Choose or view your breathing style\n"
        "/rpgprofile — View EXP, rank, RPG coins and personal defeats\n"
        "/rpgstore — Browse RPG items\n"
        "/rpgbuy &lt;item&gt; — Buy an item (potion, whetstone, armor, katana, charm)\n"
        "/rpginventory — View RPG inventory\n"
        "/rpguse potion — Use a potion for +80 next-attack damage\n"
        "/rpgtrain &lt;style&gt; — Unlock/equip a standard style (100 coins + 100 EXP)\n"
        "/legendary sun|moon — Unlock a separate legendary path after 100 personal defeats\n"
        "/rpgleaderboard — View top RPG Slayers\n\n"
        "RPG coins and EXP are separate from legacy Slayer Points. Use /help for all bot features."
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML)


async def rpg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user or not query.data:
        return
    data = query.data.split(":")
    if len(data) < 2 or data[0] != PREFIX:
        return
    action = data[1]
    try:
        if action == "style":
            if len(data) != 4 or int(data[2]) != user.id:
                await query.answer("These controls belong to another Slayer.", show_alert=True)
                return
            key = data[3]
            if key not in STANDARD_STYLES:
                await query.answer("Invalid style.", show_alert=True)
                return
            _ensure_profile(user)
            p = _get_profile(user.id)
            if p.get("style_finalized"):
                await query.answer("Your starting style is already finalized. Use your free correction or train a new style.", show_alert=True)
                return
            with _db() as (_, cur):
                ph = "%s" if USE_POSTGRES else "?"
                cur.execute(f"UPDATE rpg_profiles SET style={ph}, style_finalized=1, updated_at=CURRENT_TIMESTAMP WHERE user_id={ph}", (key, user.id))
            await query.answer("Breathing style selected!")
            try:
                await query.edit_message_text(f"✅ {STANDARD_STYLES[key]['emoji']} {STANDARD_STYLES[key]['name']} selected. Your one-time correction is available.")
            except BadRequest:
                pass
            raid = None
            # The user can join a raid from its group card, or use /raidstatus in the group.
            await context.bot.send_message(user.id, f"{STANDARD_STYLES[key]['emoji']} <b>{STANDARD_STYLES[key]['name']}</b> equipped.\nJoin a group raid and tap Join Raid to get your personal battle panel.", parse_mode=ParseMode.HTML)
            return

        if action == "styles" or action == "correction":
            if len(data) != 3 or int(data[2]) != user.id:
                await query.answer("These controls belong to another Slayer.", show_alert=True)
                return
            p = _get_profile(user.id)
            if not p or not p.get("style"):
                await query.answer("Choose your first style first.", show_alert=True)
                return
            correction = action == "correction"
            if correction and p.get("correction_used"):
                await query.answer("Your free correction has already been used.", show_alert=True)
                return
            if correction:
                await query.edit_message_text("🔄 <b>One-time free correction</b>\nChoose the style you meant to select.", parse_mode=ParseMode.HTML, reply_markup=_style_keyboard(user.id, correction=True))
            else:
                await query.edit_message_text("🌬️ To change to another standard style, use /rpgtrain &lt;style&gt; after earning 100 EXP and 100 RPG coins.\nYour free correction is only for correcting your first choice.", parse_mode=ParseMode.HTML, reply_markup=_profile_keyboard(user.id, p))
            await query.answer()
            return

        if action == "correct":
            if len(data) != 4 or int(data[2]) != user.id:
                await query.answer("These controls belong to another Slayer.", show_alert=True)
                return
            key = data[3]
            if key not in STANDARD_STYLES:
                await query.answer("Invalid style.", show_alert=True)
                return
            p = _get_profile(user.id)
            if not p or not p.get("style") or p.get("correction_used"):
                await query.answer("Your one-time correction is unavailable.", show_alert=True)
                return
            with _db() as (_, cur):
                ph = "%s" if USE_POSTGRES else "?"
                now = int(time.time())
                cur.execute(
                    f"SELECT c.raid_id FROM rpg_contributions c JOIN rpg_raids r ON r.raid_id=c.raid_id "
                    f"WHERE c.user_id={ph} AND r.status='active' AND r.deadline>{ph} LIMIT 1",
                    (user.id, now),
                )
                active_membership = cur.fetchone()
                if active_membership:
                    await query.answer("You cannot change style during an active raid.", show_alert=True)
                    return
                cur.execute(f"UPDATE rpg_profiles SET style={ph}, correction_used=1, updated_at=CURRENT_TIMESTAMP WHERE user_id={ph}", (key, user.id))
            await query.answer("Free correction used.")
            await query.edit_message_text(f"✅ Corrected to {STANDARD_STYLES[key]['emoji']} {STANDARD_STYLES[key]['name']}. Your free correction is now used.")
            return

        if action == "join":
            if len(data) != 3:
                await query.answer("Invalid raid.", show_alert=True)
                return
            raid = _get_raid(data[2])
            if not raid or raid["status"] != "active" or int(raid["deadline"]) <= int(time.time()):
                await query.answer("This raid has ended.", show_alert=True)
                return
            _ensure_profile(user)
            p = _get_profile(user.id)
            if not p or not p.get("style"):
                await query.answer()
                await context.bot.send_message(user.id, "Choose your breathing style first:", reply_markup=_style_keyboard(user.id))
                return
            # Register a participant before their first attack so style cannot change mid-raid.
            with _db() as (_, cur):
                if USE_POSTGRES:
                    cur.execute("""INSERT INTO rpg_contributions(raid_id,user_id,damage,actions,last_action)
                        VALUES(%s,%s,0,0,0) ON CONFLICT(raid_id,user_id) DO NOTHING""", (raid["raid_id"], user.id))
                else:
                    cur.execute("""INSERT INTO rpg_contributions(raid_id,user_id,damage,actions,last_action)
                        VALUES(?,?,0,0,0) ON CONFLICT(raid_id,user_id) DO NOTHING""", (raid["raid_id"], user.id))
            await query.answer("Opening your private battle panel.")
            try:
                await _send_personal_panel(context, user.id, raid)
            except (Forbidden, TelegramError):
                await query.answer("Open my private chat and press Start first.", show_alert=True)
            return

        if action == "panel":
            if len(data) != 3 or int(data[2]) != user.id:
                await query.answer("These controls belong to another Slayer.", show_alert=True)
                return
            raid = None
            with _db() as (_, cur):
                cur.execute("SELECT raid_id FROM rpg_raids WHERE status='active' AND deadline > " + ("%s" if USE_POSTGRES else "?") + " ORDER BY created_at DESC", (int(time.time()),))
                rows = cur.fetchall()
            for row in rows:
                raid = _get_raid(row[0])
                if raid:
                    break
            if not raid:
                await query.answer("No active raid found.", show_alert=True)
                return
            await query.answer()
            await _send_personal_panel(context, user.id, raid)
            return

        if action == "status":
            if len(data) != 4:
                await query.answer("Invalid status request.", show_alert=True)
                return
            raid_id = data[2]
            target_user = int(data[3])
            if target_user not in (0, user.id):
                await query.answer("These controls belong to another Slayer.", show_alert=True)
                return
            raid = _get_raid(raid_id)
            if not raid:
                await query.answer("Raid not found.", show_alert=True)
                return
            await query.answer()
            await query.message.reply_text(_raid_text(raid), parse_mode=ParseMode.HTML, reply_markup=_raid_keyboard(raid_id))
            return

        if action == "inventory":
            if len(data) != 3 or int(data[2]) != user.id:
                await query.answer("These controls belong to another Slayer.", show_alert=True)
                return
            await query.answer()
            await context.bot.send_message(user.id, "Use /rpginventory to view your RPG items.")
            return

        if action == "buy":
            if len(data) != 3:
                await query.answer("Invalid item.", show_alert=True)
                return
            _ensure_profile(user)
            await _buy_item(user.id, data[2], query=query)
            return

        if action == "act":
            if len(data) != 5:
                await query.answer("Invalid action.", show_alert=True)
                return
            raid_id, owner_id, combat_action = data[2], int(data[3]), data[4]
            if owner_id != user.id:
                await query.answer("These controls belong to another Slayer.", show_alert=True)
                return
            raid = _get_raid(raid_id)
            if not raid or raid["status"] != "active" or int(raid["deadline"]) <= int(time.time()):
                await query.answer("The raid has ended.", show_alert=True)
                return
            profile = _get_profile(user.id)
            if not profile or not profile.get("style"):
                await query.answer("Choose your style first.", show_alert=True)
                return
            now = int(time.time())
            with _db(immediate=True) as (_, cur):
                ph = "%s" if USE_POSTGRES else "?"
                lock_sql = f"SELECT status, deadline, hp FROM rpg_raids WHERE raid_id={ph}" + (" FOR UPDATE" if USE_POSTGRES else "")
                cur.execute(lock_sql, (raid_id,))
                locked_raid = cur.fetchone()
                if not locked_raid or locked_raid[0] != "active" or int(locked_raid[1]) <= now:
                    if locked_raid and locked_raid[0] == "active" and int(locked_raid[1]) <= now:
                        _expire_raid(cur, raid_id)
                    await query.answer("The raid has ended.", show_alert=True)
                    return
                cur.execute(f"SELECT last_action FROM rpg_contributions WHERE raid_id={ph} AND user_id={ph}", (raid_id, user.id))
                last = cur.fetchone()
                if last and now - int(last[0] or 0) < 3:
                    await query.answer("Your breathing is recovering. Wait a moment.", show_alert=True)
                    return
                style = profile["style"]
                st = STANDARD_STYLES.get(style, LEGENDARY_STYLES.get(style, {"power": 1.0, "emoji": "⚔️", "name": style}))
                base = {"attack": 75, "defend": 35, "form": 120, "ultimate": 220}.get(combat_action)
                if base is None:
                    await query.answer("Unknown action.", show_alert=True)
                    return
                if combat_action == "ultimate" and int(profile.get("exp") or 0) < 100:
                    await query.answer("Ultimate requires 100 EXP.", show_alert=True)
                    return
                bonus = int(profile.get("next_attack_bonus") or 0)
                damage = int(base * float(st.get("power", 1.0))) + bonus
                damage = max(1, damage)
                cur.execute(f"UPDATE rpg_raids SET hp=MAX(0,hp-{ph}) WHERE raid_id={ph}" if not USE_POSTGRES else f"UPDATE rpg_raids SET hp=GREATEST(0,hp-{ph}) WHERE raid_id={ph}", (damage, raid_id))
                _upsert_contribution(cur, raid_id, user.id, damage, now)
                if bonus:
                    cur.execute(f"UPDATE rpg_profiles SET next_attack_bonus=0 WHERE user_id={ph}", (user.id,))
                cur.execute(f"UPDATE rpg_profiles SET exp=exp+5, updated_at=CURRENT_TIMESTAMP WHERE user_id={ph}", (user.id,))
                cur.execute(f"SELECT hp FROM rpg_raids WHERE raid_id={ph}", (raid_id,))
                hp_row = cur.fetchone()
                hp_left = int(hp_row[0]) if hp_row else int(raid["hp"])
                if hp_left <= 0:
                    cur.execute(f"UPDATE rpg_raids SET status='victory', hp=0 WHERE raid_id={ph} AND status='active'", (raid_id,))
                    cur.execute(f"SELECT user_id, damage FROM rpg_contributions WHERE raid_id={ph}", (raid_id,))
                    contributors = cur.fetchall()
                    boss = BOSSES[raid["boss_key"]]
                    min_contribution = max(1, int(raid["max_hp"]) // 100)
                    for contributor in contributors:
                        uid, total_damage = int(contributor[0]), int(contributor[1])
                        if total_damage < min_contribution:
                            continue
                        cur.execute(
                            f"UPDATE rpg_profiles SET coins=coins+{ph}, exp=exp+{ph}, victories=victories+1, "
                            f"personal_defeats=personal_defeats+1, "
                            f"corps_rank=CASE WHEN exp+{ph} >= 3000 THEN 'Hashira' "
                            f"WHEN exp+{ph} >= 1500 THEN 'Kinoe' "
                            f"WHEN exp+{ph} >= 700 THEN 'Kanoto' "
                            f"WHEN exp+{ph} >= 300 THEN 'Kanoe' "
                            f"WHEN exp+{ph} >= 100 THEN 'Mizunoe' ELSE 'Mizunoto' END, "
                            f"updated_at=CURRENT_TIMESTAMP WHERE user_id={ph}",
                            (boss["reward"], boss["exp"], boss["exp"], boss["exp"], boss["exp"], boss["exp"], boss["exp"], uid)
                        )
                        cur.execute(f"SELECT legendary_path FROM rpg_profiles WHERE user_id={ph}", (uid,))
                        path_row = cur.fetchone()
                        selected_path = (path_row[0] if path_row else "") or ""
                        if selected_path == "sun":
                            cur.execute(f"UPDATE rpg_profiles SET sun_defeats=sun_defeats+1 WHERE user_id={ph}", (uid,))
                        elif selected_path == "moon":
                            cur.execute(f"UPDATE rpg_profiles SET moon_defeats=moon_defeats+1 WHERE user_id={ph}", (uid,))
            await query.answer(f"{st['emoji']} {combat_action.title()} dealt {damage} damage!")
            refreshed = _get_raid(raid_id)
            if refreshed:
                if refreshed["status"] == "victory":
                    await context.bot.send_message(chat_id=refreshed["chat_id"],
                        text=f"🎉 <b>{html.escape(refreshed['boss_name'])} defeated!</b>\nEligible contributors received RPG rewards. Use /rpgprofile to see your progress.",
                        parse_mode=ParseMode.HTML)
                    try:
                        await context.bot.edit_message_caption(chat_id=refreshed["chat_id"], message_id=refreshed["message_id"],
                            caption=_raid_text(refreshed), parse_mode=ParseMode.HTML, reply_markup=None)
                    except TelegramError:
                        pass
                else:
                    try:
                        await context.bot.edit_message_caption(chat_id=refreshed["chat_id"], message_id=refreshed["message_id"],
                            caption=_raid_text(refreshed), parse_mode=ParseMode.HTML, reply_markup=_raid_keyboard(raid_id))
                    except TelegramError:
                        pass
            return

    except (ValueError, KeyError, BadRequest, TelegramError) as exc:
        logger.warning("RPG callback error for user %s: %s", user.id, exc)
        try:
            await query.answer("Couldn't process that action. Please try again.", show_alert=True)
        except TelegramError:
            pass


def rpg_command_handlers():
    """Return handlers to register in bot.py's existing PTB application."""
    from telegram.ext import CommandHandler, CallbackQueryHandler
    return [
        CommandHandler("launchhunt", launch_hunt),
        CommandHandler("raidstatus", raid_status_command),
        CommandHandler("breathing", breathing_command),
        CommandHandler("rpgprofile", rpg_profile_command),
        CommandHandler("rpgstore", rpg_store_command),
        CommandHandler("rpgbuy", rpg_buy_command),
        CommandHandler("rpginventory", rpg_inventory_command),
        CommandHandler("rpguse", rpg_use_command),
        CommandHandler("rpgtrain", rpg_train_command),
        CommandHandler("legendary", legendary_command),
        CommandHandler("rpgleaderboard", rpg_leaderboard_command),
        CommandHandler("rpghelp", rpg_help_command),
        CallbackQueryHandler(rpg_callback, pattern=r"^rpg:"),
    ]


# Database initialization is performed explicitly by bot.py after import.
