# Authorised by NyxLuciferX02

from html import escape

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes

from database import db, cursor


# ==========================================================
# DEFAULT WELCOME
# ==========================================================

DEFAULT_WELCOME = (
    "╭━━━━━━━━━━━━━━━━╮\n"
    "       🌸 <b>WELCOME</b> 🌸\n"
    "╰━━━━━━━━━━━━━━━━╯\n\n"

    "👋 Hello {mention}!\n\n"

    "✨ Welcome to <b>{group}</b>!\n\n"

    "👥 You are member <b>#{count}</b>\n\n"

    "💫 Hope you enjoy your stay here!\n"
    "🤝 Have fun and make some friends!\n\n"

    "╰━━━━━━━━━━━━━━━━╯"
)


# ==========================================================
# SET WELCOME
# ==========================================================

async def setwelcome(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_chat:
        return

    chat = update.effective_chat

    if chat.type not in ["group", "supergroup"]:
        return

    # ------------------------------------------------------
    # CHECK ADMIN
    # ------------------------------------------------------

    member = await context.bot.get_chat_member(
        chat.id,
        update.effective_user.id
    )

    if member.status not in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    ):

        await update.message.reply_text(
            "❌ Only admins can use this command."
        )
        return

    # ------------------------------------------------------
    # MUST REPLY TO MESSAGE
    # ------------------------------------------------------

    if not update.message.reply_to_message:

        await update.message.reply_text(
            "❌ Reply to a text, photo, video or GIF "
            "with /setwelcome."
        )
        return

    msg = update.message.reply_to_message

    media_type = "text"
    file_id = None
    text = ""

    # ------------------------------------------------------
    # PHOTO
    # ------------------------------------------------------

    if msg.photo:

        media_type = "photo"
        file_id = msg.photo[-1].file_id
        text = msg.caption or ""

    # ------------------------------------------------------
    # VIDEO
    # ------------------------------------------------------

    elif msg.video:

        media_type = "video"
        file_id = msg.video.file_id
        text = msg.caption or ""

    # ------------------------------------------------------
    # GIF / ANIMATION
    # ------------------------------------------------------

    elif msg.animation:

        media_type = "animation"
        file_id = msg.animation.file_id
        text = msg.caption or ""

    # ------------------------------------------------------
    # TEXT
    # ------------------------------------------------------

    elif msg.text:

        media_type = "text"
        text = msg.text

    else:

        await update.message.reply_text(
            "❌ Unsupported message type."
        )
        return

    chat_id = chat.id

    try:

        # ==================================================
        # POSTGRESQL UPSERT
        # ==================================================

        cursor.execute(
            """
            INSERT INTO welcome_settings
            (
                chat_id,
                enabled,
                text,
                file_id,
                media_type
            )
            VALUES (%s, 1, %s, %s, %s)

            ON CONFLICT (chat_id)
            DO UPDATE SET
                text = EXCLUDED.text,
                file_id = EXCLUDED.file_id,
                media_type = EXCLUDED.media_type
            """,
            (
                chat_id,
                text,
                file_id,
                media_type,
            )
        )

        db.commit()

        print(
            f"✅ Welcome saved | "
            f"chat={chat_id} | "
            f"type={media_type}"
        )

        await update.message.reply_text(
            "✅ Welcome message saved successfully!"
        )

    except Exception as e:

        db.rollback()

        print(
            f"❌ SetWelcome database error: {e}"
        )

        await update.message.reply_text(
            "❌ Failed to save the welcome message."
        )


# ==========================================================
# WELCOME ON / OFF
# ==========================================================

async def welcome_toggle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_chat:
        return

    chat = update.effective_chat

    if chat.type not in ["group", "supergroup"]:
        return

    # ------------------------------------------------------
    # ADMIN CHECK
    # ------------------------------------------------------

    member = await context.bot.get_chat_member(
        chat.id,
        update.effective_user.id
    )

    if member.status not in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    ):

        await update.message.reply_text(
            "❌ Only admins can use this command."
        )
        return

    # ------------------------------------------------------
    # ARGUMENT CHECK
    # ------------------------------------------------------

    if not context.args:

        await update.message.reply_text(
            "⚙️ Usage:\n"
            "/welcome on\n"
            "/welcome off"
        )
        return

    option = context.args[0].lower()

    if option not in ("on", "off"):

        await update.message.reply_text(
            "❌ Use only:\n"
            "/welcome on\n"
            "/welcome off"
        )
        return

    chat_id = chat.id
    enabled = 1 if option == "on" else 0

    try:

        # ==================================================
        # CREATE SETTINGS IF NEEDED
        # ==================================================

        cursor.execute(
            """
            INSERT INTO welcome_settings
            (
                chat_id,
                enabled,
                text,
                file_id,
                media_type
            )
            VALUES (%s, 1, NULL, NULL, 'text')

            ON CONFLICT (chat_id)
            DO NOTHING
            """,
            (chat_id,)
        )

        # ==================================================
        # UPDATE STATUS
        # ==================================================

        cursor.execute(
            """
            UPDATE welcome_settings
            SET enabled = %s
            WHERE chat_id = %s
            """,
            (
                enabled,
                chat_id
            )
        )

        db.commit()

        print(
            f"⚙️ Welcome {'ON' if enabled else 'OFF'} | "
            f"chat={chat_id}"
        )

        if enabled:

            await update.message.reply_text(
                "✅ Welcome messages are now ON."
            )

        else:

            await update.message.reply_text(
                "🔕 Welcome messages are now OFF."
            )

    except Exception as e:

        db.rollback()

        print(
            f"❌ Welcome toggle database error: {e}"
        )

        await update.message.reply_text(
            "❌ Failed to change welcome settings."
        )


