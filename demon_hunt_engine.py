"""Muichiro Demon Hunt RPG engine.

This is a separate, persistent group-raid RPG. It deliberately does not replace
or edit the existing character-guessing game in demonslayer_hunt.py.

Requires the project's existing database.py connection and python-telegram-bot.
Database operations use the same PostgreSQL/SQLite connection as the main bot.
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from database import db, cursor, USE_POSTGRES

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets" / "demon_hunt_rpg"
CHARACTER_ASSET_DIR = ROOT / "assets" / "demon_hunt"
OWNER_ID = 6608396796
PREFIX = "dhrpg"

STYLE_INFO: Dict[str, Dict[str, str]] = {
    "mist": {"name": "Mist Breathing", "emoji": "🌫️", "title": "MUICHIRO • MIST DOMAIN", "forms": "Low Clouds • Obscuring Mist • Shifting Flow", "image": "muichiro.jpeg"},
    "water": {"name": "Water Breathing", "emoji": "🌊", "title": "WATER • FLOWING DOMAIN", "forms": "Water Surface Slash • Flowing Dance • Ripple Thrust", "image": "tanjiro.jpeg"},
    "flame": {"name": "Flame Breathing", "emoji": "🔥", "title": "FLAME • BURNING DOMAIN", "forms": "Unknowing Fire • Rising Scorching Sun • Flame Tiger", "image": "rengoku.jpeg"},
    "thunder": {"name": "Thunder Breathing", "emoji": "⚡", "title": "THUNDER • FLASH DOMAIN", "forms": "Thunderclap • Sixfold Flash • Godlike Speed", "image": "zenitsu.jpeg"},
    "wind": {"name": "Wind Breathing", "emoji": "🌪️", "title": "WIND • GALE DOMAIN", "forms": "Dust Whirlwind • Clean Storm Wind Tree", "image": "sanemi.jpeg"},
    "stone": {"name": "Stone Breathing", "emoji": "🪨", "title": "STONE • FORTRESS DOMAIN", "forms": "Serpentinite Bipolar • Stone Skin", "image": "gyomei.jpeg"},
    "beast": {"name": "Beast Breathing", "emoji": "🐗", "title": "BEAST • FERAL DOMAIN", "forms": "Pierce • Slice • Spatial Awareness", "image": "inosuke.jpeg"},
    "love": {"name": "Love Breathing", "emoji": "💗", "title": "LOVE • HEART DOMAIN", "forms": "Shivers of First Love • Catlove Shower", "image": "mitsuri.jpeg"},
    "serpent": {"name": "Serpent Breathing", "emoji": "🐍", "title": "SERPENT • COIL DOMAIN", "forms": "Winding Serpent • Slithering Serpent", "image": "obanai.jpeg"},
    "sound": {"name": "Sound Breathing", "emoji": "🎵", "title": "SOUND • RHYTHM DOMAIN", "forms": "Roar • String Performance • Resonant Slash", "image": "tengen.jpeg"},
    "flower": {"name": "Flower Breathing", "emoji": "🌸", "title": "FLOWER • PETAL DOMAIN", "forms": "Whirling Peach • Honorable Shadow Plum", "image": "mitsuri.jpeg"},
    "insect": {"name": "Insect Breathing", "emoji": "🦋", "title": "INSECT • VENOM DOMAIN", "forms": "Butterfly Dance • Dance of the Bee Sting", "image": "shinobu.jpeg"},
    "sun": {"name": "Sun Breathing", "emoji": "🌞", "title": "SUN • LEGENDARY DOMAIN", "forms": "Dance • Clear Blue Sky • Sunflower Thrust", "image": "rengoku.jpeg"},
    "moon": {"name": "Moon Breathing", "emoji": "🌙", "title": "MOON • LEGENDARY DOMAIN", "forms": "Dark Moon • Evening Palace • Moon-Dragon Ringtail", "image": "muichiro.jpeg"},
}
STANDARD_STYLES = tuple(k for k in STYLE_INFO if k not in {"sun", "moon"})

BOSSES: Dict[str, Dict[str, Any]] = {
    "easy": {"name": "Rui", "rank": "Lower Rank", "hp": 650, "seconds": 600, "reward": 90, "xp": 90, "image": "raid_banner.png"},
    "normal": {"name": "Enmu", "rank": "Lower Rank", "hp": 1000, "seconds": 720, "reward": 130, "xp": 130, "image": "raid_banner.png"},
    "hard": {"name": "Akaza", "rank": "Upper Rank", "hp": 1600, "seconds": 900, "reward": 190, "xp": 190, "image": "raid_banner.png"},
    "upper": {"name": "Doma", "rank": "Upper Rank", "hp": 2200, "seconds": 1080, "reward": 260, "xp": 260, "image": "raid_banner.png"},
    "final": {"name": "Muzan Kibutsuji", "rank": "Final Boss", "hp": 3600, "seconds": 1200, "reward": 400, "xp": 400, "image": "raid_banner.png"},
}
STORE_ITEMS: Dict[str, Dict[str, Any]] = {
    "nichirin": {"name": "Nichirin Blade", "price": 300, "kind": "weapon", "damage": 10, "description": "+10 damage per attack"},
    "haori": {"name": "Reinforced Haori", "price": 250, "kind": "armor", "description": "A Corps uniform upgrade"},
    "potion": {"name": "Wisteria Potion", "price": 120, "kind": "consumable", "heal": 35, "description": "Restore 35 HP with /rpguse potion"},
    "ration": {"name": "Battle Ration", "price": 80, "kind": "consumable", "stamina": 35, "description": "Restore 35 stamina with /rpguse ration"},
    "crystal": {"name": "Demon Crystal", "price": 450, "kind": "material", "description": "Rare crafting material"},
    "scroll": {"name": "Training Scroll", "price": 200, "kind": "material", "description": "Unlock a style without spending RPG coins"},
}

DB_LOCK = asyncio.Lock()
_WATCHDOG_TASK: Optional[asyncio.Task] = None


def _q(sql: str) -> str:
    return sql if USE_POSTGRES else sql.replace("%s", "?")


def _execute(sql: str, params: tuple = ()):
    cursor.execute(_q(sql), params)
    return cursor


def _commit() -> None:
    db.commit()


def _rollback() -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _ensure_profile(user) -> None:
    _execute(
        """INSERT INTO rpg_profiles
        (user_id, username, full_name) VALUES (%s, %s, %s)
        ON CONFLICT(user_id) DO NOTHING""",
        (user.id, user.username or "", user.full_name or user.first_name or "Slayer"),
    )
    _execute("UPDATE rpg_profiles SET username=%s, full_name=%s WHERE user_id=%s", (user.username or "", user.full_name or user.first_name or "Slayer", user.id))
    _commit()


def _get_profile(user_id: int) -> Optional[dict]:
    _execute("""SELECT user_id, username, full_name, style, style_finalized,
        free_correction_used, unlocked_styles, xp, corps_rank, demon_defeats,
        sun_progress, moon_progress, legendary_focus, currency, hp, stamina,
        wins, losses FROM rpg_profiles WHERE user_id=%s""", (user_id,))
    row = cursor.fetchone()
    if not row:
        return None
    keys = ["user_id", "username", "full_name", "style", "style_finalized", "free_correction_used", "unlocked_styles", "xp", "corps_rank", "demon_defeats", "sun_progress", "moon_progress", "legendary_focus", "currency", "hp", "stamina", "wins", "losses"]
    result = dict(zip(keys, row))
    result["style_finalized"] = bool(result["style_finalized"])
    result["free_correction_used"] = bool(result["free_correction_used"])
    result["unlocked_styles"] = [x for x in (result["unlocked_styles"] or "").split(",") if x]
    return result


def _active_raid(chat_id: int) -> Optional[dict]:
    _execute("SELECT raid_id, chat_id, demon_key, demon_name, demon_rank, hp, max_hp, ends_at, status, started_by, message_id FROM rpg_raids WHERE chat_id=%s AND status='active'", (chat_id,))
    row = cursor.fetchone()
    if not row:
        return None
    keys = ["raid_id", "chat_id", "demon_key", "demon_name", "demon_rank", "hp", "max_hp", "ends_at", "status", "started_by", "message_id"]
    return dict(zip(keys, row))


def _raid_by_id(raid_id: str) -> Optional[dict]:
    _execute("SELECT raid_id, chat_id, demon_key, demon_name, demon_rank, hp, max_hp, ends_at, status, started_by, message_id FROM rpg_raids WHERE raid_id=%s", (raid_id,))
    row = cursor.fetchone()
    if not row:
        return None
    keys = ["raid_id", "chat_id", "demon_key", "demon_name", "demon_rank", "hp", "max_hp", "ends_at", "status", "started_by", "message_id"]
    return dict(zip(keys, row))


def _joined(raid_id: str, user_id: int) -> bool:
    _execute("SELECT 1 FROM rpg_contributions WHERE raid_id=%s AND user_id=%s", (raid_id, user_id))
    return cursor.fetchone() is not None


def _in_active_raid(user_id: int) -> bool:
    _execute("""SELECT 1 FROM rpg_contributions c JOIN rpg_raids r ON r.raid_id=c.raid_id
        WHERE c.user_id=%s AND r.status='active' LIMIT 1""", (user_id,))
    return cursor.fetchone() is not None


def _unlocked_styles(profile: dict) -> list[str]:
    unlocked = profile.get("unlocked_styles") or []
    if profile.get("style") and profile["style"] not in unlocked:
        unlocked.append(profile["style"])
    return unlocked


def _rank_from_xp(xp: int) -> str:
    if xp >= 15000: return "Hashira"
    if xp >= 7000: return "Kinoe"
    if xp >= 3000: return "Hinoe"
    if xp >= 1200: return "Kanoto"
    if xp >= 400: return "Mizunoto"
    return "Mizunoe"


def _style_keyboard(profile: dict, correction: bool = False) -> InlineKeyboardMarkup:
    if correction:
        styles = list(STANDARD_STYLES)
    elif profile.get("style_finalized"):
        styles = _unlocked_styles(profile)
    else:
        styles = list(STANDARD_STYLES)
    rows, row = [], []
    for style_id in styles:
        if style_id not in STYLE_INFO:
            continue
        info = STYLE_INFO[style_id]
        row.append(InlineKeyboardButton(f"{info['emoji']} {info['name']}", callback_data=f"{PREFIX}:{'correct' if correction else 'style'}:{style_id}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    if profile.get("style_finalized") and not correction:
        rows.append([InlineKeyboardButton("🔄 One-time free correction", callback_data=f"{PREFIX}:correction")])
        rows.append([InlineKeyboardButton("📜 Train to unlock another style", callback_data=f"{PREFIX}:training")])
    return InlineKeyboardMarkup(rows)


def _battle_keyboard(raid_id: str, user_id: int, style_id: str) -> InlineKeyboardMarkup:
    info = STYLE_INFO.get(style_id, STYLE_INFO["water"])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{info['emoji']} Quick Attack", callback_data=f"{PREFIX}:act:{raid_id}:{user_id}:attack"), InlineKeyboardButton("🛡️ Defend", callback_data=f"{PREFIX}:act:{raid_id}:{user_id}:defend")],
        [InlineKeyboardButton("🌟 Breathing Form", callback_data=f"{PREFIX}:act:{raid_id}:{user_id}:form"), InlineKeyboardButton("💥 Ultimate", callback_data=f"{PREFIX}:act:{raid_id}:{user_id}:ultimate")],
        [InlineKeyboardButton("🧪 Use Potion", callback_data=f"{PREFIX}:use:{raid_id}:{user_id}:potion"), InlineKeyboardButton("📊 Raid Status", callback_data=f"{PREFIX}:status:{raid_id}")],
    ])


def _raid_keyboard(raid_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Join Raid", callback_data=f"{PREFIX}:join:{raid_id}"), InlineKeyboardButton("📊 Raid Status", callback_data=f"{PREFIX}:status:{raid_id}")],
        [InlineKeyboardButton("🌫️ Choose Breathing", callback_data=f"{PREFIX}:open_styles")],
    ])


def _remaining(ends_at: float) -> str:
    secs = max(0, int(float(ends_at) - time.time()))
    return f"{secs // 60:02d}:{secs % 60:02d}"


def _raid_caption(raid: dict) -> str:
    hp = max(0, int(raid["hp"]))
    max_hp = int(raid["max_hp"])
    bar_len = 16
    filled = max(0, min(bar_len, round(bar_len * hp / max(1, max_hp))))
    bar = "🟥" * filled + "⬛" * (bar_len - filled)
    _execute("SELECT COUNT(*), COALESCE(SUM(damage), 0) FROM rpg_contributions WHERE raid_id=%s", (raid["raid_id"],))
    row = cursor.fetchone() or (0, 0)
    return (
        "⚔️ <b>MUICHIRO • DEMON RAID</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👹 <b>{html.escape(str(raid['demon_name']))}</b> · {html.escape(str(raid['demon_rank']))}\n"
        f"❤️ HP: <b>{hp:,}/{max_hp:,}</b>\n{bar}\n"
        f"👥 Slayers joined: <b>{int(row[0])}</b>\n"
        f"⏳ Time left: <b>{_remaining(float(raid['ends_at']))}</b>\n\n"
        "Join the raid, then use your private combat panel.\n"
        "<i>Personal controls are private; raid progress is shared.</i>"
    )


async def _send_feature_photo(update: Update, filename: str, caption: str, reply_markup=None) -> None:
    message = update.effective_message
    if not message:
        return
    path = ASSET_DIR / filename
    if path.exists():
        if len(caption) > 950:
            with path.open("rb") as photo:
                await message.reply_photo(photo=photo, caption=caption.split("\n", 1)[0], parse_mode=ParseMode.HTML)
            await message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            with path.open("rb") as photo:
                await message.reply_photo(photo=photo, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def initialize_demon_hunt_rpg(application: Application) -> None:
    """Create RPG tables and start the raid expiry watcher."""
    global _WATCHDOG_TASK
    async with DB_LOCK:
        try:
            _execute("""CREATE TABLE IF NOT EXISTS rpg_profiles (
                user_id BIGINT PRIMARY KEY, username TEXT DEFAULT '', full_name TEXT DEFAULT '',
                style TEXT, style_finalized INTEGER DEFAULT 0, free_correction_used INTEGER DEFAULT 0,
                unlocked_styles TEXT DEFAULT '', xp BIGINT DEFAULT 0, corps_rank TEXT DEFAULT 'Mizunoe',
                demon_defeats INTEGER DEFAULT 0, sun_progress INTEGER DEFAULT 0, moon_progress INTEGER DEFAULT 0,
                legendary_focus TEXT DEFAULT '', currency BIGINT DEFAULT 0, hp INTEGER DEFAULT 100,
                stamina INTEGER DEFAULT 100, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            _execute("""CREATE TABLE IF NOT EXISTS rpg_raids (
                raid_id TEXT PRIMARY KEY, chat_id BIGINT NOT NULL, demon_key TEXT NOT NULL,
                demon_name TEXT NOT NULL, demon_rank TEXT NOT NULL, hp INTEGER NOT NULL,
                max_hp INTEGER NOT NULL, ends_at DOUBLE PRECISION NOT NULL, status TEXT NOT NULL DEFAULT 'active',
                started_by BIGINT, message_id BIGINT, started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP
            )""")
            _execute("CREATE INDEX IF NOT EXISTS idx_rpg_raids_chat_status ON rpg_raids(chat_id, status)")
            _execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_rpg_one_active_raid_per_chat ON rpg_raids(chat_id) WHERE status='active'")
            _execute("""CREATE TABLE IF NOT EXISTS rpg_contributions (
                raid_id TEXT NOT NULL, user_id BIGINT NOT NULL, username TEXT DEFAULT '', full_name TEXT DEFAULT '',
                damage INTEGER DEFAULT 0, actions INTEGER DEFAULT 0, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_attack DOUBLE PRECISION DEFAULT 0, last_form DOUBLE PRECISION DEFAULT 0,
                last_ultimate DOUBLE PRECISION DEFAULT 0, defending_until DOUBLE PRECISION DEFAULT 0,
                PRIMARY KEY(raid_id, user_id)
            )""")
            _execute("""CREATE TABLE IF NOT EXISTS rpg_inventory (
                user_id BIGINT NOT NULL, item_key TEXT NOT NULL, quantity INTEGER DEFAULT 0,
                equipped INTEGER DEFAULT 0, PRIMARY KEY(user_id, item_key)
            )""")
            _commit()
        except Exception:
            _rollback()
            log.exception("Demon Hunt RPG schema initialization failed")
            raise
    if _WATCHDOG_TASK is None or _WATCHDOG_TASK.done():
        _WATCHDOG_TASK = asyncio.create_task(_raid_watchdog(application))
    log.info("Demon Hunt RPG tables ready")


async def _raid_watchdog(application: Application) -> None:
    while True:
        try:
            _execute("SELECT raid_id FROM rpg_raids WHERE status='active' AND ends_at <= %s", (time.time(),))
            rows = cursor.fetchall() or []
            for (raid_id,) in rows:
                await _resolve_raid(application.bot, str(raid_id), victory=False, reason="time")
            await asyncio.sleep(20)
        except asyncio.CancelledError:
            return
        except Exception:
            _rollback()
            log.exception("Demon Hunt RPG watchdog error")
            await asyncio.sleep(20)


async def _is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user, chat = update.effective_user, update.effective_chat
    if not user or not chat:
        return False
    if user.id == OWNER_ID:
        return True
    if chat.type == ChatType.PRIVATE:
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except TelegramError:
        return False


async def launch_hunt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Group admins can launch a new shared RPG raid with /launchhunt [tier]."""
    chat, user, msg = update.effective_chat, update.effective_user, update.effective_message
    if not chat or not user or not msg:
        return
    if chat.type == ChatType.PRIVATE:
        await msg.reply_text("Start a raid inside a group: /launchhunt [easy|normal|hard|upper|final].")
        return
    if not await _is_group_admin(update, context):
        await msg.reply_text("⛔ Only group admins can launch a Demon Raid.")
        return
    tier = (context.args[0].lower() if context.args else random.choice(["easy", "normal", "hard"]))
    if tier not in BOSSES:
        await msg.reply_text("Usage: /launchhunt [easy|normal|hard|upper|final]")
        return
    existing = _active_raid(chat.id)
    if existing:
        await msg.reply_text("⚔️ A Demon Raid is already active here. Use /raidstatus to check it.")
        return
    boss = BOSSES[tier]
    raid_id = f"{chat.id}_{int(time.time())}_{random.randint(100,999)}"
    try:
        _execute("INSERT INTO rpg_raids (raid_id, chat_id, demon_key, demon_name, demon_rank, hp, max_hp, ends_at, status, started_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'active',%s)", (raid_id, chat.id, tier, boss["name"], boss["rank"], boss["hp"], boss["hp"], time.time()+boss["seconds"], user.id))
        _commit()
    except Exception:
        _rollback()
        log.exception("Could not create RPG raid")
        await msg.reply_text("⚠️ Couldn't launch the raid due to a database error. Please try again.")
        return
    caption = (
        "⚔️ <b>A NEW DEMON RAID HAS BEGUN!</b>\n\n"
        f"👹 <b>{html.escape(boss['name'])}</b> · {html.escape(boss['rank'])}\n"
        f"❤️ Demon HP: <b>{boss['hp']:,}</b>\n"
        f"⏳ Deadline: <b>{boss['seconds']//60} minutes</b>\n"
        f"💎 Team reward: up to <b>{boss['reward']:,} RPG coins</b> + EXP\n\n"
        "Tap Join Raid, choose your style if needed, and fight from your private controls.\n"
        "<i>Rewards are granted once when the raid is resolved.</i>"
    )
    image = ASSET_DIR / boss["image"]
    try:
        if image.exists():
            with image.open("rb") as photo:
                sent = await context.bot.send_photo(chat.id, photo=photo, caption=caption, parse_mode=ParseMode.HTML, reply_markup=_raid_keyboard(raid_id))
        else:
            sent = await context.bot.send_message(chat.id, caption, parse_mode=ParseMode.HTML, reply_markup=_raid_keyboard(raid_id))
        _execute("UPDATE rpg_raids SET message_id=%s WHERE raid_id=%s", (sent.message_id, raid_id)); _commit()
    except TelegramError:
        _execute("UPDATE rpg_raids SET status='failed', ended_at=CURRENT_TIMESTAMP WHERE raid_id=%s", (raid_id,)); _commit()
        await msg.reply_text("⚠️ I couldn't post the raid card. Check my group permissions and try again.")


async def raid_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat or not update.effective_message:
        return
    raid = _active_raid(chat.id) if chat.type != ChatType.PRIVATE else None
    if not raid and context.args:
        raid = _raid_by_id(context.args[0])
    if not raid:
        await update.effective_message.reply_text("No active Demon Raid here. A group admin can start one with /launchhunt.")
        return
    await update.effective_message.reply_text(_raid_caption(raid), parse_mode=ParseMode.HTML, reply_markup=_raid_keyboard(str(raid["raid_id"])))


async def breathing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    _ensure_profile(user)
    profile = _get_profile(user.id)
    if not profile:
        return
    text = "🌫️ <b>CHOOSE YOUR BREATHING STYLE</b>\n━━━━━━━━━━━━━━━━━━\nChoose one standard style. Sun and Moon are legendary paths, not initial options.\n\nYou have one free correction if you choose by mistake. Later styles unlock through training."
    if profile["style_finalized"]:
        info = STYLE_INFO.get(profile["style"], STYLE_INFO["water"])
        text = f"{info['emoji']} <b>YOUR STYLE: {html.escape(info['name'])}</b>\n\nChoose an unlocked style or use the one-time correction. Train with /rpgtrain <style> to unlock another standard style."
    markup = _style_keyboard(profile)
    if update.effective_chat and update.effective_chat.type != ChatType.PRIVATE:
        try:
            await context.bot.send_message(user.id, text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await update.effective_message.reply_text("📩 I sent your personal breathing-style menu in private chat. Open my PM and press Start first if needed.")
        except (Forbidden, TelegramError):
            await update.effective_message.reply_text("Open my private chat and press Start, then run /breathing again.")
        return
    await _send_feature_photo(update, "styles_banner.png", text, markup)


async def rpg_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.effective_message:
        return
    _ensure_profile(user); p = _get_profile(user.id)
    if not p: return
    style = STYLE_INFO.get(p["style"], {"name": "Not chosen", "emoji": "🌫️"})
    caption = (
        "👤 <b>SLAYER PROFILE</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"⚔️ Slayer: <b>{html.escape(p['full_name'])}</b>\n"
        f"🌫️ Style: <b>{style['emoji']} {html.escape(style['name'])}</b>\n"
        f"🎖️ Corps Rank: <b>{html.escape(p['corps_rank'])}</b>\n"
        f"✨ EXP: <b>{p['xp']:,}</b>\n💎 RPG Coins: <b>{p['currency']:,}</b>\n"
        f"👹 Personal demon defeats: <b>{p['demon_defeats']}</b>\n"
        f"🏆 Raids won/lost: <b>{p['wins']}/{p['losses']}</b>\n"
        f"🌞 Sun path: <b>{p['sun_progress']}/100</b> · 🌙 Moon path: <b>{p['moon_progress']}/100</b>\n"
        f"❤️ HP: <b>{p['hp']}/100</b> · ⚡ Stamina: <b>{p['stamina']}/100</b>"
    )
    await _send_feature_photo(update, "profile_banner.png", caption)


async def rpg_store_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["🏪 <b>DEMON CORPS STORE</b>", "━━━━━━━━━━━━━━━━━━"]
    rows = []
    for key, item in STORE_ITEMS.items():
        lines.append(f"• <b>{html.escape(item['name'])}</b> — 💎 {item['price']} coins\n  <i>{html.escape(item['description'])}</i>\n  Buy: <code>/rpgbuy {key}</code>")
        rows.append([InlineKeyboardButton(f"🛒 {item['name']} · {item['price']}", callback_data=f"{PREFIX}:buy:{key}")])
    lines.append("\nYour RPG coins are separate from existing Slayer Points and music features.")
    await _send_feature_photo(update, "store_banner.png", "\n".join(lines), InlineKeyboardMarkup(rows))


async def rpg_buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg: return
    if not context.args or context.args[0].lower() not in STORE_ITEMS:
        await msg.reply_text("Usage: /rpgbuy <item>\nItems: " + ", ".join(STORE_ITEMS))
        return
    await _buy_item(user, context.args[0].lower(), msg.reply_text)


async def _buy_item(user, key: str, reply_func) -> None:
    if key not in STORE_ITEMS:
        await reply_func("Unknown store item."); return
    _ensure_profile(user); item = STORE_ITEMS[key]
    _execute("SELECT currency FROM rpg_profiles WHERE user_id=%s", (user.id,)); row = cursor.fetchone()
    balance = int(row[0] or 0) if row else 0
    if balance < item["price"]:
        await reply_func(f"❌ Not enough RPG coins. Need {item['price']:,}; you have {balance:,}. Earn coins by winning raids."); return
    try:
        _execute("UPDATE rpg_profiles SET currency=currency-%s, updated_at=CURRENT_TIMESTAMP WHERE user_id=%s AND currency >= %s", (item["price"], user.id, item["price"]))
        if cursor.rowcount != 1:
            _rollback(); await reply_func("❌ Your balance changed; try again."); return
        _execute("INSERT INTO rpg_inventory (user_id, item_key, quantity) VALUES (%s,%s,1) ON CONFLICT(user_id,item_key) DO UPDATE SET quantity=rpg_inventory.quantity+1", (user.id, key))
        _commit()
        await reply_func(f"✅ Purchased <b>{html.escape(item['name'])}</b> for {item['price']:,} RPG coins.", parse_mode=ParseMode.HTML)
    except Exception:
        _rollback(); log.exception("RPG store purchase failed")
        await reply_func("⚠️ Purchase failed; no reward was applied. Try again later.")


async def rpg_inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user: return
    _ensure_profile(user)
    _execute("SELECT item_key, quantity, equipped FROM rpg_inventory WHERE user_id=%s AND quantity > 0 ORDER BY item_key", (user.id,)); rows = cursor.fetchall() or []
    lines = ["🎒 <b>SLAYER INVENTORY</b>", "━━━━━━━━━━━━━━━━━━"]
    if not rows: lines.append("Your inventory is empty. Visit /rpgstore to prepare for battle.")
    for key, qty, equipped in rows:
        item = STORE_ITEMS.get(key, {"name": key})
        suffix = " · EQUIPPED" if equipped else ""
        lines.append(f"• {html.escape(item['name'])} × {int(qty)}{suffix}")
    lines.append("\nUse /rpguse potion or /rpguse ration during a raid.")
    await _send_feature_photo(update, "inventory_banner.png", "\n".join(lines))


async def rpg_use_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, chat, msg = update.effective_user, update.effective_chat, update.effective_message
    if not user or not msg: return
    if not context.args or context.args[0].lower() not in {"potion", "ration"}:
        await msg.reply_text("Usage: /rpguse potion|ration (works during an active raid)"); return
    _ensure_profile(user)
    item_key = context.args[0].lower()
    _execute("SELECT quantity FROM rpg_inventory WHERE user_id=%s AND item_key=%s", (user.id, item_key)); row = cursor.fetchone()
    if not row or int(row[0]) <= 0:
        await msg.reply_text(f"You don't have a {item_key}. Buy one with /rpgstore."); return
    _execute("SELECT hp, stamina FROM rpg_profiles WHERE user_id=%s", (user.id,)); p = cursor.fetchone() or (100,100)
    if item_key == "potion": hp, stamina = min(100, int(p[0])+35), int(p[1])
    else: hp, stamina = int(p[0]), min(100, int(p[1])+35)
    _execute("UPDATE rpg_profiles SET hp=%s, stamina=%s WHERE user_id=%s", (hp, stamina, user.id))
    _execute("UPDATE rpg_inventory SET quantity=quantity-1 WHERE user_id=%s AND item_key=%s AND quantity > 0", (user.id, item_key)); _commit()
    await msg.reply_text(f"🧪 Used {item_key}. ❤️ HP: {hp}/100 · ⚡ Stamina: {stamina}/100")


async def rpg_train_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg: return
    if not context.args or context.args[0].lower() not in STANDARD_STYLES:
        await msg.reply_text("Usage: /rpgtrain <style>\nStyles: " + ", ".join(STANDARD_STYLES)); return
    style = context.args[0].lower(); _ensure_profile(user); p = _get_profile(user.id)
    if style in _unlocked_styles(p):
        await msg.reply_text("You already unlocked that style."); return
    if _in_active_raid(user.id):
        await msg.reply_text("Finish your active raid before training."); return
    try:
        _execute("SELECT quantity FROM rpg_inventory WHERE user_id=%s AND item_key='scroll'", (user.id,))
        scroll_row = cursor.fetchone()
        has_scroll = bool(scroll_row and int(scroll_row[0]) > 0)
        if has_scroll:
            _execute("UPDATE rpg_inventory SET quantity=quantity-1 WHERE user_id=%s AND item_key='scroll' AND quantity>0", (user.id,))
        else:
            _execute("UPDATE rpg_profiles SET currency=currency-250 WHERE user_id=%s AND currency>=250", (user.id,))
            if cursor.rowcount != 1:
                _rollback(); await msg.reply_text("Training costs 250 RPG coins or one Training Scroll. Win raids or visit /rpgstore."); return
        unlocked = _unlocked_styles(p); unlocked.append(style)
        _execute("UPDATE rpg_profiles SET unlocked_styles=%s, updated_at=CURRENT_TIMESTAMP WHERE user_id=%s", (",".join(sorted(set(unlocked))), user.id))
        _commit()
    except Exception:
        _rollback(); log.exception("RPG style training failed")
        await msg.reply_text("Could not complete training; try again."); return
    payment = "one Training Scroll" if has_scroll else "250 RPG coins"
    await msg.reply_text(f"📜 Training complete using {payment}! {STYLE_INFO[style]['emoji']} {STYLE_INFO[style]['name']} is now unlocked. Use /breathing to equip it.")


async def legendary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user: return
    _ensure_profile(user); p = _get_profile(user.id)
    text = ("🌞 <b>LEGENDARY BREATHING PATHS</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🌞 Sun Breathing path: <b>{p['sun_progress']}/100</b> confirmed personal defeats\n"
            f"🌙 Moon Breathing path: <b>{p['moon_progress']}/100</b> confirmed personal defeats\n\n"
            "Choose one path to focus on. Only a successful raid with minimum personal contribution counts. Each raid adds at most one defeat to your selected path.")
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🌞 Focus Sun", callback_data=f"{PREFIX}:focus:sun"), InlineKeyboardButton("🌙 Focus Moon", callback_data=f"{PREFIX}:focus:moon")]])
    await _send_feature_photo(update, "legendary_banner.png", text, markup)


async def rpg_leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _execute("SELECT full_name, corps_rank, xp, wins, demon_defeats FROM rpg_profiles ORDER BY wins DESC, xp DESC LIMIT 10")
    rows = cursor.fetchall() or []
    lines = ["🏆 <b>DEMON CORPS LEADERBOARD</b>", "━━━━━━━━━━━━━━━━━━"]
    if not rows: lines.append("No Slayers have completed a raid yet.")
    for i, row in enumerate(rows, 1):
        lines.append(f"<b>{i}.</b> {html.escape(str(row[0] or 'Slayer'))} · {html.escape(str(row[1]))}\n   🏆 {int(row[3])} wins · 👹 {int(row[4])} defeats · ✨ {int(row[2])} EXP")
    await _send_feature_photo(update, "leaderboard_banner.png", "\n".join(lines))


async def rpg_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = ("⚔️ <b>DEMON HUNT RPG COMMANDS</b>\n━━━━━━━━━━━━━━━━━━\n"
            "<code>/launchhunt [easy|normal|hard|upper|final]</code> — group admin starts a raid\n"
            "<code>/raidstatus</code> — check the active group raid\n<code>/breathing</code> — choose/equip a breathing style\n"
            "<code>/rpgprofile</code> — your RPG progress\n<code>/rpgstore</code> — buy equipment and supplies\n"
            "<code>/rpgbuy &lt;item&gt;</code> — buy a store item\n<code>/rpginventory</code> — view items\n"
            "<code>/rpguse potion|ration</code> — consume supplies\n<code>/rpgtrain &lt;style&gt;</code> — unlock another standard style (250 coins)\n"
            "<code>/legendary</code> — choose Sun/Moon progression\n<code>/rpgleaderboard</code> — top Slayers\n<code>/rpghelp</code> — this guide\n\n"
            "RPG coins and EXP are separate from the existing Slayer Points system.")
    await _send_feature_photo(update, "help_banner.png", text)


async def _send_private_panel(bot, user_id: int, raid: dict) -> bool:
    _execute("SELECT style, hp, stamina FROM rpg_profiles WHERE user_id=%s", (user_id,)); row = cursor.fetchone()
    if not row or not row[0]:
        try:
            await bot.send_message(user_id, "Choose your breathing style first with /breathing.")
        except TelegramError:
            pass
        return False
    style_id, hp, stamina = row
    style = STYLE_INFO.get(style_id, STYLE_INFO["water"])
    caption = (f"{style['emoji']} <b>{html.escape(style['title'])}</b>\n━━━━━━━━━━━━━━━━━━\n"
               f"👹 Target: <b>{html.escape(str(raid['demon_name']))}</b>\n❤️ HP: <b>{int(hp)}/100</b> · ⚡ Stamina: <b>{int(stamina)}/100</b>\n"
               f"🌟 Forms: {html.escape(style['forms'])}\n⏳ Raid time left: <b>{_remaining(float(raid['ends_at']))}</b>\n\n"
               "Choose an action. Cooldowns and stamina are enforced by the raid engine.")
    image = CHARACTER_ASSET_DIR / style.get("image", "tanjiro.jpeg")
    try:
        if image.exists():
            with image.open("rb") as photo:
                await bot.send_photo(user_id, photo=photo, caption=caption, parse_mode=ParseMode.HTML, reply_markup=_battle_keyboard(str(raid['raid_id']), user_id, style_id))
        else:
            await bot.send_message(user_id, caption, parse_mode=ParseMode.HTML, reply_markup=_battle_keyboard(str(raid['raid_id']), user_id, style_id))
        return True
    except (Forbidden, TelegramError):
        return False


async def _join_raid(query, context: ContextTypes.DEFAULT_TYPE, raid_id: str) -> None:
    user = query.from_user; raid = _raid_by_id(raid_id)
    if not raid or raid["status"] != "active" or float(raid["ends_at"]) <= time.time():
        await query.answer("This raid has ended.", show_alert=True); return
    _ensure_profile(user); p = _get_profile(user.id)
    if not p or not p["style"]:
        await query.answer("Choose your breathing style first.", show_alert=True)
        try:
            await context.bot.send_message(user.id, "Begin your Slayer journey with /breathing.")
        except TelegramError:
            pass
        return
    try:
        _execute("INSERT INTO rpg_contributions (raid_id,user_id,username,full_name) VALUES (%s,%s,%s,%s) ON CONFLICT(raid_id,user_id) DO NOTHING", (raid_id, user.id, user.username or "", user.full_name or user.first_name or "Slayer")); _commit()
    except Exception:
        _rollback(); await query.answer("Couldn't join this raid right now.", show_alert=True); return
    sent = await _send_private_panel(context.bot, user.id, raid)
    if sent:
        await query.answer("Joined! Your personal controls are in private chat.")
    else:
        await query.answer("Open my private chat and press Start, then tap Join Raid again.", show_alert=True)


async def _resolve_raid(bot, raid_id: str, victory: bool, reason: str = "damage") -> None:
    """Resolve once and distribute all rewards in one database transaction."""
    raid = _raid_by_id(raid_id)
    if not raid or raid["status"] != "active":
        return
    new_status = "won" if victory else "failed"
    boss = BOSSES.get(str(raid["demon_key"]), BOSSES["normal"])
    try:
        _execute("UPDATE rpg_raids SET status=%s, ended_at=CURRENT_TIMESTAMP WHERE raid_id=%s AND status='active'", (new_status, raid_id))
        if cursor.rowcount != 1:
            _rollback()
            return
        _execute("SELECT user_id, damage FROM rpg_contributions WHERE raid_id=%s", (raid_id,))
        contributors = cursor.fetchall() or []
        eligible = [(int(uid), int(damage)) for uid, damage in contributors if int(damage) >= max(20, int(raid["max_hp"]) * 0.05)]
        if victory:
            # Restore everyone who joined, but only qualifying contributors receive victory rewards.
            for user_id, _damage in contributors:
                _execute("UPDATE rpg_profiles SET hp=100, stamina=100 WHERE user_id=%s", (int(user_id),))
            for user_id, damage in eligible:
                _execute("SELECT legendary_focus FROM rpg_profiles WHERE user_id=%s", (user_id,))
                focus_row = cursor.fetchone()
                focus = (focus_row[0] if focus_row else "") or ""
                _execute("UPDATE rpg_profiles SET xp=xp+%s, currency=currency+%s, demon_defeats=demon_defeats+1, wins=wins+1, updated_at=CURRENT_TIMESTAMP WHERE user_id=%s", (int(boss["xp"]), int(boss["reward"]), user_id))
                _execute("SELECT xp FROM rpg_profiles WHERE user_id=%s", (user_id,))
                xp_row = cursor.fetchone()
                xp_now = int(xp_row[0] or 0) if xp_row else 0
                _execute("UPDATE rpg_profiles SET corps_rank=%s WHERE user_id=%s", (_rank_from_xp(xp_now), user_id))
                if focus in {"sun", "moon"}:
                    progress_col = "sun_progress" if focus == "sun" else "moon_progress"
                    _execute(f"UPDATE rpg_profiles SET {progress_col}=CASE WHEN {progress_col}+1 > 100 THEN 100 ELSE {progress_col}+1 END WHERE user_id=%s", (user_id,))
                    _execute(f"SELECT {progress_col}, unlocked_styles FROM rpg_profiles WHERE user_id=%s", (user_id,))
                    progress_row = cursor.fetchone()
                    if progress_row and int(progress_row[0]) >= 100:
                        unlocked = [x for x in (progress_row[1] or "").split(",") if x]
                        if focus not in unlocked:
                            unlocked.append(focus)
                            _execute("UPDATE rpg_profiles SET unlocked_styles=%s WHERE user_id=%s", (",".join(sorted(set(unlocked))), user_id))
        else:
            for user_id, _damage in contributors:
                _execute("UPDATE rpg_profiles SET losses=losses+1, hp=100, stamina=100 WHERE user_id=%s", (int(user_id),))
        _commit()
    except Exception:
        _rollback()
        log.exception("Atomic Demon Hunt RPG raid resolution failed for %s", raid_id)
        return

    if victory:
        caption = (f"🏆 <b>DEMON DEFEATED!</b>\n\n👹 {html.escape(str(raid['demon_name']))} has fallen.\n"
                   f"⚔️ Eligible contributors rewarded: <b>{len(eligible)}</b>\n💎 Each eligible Slayer earned {int(boss['reward'])} RPG coins and {int(boss['xp'])} EXP.\n"
                   "🌞/🌙 Legendary path progress counts at most once per successful raid.")
    else:
        caption = (f"💀 <b>RAID FAILED</b>\n\n👹 {html.escape(str(raid['demon_name']))} survived.\n"
                   f"Reason: {'time limit reached' if reason == 'time' else 'the raid could not be completed'}.\n"
                   "No victory rewards or personal demon defeats were awarded.")
    try:
        if raid.get("message_id"):
            await bot.send_message(chat_id=int(raid["chat_id"]), text=caption, parse_mode=ParseMode.HTML, reply_to_message_id=int(raid["message_id"]))
        else:
            await bot.send_message(chat_id=int(raid["chat_id"]), text=caption, parse_mode=ParseMode.HTML)
    except TelegramError:
        log.warning("Could not post RPG raid result for %s", raid_id)


async def _combat_action(query, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    if len(parts) != 5:
        await query.answer("Invalid action button.", show_alert=True); return
    _, _, raid_id, owner_text, action = parts
    user = query.from_user
    try: owner_id = int(owner_text)
    except ValueError: await query.answer("Invalid player.", show_alert=True); return
    if user.id != owner_id:
        await query.answer("These combat controls belong to another Slayer.", show_alert=True); return
    raid = _raid_by_id(raid_id)
    if not raid or raid["status"] != "active":
        await query.answer("This raid has ended.", show_alert=True); return
    if float(raid["ends_at"]) <= time.time():
        await _resolve_raid(context.bot, raid_id, victory=False, reason="time")
        await query.answer("Time is up. The raid has ended.", show_alert=True); return
    if not _joined(raid_id, user.id):
        await query.answer("Join the raid first.", show_alert=True); return
    _ensure_profile(user)
    _execute("SELECT style, hp, stamina FROM rpg_profiles WHERE user_id=%s", (user.id,)); p = cursor.fetchone()
    if not p or not p[0]: await query.answer("Choose a style first with /breathing.", show_alert=True); return
    style_id, hp, stamina = p; hp, stamina = int(hp), int(stamina)
    if hp <= 0: await query.answer("You're knocked out. Use /rpguse potion if you have one.", show_alert=True); return
    _execute("SELECT damage, actions, last_attack, last_form, last_ultimate, defending_until FROM rpg_contributions WHERE raid_id=%s AND user_id=%s", (raid_id, user.id)); c = cursor.fetchone()
    if not c: await query.answer("Join the raid first.", show_alert=True); return
    damage_total, actions, last_attack, last_form, last_ultimate, defending_until = c
    now = time.time(); damage = 0; cost = 0; cooldown_col = None; cooldown = 0
    style_bonus = {"mist": 8, "water": 5, "flame": 9, "thunder": 11, "wind": 8, "stone": 7, "beast": 9, "love": 7, "serpent": 8, "sound": 9, "flower": 6, "insect": 7, "sun": 14, "moon": 13}.get(style_id, 5)
    _execute("SELECT quantity FROM rpg_inventory WHERE user_id=%s AND item_key='nichirin'", (user.id,)); weapon_row = cursor.fetchone(); weapon_bonus = 10 if weapon_row and int(weapon_row[0]) > 0 else 0
    _execute("SELECT quantity FROM rpg_inventory WHERE user_id=%s AND item_key='haori'", (user.id,)); armor_row = cursor.fetchone(); armor_bonus = 3 if armor_row and int(armor_row[0]) > 0 else 0
    if action == "attack": cost, cooldown_col, cooldown = 10, "last_attack", 5; damage = random.randint(28, 42) + style_bonus + weapon_bonus
    elif action == "form": cost, cooldown_col, cooldown = 25, "last_form", 20; damage = random.randint(55, 78) + style_bonus * 2 + weapon_bonus
    elif action == "ultimate": cost, cooldown_col, cooldown = 45, "last_ultimate", 90; damage = random.randint(120, 165) + style_bonus * 3 + weapon_bonus
    elif action == "defend": cost = 5
    else: await query.answer("Unknown action.", show_alert=True); return
    if cooldown_col:
        last = float({"last_attack": last_attack, "last_form": last_form, "last_ultimate": last_ultimate}[cooldown_col] or 0)
        wait = cooldown - (now - last)
        if wait > 0: await query.answer(f"Cooldown: {int(wait)+1}s remaining.", show_alert=True); return
    if stamina < cost:
        await query.answer(f"Not enough stamina. Need {cost}; you have {stamina}.", show_alert=True); return
    if action == "defend":
        _execute("UPDATE rpg_profiles SET stamina=CASE WHEN stamina-%s+20 > 100 THEN 100 ELSE stamina-%s+20 END WHERE user_id=%s", (cost, cost, user.id))
        _execute("UPDATE rpg_contributions SET defending_until=%s, actions=actions+1 WHERE raid_id=%s AND user_id=%s", (now+30, raid_id, user.id))
        _commit(); await query.answer("Defense stance active for 30 seconds. +15 stamina.")
        return
    # Resolve damage against the shared raid HP; no user-provided damage is trusted.
    new_hp = max(0, int(raid["hp"]) - damage)
    retaliation = max(1, random.randint(5, 12) + {"easy":0,"normal":3,"hard":6,"upper":9,"final":12}.get(str(raid["demon_key"]), 3) - armor_bonus)
    if float(defending_until or 0) > now: retaliation = max(1, retaliation // 3)
    new_player_hp = max(0, hp - retaliation)
    new_stamina = max(0, stamina - cost)
    try:
        _execute("UPDATE rpg_raids SET hp=%s WHERE raid_id=%s AND status='active'", (new_hp, raid_id))
        _execute(f"UPDATE rpg_contributions SET damage=damage+%s, actions=actions+1, {cooldown_col}=%s WHERE raid_id=%s AND user_id=%s", (damage, now, raid_id, user.id))
        _execute("UPDATE rpg_profiles SET hp=%s, stamina=%s WHERE user_id=%s", (new_player_hp, new_stamina, user.id))
        _commit()
    except Exception:
        _rollback(); log.exception("RPG combat update failed"); await query.answer("Action failed safely; try again.", show_alert=True); return
    if new_hp <= 0:
        await _resolve_raid(context.bot, raid_id, victory=True)
        await query.answer(f"Critical hit! {damage} damage — demon defeated!")
        return
    await query.answer(f"{damage} damage! Demon HP: {new_hp:,}. You took {retaliation} damage.")
    # Refresh shared raid card by sending a concise update, avoiding editing someone else's style UI.
    if int(raid.get("message_id") or 0):
        try:
            await context.bot.send_message(chat_id=int(raid["chat_id"]), text=f"⚔️ <b>{html.escape(str(raid['demon_name']))}</b> · ❤️ {new_hp:,}/{int(raid['max_hp']):,} HP\n{html.escape(user.full_name)} dealt <b>{damage}</b> damage.\n⏳ { _remaining(float(raid['ends_at'])) } left.", parse_mode=ParseMode.HTML, reply_to_message_id=int(raid["message_id"]))
        except TelegramError:
            pass


async def demon_hunt_rpg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data: return
    parts = query.data.split(":")
    if len(parts) < 2 or parts[0] != PREFIX: return
    action = parts[1]
    try:
        if action == "join" and len(parts) == 3:
            await _join_raid(query, context, parts[2]); return
        if action == "status" and len(parts) == 3:
            raid = _raid_by_id(parts[2])
            if not raid: await query.answer("Raid not found.", show_alert=True); return
            await query.answer(); await query.message.reply_text(_raid_caption(raid), parse_mode=ParseMode.HTML, reply_markup=_raid_keyboard(str(raid['raid_id']))); return
        if action == "open_styles":
            await query.answer();
            try: await context.bot.send_message(query.from_user.id, "Use /breathing to open your personal style menu.")
            except TelegramError: pass
            return
        if action == "style" and len(parts) == 3:
            user = query.from_user; style = parts[2]
            if style not in STYLE_INFO:
                await query.answer("That style is not available.", show_alert=True); return
            _ensure_profile(user); p = _get_profile(user.id)
            if not p["style_finalized"] and style in {"sun", "moon"}:
                await query.answer("Sun and Moon are legendary paths, not initial styles.", show_alert=True); return
            if p["style_finalized"]:
                if style not in _unlocked_styles(p):
                    await query.answer("Unlock this style first with /rpgtrain <style>, or use your one-time correction.", show_alert=True); return
            if _in_active_raid(user.id): await query.answer("You cannot change style during an active raid.", show_alert=True); return
            unlocked = _unlocked_styles(p)
            if style not in unlocked: unlocked.append(style)
            _execute("UPDATE rpg_profiles SET style=%s, style_finalized=1, unlocked_styles=%s, updated_at=CURRENT_TIMESTAMP WHERE user_id=%s", (style, ",".join(sorted(set(unlocked))), user.id)); _commit()
            await query.answer("Breathing style equipped.")
            info = STYLE_INFO[style]
            try: await query.edit_message_text(f"{info['emoji']} <b>{html.escape(info['name'])} selected.</b>\n{html.escape(info['forms'])}", parse_mode=ParseMode.HTML)
            except BadRequest: pass
            try:
                await context.bot.send_message(user.id, f"{info['emoji']} <b>{html.escape(info['title'])}</b>\nYour personal style theme is active. Join a raid to get combat buttons.", parse_mode=ParseMode.HTML)
            except TelegramError: pass
            return
        if action == "correction":
            user = query.from_user; _ensure_profile(user); p = _get_profile(user.id)
            if not p["style_finalized"]: await query.answer("Choose a style first.", show_alert=True); return
            if p["free_correction_used"]: await query.answer("Your one-time correction has already been used.", show_alert=True); return
            if _in_active_raid(user.id): await query.answer("Finish your active raid before changing styles.", show_alert=True); return
            await query.answer(); await query.message.reply_text("🔄 <b>ONE-TIME FREE CORRECTION</b> — select the style you meant to choose.", parse_mode=ParseMode.HTML, reply_markup=_style_keyboard(p, correction=True)); return
        if action == "correct" and len(parts) == 3:
            user = query.from_user; style = parts[2]
            if style not in STANDARD_STYLES:
                await query.answer("Choose a standard style for your free correction.", show_alert=True); return
            _ensure_profile(user); p = _get_profile(user.id)
            if not p["style_finalized"]: await query.answer("Choose a style first.", show_alert=True); return
            if p["free_correction_used"]: await query.answer("Your one-time correction has already been used.", show_alert=True); return
            if _in_active_raid(user.id): await query.answer("Finish your active raid before changing styles.", show_alert=True); return
            unlocked = _unlocked_styles(p)
            if style not in unlocked: unlocked.append(style)
            _execute("UPDATE rpg_profiles SET style=%s, free_correction_used=1, unlocked_styles=%s, updated_at=CURRENT_TIMESTAMP WHERE user_id=%s", (style, ",".join(sorted(set(unlocked))), user.id)); _commit()
            info = STYLE_INFO[style]
            await query.answer("Free correction used. New style equipped.")
            try: await query.edit_message_text(f"✅ <b>Style corrected:</b> {info['emoji']} {html.escape(info['name'])}\nYour one-time free correction has now been used.", parse_mode=ParseMode.HTML)
            except BadRequest: pass
            try: await context.bot.send_message(user.id, f"{info['emoji']} <b>{html.escape(info['title'])}</b>\nYour personal style theme is active.", parse_mode=ParseMode.HTML)
            except TelegramError: pass
            return
        if action == "training":
            await query.answer("Use /rpgtrain <style> to unlock another style for 250 RPG coins.", show_alert=True); return
        if action == "focus" and len(parts) == 3:
            user = query.from_user; focus = parts[2]
            if focus not in {"sun", "moon"}: await query.answer("Invalid path.", show_alert=True); return
            if _in_active_raid(user.id): await query.answer("Choose a legendary path between raids.", show_alert=True); return
            _ensure_profile(user); _execute("UPDATE rpg_profiles SET legendary_focus=%s WHERE user_id=%s", (focus, user.id)); _commit()
            await query.answer(f"{focus.title()} path selected. Successful eligible raids count toward it."); return
        if action == "buy" and len(parts) == 3:
            await query.answer(); await _buy_item(query.from_user, parts[2], query.message.reply_text); return
        if action == "use" and len(parts) == 5:
            _, _, raid_id, owner_id, item_key = parts
            if int(owner_id) != query.from_user.id: await query.answer("These controls belong to another Slayer.", show_alert=True); return
            raid = _raid_by_id(raid_id)
            if not raid or raid["status"] != "active" or float(raid["ends_at"]) <= time.time():
                await query.answer("This raid has ended.", show_alert=True); return
            if item_key not in {"potion", "ration"}: await query.answer("Invalid consumable.", show_alert=True); return
            if not _joined(raid_id, query.from_user.id): await query.answer("Join the raid first.", show_alert=True); return
            _ensure_profile(query.from_user); _execute("SELECT quantity FROM rpg_inventory WHERE user_id=%s AND item_key=%s", (query.from_user.id, item_key)); row = cursor.fetchone()
            if not row or int(row[0]) <= 0: await query.answer("You don't have this item.", show_alert=True); return
            _execute("SELECT hp, stamina FROM rpg_profiles WHERE user_id=%s", (query.from_user.id,)); hp, stamina = cursor.fetchone()
            if item_key == "potion": hp = min(100, int(hp)+35)
            elif item_key == "ration": stamina = min(100, int(stamina)+35)
            _execute("UPDATE rpg_profiles SET hp=%s, stamina=%s WHERE user_id=%s", (hp, stamina, query.from_user.id)); _execute("UPDATE rpg_inventory SET quantity=quantity-1 WHERE user_id=%s AND item_key=%s AND quantity>0", (query.from_user.id, item_key)); _commit()
            await query.answer(f"Used {item_key}. HP {hp}/100 · stamina {stamina}/100."); return
        if action == "act":
            await _combat_action(query, context, parts); return
        await query.answer("Unknown Demon Hunt RPG button.", show_alert=True)
    except Exception:
        _rollback(); log.exception("Demon Hunt RPG callback failed")
        try: await query.answer("That action failed safely. Please try again.", show_alert=True)
        except TelegramError: pass


def register_demon_hunt_rpg_handlers(application: Application) -> None:
    """Register RPG commands; call from bot.main() exactly once."""
    application.add_handler(CommandHandler("launchhunt", launch_hunt_command))
    application.add_handler(CommandHandler("raid", raid_status_command))
    application.add_handler(CommandHandler("raidstatus", raid_status_command))
    application.add_handler(CommandHandler("breathing", breathing_command))
    application.add_handler(CommandHandler("rpgprofile", rpg_profile_command))
    application.add_handler(CommandHandler("rpgstore", rpg_store_command))
    application.add_handler(CommandHandler("rpgbuy", rpg_buy_command))
    application.add_handler(CommandHandler("rpginventory", rpg_inventory_command))
    application.add_handler(CommandHandler("rpguse", rpg_use_command))
    application.add_handler(CommandHandler("rpgtrain", rpg_train_command))
    application.add_handler(CommandHandler("legendary", legendary_command))
    application.add_handler(CommandHandler("rpgleaderboard", rpg_leaderboard_command))
    application.add_handler(CommandHandler("rpghelp", rpg_help_command))
    application.add_handler(CallbackQueryHandler(demon_hunt_rpg_callback, pattern=r"^dhrpg:"))
