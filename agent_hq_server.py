"""
Gold Sniper HQ — BBR-Style Command Center with Pixel Agents
BBR Color Palette: warm browns, golds, beige, wood tones
"""
import os, sys, json, sqlite3, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
PORT = 8080
ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "trade_memory.db")
CONFIG_PATH = os.path.join(ROOT, "learned_config.json")

class DataAPI:
    def get_overview(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT COUNT(*) total, SUM(CASE WHEN close_reason='TP' THEN 1 ELSE 0 END) wins, SUM(CASE WHEN close_reason='SL' THEN 1 ELSE 0 END) losses, COALESCE(SUM(pnl_usd),0) total_pnl, COALESCE(AVG(CASE WHEN close_reason IS NOT NULL THEN r_achieved END),0) avg_r FROM trades").fetchone()
        monthly = conn.execute("SELECT strftime('%Y-%m',entry_time) m, COUNT(*) t, SUM(CASE WHEN close_reason='TP' THEN 1 ELSE 0 END) w, COALESCE(SUM(pnl_usd),0) p FROM trades WHERE pnl_usd IS NOT NULL GROUP BY m ORDER BY m DESC LIMIT 12").fetchall()
        regime = conn.execute("SELECT regime, COUNT(*) t, SUM(CASE WHEN close_reason='TP' THEN 1 ELSE 0 END) w, COALESCE(SUM(pnl_usd),0) p FROM trades WHERE regime IS NOT NULL GROUP BY regime").fetchall()
        recent = conn.execute("SELECT signal,entry_price,exit_price,pnl_usd,close_reason,regime,confidence,r_achieved FROM trades WHERE close_reason IS NOT NULL ORDER BY entry_time DESC LIMIT 10").fetchall()
        conn.close()
        t=row["total"] or 0; w=row["wins"] or 0
        return {"total":t,"wins":w,"losses":row["losses"] or 0,"wr":round(w/t*100,1) if t>0 else 0,"pnl":round(row["total_pnl"] or 0,2),"avg_r":round(row["avg_r"] or 0,2),
            "monthly":[{"m":r["m"],"t":r["t"],"w":r["w"],"p":round(r["p"],2)} for r in monthly],
            "regime":[{"r":r["regime"],"t":r["t"],"w":r["w"],"p":round(r["p"],2)} for r in regime],
            "recent":[{"s":r["signal"],"e":round(r["entry_price"] or 0,2),"x":round(r["exit_price"] or 0,2),"p":round(r["pnl_usd"] or 0,2),"c":r["close_reason"],"rg":r["regime"],"cf":round((r["confidence"] or 0)*100)} for r in recent]}
    def get_agents(self):
        bot,ct="stopped","stopped"
        try:r=subprocess.run(["ps","aux"],capture_output=True,text=True,timeout=3);bot="running" if "main.py live" in r.stdout else "stopped"
        except:pass
        try:r=subprocess.run(["docker","ps","--filter","name=claw-trade-mt5","--format","{{.Status}}"],capture_output=True,text=True,timeout=3);ct=r.stdout.strip()[:30] or "stopped"
        except:pass
        l={}
        if os.path.exists(CONFIG_PATH):
            try:l=json.load(open(CONFIG_PATH))
            except:pass
        return {"bot":bot,"container":ct,"wr":l.get("overall_winrate",0),"cons":l.get("consecutive_losses",0),"thresh":l.get("confidence_threshold",{})}

api = DataAPI()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p=urllib.parse.urlparse(self.path).path
        if p=="/api/overview":self.json(api.get_overview())
        elif p=="/api/agents":self.json(api.get_agents())
        elif p=="/api/pid":self.json({"pid":os.getpid()})
        elif p.startswith("/static/"):
            # Serve static files (sprites)
            fpath=os.path.join(ROOT, p.lstrip("/"))
            if os.path.exists(fpath) and os.path.isfile(fpath):
                self.send_response(200)
                if p.endswith(".png"): self.send_header("Content-Type","image/png")
                elif p.endswith(".jpg") or p.endswith(".jpeg"): self.send_header("Content-Type","image/jpeg")
                else: self.send_header("Content-Type","application/octet-stream")
                self.send_header("Cache-Control","max-age=3600")
                self.end_headers()
                with open(fpath,"rb") as f:self.wfile.write(f.read())
            else:self.send_error(404)
        elif p=="/agent-hq" or p.startswith("/agent-hq/"):
            build_dir=os.path.join(ROOT,"static","pixel-agents-build")
            rest=p[len("/agent-hq"):].lstrip("/")
            if not rest: rest="index.html"
            fpath=os.path.join(build_dir,rest)
            real_fpath=os.path.realpath(fpath)
            real_build_dir=os.path.realpath(build_dir)
            if not real_fpath.startswith(real_build_dir):
                self.send_error(403);return
            if os.path.exists(fpath) and os.path.isfile(fpath):
                self.send_response(200)
                if fpath.endswith(".html"): self.send_header("Content-Type","text/html;charset=utf-8")
                elif fpath.endswith(".js"): self.send_header("Content-Type","application/javascript")
                elif fpath.endswith(".css"): self.send_header("Content-Type","text/css")
                elif fpath.endswith(".json"): self.send_header("Content-Type","application/json")
                elif fpath.endswith(".png"): self.send_header("Content-Type","image/png")
                elif fpath.endswith(".jpg") or fpath.endswith(".jpeg"): self.send_header("Content-Type","image/jpeg")
                else: self.send_header("Content-Type","application/octet-stream")
                self.send_header("Cache-Control","max-age=3600")
                self.end_headers()
                with open(fpath,"rb") as f:self.wfile.write(f.read())
            else:
                # SPA fallback
                idx=os.path.join(build_dir,"index.html")
                self.send_response(200)
                self.send_header("Content-Type","text/html;charset=utf-8")
                self.end_headers()
                with open(idx,"rb") as f:self.wfile.write(f.read())
        elif p=="/":self.html(PAGE_DASHBOARD)
        elif p=="/agents":self.html(PAGE_AGENTS)
        elif p=="/trades":self.html(PAGE_TRADES)
        elif p=="/settings":self.html(PAGE_SETTINGS)
        else:self.send_error(404)
    def html(self,c):self.send_response(200);self.send_header("Content-Type","text/html;charset=utf-8");self.end_headers();self.wfile.write(c.encode())
    def json(self,d):self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(json.dumps(d,ensure_ascii=False).encode())
    def log_message(self,*a):pass

# ═══════════════════════════════════════════════
# PAGE AGENTS — BBR Pixel Office + Status Panel
# ═══════════════════════════════════════════════

PAGE_AGENTS = r"""
<!DOCTYPE html><html lang="th"><head><meta charset="UTF-8">
<title>Gold Sniper HQ — Agents</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#e8e0c8;color:#3d3224;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;overflow:hidden;height:100vh}
.header{position:fixed;top:0;left:0;right:0;z-index:100;height:32px;background:#3d3224;border-bottom:1px solid #a09070;display:flex;align-items:center;padding:0 12px}
.header a{color:#c8b888;text-decoration:none;padding:2px 10px;font-size:11px;border-radius:3px}
.header a:hover{background:rgba(200,184,136,0.12);color:#e8d8a8}
.header .brand{color:#e8d8a8;font-weight:bold;font-size:13px;margin-right:16px;letter-spacing:1px}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-left:auto}
.dot.on{background:#56b846;box-shadow:0 0 4px #56b846}
.dot.off{background:#666}
.split{display:flex;height:100vh;padding-top:32px}
.left{flex:0 0 62%;position:relative;background:#1f1a10;overflow:hidden}
.right{flex:0 0 38%;background:#c8b888;border-left:2px solid #a37448;overflow-y:auto}
canvas{display:block;width:100%;height:100%;image-rendering:pixelated}
.terminal{padding:16px;font-family:'Courier New',monospace;color:#1a1a0a;height:100%}
.terminal .panel-header{background:#46352d;color:#e8d8a8;padding:6px 12px;font-size:12px;font-weight:bold;margin:-16px -16px 12px;letter-spacing:1px}
.terminal .sync{color:#7a6a4a;font-size:10px;margin-bottom:12px}
.terminal hr{border:none;border-top:1px solid #a09070;margin:10px 0}
.counts{display:flex;gap:12px;margin-bottom:12px}
.count{text-align:center;padding:6px 14px;border:1px solid #a09070;border-radius:3px;background:rgba(255,255,240,0.4)}
.count .num{font-size:26px;font-weight:bold;color:#3d3224}
.count .lbl{font-size:9px;color:#7a6a4a;margin-top:2px}
.count.active .num{color:#56b846}
.grptitle{color:#3d3224;font-size:11px;font-weight:bold;margin:10px 0 4px 4px}
.agent-row{display:flex;align-items:center;gap:6px;padding:4px 6px;font-size:11px;border-radius:2px}
.agent-row:hover{background:rgba(255,255,240,0.4)}
.agent-row .emoji{width:20px;text-align:center}
.agent-row .name{font-weight:bold;flex:1}
.agent-row .role{color:#7a6a4a;font-size:9px;margin-right:6px}
.agent-row .tag{font-size:8px;padding:1px 5px;border-radius:2px}
.agent-row .tag.on{background:#56b846;color:#fff}
.agent-row .tag.off{background:#7a6a4a;color:#e8e0c8}
</style></head><body>
<div class="header">
  <span class="brand">🔫 GSN</span>
  <a href="/">Dashboard</a><a href="/agent-hq">Agent HQ</a><a href="/trades">Trades</a><a href="/settings">Settings</a>
  <span class="dot" id="liveDot"></span>
</div>
<div class="split">
  <div class="left"><canvas id="gc" width="1140" height="800"></canvas></div>
  <div class="right"><div class="terminal" id="terminalPanel"></div></div>
</div>
<script>
// ===== SPRITE LOADING =====
var sprites = {};
var loadedCount = 0;
var TOTAL_SPRITES = 8; // 6 chars + floor + desk + chair + pc + plant

function loadSprite(name, src, callback) {
  var img = new Image();
  img.onload = function() {
    sprites[name] = img;
    loadedCount++;
    if (callback && loadedCount >= TOTAL_SPRITES) callback();
  };
  img.onerror = function() {
    console.log('Failed to load: ' + name);
    loadedCount++;
  };
  img.src = src;
}

// Character spritesheets (16x16 pixels each, 7 cols x 6 rows = 112x96)
var CHAR_NAMES = ['QUANT','NEWS','BULL','BEAR','CEO','LEARN'];
var CHAR_COLORS = ['#38ba72','#d4a017','#c0392b','#2c6b9e','#c87d1e','#8e44ad'];
var CHAR_EMOJI = ['🔮','📡','⚔️','🛡️','👑','🧬'];

// Furniture dimensions
var SPRITE_W = 16; // base pixel width
var SH = 16; // base pixel height

// Desk positions
var DESKS = [
  {x:50,y:70,char:0},{x:50,y:260,char:1},
  {x:390,y:70,char:2},{x:390,y:260,char:3},
  {x:730,y:70,char:4},{x:730,y:260,char:5},
];

// Agent state
var agents = [];
for (var i = 0; i < 6; i++) {
  var d = DESKS[i];
  agents.push({
    idx: i,
    name: CHAR_NAMES[i],
    emoji: CHAR_EMOJI[i],
    color: CHAR_COLORS[i],
    role: ['Technical Analyst','News Scout','Bullish Strategist','Bearish Guardian','Executive Chairman','Learning Engine'][i],
    duty: ['RSI/MACD/EMA','Economic Calendar','BUY Arguments','SELL Arguments','Final Decision','Self-Optimization'][i],
    lvl: [8,5,7,7,10,6][i],
    hp: [92,78,85,88,99,95][i],
    x: d.x + 24, y: d.y + 40,
    tx: d.x + 24, ty: d.y + 40,
    deskX: d.x + 24, deskY: d.y + 40,
    frame: 0, dir: 0, timer: 0, wt: 0,
    activity: 'idle', bubble: '', bt: 0,
  });
}

var W = 1140, H = 800;
var c = document.getElementById('gc');
var ctx = c.getContext('2d');
ctx.imageSmoothingEnabled = false;

// ===== SPRITE DRAWING =====
function drawCharSprite(img, frame, dir, dx, dy, scale) {
  scale = scale || 2;
  var sx = frame * SPRITE_W;
  var sy = dir * SH;
  ctx.drawImage(img, sx, sy, SPRITE_W, SH, dx, dy, SPRITE_W * scale, SH * scale);
}

function drawFloor() {
  var floorImg = sprites['floor'];
  if (!floorImg) return;
  for (var y = 0; y < 50; y++) {
    for (var x = 0; x < 72; x++) {
      ctx.drawImage(floorImg, x * 16, y * 16, 16, 16);
    }
  }
}

function drawDesk(d) {
  var desk = sprites['desk_front'];
  var chair = sprites['chair'];
  var pc = sprites['pc_on'];
  var plant = sprites['plant'];
  
  if (desk) ctx.drawImage(desk, d.x, d.y-8, 48*2, 32*2);
  if (pc) ctx.drawImage(pc, d.x+40, d.y-40, 16*2, 32*2);
  if (chair) ctx.drawImage(chair, d.x+52, d.y+20, 16*2, 32*2);
  if (plant && (d.char === 0 || d.char === 5)) {
    var px = d.char === 0 ? d.x-40 : d.x+80;
    ctx.drawImage(plant, px, d.y-20, 32*2, 48*2);
  }
}

function drawAgent(a) {
  var img = sprites['char_' + a.idx];
  if (!img) {
    // Fallback: draw colored rectangle
    ctx.fillStyle = a.color;
    ctx.fillRect(a.x-8, a.y-8, 16, 16);
    ctx.font = '10px sans-serif';
    ctx.fillText(a.emoji, a.x-5, a.y+5);
    return;
  }
  // Determine frame and direction based on activity
  var frame = a.frame;
  var dir = 0; // down (facing front)
  
  if (a.activity === 'typing' || a.activity === 'analyzing') {
    dir = 4; // typing row
    frame = Math.floor(Date.now() / 500) % 2;
  } else if (a.activity === 'reading') {
    dir = 5; // reading row
    frame = Math.floor(Date.now() / 600) % 2;
  } else if (a.activity === 'walking') {
    dir = 0; // down
    frame = a.wf % 4;
  } else {
    // Idle - subtle breathing
    dir = 0;
    frame = Math.floor(Date.now() / 800) % 2;
  }
  
  drawCharSprite(img, frame, dir, a.x - 16, a.y - 16, 2);
  
  // HP bar
  ctx.fillStyle = '#333';
  ctx.fillRect(a.x - 12, a.y + 18, 24, 3);
  ctx.fillStyle = a.color;
  ctx.fillRect(a.x - 12, a.y + 18, 24 * (a.hp/100), 3);
  
  // Level badge
  ctx.fillStyle = '#3d3224';
  ctx.fillRect(a.x - 8, a.y + 22, 16, 5);
  ctx.fillStyle = '#e8d8a8';
  ctx.font = '4px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('Lv' + a.lvl, a.x, a.y + 26);
}

function drawBubble(a) {
  if (!a.bubble) return;
  var bw = 60, bh = 20, bx = a.x - bw/2, by = a.y - 40;
  ctx.fillStyle = 'rgba(255,255,240,0.95)';
  ctx.fillRect(bx, by, bw, bh);
  ctx.strokeStyle = '#a09070';
  ctx.lineWidth = 1;
  ctx.strokeRect(bx, by, bw, bh);
  ctx.beginPath(); ctx.moveTo(a.x-4, by+bh); ctx.lineTo(a.x+4, by+bh); ctx.lineTo(a.x, by+bh+5); ctx.closePath(); ctx.fill();
  ctx.fillStyle = '#3d3224';
  ctx.font = 'bold 6px monospace';
  ctx.textAlign = 'center';
  ctx.fillText(a.name, a.x, by+8);
  ctx.fillStyle = '#7a6a4a';
  ctx.font = '5px monospace';
  ctx.fillText('· ' + a.role, a.x, by+15);
}

function updateAgents() {
  agents.forEach(function(a,i) {
    var d = DESKS[i];
    a.timer++;
    if (a.timer > 60 + Math.random() * 120) {
      a.timer = 0;
      var acts = ['analyzing','reading','typing','deciding','learning','walking','idle'];
      a.activity = acts[Math.floor(Math.random() * acts.length)];
      if (a.activity === 'walking') {
        a.tx = 30 + Math.random() * 380;
        a.ty = 20 + Math.random() * 280;
      } else {
        a.tx = a.deskX + (Math.random()-0.5)*8;
        a.ty = a.deskY + (Math.random()-0.5)*8;
      }
      if (a.activity !== 'idle') {
        a.bubble = a.name + ' · ' + a.role;
        a.bt = 50;
      } else { a.bubble = ''; a.bt = 0; }
    }
    if (a.bt > 0) a.bt--; else a.bubble = '';
    var dx = a.tx - a.x, dy = a.ty - a.y;
    var dist = Math.sqrt(dx*dx+dy*dy);
    if (dist > 2) {
      a.x += dx/dist * 1.2;
      a.y += dy/dist * 1.2;
      a.wt++;
      if (a.wt > 10) { a.wf = (a.wf+1)%4; a.wt = 0; }
    } else { a.wf = 0; a.wt = 0; }
  });
}

function renderTerminal(d) {
  var el = document.getElementById('terminalPanel');
  if (!el) return;
  var n = new Date();
  var days = ['อา.','จ.','อ.','พ.','พฤ.','ศ.','ส.'];
  var ts = days[n.getDay()]+' '+n.getDate()+' มิ.ย. '+n.getFullYear()+' '+String(n.getHours()).padStart(2,'0')+':'+String(n.getMinutes()).padStart(2,'0')+':'+String(n.getSeconds()).padStart(2,'0');
  var isActive = d && d.bot === 'running';
  var list = [];
  for (var i = 0; i < 6; i++) {
    list.push({n:CHAR_NAMES[i], e:CHAR_EMOJI[i], r:['Technical Analyst','News Scout','Bullish Strategist','Bearish Guardian','Executive Chairman','Learning Engine'][i], s:isActive&&i%2===0?'on':'off'});
  }
  var ac = list.filter(function(a){return a.s==='on';}).length;
  var ic = list.length - ac;
  var html = '<div class="panel-header">📡 TEAM STATUS · สถานะทีม</div><div class="sync">🔄 Sync: '+ts+'</div><hr><div class="counts"><div class="count active"><div class="num">'+ac+'</div><div class="lbl">กำลังทำงาน</div></div><div class="count"><div class="num">'+ic+'</div><div class="lbl">ว่าง / Idle</div></div></div><hr><div class="grptitle">🔥 กำลังทำงาน</div>';
  for (var i = 0; i < list.length; i++) {
    var a = list[i];
    if (i%2===0 && isActive) {
      html += '<div class="agent-row"><span class="emoji">'+a.e+'</span><span class="name">'+a.n+'</span><span class="role">'+a.r+'</span><span class="tag on">Working</span></div>';
    }
  }
  html += '<div class="grptitle">💤 ว่าง</div>';
  for (var i = 0; i < list.length; i++) {
    var a = list[i];
    if (i%2!==0 || !isActive) {
      html += '<div class="agent-row"><span class="emoji">'+a.e+'</span><span class="name">'+a.n+'</span><span class="role">'+a.r+'</span><span class="tag off">Idle</span></div>';
    }
  }
  el.innerHTML = html;
}

// ===== GAME LOOP =====
function gameLoop() {
  updateAgents();
  ctx.clearRect(0, 0, W, H);
  drawFloor();
  
  // Draw desks
  for (var i = 0; i < DESKS.length; i++) drawDesk(DESKS[i]);
  
  // Sort agents by Y and draw
  var sorted = agents.slice().sort(function(a,b){return a.y-b.y;});
  for (var i = 0; i < sorted.length; i++) {
    drawBubble(sorted[i]);
    drawAgent(sorted[i]);
  }
  
  requestAnimationFrame(gameLoop);
}

// ===== STARTUP =====
function startGame() {
  gameLoop();
}

// Load all sprites
loadSprite('floor', '/static/assets/floors/floor_0.png');
loadSprite('desk_front', '/static/assets/furniture/DESK/DESK_FRONT.png');
loadSprite('chair', '/static/assets/furniture/WOODEN_CHAIR/WOODEN_CHAIR_FRONT.png');
loadSprite('pc_on', '/static/assets/furniture/PC/PC_FRONT_ON_1.png');
loadSprite('pc_off', '/static/assets/furniture/PC/PC_FRONT_OFF.png');
loadSprite('plant', '/static/assets/furniture/LARGE_PLANT/LARGE_PLANT.png');

// Character spritesheets
for (var i = 0; i < 6; i++) {
  loadSprite('char_' + i, '/static/assets/characters/char_' + i + '.png');
}

// Set a timeout to start even if sprites fail
setTimeout(startGame, 2000);

// Periodic refresh
async function refresh() {
  try {
    var r = await fetch('/api/agents');
    var d = await r.json();
    document.getElementById('liveDot').className = 'dot ' + (d.bot==='running'?'on':'off');
    renderTerminal(d);
  } catch(e){}
}
refresh();
setInterval(refresh, 10000);
renderTerminal({bot:'stopped'});
</script></body></html>"""
PAGE_DASHBOARD = r"""<!DOCTYPE html><html lang="th"><head><meta charset="UTF-8">
<title>Gold Sniper — Command Center</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#f5f0e0;color:#3d3224;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.header{background:#3d3224;border-bottom:2px solid #a37448;padding:0 20px;height:40px;display:flex;align-items:center;position:sticky;top:0;z-index:100}
.header a{color:#c8b888;text-decoration:none;padding:4px 12px;font-size:12px;border-radius:3px}
.header a:hover{background:rgba(200,184,136,0.1);color:#e8d8a8}
.header .brand{color:#e8d8a8;font-weight:bold;font-size:14px;margin-right:24px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-left:auto}
.dot.on{background:#56b846;box-shadow:0 0 4px #56b846}
.dot.off{background:#7a6a4a}
.container{max-width:1200px;margin:0 auto;padding:24px}
h1{font-size:24px;margin-bottom:4px;color:#3d3224}
.sub{color:#7a6a4a;font-size:12px;margin-bottom:20px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.card{background:#fff8ee;border:1px solid #d8c8a0;border-radius:6px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.card .num{font-size:28px;font-weight:bold;margin-bottom:2px}
.card .lbl{font-size:11px;color:#7a6a4a}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}
.panel{background:#fff8ee;border:1px solid #d8c8a0;border-radius:6px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.panel h3{font-size:13px;color:#a37448;margin-bottom:10px;border-bottom:1px solid #e8dcc0;padding-bottom:6px}
.row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0e8d0;font-size:12px}
.bar-chart{display:flex;align-items:flex-end;gap:6px;height:120px;margin-top:8px}
.bar{flex:1;max-width:32px;border-radius:3px 3px 0 0;min-height:3px}
.bar-lbl{font-size:8px;color:#7a6a4a;text-align:center;margin-top:3px}
.badge{display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600}
.badge.buy{background:#e8f0d8;color:#3a7a2a}
.badge.sell{background:#f8e0d8;color:#a04030}
.badge.tp{background:#e8f0d8;color:#3a7a2a}
.badge.sl{background:#f8e0d8;color:#a04030}
.loading{text-align:center;padding:50px;color:#7a6a4a}
@media(max-width:768px){.cards{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}}
</style></head><body>
<div class="header">
  <span class="brand">🔫 GSN Command Center</span>
  <a href="/">Dashboard</a><a href="/agent-hq">Agent HQ</a><a href="/trades">Trades</a><a href="/settings">Settings</a>
  <span class="dot" id="liveDot"></span>
</div>
<div class="container"><div id="content" class="loading">⏳ Loading...</div></div>
<script>
async function load(){
  try{
    var r=await fetch('/api/overview'),d=await r.json();
    var n=new Date(),days=['อา.','จ.','อ.','พ.','พฤ.','ศ.','ส.'];
    var ts=days[n.getDay()]+' '+n.getDate()+' มิ.ย. '+n.getFullYear()+' '+String(n.getHours()).padStart(2,'0')+':'+String(n.getMinutes()).padStart(2,'0')+':'+String(n.getSeconds()).padStart(2,'0');
    var wr=d.wr||0;
    var statusHtml='';try{
      var r2=await fetch('/api/agents'),d2=await r2.json();
      var bColor=d2.bot==='running'?'#3a7a2a':'#a04030';
      var bIcon=d2.bot==='running'?'🟢':'🔴';
      statusHtml='<div class="card" style="border-left:3px solid '+bColor+'"><div class="num" style="color:'+bColor+';font-size:20px">'+bIcon+' '+d2.bot.charAt(0).toUpperCase()+d2.bot.slice(1)+'</div><div class="lbl">Trading System (PID '+Math.floor(Math.random()*9000)+1000+')</div>';
      var cColor=d2.container&&d2.container.toLowerCase().indexOf('error')<0&&d2.container!=='stopped'?'#2c6b9e':'#7a6a4a';
      var pid='';try{var pr=await fetch('/api/pid'),pp=await pr.json();pid=' PID '+pp.pid}catch(e){}
      statusHtml+='<div class="row" style="margin-top:6px"><span>MT5 Container</span><span style="color:'+cColor+';font-size:11px">'+(d2.container||'stopped')+'</span></div>';
      if(pid) statusHtml+='<div class="row"><span>Bot</span><span style="font-size:11px;font-family:monospace">'+pid+'</span></div>';
      statusHtml+='</div>';
    }catch(e){statusHtml='<div class="card" style="border-left:3px solid #a04030"><div class="num" style="color:#a04030;font-size:20px">⚠️</div><div class="lbl">Status Unknown</div></div>';}
    var mh='';if(d.monthly&&d.monthly.length){
      var m=[...d.monthly].reverse(),mx=Math.max(...m.map(function(x){return Math.abs(x.p)}),1);
      mh='<div class="bar-chart">'+m.map(function(x){var pct=Math.max(Math.abs(x.p)/mx*100,5);return '<div style="flex:1;text-align:center"><div style="font-size:9px;color:#7a6a4a;margin-bottom:2px;font-family:monospace">'+(x.p>=0?'+':'')+'$'+x.p.toFixed(0)+'</div><div class="bar" style="height:'+pct+'%;background:'+(x.p>=0?'#56b846':'#c0392b')+'"></div><div class="bar-lbl">'+x.m.slice(5)+'</div></div>';}).join('')+'</div>';
    }
    var rh=d.regime&&d.regime.length?d.regime.map(function(r){return'<div class="row"><span style="color:#a37448">'+r.r+'</span><span>'+r.w+'W / '+r.t+'T <span style="color:'+(r.p>=0?'#3a7a2a':'#a04030')+'">$'+r.p.toFixed(0)+'</span></span></div>';}).join(''):'<div style="color:#aaa">No data</div>';
    var th=d.recent&&d.recent.length?d.recent.map(function(t){return'<div class="row"><span><span class="badge '+(t.s==='BUY'?'buy':'sell')+'">'+t.s+'</span></span><span style="font-family:monospace">$'+t.e.toFixed(2)+'</span><span style="font-family:monospace">$'+t.x.toFixed(2)+'</span><span style="font-family:monospace;font-weight:600;color:'+(t.p>=0?'#3a7a2a':'#a04030')+'">'+(t.p>=0?'+':'')+'$'+t.p.toFixed(2)+'</span><span><span class="badge '+(t.c==='TP'?'tp':'sl')+'">'+t.c+'</span></span><span style="color:#7a6a4a;font-size:11px">'+t.cf+'%</span></div>';}).join(''):'<div style="padding:20px;text-align:center;color:#aaa">No trades yet</div>';
    document.getElementById('content').innerHTML='<h1>ศูนย์บัญชาการ Gold Sniper</h1><div class="sub">ภาพรวมระบบ AI Trading Agents — 6 Agents 3 สาย ทำงานเรียลไทม์ | 🕐 '+ts+'</div><div class="cards"><div class="card"><div class="num" style="color:#a37448">'+d.total+'</div><div class="lbl">Total Trades</div></div><div class="card"><div class="num" style="color:'+(wr>=50?'#3a7a2a':'#a04030')+'">'+wr.toFixed(1)+'%</div><div class="lbl">Win Rate</div></div><div class="card"><div class="num" style="color:'+(d.pnl>=0?'#3a7a2a':'#a04030')+'">'+(d.pnl>=0?'+':'')+'$'+d.pnl.toFixed(0)+'</div><div class="lbl">P&L</div></div><div class="card"><div class="num" style="color:#2c6b9e">'+d.avg_r.toFixed(2)+'</div><div class="lbl">Avg R:R</div></div></div><div class="grid2"><div class="panel"><h3>📈 Monthly P&L</h3>'+(mh||'<div style="color:#aaa;padding:12px">No data</div>')+'</div><div class="panel"><h3>🏷️ By Regime</h3>'+rh+'</div></div><div class="panel"><h3>📋 Recent Trades</h3>'+th+'</div>';
  }catch(e){document.getElementById('content').innerHTML='<div style="text-align:center;padding:50px;color:#a04030">⚠️ Error: '+e.message+'</div>';}
}
async function dot(){try{var r=await fetch('/api/agents'),d=await r.json();document.getElementById('liveDot').className='dot '+(d.bot==="running"?'on':'off')}catch(e){}}
load();setInterval(load,15000);dot();setInterval(dot,10000);
</script></body></html>"""

# ═══════════════════════════════════════════════
# PAGE TRADES
# ═══════════════════════════════════════════════

PAGE_TRADES = r"""<!DOCTYPE html><html lang="th"><head><meta charset="UTF-8"><title>Gold Sniper — Trades</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#f5f0e0;color:#3d3224;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.header{background:#3d3224;border-bottom:2px solid #a37448;padding:0 20px;height:40px;display:flex;align-items:center;position:sticky;top:0;z-index:100}
.header a{color:#c8b888;text-decoration:none;padding:4px 12px;font-size:12px;border-radius:3px}
.header a:hover{background:rgba(200,184,136,0.1);color:#e8d8a8}
.header .brand{color:#e8d8a8;font-weight:bold;font-size:14px;margin-right:24px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-left:auto}
.dot.on{background:#56b846;box-shadow:0 0 4px #56b846}.dot.off{background:#7a6a4a}
.container{max-width:1200px;margin:0 auto;padding:24px}
h1{font-size:22px;margin-bottom:16px}
table{width:100%;border-collapse:collapse;background:#fff8ee;border:1px solid #d8c8a0;border-radius:6px;overflow:hidden}
th{background:#e8dcc0;padding:10px 12px;text-align:left;font-size:11px;color:#7a6a4a;border-bottom:1px solid #d8c8a0}
td{padding:10px 12px;border-bottom:1px solid #f0e8d0;font-size:12px}
tr:hover td{background:#fdf8ee}
.badge{display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600}
.badge.buy{background:#e8f0d8;color:#3a7a2a}.badge.sell{background:#f8e0d8;color:#a04030}
.badge.tp{background:#e8f0d8;color:#3a7a2a}.badge.sl{background:#f8e0d8;color:#a04030}
.loading{text-align:center;padding:50px;color:#7a6a4a}
</style></head><body>
<div class="header">
  <span class="brand">🔫 GSN Command Center</span>
  <a href="/">Dashboard</a><a href="/agent-hq">Agent HQ</a><a href="/trades">Trades</a><a href="/settings">Settings</a>
  <span class="dot" id="liveDot"></span>
</div>
<div class="container">
<h1>📋 Trade History</h1>
<div id="tc" class="loading">⏳ Loading...</div></div>
<script>
async function load(){
  try{
    var r=await fetch('/api/overview'),d=await r.json();
    if(!d.recent||!d.recent.length){document.getElementById('tc').innerHTML='<div style="padding:40px;text-align:center;color:#aaa;background:#fff8ee;border:1px solid #d8c8a0;border-radius:6px">No trades yet</div>';return}
    document.getElementById('tc').innerHTML='<table><thead><tr><th>Signal</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Result</th><th>Regime</th><th>Conf</th></tr></thead><tbody>'+d.recent.map(function(t){return'<tr><td><span class="badge '+(t.s==='BUY'?'buy':'sell')+'">'+t.s+'</span></td><td style="font-family:monospace">$'+t.e.toFixed(2)+'</td><td style="font-family:monospace">$'+t.x.toFixed(2)+'</td><td style="font-family:monospace;font-weight:600;color:'+(t.p>=0?'#3a7a2a':'#a04030')+'">'+(t.p>=0?'+':'')+'$'+t.p.toFixed(2)+'</td><td><span class="badge '+(t.c==='TP'?'tp':'sl')+'">'+t.c+'</span></td><td style="color:#7a6a4a;font-size:11px">'+t.rg+'</td><td>'+t.cf+'%</td></tr>';}).join('')+'</tbody></table>';
  }catch(e){document.getElementById('tc').innerHTML='<div style="color:#a04030;padding:40px">Error</div>'}
}
async function dot(){try{var r=await fetch('/api/agents'),d=await r.json();document.getElementById('liveDot').className='dot '+(d.bot==="running"?'on':'off')}catch(e){}}
load();setInterval(load,30000);dot();setInterval(dot,10000);
</script></body></html>"""

# ═══════════════════════════════════════════════
# PAGE SETTINGS
# ═══════════════════════════════════════════════

PAGE_SETTINGS = r"""<!DOCTYPE html><html lang="th"><head><meta charset="UTF-8"><title>Gold Sniper — Settings</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#f5f0e0;color:#3d3224;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.header{background:#3d3224;border-bottom:2px solid #a37448;padding:0 20px;height:40px;display:flex;align-items:center;position:sticky;top:0;z-index:100}
.header a{color:#c8b888;text-decoration:none;padding:4px 12px;font-size:12px;border-radius:3px}
.header a:hover{background:rgba(200,184,136,0.1);color:#e8d8a8}
.header .brand{color:#e8d8a8;font-weight:bold;font-size:14px;margin-right:24px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-left:auto}
.dot.on{background:#56b846;box-shadow:0 0 4px #56b846}.dot.off{background:#7a6a4a}
.container{max-width:1000px;margin:0 auto;padding:24px}
h1{font-size:22px;margin-bottom:16px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
.panel{background:#fff8ee;border:1px solid #d8c8a0;border-radius:6px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.panel h3{font-size:13px;color:#a37448;margin-bottom:10px;border-bottom:1px solid #e8dcc0;padding-bottom:6px}
.row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0e8d0;font-size:12px}
.loading{text-align:center;padding:30px;color:#7a6a4a}
</style></head><body>
<div class="header">
  <span class="brand">🔫 GSN Command Center</span>
  <a href="/">Dashboard</a><a href="/agent-hq">Agent HQ</a><a href="/trades">Trades</a><a href="/settings">Settings</a>
  <span class="dot" id="liveDot"></span>
</div>
<div class="container">
<h1>⚙️ Settings</h1>
<div class="grid2">
  <div class="panel" id="sysPanel"><h3>🤖 System Status</h3><div class="loading">Loading...</div></div>
  <div class="panel" id="paramPanel"><h3>🧠 Learned Params</h3><div class="loading">Loading...</div></div>
</div></div>
<script>
async function load(){
  try{
    var r=await fetch('/api/agents'),d=await r.json();
    document.getElementById('sysPanel').innerHTML='<h3>🤖 System Status</h3><div class="row"><span>Bot</span><span style="color:'+(d.bot==="running"?'#3a7a2a':'#a04030')+';font-weight:600">'+(d.bot==="running"?'🟢 Running':'🔴 Stopped')+'</span></div><div class="row"><span>Container</span><span style="color:#2c6b9e">'+d.container+'</span></div><div class="row"><span>Win Rate</span><span style="color:#a37448;font-weight:600">'+d.wr.toFixed(1)+'%</span></div><div class="row"><span>Consecutive Losses</span><span style="color:'+(d.cons>=3?'#a04030':'#7a6a4a')+'">'+d.cons+'</span></div>';
    var th=d.thresh||{};document.getElementById('paramPanel').innerHTML='<h3>🧠 Confidence Thresholds</h3>'+Object.entries(th).map(function(kv){return'<div class="row"><span>'+kv[0]+'</span><span style="color:#a37448;font-family:monospace">'+(kv[1]*100).toFixed(0)+'%</span></div>';}).join('')||'<div style="color:#aaa">Default params</div>';
  }catch(e){['sysPanel','paramPanel'].forEach(function(id){var el=document.getElementById(id);if(el)el.innerHTML='<h3>⚠️</h3><div style="color:#a04030">Error</div>';})}
}
async function dot(){try{var r=await fetch('/api/agents'),d=await r.json();document.getElementById('liveDot').className='dot '+(d.bot==="running"?'on':'off')}catch(e){}}
load();setInterval(load,30000);dot();setInterval(dot,10000);
</script></body></html>"""

if __name__ == "__main__":
    print(f"🎮 Gold Sniper HQ running on :{PORT}")
    HTTPServer(("0.0.0.0",PORT), Handler).serve_forever()