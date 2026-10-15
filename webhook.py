import os
import secrets

from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import monitoring
from telegram import Update
from demonslayer_hunt import initialize_demon_hunt
from music import runtime as music_runtime
from music.voice import VoiceChat
from music.handlers import on_stream_end

import bot


app = FastAPI()
monitor_security = HTTPBasic()

WEBHOOK_URL = os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
ptb_app = None

MONITOR_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Muichiro · Live Monitor</title>
<style>
:root{color-scheme:dark;--bg:#090d16;--card:#111827;--line:#263246;--muted:#9aa9bd;--text:#eef4ff;--accent:#8b9cff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top,#18233b 0,#090d16 55%);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--text)}
header{padding:26px 20px 18px;max-width:1180px;margin:auto}h1{margin:0;font-size:clamp(24px,4vw,34px);letter-spacing:.02em}header p{margin:7px 0;color:var(--muted)}.status{display:inline-block;margin-top:10px;padding:5px 10px;border:1px solid #285a46;border-radius:999px;color:#8af0bd;background:#123326;font-size:12px}
main{max-width:1180px;margin:auto;padding:0 20px 30px;display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr))}.panel{background:rgba(17,24,39,.92);border:1px solid var(--line);border-radius:16px;overflow:hidden;min-width:0;box-shadow:0 14px 36px #0003}.panel h2{font-size:16px;margin:0;padding:15px 16px;border-bottom:1px solid var(--line)}.panel h2 span{font-size:12px;color:var(--muted);font-weight:500;display:block;margin-top:3px}.entries{padding:10px;max-height:66vh;min-height:220px;overflow:auto}.entry{padding:10px 11px;margin-bottom:8px;border:1px solid #263246;border-radius:10px;background:#0b1220;overflow-wrap:anywhere}.entry:last-child{margin-bottom:0}.meta{font-size:11px;color:var(--muted);margin-bottom:5px;display:flex;gap:8px;flex-wrap:wrap}.level{font-weight:700;color:#b9c5ff}.message{white-space:pre-wrap}.empty{padding:24px 10px;color:var(--muted);text-align:center}.foot{max-width:1180px;padding:0 20px 26px;margin:auto;color:var(--muted);font-size:12px}
</style></head><body>
<header><h1>🎧 Muichiro Live Monitor</h1><p>Read-only monitoring · automatically refreshes every 5 seconds</p><div class="status">● Dashboard connected</div></header>
<main>
<section class="panel"><h2>🎵 01 · Music Logs <span>Playback, queue, audio delivery and player errors</span></h2><div id="music" class="entries"><div class="empty">Waiting for music events…</div></div></section>
<section class="panel"><h2>📊 02 · Bot Activity & Health <span>Commands, users/chats, webhook activity and errors</span></h2><div id="activity" class="entries"><div class="empty">Waiting for activity…</div></div></section>
<section class="panel"><h2>🖥️ 03 · Render / Application Logs <span>Mirrored app stdout, stderr and Python logging</span></h2><div id="render" class="entries"><div class="empty">Waiting for application output…</div></div></section>
</main><div class="foot">Privacy: message text is not stored in general activity logs; commands and chat/user metadata may be shown. Logs are held in memory and clear when the service restarts. Render build/deploy/platform logs remain in the Render dashboard.</div>
<script>
function renderList(id,items){const box=document.getElementById(id);box.replaceChildren();if(!items||!items.length){const e=document.createElement('div');e.className='empty';e.textContent='No entries yet.';box.appendChild(e);return}for(const item of items){const card=document.createElement('div');card.className='entry';const meta=document.createElement('div');meta.className='meta';const time=document.createElement('span');time.textContent=item.time||'';const level=document.createElement('span');level.className='level';level.textContent=item.level||'INFO';meta.append(time,level);const message=document.createElement('div');message.className='message';message.textContent=item.message||'';card.append(meta,message);box.appendChild(card)}}
async function refresh(){try{const response=await fetch('/monitor/data',{cache:'no-store'});if(!response.ok)throw new Error('HTTP '+response.status);const data=await response.json();renderList('music',data.music);renderList('activity',data.activity);renderList('render',data.render)}catch(e){for(const id of ['music','activity','render']){const box=document.getElementById(id);const msg=document.createElement('div');msg.className='empty';msg.textContent='Monitor data unavailable. Check authentication and service status.';box.replaceChildren(msg)}}}
refresh();setInterval(refresh,5000);
</script></body></html>'''


def require_monitor_auth(credentials: HTTPBasicCredentials = Depends(monitor_security)):
    expected_user = os.environ.get("MONITOR_USERNAME", "").strip()
    expected_password = os.environ.get("MONITOR_PASSWORD", "")
    if not expected_user or not expected_password:
        raise HTTPException(status_code=503, detail="Set MONITOR_USERNAME and MONITOR_PASSWORD to enable the protected monitor dashboard.")
    valid_user = secrets.compare_digest(credentials.username.encode("utf-8"), expected_user.encode("utf-8"))
    valid_password = secrets.compare_digest(credentials.password.encode("utf-8"), expected_password.encode("utf-8"))
    if not (valid_user and valid_password):
        raise HTTPException(status_code=401, detail="Invalid monitoring credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


@app.get("/", response_class=HTMLResponse)
async def home(_: str = Depends(require_monitor_auth)):
    return HTMLResponse(MONITOR_HTML)


@app.get("/monitor/data")
async def monitor_data(_: str = Depends(require_monitor_auth)):
    return monitoring.snapshot()


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

    update = Update.de_json(data, ptb_app.bot)
    summary = monitoring.describe_update(update)
    if summary:
        monitoring.activity_event(summary)
    else:
        monitoring.activity_event("Received Telegram update (no user/chat metadata available).")

    await ptb_app.update_queue.put(update)

    return {"ok": True}

@app.on_event("startup")
async def startup():

    global ptb_app

    monitoring.install_render_capture()
    monitoring.activity_event("Muichiro service startup beginning.")

    # Build bot application and all handlers
    ptb_app = bot.main()

    print("Bot application created ✅")
    monitoring.activity_event("Telegram bot application created.")

    # Initialize PTB
    await ptb_app.initialize()

    # Start PTB update processing
    await ptb_app.start()

    print("PTB application started ✅")
    monitoring.activity_event("Telegram update processing started.")

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
    monitoring.activity_event("Music voice-chat layer started.")

    await initialize_demon_hunt (ptb_app)
    print("Demon hunt ready")
    monitoring.activity_event("Demon hunt subsystem ready.")

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

    monitoring.activity_event("Muichiro service shutdown requested.", "WARNING")
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
    monitoring.activity_event("Telegram bot application shutdown complete.")