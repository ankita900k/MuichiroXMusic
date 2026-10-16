"""Owner-only Muichiro HQ intelligence, diagnostics, audit and backup routes."""
from __future__ import annotations
import csv, io, json, os, sqlite3, sys, tempfile, shutil
from datetime import datetime, timezone
from pathlib import Path
from fastapi import Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
import monitoring

OWNER_HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Muichiro HQ · Owner Command</title><style>
:root{color-scheme:dark;--bg:#050b0d;--card:#0c1719;--card2:#102124;--line:#1d3c3e;--muted:#8ba8a8;--text:#e6fffb;--teal:#72e6d2;--red:#ff8790;--gold:#f1d58a}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 10% 0%,#12383a,transparent 36%),radial-gradient(ellipse at 90% 15%,#15292c,transparent 30%),var(--bg);color:var(--text);font:14px/1.5 system-ui,sans-serif}.wrap{max-width:1400px;margin:auto;padding:22px}header{display:flex;justify-content:space-between;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:20px}.brand{display:flex;gap:12px;align-items:center}.mark{display:grid;place-items:center;width:48px;height:48px;border-radius:15px;border:1px solid #397a77;background:#102a2c;color:var(--teal);font-size:24px}h1{margin:0;font-size:clamp(24px,3vw,34px)}h2{margin:0 0 12px;font-size:17px}.muted{color:var(--muted)}.badge{border:1px solid #326663;border-radius:99px;padding:7px 12px;color:var(--teal);background:#0a2425}.nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}.nav button,.btn{border:1px solid #285052;background:#102426;color:var(--text);border-radius:10px;padding:9px 12px;cursor:pointer;font:inherit}.nav button.active,.btn.primary{background:#174b49;border-color:#338c82}.btn.danger{border-color:#78464a;color:#ffb5b9;background:#291719}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:14px}.card,.panel{border:1px solid var(--line);background:linear-gradient(145deg,#0d1b1d,#091315);border-radius:16px;padding:16px;min-width:0}.metric{font-size:27px;color:var(--teal);font-weight:750;margin-top:4px}.sub{font-size:12px;color:var(--muted)}.layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.wide{grid-column:1/-1}.list{display:grid;gap:8px;max-height:420px;overflow:auto}.item{padding:10px;border:1px solid #1a383a;background:#081315;border-radius:10px;overflow-wrap:anywhere}.item strong{color:var(--teal)}.item.warn strong{color:var(--gold)}.item.bad strong{color:var(--red)}button:disabled{opacity:.5;cursor:not-allowed}input,select{background:#061012;border:1px solid #285052;color:var(--text);padding:9px;border-radius:9px;max-width:100%}.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}.setting{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--line)}.setting:last-child{border-bottom:0}.toggle{accent-color:#2db8a6;width:18px;height:18px}.hidden{display:none!important}.notice{border:1px solid #66552c;background:#211d10;color:#f1d58a;padding:12px;border-radius:10px;margin-bottom:14px}.bar{height:8px;background:#142b2d;border-radius:99px;overflow:hidden;margin-top:8px}.bar span{display:block;height:100%;background:linear-gradient(90deg,#2db8a6,#72e6d2);width:0%}canvas{width:100%;height:220px;display:block}.foot{font-size:12px;color:var(--muted);margin:16px 2px}.toast{position:fixed;right:18px;bottom:18px;padding:12px 16px;background:#143536;border:1px solid #397a77;border-radius:12px;max-width:90vw}@media(max-width:800px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.layout{grid-template-columns:1fr}.wide{grid-column:auto}.wrap{padding:14px}}@media(max-width:420px){.grid{grid-template-columns:1fr 1fr}.metric{font-size:22px}}
</style></head><body><div class="wrap"><header><div class="brand"><div class="mark">霧</div><div><h1>MUICHIRO <span style="color:var(--teal)">HQ</span></h1><div class="muted">Owner Command Center · Pulse / Intelligence / Security</div></div></div><div class="row"><span class="badge">✦ OWNER ACCESS</span><button class="btn" id="csvBtn">⇩ Export CSV</button><a class="btn" href="/">← Monitor logs</a></div></header><div class="notice">Owner-only controls are protected server-side. Diagnostics never reveal secret values. Backups contain monitoring history and audit/settings data, not your whole Render filesystem.</div>
<div class="nav"><button class="active" data-page="overview">◈ Command Center</button><button data-page="music">♫ Music Intelligence</button><button data-page="errors">⌕ Error Detective</button><button data-page="security">⛨ Security & Audit</button><button data-page="database">▣ Database Guardian</button><button data-page="settings">⚙ Control Room</button><button data-page="deploy">⌁ Diagnostics</button></div>
<div id="page-overview"><div class="grid"><div class="card"><div class="sub">MUICHIRO PULSE</div><div class="metric" id="pulse">—</div><div class="sub" id="pulseText">Waiting for checks</div><div class="bar"><span id="pulseBar"></span></div></div><div class="card"><div class="sub">PLAYBACK SUCCESS</div><div class="metric" id="playSuccess">—</div><div class="sub">Estimated from recent music log events</div></div><div class="card"><div class="sub">RECENT ERRORS</div><div class="metric" id="errorCount">—</div><div class="sub">Warnings and errors in stored logs</div></div><div class="card"><div class="sub">DATABASE SIZE</div><div class="metric" id="dbSize">—</div><div class="sub" id="dbPath">SQLite monitor database</div></div></div><div class="layout"><section class="panel"><h2>Live system checks</h2><div id="checks" class="list"></div></section><section class="panel"><h2>Incident Center</h2><div class="sub">Recent warning/error signals detected in application logs.</div><div id="incidents" class="list" style="margin-top:10px"></div></section><section class="panel wide"><h2>Activity trend · recent stored events</h2><canvas id="trend" width="900" height="220" aria-label="Recent activity trend"></canvas><div class="sub">Trend is derived from saved monitor events, not Render platform metrics.</div></section></div></div>
<div id="page-music" class="hidden"><div class="grid"><div class="card"><div class="sub">TRACK / MUSIC EVENTS</div><div class="metric" id="musicEvents">—</div></div><div class="card"><div class="sub">PLAYBACK FAILURES</div><div class="metric" id="playFails">—</div></div><div class="card"><div class="sub">QUEUE / FAV ACTIVITY</div><div class="metric" id="queueEvents">—</div></div><div class="card"><div class="sub">API / DOWNLOAD SIGNALS</div><div class="metric" id="apiEvents">—</div></div></div><div class="layout"><section class="panel"><h2>Music event breakdown</h2><div id="musicBreakdown" class="list"></div></section><section class="panel"><h2>Frequent failure patterns</h2><div id="failurePatterns" class="list"></div></section></div></div>
<div id="page-errors" class="hidden"><section class="panel"><h2>Error Detective</h2><div class="row"><input id="errorSearch" placeholder="Filter errors…"><button class="btn" id="reloadErrors">Refresh</button></div><div id="errorList" class="list"></div></section></div>
<div id="page-security" class="hidden"><div class="grid"><div class="card"><div class="sub">AUDIT EVENTS</div><div class="metric" id="auditCount">—</div></div><div class="card"><div class="sub">AUTH CONFIGURATION</div><div class="metric" style="font-size:18px">Basic Auth</div><div class="sub">Use HTTPS and strong passwords</div></div><div class="card"><div class="sub">OWNER ACCOUNT</div><div class="metric" style="font-size:18px">Protected</div><div class="sub">Role enforced server-side</div></div><div class="card"><div class="sub">SESSION MODEL</div><div class="metric" style="font-size:18px">Stateless</div><div class="sub">HTTP Basic; no server session list</div></div></div><section class="panel"><h2>Security & owner audit trail</h2><div class="sub">Sensitive actions are recorded. Failed HTTP Basic attempts are handled by the web server and are not captured here by default.</div><div id="auditList" class="list" style="margin-top:12px"></div></section></div>
<div id="page-database" class="hidden"><div class="layout"><section class="panel"><h2>Database Guardian</h2><div id="dbDetails" class="list"></div><div class="row"><button class="btn primary" id="backupBtn">⇩ Create & download SQLite backup</button><button class="btn" id="integrityBtn">Run integrity check</button></div><div id="integrityResult" class="sub"></div></section><section class="panel"><h2>Retention & storage notes</h2><p class="muted">Monitoring history is trimmed by MONITOR_MAX_ENTRIES. For persistence across Render redeploys, point MONITOR_DB_PATH at a mounted persistent disk, e.g. <code>/var/data/muichiro_monitor.sqlite3</code>.</p><p class="muted">Backup download covers this SQLite database only. It does not back up Telegram sessions, source files, environment variables, or other external services.</p></section></div></div>
<div id="page-settings" class="hidden"><section class="panel"><h2>Owner Control Room</h2><p class="muted">These preferences are saved in the monitor database. Maintenance mode is a dashboard/status flag only; it does not stop Telegram commands unless your bot code is separately wired to enforce it.</p><div class="setting"><div><strong>Maintenance banner</strong><div class="sub">Flag the service as under maintenance in HQ.</div></div><input class="toggle" type="checkbox" id="maintenance"></div><div class="setting"><div><strong>Verbose diagnostic mode</strong><div class="sub">Preference flag for future diagnostic integrations; does not change Python logging level yet.</div></div><input class="toggle" type="checkbox" id="verbose"></div><div class="setting"><div><strong>Safe mode preference</strong><div class="sub">Record a safe-mode flag for owner visibility; does not automatically disable music features.</div></div><input class="toggle" type="checkbox" id="safeMode"></div><div class="row"><button class="btn primary" id="saveSettings">Save owner preferences</button><button class="btn" id="reloadSettings">Reload</button></div><div id="settingsResult" class="sub"></div></section></div>
<div id="page-deploy" class="hidden"><div class="layout"><section class="panel"><h2>Runtime diagnostics</h2><div id="diagList" class="list"></div><div class="row"><button class="btn primary" id="runDiag">Run checks again</button></div></section><section class="panel"><h2>Deployment information</h2><div class="sub">This app can report its runtime environment, not Render's private build logs or complete deployment history.</div><div id="deployList" class="list" style="margin-top:12px"></div></section></div></div>
<div class="foot">Muichiro HQ · data-driven health only · no secret values displayed · automatic refresh every 15 seconds</div></div><div id="toast" class="toast hidden"></div><script>
let state={},timer=null;const $=id=>document.getElementById(id);function toast(s){$('toast').textContent=s;$('toast').classList.remove('hidden');setTimeout(()=>$('toast').classList.add('hidden'),2800)}function item(title,detail='',kind=''){let d=document.createElement('div');d.className='item '+kind;let s=document.createElement('strong');s.textContent=title;d.appendChild(s);if(detail){let p=document.createElement('div');p.className='sub';p.textContent=detail;d.appendChild(p)}return d}function fill(id,arr,empty='No events yet.'){let el=$(id);el.replaceChildren();if(!arr||!arr.length){el.appendChild(item(empty));return}arr.forEach(x=>el.appendChild(item(x.title||x.level||'Event',x.detail||x.message||x.time||'',x.kind||'')))}async function api(url,opts={}){let r=await fetch(url,{cache:'no-store',...opts});let j=await r.json().catch(()=>({}));if(!r.ok)throw Error(j.detail||('HTTP '+r.status));return j}function bytes(n){if(!Number.isFinite(n))return '—';let u=['B','KB','MB','GB'],i=0;while(n>=1024&&i<u.length-1){n/=1024;i++}return n.toFixed(i?1:0)+' '+u[i]}
function drawTrend(points){let c=$('trend'),ctx=c.getContext('2d'),w=c.width,h=c.height;ctx.clearRect(0,0,w,h);ctx.strokeStyle='#1d3c3e';ctx.lineWidth=1;for(let i=1;i<5;i++){ctx.beginPath();ctx.moveTo(0,h*i/5);ctx.lineTo(w,h*i/5);ctx.stroke()}let vals=points.map(x=>x.count||0),max=Math.max(1,...vals);ctx.strokeStyle='#72e6d2';ctx.lineWidth=3;ctx.beginPath();vals.forEach((v,i)=>{let x=vals.length<2?w/2:i*w/(vals.length-1),y=h-18-(v/max)*(h-36);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y)});ctx.stroke();vals.forEach((v,i)=>{let x=vals.length<2?w/2:i*w/(vals.length-1),y=h-18-(v/max)*(h-36);ctx.fillStyle='#72e6d2';ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill()})}
async function load(){try{state=await api('/owner/api/overview');$('pulse').textContent=state.pulse.score+' / 100';$('pulseBar').style.width=state.pulse.score+'%';$('pulseText').textContent=state.pulse.label;$('playSuccess').textContent=state.music.success_rate===null?'—':state.music.success_rate+'%';$('errorCount').textContent=state.errors.length;$('dbSize').textContent=bytes(state.database.size_bytes);$('dbPath').textContent=state.database.persistent_hint?'Persistent path configured':'Check Render disk configuration';$('musicEvents').textContent=state.music.total;$('playFails').textContent=state.music.failures;$('queueEvents').textContent=state.music.queue_fav_events;$('apiEvents').textContent=state.music.api_events;$('auditCount').textContent=state.audit.length;fill('checks',state.checks.map(x=>({title:(x.ok?'✓ ':'⚠ ')+x.name,detail:x.detail,kind:x.ok?'':'warn'})));fill('incidents',state.errors.slice(0,30).map(x=>({title:x.level+' · '+x.time,detail:x.message,kind:x.level==='ERROR'||x.level==='CRITICAL'?'bad':'warn'})),'No recent warnings or errors.');fill('musicBreakdown',state.music.breakdown.map(x=>({title:x.name,detail:String(x.count)+' events'})));fill('failurePatterns',state.music.patterns.map(x=>({title:x.name,detail:String(x.count)+' matches',kind:'bad'})),'No recurring failures detected.');fill('errorList',state.errors.map(x=>({title:x.level+' · '+x.time,detail:x.message,kind:x.level==='ERROR'||x.level==='CRITICAL'?'bad':'warn'})));fill('auditList',state.audit.map(x=>({title:x.action+' · '+x.time,detail:x.actor+' — '+x.detail})));fill('dbDetails',[{title:'Database path',detail:state.database.path},{title:'Database size',detail:bytes(state.database.size_bytes)},{title:'Stored monitor events',detail:String(state.database.event_count)},{title:'Integrity',detail:state.database.integrity}]);fill('diagList',state.checks.map(x=>({title:(x.ok?'✓ ':'⚠ ')+x.name,detail:x.detail,kind:x.ok?'':'warn'})));fill('deployList',state.deployment.map(x=>({title:x.name,detail:x.value})));drawTrend(state.trend);await loadSettings()}catch(e){toast('Owner data unavailable: '+e.message)}}async function loadSettings(){try{let s=await api('/owner/api/settings');$('maintenance').checked=!!s.maintenance;$('verbose').checked=!!s.verbose_diagnostics;$('safeMode').checked=!!s.safe_mode;$('settingsResult').textContent='Preferences loaded.'}catch(e){$('settingsResult').textContent=e.message}}document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-page]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('[id^="page-"]').forEach(x=>x.classList.add('hidden'));$('page-'+b.dataset.page).classList.remove('hidden')}));$('csvBtn').addEventListener('click',()=>{window.location.href='/owner/api/export.csv';toast('Preparing CSV export')});$('backupBtn').addEventListener('click',async()=>{try{let r=await fetch('/owner/api/backup');if(!r.ok)throw Error('Backup failed');let blob=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='muichiro-hq-backup.sqlite3';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);toast('SQLite backup downloaded')}catch(e){toast(e.message)}});$('integrityBtn').addEventListener('click',async()=>{try{let j=await api('/owner/api/integrity');$('integrityResult').textContent='SQLite integrity check: '+j.result;toast(j.result==='ok'?'Database check passed':'Database check reported an issue')}catch(e){$('integrityResult').textContent=e.message}});$('runDiag').addEventListener('click',load);$('reloadErrors').addEventListener('click',load);$('errorSearch').addEventListener('input',()=>{let q=$('errorSearch').value.toLowerCase();[...$('errorList').children].forEach(x=>x.classList.toggle('hidden',!x.textContent.toLowerCase().includes(q)))});$('saveSettings').addEventListener('click',async()=>{try{let s=await api('/owner/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({maintenance:$('maintenance').checked,verbose_diagnostics:$('verbose').checked,safe_mode:$('safeMode').checked})});$('settingsResult').textContent='Saved at '+s.updated_at+'. Note: flags are stored preferences, not automatic runtime switches.';toast('Owner preferences saved')}catch(e){toast('Save failed: '+e.message)}});$('reloadSettings').addEventListener('click',loadSettings);load();timer=setInterval(load,15000);
</script></body></html>'''


def _db_path():
    return Path(monitoring.DB_PATH).resolve()

def _connect():
    conn=sqlite3.connect(str(_db_path()),timeout=10)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA busy_timeout=10000')
    return conn

def _init_owner_tables():
    with _connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS owner_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS owner_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL)')
        c.commit()

def _audit(actor, action, detail=''):
    _init_owner_tables()
    with _connect() as c:
        c.execute('INSERT INTO owner_audit(time,actor,action,detail) VALUES(?,?,?,?)',(datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),str(actor)[:80],str(action)[:100],str(detail)[:500]))
        c.commit()

def _events(limit=1000):
    return monitoring.snapshot(limit=max(20,min(int(limit),1000)))

def _overview():
    snap=_events(1000); all_events=[]
    for cat in ('music','activity','render'):
        for x in snap.get(cat,[]): all_events.append({**x,'category':cat})
    errors=[x for x in all_events if str(x.get('level','')).upper() in ('ERROR','CRITICAL','WARNING') or any(k in x.get('message','').lower() for k in ('failed','failure','exception','traceback','unavailable'))]
    music=snap.get('music',[]); fail=[x for x in music if any(k in x.get('message','').lower() for k in ('failed','failure','exception','error','rejected'))]
    success=[x for x in music if any(k in x.get('message','').lower() for k in ('playing','started','success','queued','sent audio','delivered'))]
    success_rate=round(len(success)*100/(len(success)+len(fail))) if success or fail else None
    cats={'playback':0,'queue / favourites':0,'API / downloads':0,'other':0}; patterns={}
    for x in music:
        m=x.get('message','').lower()
        if any(k in m for k in ('queue','favourite','favorite','playfav')): cats['queue / favourites']+=1
        elif any(k in m for k in ('api','download','hep','http','stream')): cats['API / downloads']+=1
        elif any(k in m for k in ('play','track','audio','voice')): cats['playback']+=1
        else: cats['other']+=1
        if any(k in m for k in ('failed','failure','exception','error','rejected')):
            name='Voice chat / assistant' if any(k in m for k in ('join','voicechat','voice chat','assistant')) else 'Playback / download' if any(k in m for k in ('play','audio','download','stream')) else 'Other error'
            patterns[name]=patterns.get(name,0)+1
    db=_db_path(); size=db.stat().st_size if db.exists() else 0
    with _connect() as c:
        event_count=c.execute('SELECT COUNT(*) FROM monitor_events').fetchone()[0]
        _init_owner_tables()
        audit=[dict(r) for r in c.execute('SELECT time,actor,action,detail FROM owner_audit ORDER BY id DESC LIMIT 100')]
        integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
        recent=c.execute("SELECT substr(time,1,13) AS bucket,COUNT(*) AS n FROM monitor_events GROUP BY bucket ORDER BY bucket DESC LIMIT 12").fetchall()
    env_checks=[('Telegram bot token',bool(os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN'))),('API_ID configured',bool(os.getenv('API_ID'))),('API_HASH configured',bool(os.getenv('API_HASH'))),('Voice session configured',bool(os.getenv('SESSION_STRING'))),('Music API key configured',bool(os.getenv('HEP_MUSIC_API_KEY')))]
    checks=[{'name':'SQLite database','ok':db.exists(),'detail':str(db) if db.exists() else 'Database file not found'}, {'name':'SQLite integrity','ok':integrity=='ok','detail':integrity}, {'name':'Monitoring history','ok':event_count>0,'detail':f'{event_count} stored events'}, {'name':'Persistent storage hint','ok':str(db).startswith('/var/data/'),'detail':'Persistent disk path detected' if str(db).startswith('/var/data/') else 'Local path; Render redeploy may reset this file'}]
    checks += [{'name':name,'ok':ok,'detail':'Configured' if ok else 'Not detected (verify variable name if this is expected)'} for name,ok in env_checks]
    score=round(sum(1 for x in checks if x['ok'])*100/max(1,len(checks)))
    label='Healthy signals' if score>=85 else 'Needs attention' if score>=60 else 'Degraded signals'
    try:
        import music.runtime as rt
        voice_ok=bool(getattr(rt,'voice',None))
    except Exception: voice_ok=False
    checks.append({'name':'Voice layer object','ok':voice_ok,'detail':'Voice runtime object exists' if voice_ok else 'Not visible in this diagnostic context'})
    deploy=[{'name':'Python','value':sys.version.split()[0]},{'name':'Platform','value':sys.platform},{'name':'Render service','value':os.getenv('RENDER_SERVICE_NAME','Not exposed')},{'name':'Render commit','value':(os.getenv('RENDER_GIT_COMMIT','')[:12] or 'Not exposed')},{'name':'Runtime start','value':os.getenv('RENDER_INSTANCE_ID','Not exposed')},{'name':'Database','value':db.name}]
    trend=[{'bucket':r['bucket'],'count':r['n']} for r in reversed(recent)]
    return {'pulse':{'score':score,'label':label},'music':{'total':len(music),'failures':len(fail),'success_rate':success_rate,'queue_fav_events':cats['queue / favourites'],'api_events':cats['API / downloads'],'breakdown':[{'name':k,'count':v} for k,v in cats.items()],'patterns':[{'name':k,'count':v} for k,v in sorted(patterns.items(),key=lambda p:-p[1])]},'errors':errors[:100],'checks':checks,'database':{'path':str(db),'size_bytes':size,'event_count':event_count,'integrity':integrity,'persistent_hint':str(db).startswith('/var/data/')},'audit':audit,'trend':trend,'deployment':deploy}

def register_owner_routes(app, require_monitor_auth):
    def owner(account):
        if account.get('role')!='owner': raise HTTPException(status_code=403,detail='Owner access required.')
        return account
    @app.get('/owner',response_class=HTMLResponse)
    async def owner_page(account=Depends(require_monitor_auth)):
        owner(account); return HTMLResponse(OWNER_HTML)
    @app.get('/owner/api/overview')
    async def owner_overview(account=Depends(require_monitor_auth)):
        owner(account); return _overview()
    @app.get('/owner/api/settings')
    async def owner_get_settings(account=Depends(require_monitor_auth)):
        owner(account); _init_owner_tables()
        with _connect() as c: rows=c.execute('SELECT key,value FROM owner_settings').fetchall()
        vals={r['key']:json.loads(r['value']) for r in rows}
        return {'maintenance':vals.get('maintenance',False),'verbose_diagnostics':vals.get('verbose_diagnostics',False),'safe_mode':vals.get('safe_mode',False)}
    @app.post('/owner/api/settings')
    async def owner_save_settings(payload:dict, account=Depends(require_monitor_auth)):
        owner(account); allowed={'maintenance','verbose_diagnostics','safe_mode'}
        if set(payload)-allowed: raise HTTPException(status_code=400,detail='Unsupported setting.')
        now=datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'); _init_owner_tables()
        with _connect() as c:
            for key,value in payload.items():
                if not isinstance(value,bool): raise HTTPException(status_code=400,detail=f'{key} must be boolean')
                c.execute('INSERT INTO owner_settings(key,value,updated_at,updated_by) VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at,updated_by=excluded.updated_by',(key,json.dumps(value),now,account['username']))
            c.commit()
        _audit(account['username'],'settings_updated',','.join(sorted(payload)))
        monitoring.activity_event(f'Owner preferences updated by {account["username"]}.','WARNING')
        return {'ok':True,'updated_at':now}
    @app.get('/owner/api/backup')
    async def owner_backup(account=Depends(require_monitor_auth)):
        owner(account); _init_owner_tables(); src=_db_path()
        if not src.exists(): raise HTTPException(status_code=404,detail='Database not found')
        fd,tmp=tempfile.mkstemp(suffix='.sqlite3'); os.close(fd)
        try:
            with sqlite3.connect(str(src)) as s, sqlite3.connect(tmp) as d: s.backup(d)
            _audit(account['username'],'database_backup_downloaded','SQLite backup generated')
            data=Path(tmp).read_bytes()
        finally:
            try: os.unlink(tmp)
            except OSError: pass
        return Response(content=data,media_type='application/vnd.sqlite3',headers={'Content-Disposition':'attachment; filename=muichiro-hq-backup.sqlite3'})
    @app.get('/owner/api/integrity')
    async def owner_integrity(account=Depends(require_monitor_auth)):
        owner(account)
        with _connect() as c: result=c.execute('PRAGMA integrity_check').fetchone()[0]
        _audit(account['username'],'database_integrity_check',str(result))
        return {'result':result}
    @app.get('/owner/api/export.csv')
    async def owner_csv(account=Depends(require_monitor_auth)):
        owner(account); snap=_events(1000); out=io.StringIO(); w=csv.writer(out); w.writerow(['category','time','level','message'])
        for cat in ('music','activity','render'):
            for r in snap.get(cat,[]): w.writerow([cat,r.get('time'),r.get('level'),r.get('message')])
        _audit(account['username'],'logs_exported_csv','Up to 1000 events per category')
        return Response(content=out.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=muichiro-monitor-logs.csv'})