# ==========================================================
# WELCOME NEW MEMBERS
# ==========================================================

async def welcome_new_members(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    members = update.message.new_chat_members

    if not members:
        return

    chat = update.effective_chat

    if not chat:
        return

    print("🔥 WELCOME HANDLER TRIGGERED!")

    # ------------------------------------------------------
    # GET BOT INFORMATION
    # ------------------------------------------------------

    me = await context.bot.get_me()

    # ------------------------------------------------------
    # BUTTON
    # ------------------------------------------------------

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Add Me",
                url=(
                    f"https://t.me/{me.username}"
                    "?startgroup=true"
                )
            )
        ]
    ])

    # ------------------------------------------------------
    # CHECK WELCOME SETTINGS
    # ------------------------------------------------------

    try:

        cursor.execute(
            """
            SELECT
                enabled,
                text,
                file_id,
                media_type
            FROM welcome_settings
            WHERE chat_id = %s
            """,
            (chat.id,)
        )

        data = cursor.fetchone()

    except Exception as e:

        db.rollback()

        print(
            f"❌ Welcome settings database error: {e}"
        )

        data = None

    # ------------------------------------------------------
    # WELCOME DISABLED
    # ------------------------------------------------------

    if data and data[0] == 0:

        print("🔕 Welcome is OFF.")

        return

    # ------------------------------------------------------
    # MEMBER COUNT
    # ------------------------------------------------------

    try:

        count = await context.bot.get_chat_member_count(
            chat.id
        )

    except Exception:

        count = "?"

    # ------------------------------------------------------
    # PROCESS MEMBERS
    # ------------------------------------------------------

    for user in members:

        # Don't welcome the bot
        if user.id == me.id:
            continue

        print(
            f"👤 New member detected: "
            f"{user.full_name} ({user.id})"
        )

        # ==================================================
        # USER VARIABLES
        # ==================================================

        mention = user.mention_html()

        first = escape(
            user.first_name or ""
        )

        firstname = first

        lastname = escape(
            user.last_name or ""
        )

        username = (
            f"@{escape(user.username)}"
            if user.username
            else mention
        )

        group_name = escape(
            chat.title or "this group"
        )

        # ==================================================
        # CHOOSE MESSAGE
        # ==================================================

        if data:

            (
                enabled,
                saved_text,
                saved_file_id,
                saved_media_type
            ) = data

            file_id = saved_file_id
            media_type = saved_media_type or "text"
            welcome_text = (
                saved_text
                or DEFAULT_WELCOME
            )

        else:

            file_id = None
            media_type = "text"
            welcome_text = DEFAULT_WELCOME

        # ==================================================
        # REPLACE VARIABLES
        # ==================================================

        welcome_text = welcome_text.replace(
            "{mention}",
            mention
        )

        welcome_text = welcome_text.replace(
            "{first}",
            first
        )

        welcome_text = welcome_text.replace(
            "{firstname}",
            firstname
        )

        welcome_text = welcome_text.replace(
            "{last}",
            lastname
        )

        welcome_text = welcome_text.replace(
            "{lastname}",
            lastname
        )

        welcome_text = welcome_text.replace(
            "{username}",
            username
        )

        welcome_text = welcome_text.replace(
            "{group}",
            group_name
        )

        welcome_text = welcome_text.replace(
            "{count}",
            str(count)
        )

        # ==================================================
        # SEND PHOTO
        # ==================================================

        if media_type == "photo" and file_id:

            await context.bot.send_photo(
                chat_id=chat.id,
                photo=file_id,
                caption=welcome_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

        # ==================================================
        # SEND VIDEO
        # ==================================================

        elif media_type == "video" and file_id:

            await context.bot.send_video(
                chat_id=chat.id,
                video=file_id,
                caption=welcome_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

        # ==================================================
        # SEND GIF
        # ==================================================

        elif media_type == "animation" and file_id:

            await context.bot.send_animation(
                chat_id=chat.id,
                animation=file_id,
                caption=welcome_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

        # ==================================================
        # SEND TEXT
        # ==================================================

        else:

            await context.bot.send_message(
                chat_id=chat.id,
                text=welcome_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

        print("✅ Welcome message sent!")


# ==========================================================
# DEBUG
# ==========================================================

async def debug_updates(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    print("🔥 UPDATE RECEIVED!")