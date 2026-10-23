"""Compatibility entrypoint for the Demon Hunt RPG UI.

The live, persistent UI now lives in demon_hunt_engine.py so style selection,
private player panels, callbacks, combat state and database state stay connected.
Importing this module does not register duplicate handlers.
"""
from demon_hunt_engine import (
    breathing_command as show_style_picker,
    demon_hunt_rpg_callback as handle_demon_hunt_ui_callback,
    register_demon_hunt_rpg_handlers as register_demon_hunt_ui_handlers,
    _active_raid,
    _send_private_panel,
)


async def show_private_battle_panel(update, context, demon_name="Unknown Demon"):
    """Open a private combat panel for the caller if their group has an active raid."""
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return
    raid = _active_raid(chat.id) if chat and chat.type != "private" else None
    if not raid:
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="No active raid found. Join a group raid first with /launchhunt and tap Join Raid.",
            )
        except Exception:
            if update.effective_message:
                await update.effective_message.reply_text(
                    "Open my private chat and press Start first, then join an active raid."
                )
        return
    sent = await _send_private_panel(context.bot, user.id, raid)
    if not sent and update.effective_message:
        await update.effective_message.reply_text(
            "Open my private chat and press Start first so I can send your personal battle controls."
        )
