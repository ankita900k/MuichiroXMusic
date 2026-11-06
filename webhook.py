import os
from dotenv import load_dotenv

load_dotenv()
import secrets
import json
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, Response
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
<title>Muichiro HQ · Monitor</title>
<style>
:root{color-scheme:dark;--bg:#050b0d;--card:#0c1719;--card2:#101f21;--line:#1d3c3e;--muted:#8ba8a8;--text:#e6fffb;--teal:#72e6d2;--teal2:#2db8a6;--red:#ff8790;--gold:#f1d58a}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 15% 0%,#12383a 0,transparent 38%),radial-gradient(ellipse at 95% 15%,#15292c 0,transparent 32%),var(--bg);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--text);min-height:100vh}
body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.14;background:repeating-linear-gradient(115deg,transparent 0 80px,#a7fff8 81px 82px,transparent 83px 180px);mask-image:linear-gradient(to bottom,black,transparent 65%)}
.wrap{max-width:1440px;margin:auto;padding:22px}header{display:flex;justify-content:space-between;gap:18px;align-items:center;flex-wrap:wrap;margin-bottom:20px}.brand{display:flex;align-items:center;gap:14px}.mark{width:48px;height:48px;border-radius:15px;background:linear-gradient(145deg,#183e40,#0b1d20);border:1px solid #397a77;display:grid;place-items:center;color:var(--teal);font-size:25px;box-shadow:0 0 35px #42cdb022}h1{font-size:clamp(23px,3vw,32px);letter-spacing:.04em;margin:0}header p{color:var(--muted);margin:3px 0 0}.role{border:1px solid #326663;border-radius:999px;color:var(--teal);padding:7px 12px;background:#0a2425;font-size:12px;white-space:nowrap}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:18px}.stat,.shell{background:linear-gradient(145deg,#0d1b1d,#091315);border:1px solid var(--line);border-radius:16px;box-shadow:0 15px 45px #0002}.stat{padding:16px}.stat label{color:var(--muted);font-size:12px}.stat strong{display:block;font-size:25px;margin-top:5px;color:var(--teal)}
.toolbar{display:flex;gap:9px;align-items:center;flex-wrap:wrap;padding:12px;border-bottom:1px solid var(--line)}button,.navbtn{font:inherit;color:var(--text);border:1px solid #285052;background:#102426;border-radius:10px;padding:9px 12px;cursor:pointer;transition:.15s;text-decoration:none}button:hover,.navbtn:hover,.navbtn.active{border-color:var(--teal2);background:#153536;color:#c9fff6}button.primary{background:#174b49;border-color:#338c82}button.danger{border-color:#78464a;color:#ffb5b9;background:#291719}button:disabled{opacity:.5;cursor:not-allowed}.search{flex:1;min-width:180px;border:1px solid #285052;background:#061012;color:var(--text);padding:10px 12px;border-radius:10px;outline:none}.search:focus{border-color:var(--teal)}.tabs{display:flex;gap:8px;flex-wrap:wrap}.section{padding:14px}.sectionhead{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;margin:0 0 12px}.sectionhead h2{font-size:16px;margin:0}.hint{font-size:12px;color:var(--muted)}.entries{display:grid;gap:8px;max-height:62vh;overflow:auto}.entry{border:1px solid #1a383a;background:#081315;border-radius:11px;padding:11px;overflow-wrap:anywhere}.meta{display:flex;gap:9px;align-items:center;flex-wrap:wrap;color:var(--muted);font-size:11px;margin-bottom:5px}.level{font-weight:800;color:var(--teal)}.level.ERROR,.level.CRITICAL{color:var(--red)}.level.WARNING{color:var(--gold)}.message{white-space:pre-wrap}.empty{padding:28px 12px;color:var(--muted);text-align:center;border:1px dashed #234346;border-radius:10px}.status{display:inline-flex;align-items:center;gap:7px;color:var(--teal);font-size:12px}.dot{width:7px;height:7px;border-radius:50%;background:#5be3ad;box-shadow:0 0 12px #5be3ad}.footer{color:var(--muted);font-size:11px;margin:15px 3px 0}.hidden{display:none!important}.toast{position:fixed;bottom:18px;right:18px;background:#143536;border:1px solid #397a77;border-radius:12px;padding:12px 16px;box-shadow:0 8px 30px #0008;max-width:90vw}
@media(max-width:720px){.wrap{padding:14px}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.stat strong{font-size:21px}.toolbar{align-items:stretch}.search{flex-basis:100%}}
</style></head><body><div class="wrap">
<header><div class="brand"><div class="mark">霧</div><div><h1>MUICHIRO <span style="color:var(--teal)">HQ</span></h1><p>Live operations · music telemetry · mist console</p></div></div><div class="role" id="roleBadge">SECURE SESSION</div></header>
<div class="stats"><div class="stat"><label>Music events stored</label><strong id="musicCount">—</strong></div><div class="stat"><label>Bot activity events</label><strong id="activityCount">—</strong></div><div class="stat"><label>Application log events</label><strong id="renderCount">—</strong></div><div class="stat"><label>Monitor status</label><strong id="healthValue" style="font-size:18px">CONNECTING</strong></div></div>
<div class="shell"><div class="toolbar"><div class="tabs"><button class="navbtn active" data-tab="music">🎵 Music Logs</button><button class="navbtn" data-tab="activity">🌫️ Activity & Health</button><button class="navbtn" data-tab="render">⌘ Application Logs</button></div><input class="search" id="search" placeholder="Search current section…" aria-label="Search logs"><button id="refreshBtn" class="primary">↻ Refresh</button><button id="pauseBtn">Ⅱ Pause</button><button id="exportBtn" class="owner-only hidden">⇩ Export JSON</button><button id="ownerHQBtn" class="owner-only hidden">✦ Owner HQ</button><button id="clearBtn" class="owner-only hidden danger">⌫ Clear Logs</button></div>
<div class="section"><div class="sectionhead"><h2 id="sectionTitle">🎵 Music Logs</h2><div class="hint"><span class="status"><span class="dot"></span><span id="lastUpdate">Waiting for first update</span></span></div></div><div id="entries" class="entries"><div class="empty">Connecting to Muichiro HQ…</div></div></div></div>
<div class="footer">SQLite-backed event history · refreshes every 5 seconds · Telegram message contents are not stored by general activity logging. Render build/deploy logs remain in Render. Owner-only actions are enforced server-side.</div></div><div id="toast" class="toast hidden" role="status"></div>
<script>
let data={music:[],activity:[],render:[],counts:{}};let activeTab='music';let paused=false;let role='viewer';let timer=null;
const titles={music:'🎵 Music Logs',activity:'🌫️ Bot Activity & Health',render:'⌘ Application Logs'};
function toast(s){const t=document.getElementById('toast');t.textContent=s;t.classList.remove('hidden');setTimeout(()=>t.classList.add('hidden'),2800)}
function render(){document.getElementById('sectionTitle').textContent=titles[activeTab];const q=document.getElementById('search').value.trim().toLowerCase();const box=document.getElementById('entries');box.replaceChildren();const items=(data[activeTab]||[]).filter(x=>!q||[x.time,x.level,x.message].some(v=>String(v||'').toLowerCase().includes(q)));if(!items.length){const e=document.createElement('div');e.className='empty';e.textContent=q?'No logs match your search.':'No entries yet. Activity appears here when the bot receives updates.';box.appendChild(e);return}for(const item of items){const card=document.createElement('article');card.className='entry';const meta=document.createElement('div');meta.className='meta';const time=document.createElement('span');time.textContent=item.time||'';const level=document.createElement('span');level.className='level '+(item.level||'INFO');level.textContent=item.level||'INFO';meta.append(time,level);const message=document.createElement('div');message.className='message';message.textContent=item.message||'';card.append(meta,message);box.appendChild(card)}}
async function refresh(){try{const r=await fetch('/monitor/data?limit=500',{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);data=await r.json();role=data.role||'viewer';document.getElementById('roleBadge').textContent=role==='owner'?'✦ OWNER ACCESS':'◉ MONITOR ACCESS';document.querySelectorAll('.owner-only').forEach(e=>e.classList.toggle('hidden',role!=='owner'));document.getElementById('musicCount').textContent=data.counts?.music??0;document.getElementById('activityCount').textContent=data.counts?.activity??0;document.getElementById('renderCount').textContent=data.counts?.render??0;document.getElementById('healthValue').textContent='ONLINE';document.getElementById('healthValue').style.color='var(--teal)';document.getElementById('lastUpdate').textContent='Updated '+new Date().toLocaleTimeString();render()}catch(e){document.getElementById('healthValue').textContent='OFFLINE';document.getElementById('healthValue').style.color='var(--red)';document.getElementById('entries').innerHTML='<div class="empty">Monitor data unavailable. Check credentials and service status.</div>'}}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{activeTab=b.dataset.tab;document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x===b));document.getElementById('search').value='';render()}));document.getElementById('search').addEventListener('input',render);document.getElementById('refreshBtn').addEventListener('click',()=>refresh());document.getElementById('pauseBtn').addEventListener('click',e=>{paused=!paused;e.currentTarget.textContent=paused?'▶ Resume':'Ⅱ Pause';if(timer)clearInterval(timer);timer=paused?null:setInterval(refresh,5000);toast(paused?'Auto-refresh paused':'Auto-refresh resumed');});document.getElementById('ownerHQBtn').addEventListener('click',()=>{window.location.href='/owner'});document.getElementById('exportBtn').addEventListener('click',async()=>{try{const r=await fetch('/monitor/export');if(!r.ok)throw new Error('Export denied');const blob=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='muichiro-monitor-logs.json';a.click();URL.revokeObjectURL(a.href);toast('Log export prepared')}catch(e){toast('Export failed')}});document.getElementById('clearBtn').addEventListener('click',async()=>{if(!confirm('Clear all stored monitoring logs? This cannot be undone.'))return;try{const r=await fetch('/monitor/clear',{method:'POST'});const j=await r.json();if(!r.ok)throw new Error(j.detail||'Clear failed');toast('Monitoring logs cleared');await refresh()}catch(e){toast('Could not clear logs: '+e.message)}});refresh();timer=setInterval(refresh,5000);
</script></body></html>'''


def require_monitor_auth(credentials: HTTPBasicCredentials = Depends(monitor_security)):
    accounts = [
        ("owner", os.environ.get("MONITOR_OWNER_USERNAME", os.environ.get("MONITOR_USERNAME", "")).strip(), os.environ.get("MONITOR_OWNER_PASSWORD", os.environ.get("MONITOR_PASSWORD", ""))),
        ("viewer", os.environ.get("MONITOR_VIEWER_USERNAME", "").strip(), os.environ.get("MONITOR_VIEWER_PASSWORD", "")),
    ]
    configured = [(role, user, password) for role, user, password in accounts if user and password]
    if not configured:
        raise HTTPException(status_code=503, detail="Configure MONITOR_OWNER_USERNAME/PASSWORD and optionally MONITOR_VIEWER_USERNAME/PASSWORD.")
    for role, user, password in configured:
        valid_user = secrets.compare_digest(credentials.username.encode("utf-8"), user.encode("utf-8"))
        valid_password = secrets.compare_digest(credentials.password.encode("utf-8"), password.encode("utf-8"))
        if valid_user and valid_password:
            return {"username": user, "role": role}
    raise HTTPException(status_code=401, detail="Invalid monitoring credentials", headers={"WWW-Authenticate": "Basic"})


import owner_hq
owner_hq.register_owner_routes(app, require_monitor_auth)


@app.get("/", response_class=HTMLResponse)
async def home(_: dict = Depends(require_monitor_auth)):
    return HTMLResponse(MONITOR_HTML)


@app.get("/monitor/data")
async def monitor_data(account: dict = Depends(require_monitor_auth), limit: int = 250):
    data = monitoring.snapshot(limit=limit)
    data["role"] = account["role"]
    data["username"] = account["username"]
    return data


@app.post("/monitor/clear")
async def monitor_clear(account: dict = Depends(require_monitor_auth)):
    if account["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner access required.")
    count = monitoring.clear_logs()
    monitoring.activity_event(f"Monitoring logs cleared by dashboard owner {account['username']}.", "WARNING")
    return {"ok": True, "deleted": count}


@app.get("/monitor/export")
async def monitor_export(account: dict = Depends(require_monitor_auth)):
    if account["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner access required.")
    payload = monitoring.snapshot(limit=1000)
    payload["exported_at"] = datetime.now(timezone.utc).isoformat()
    return Response(content=json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": "attachment; filename=muichiro-monitor-logs.json"})


@app.get("/health")
async def health():
    # Liveness endpoint: keep Render's process check independent from a
    # temporary Neon outage so Render does not restart-loop the bot.
    return {"status": "alive"}


@app.get("/health/database")
async def database_health():
    from database import health_check, get_status

    healthy = health_check()
    status = get_status()
    from emergency_journal import get_status as get_journal_status
    journal_status = get_journal_status()
    # Keep internal connection errors private; this endpoint is public for
    # operational health checks and must not expose connection details.
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "connected" if healthy else "degraded",
            "backend": status.get("backend"),
            "generation": status.get("generation"),
            "emergency_journal_configured": journal_status.get("configured", False),
        },
    )


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