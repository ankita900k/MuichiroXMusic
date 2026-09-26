import os

from fastapi import FastAPI, Request, Header, HTTPException
from telegram import Update
from demonslayer_hunt import initialize_demon_hunt
from music import runtime as music_runtime
from music.voice import VoiceChat
from music.handlers import on_stream_end

import bot


app = FastAPI()

WEBHOOK_URL = os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
ptb_app = None

@app.get("/")
async def home():
    return {
        "status": "online",
        "bot": "Muichiro"
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }


@app.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        default=None
    )
):

    if WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
            raise HTTPException(
                status_code=403,
                detail="Forbidden"
            )

    data = await request.json()

    print("🔥 UPDATE RECEIVED!")

    update = Update.de_json(
        data,
        ptb_app.bot
    )

    await ptb_app.update_queue.put(update)

    return {"ok": True}

@app.on_event("startup")
async def startup():

    global ptb_app

    # Build bot application and all handlers
    ptb_app = bot.main()

    print("Bot application created ✅")

    # Initialize PTB
    await ptb_app.initialize()

    # Start PTB update processing
    await ptb_app.start()

    print("PTB application started ✅")

    # Start the separate MTProto user-session client used only for
    # Telegram voice-chat playback.
    try:
        api_id = int(os.environ.get("API_ID", "0"))
    except ValueError:
        api_id = 0

    music_runtime.voice = VoiceChat(
        api_id=api_id,
        api_hash=os.environ.get("API_HASH", ""),
        session_string=os.environ.get("SESSION_STRING", ""),
    )
    await music_runtime.voice.start()
    music_runtime.voice.register_stream_end(
        lambda chat_id: on_stream_end(chat_id, ptb_app.bot)
    )
    print("Music VC layer started ✅")

    await initialize_demon_hunt (ptb_app)
    print("Demon hunt ready")

    if not WEBHOOK_URL:
        print("⚠️ WEBHOOK_URL not configured.")
        print("🌐 Local webhook server is running.")
        return

    webhook_endpoint = (
        WEBHOOK_URL.rstrip("/")
        + "/telegram"
    )

    await ptb_app.bot.set_webhook(
        url=webhook_endpoint,
        allowed_updates=Update.ALL_TYPES,
        secret_token=WEBHOOK_SECRET
    )

    print("====================================")
    print("🌐 MUICHIRO WEBHOOK STARTED")
    print("====================================")
    print(f"Webhook: {webhook_endpoint}")
    print("Bot: Muichiro")
    print("Status: ONLINE ✅")
    print("====================================")

@app.on_event("shutdown")
async def shutdown():

    global ptb_app

    print("🛑 PTB application shutting down...")

    if music_runtime.voice:
        try:
            await music_runtime.voice.stop()
        except Exception as e:
            print(f"⚠️ Music shutdown error: {e}")
        finally:
            music_runtime.voice = None

    if ptb_app:
        try:
            await ptb_app.stop()
        except Exception as e:
            print(f"⚠️ PTB stop error: {e}")

        try:
            await ptb_app.shutdown()
        except Exception as e:
            print(f"⚠️ PTB shutdown error: {e}")

    print("✅ PTB application shutdown complete.")