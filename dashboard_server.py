"""
Pixel Art Trading Dashboard Server
Serves a retro pixel-art dashboard with Canvas-based Agent HQ
"""
import os, sys, json, sqlite3, subprocess, mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from pathlib import Path

# mt5linux for live price
try:
    from mt5linux import MetaTrader5 as _MT5
except ImportError:
    _MT5 = None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

DB_PATH = os.path.join(os.path.dirname(__file__), "trade_memory.db")
LEARNED_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "learned_config.json")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
PORT = 8080


class DashboardAPI:
    def __init__(self):
        self.db_path = DB_PATH

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_overview(self) -> dict:
        try:
            learned = {}
            if os.path.exists(LEARNED_CONFIG_PATH):
                with open(LEARNED_CONFIG_PATH) as f:
                    learned = json.load(f)
        except:
            learned = {}

        conn = self._get_conn()
        try:
            row = conn.execute("""
                SELECT COUNT(*) as total,
                    SUM(CASE WHEN close_reason='TP' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN close_reason='SL' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN close_reason='BREAKEVEN' THEN 1 ELSE 0 END) as breakevens,
                    COALESCE(SUM(pnl_usd), 0) as total_pnl,
                    COALESCE(AVG(CASE WHEN close_reason IS NOT NULL THEN r_achieved END), 0) as avg_r
                FROM trades
            """).fetchone()
            monthly = conn.execute("""
                SELECT strftime('%Y-%m', entry_time) as month, COUNT(*) as trades,
                    SUM(CASE WHEN close_reason='TP' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN close_reason='SL' THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(pnl_usd), 0) as pnl
                FROM trades WHERE pnl_usd IS NOT NULL
                GROUP BY month ORDER BY month DESC LIMIT 12
            """).fetchall()
            regime_stats = conn.execute("""
                SELECT regime, COUNT(*) as total,
                    SUM(CASE WHEN close_reason='TP' THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(pnl_usd), 0) as pnl
                FROM trades WHERE regime IS NOT NULL
                GROUP BY regime
            """).fetchall()
            recent = conn.execute("""
                SELECT signal, entry_price, exit_price, pnl_usd, close_reason,
                       regime, confidence, entry_time, r_achieved
                FROM trades WHERE close_reason IS NOT NULL
                ORDER BY entry_time DESC LIMIT 10
            """).fetchall()
            session_stats = conn.execute("""
                SELECT session, COUNT(*) as total,
                    SUM(CASE WHEN close_reason='TP' THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(pnl_usd), 0) as pnl
                FROM trades WHERE session IS NOT NULL
                GROUP BY session
            """).fetchall()
            confidence_stats = conn.execute("""
                SELECT CASE
                    WHEN confidence >= 0.95 THEN 'ULTRA_HIGH'
                    WHEN confidence >= 0.90 THEN 'HIGH'
                    WHEN confidence >= 0.85 THEN 'MODERATE'
                    WHEN confidence >= 0.78 THEN 'STANDARD'
                    ELSE 'LOW' END as bucket,
                    COUNT(*) as total,
                    SUM(CASE WHEN close_reason='TP' THEN 1 ELSE 0 END) as wins
                FROM trades WHERE confidence IS NOT NULL
                GROUP BY bucket
            """).fetchall()
            total = row["total"] or 0
            wins = row["wins"] or 0
            losses = row["losses"] or 0
            total_pnl = row["total_pnl"] or 0.0
            winrate = (wins / total * 100) if total > 0 else 0
            avg_r = row["avg_r"] or 0.0
            return {
                "status": "ok",
                "total_trades": total,
                "wins": wins, "losses": losses,
                "breakevens": row["breakevens"] or 0,
                "winrate": round(winrate, 1),
                "total_pnl": round(total_pnl, 2),
                "avg_r": round(avg_r, 2),
                "consecutive_losses": learned.get("consecutive_losses", 0),
                "overall_winrate": learned.get("overall_winrate", 0),
                "monthly": [{"month": m["month"], "trades": m["trades"],
                    "wins": m["wins"], "losses": m["losses"], "pnl": round(m["pnl"], 2)} for m in monthly],
                "by_regime": [{"regime": r["regime"], "total": r["total"],
                    "wins": r["wins"], "pnl": round(r["pnl"], 2),
                    "winrate": round((r["wins"]/r["total"]*100) if r["total"]>0 else 0, 1)} for r in regime_stats],
                "by_session": [{"session": s["session"], "total": s["total"],
                    "wins": s["wins"], "pnl": round(s["pnl"], 2),
                    "winrate": round((s["wins"]/s["total"]*100) if s["total"]>0 else 0, 1)} for s in session_stats],
                "by_confidence": [{"bucket": c["bucket"], "total": c["total"],
                    "wins": c["wins"],
                    "winrate": round((c["wins"]/c["total"]*100) if c["total"]>0 else 0, 1)} for c in confidence_stats],
                "recent_trades": [{"signal": r["signal"],
                    "entry": round(r["entry_price"], 2) if r["entry_price"] else 0,
                    "exit": round(r["exit_price"], 2) if r["exit_price"] else 0,
                    "pnl": round(r["pnl_usd"], 2) if r["pnl_usd"] else 0,
                    "result": r["close_reason"], "regime": r["regime"],
                    "confidence": round(r["confidence"]*100) if r["confidence"] else 0,
                    "time": r["entry_time"][:19] if r["entry_time"] else "",
                    "r": round(r["r_achieved"], 2) if r["r_achieved"] else 0} for r in recent]
            }
        finally:
            conn.close()

    def get_agents_status(self) -> dict:
        try:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
            bot_running = "main.py live" in result.stdout
        except:
            bot_running = False
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=claw-trade-mt5", "--format", "{{.Status}}"],
                capture_output=True, text=True, timeout=5)
            container_status = result.stdout.strip()[:50] if result.stdout.strip() else "stopped"
        except:
            container_status = "unknown"
        try:
            with open(LEARNED_CONFIG_PATH) as f:
                learned = json.load(f)
        except:
            learned = {}

        # Calculate real Levels from DB performance
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) as c FROM trades").fetchone()["c"] or 0
            wins = conn.execute("SELECT COUNT(*) as c FROM trades WHERE close_reason='TP'").fetchone()["c"] or 0

            # Quant Analyst: macd_state accuracy
            q_wins = conn.execute("SELECT COUNT(*) as c FROM trades WHERE close_reason='TP' AND macd_state IS NOT NULL").fetchone()["c"] or 0
            q_total = conn.execute("SELECT COUNT(*) as c FROM trades WHERE macd_state IS NOT NULL").fetchone()["c"] or 0
            q_lvl = min(10, 1 + q_wins * 2 + int(q_total * 0.3)) if q_total > 0 else 1

            # News Analyst: session-based accuracy
            n_wins = conn.execute("SELECT COUNT(*) as c FROM trades WHERE close_reason='TP' AND session IS NOT NULL").fetchone()["c"] or 0
            n_total = conn.execute("SELECT COUNT(*) as c FROM trades WHERE session IS NOT NULL").fetchone()["c"] or 0
            n_lvl = min(10, 1 + n_wins * 2 + int(n_total * 0.3)) if n_total > 0 else 1

            # Bull Agent: BUY signal accuracy
            b_wins = conn.execute("SELECT COUNT(*) as c FROM trades WHERE close_reason='TP' AND signal='BUY'").fetchone()["c"] or 0
            b_total = conn.execute("SELECT COUNT(*) as c FROM trades WHERE signal='BUY'").fetchone()["c"] or 0
            b_lvl = min(10, 1 + b_wins * 2 + int(b_total * 0.3)) if b_total > 0 else 1

            # Bear Agent: SELL signal accuracy
            be_wins = conn.execute("SELECT COUNT(*) as c FROM trades WHERE close_reason='TP' AND signal='SELL'").fetchone()["c"] or 0
            be_total = conn.execute("SELECT COUNT(*) as c FROM trades WHERE signal='SELL'").fetchone()["c"] or 0
            be_lvl = min(10, 1 + be_wins * 2 + int(be_total * 0.3)) if be_total > 0 else 1

            # CEO Agent: overall decision accuracy
            ceo_lvl = min(10, 1 + wins * 2 + int(total * 0.3)) if total > 0 else 1

            # Learning Engine: trades analyzed
            le_lvl = min(10, 1 + int(total * 0.5) + int(learned.get("overall_winrate", 0) / 20))
        finally:
            conn.close()

        agents = [
            {"name": "Quant Analyst", "title": "เทคนิคัล วิซาร์ด", "status": "active" if bot_running else "idle",
             "color": "#00ff88", "duty": "RSI, MACD, EMA, Fibo", "level": q_lvl},
            {"name": "News Analyst", "title": "นักข่าวสงคราม", "status": "active" if bot_running else "idle",
             "color": "#ffaa00", "duty": "News & Sentiment", "level": n_lvl},
            {"name": "Bull Agent", "title": "อัศวินกระทิง", "status": "active" if bot_running else "idle",
             "color": "#ff4444", "duty": "Long Signals", "level": b_lvl},
            {"name": "Bear Agent", "title": "จอมพลหมี", "status": "active" if bot_running else "idle",
             "color": "#4488ff", "duty": "Short Signals", "level": be_lvl},
            {"name": "CEO Agent", "title": "ท่านประธาน", "status": "active" if bot_running else "idle",
             "color": "#ffdd00", "duty": "Final Decision", "level": ceo_lvl},
            {"name": "Learning Engine", "title": "สมองกล", "status": "active",
             "color": "#ff66ff", "duty": f"Optimizer ({learned.get('overall_winrate', 0):.0f}% WR)", "level": le_lvl}
        ]
        return {"agents": agents, "bot_running": bot_running, "container_status": container_status,
                "confidence_thresholds": learned.get("confidence_threshold", {})}

    def get_performance_chart(self) -> dict:
        conn = self._get_conn()
        try:
            trades = conn.execute("""
                SELECT entry_time, pnl_usd, close_reason
                FROM trades WHERE close_reason IS NOT NULL
                ORDER BY entry_time ASC
            """).fetchall()
            equity_curve = []
            balance = 10450.96
            for t in trades:
                if t["pnl_usd"] is not None:
                    balance += t["pnl_usd"]
                    equity_curve.append({
                        "date": t["entry_time"][:10] if t["entry_time"] else "",
                        "balance": round(balance, 2),
                        "pnl": round(t["pnl_usd"], 2), "result": t["close_reason"]
                    })
            return {
                "equity_curve": equity_curve,
                "current_balance": round(balance, 2),
                "initial_balance": 10450.96,
                "total_growth": round(((balance - 10450.96) / 10450.96) * 100, 2)
            }
        finally:
            conn.close()

    def get_hermes_status(self) -> dict:
        try:
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=5
            )
            running = "hermes gateway" in result.stdout or "hermes agent" in result.stdout.lower()
        except:
            running = False

        # Get uptime
        uptime = "--"
        try:
            result = subprocess.run(
                ["ps", "-eo", "pid,etime,cmd", "--no-headers"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if "hermes" in line.lower() and "gateway" in line.lower():
                    parts = line.strip().split(None, 2)
                    if len(parts) >= 2:
                        uptime = parts[1]
                    break
        except:
            pass

        return {
            "running": running,
            "uptime": uptime,
            "version": "v0.1.0",
            "profile": "default"
        }

    def get_spawned_agents(self) -> dict:
        """Return dynamically spawned agents (from delegate_task etc)."""
        path = os.path.join(os.path.dirname(__file__), "spawned_agents.json")
        try:
            if os.path.exists(path):
                with open(path) as f:
                    agents = json.load(f)
            else:
                agents = []
        except:
            agents = []
        # Clean up stale agents (older than 1 hour)
        now = datetime.now().timestamp()
        alive = []
        for a in agents:
            t = a.get("created_at", 0)
            if now - t < 3600:
                alive.append(a)
        return {"agents": alive, "count": len(alive)}

    def get_live_price(self) -> dict:
        """Fetch live XAU/USD price from MT5 via mt5linux."""
        if _MT5 is None:
            return {"ok": False, "price": 0, "change": 0, "regime": "--", "session": "--", "spread": 0}
        try:
            m = _MT5(host='localhost', port=8001)
            m.initialize()
            tick = m.symbol_info_tick("XAUUSDc")
            if tick:
                return {
                    "price": round(tick.ask, 2),
                    "bid": round(tick.bid, 2),
                    "ask": round(tick.ask, 2),
                    "spread": round((tick.ask - tick.bid) * 100, 1),
                    "change": round(tick.ask - tick.last, 2) if tick.last else 0,
                    "regime": "--",
                    "session": "--",
                    "ok": True
                }
        except Exception:
            pass
        return {"ok": False, "price": 0, "change": 0, "regime": "--", "session": "--", "spread": 0}

    def register_agent(self, name: str, task: str, agent_type: str = "hermes") -> dict:
        """Register a spawned agent so it appears on the dashboard."""
        path = os.path.join(os.path.dirname(__file__), "spawned_agents.json")
        try:
            if os.path.exists(path):
                with open(path) as f:
                    agents = json.load(f)
            else:
                agents = []
        except:
            agents = []
        entry = {
            "id": len(agents) + 1,
            "name": name,
            "task": task,
            "type": agent_type,
            "status": "working",
            "created_at": datetime.now().timestamp(),
            "started_at": datetime.now().strftime("%H:%M:%S")
        }
        agents.append(entry)
        with open(path, "w") as f:
            json.dump(agents, f, indent=2)
        return {"ok": True, "id": entry["id"]}

    def complete_agent(self, agent_id: int) -> dict:
        """Mark a spawned agent as completed."""
        path = os.path.join(os.path.dirname(__file__), "spawned_agents.json")
        try:
            with open(path) as f:
                agents = json.load(f)
        except:
            return {"ok": False, "error": "no agents"}
        for a in agents:
            if a.get("id") == agent_id:
                a["status"] = "completed"
                a["completed_at"] = datetime.now().strftime("%H:%M:%S")
                break
        with open(path, "w") as f:
            json.dump(agents, f, indent=2)
        return {"ok": True}


class DashboardHandler(BaseHTTPRequestHandler):
    api = DashboardAPI()

    def do_GET(self):
        # Parse query params
        full_path = self.path
        if "?" in full_path:
            path, query = full_path.split("?", 1)
            theme = dict(q.split("=") for q in query.split("&") if "=" in q).get("theme", "")
        else:
            path = full_path
            theme = ""

        # API routes
        if path == "/api/overview":
            return self._serve_json(self.api.get_overview())
        elif path == "/api/agents":
            return self._serve_json(self.api.get_agents_status())
        elif path == "/api/chart":
            return self._serve_json(self.api.get_performance_chart())
        elif path == "/api/hermes":
            return self._serve_json(self.api.get_hermes_status())
        elif path == "/api/spawned-agents":
            return self._serve_json(self.api.get_spawned_agents())
        elif path == "/api/live-price":
            return self._serve_json(self.api.get_live_price())
        elif path == "/agent-hq" or path == "/agent-hq/":
            # Serve actual Pixel Agent Office from static build
            fpath = os.path.join(os.path.dirname(__file__), "static", "pixel-agents-build", "index.html")
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404)
            return

        # Static assets (mapped from static/ directory)
        if path.startswith("/assets/") or path.startswith("/pixel-agents-build/") or path.startswith("/agent-hq/"):
            return self._serve_static()

        # Serve pages - default dashboard
        return self._serve_light_html()

    def do_POST(self):
        path = self.path.split("?")[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len)) if content_len else {}

        if path == "/api/register-agent":
            result = self.api.register_agent(
                name=body.get("name", "Unnamed"),
                task=body.get("task", ""),
                agent_type=body.get("type", "hermes")
            )
            return self._serve_json(result)
        elif path == "/api/complete-agent":
            result = self.api.complete_agent(agent_id=body.get("id", 0))
            return self._serve_json(result)
        else:
            self.send_error(404)

    def _serve_static(self):
        rel = self.path.lstrip("/")
        # Map /agent-hq/ paths to the pixel-agents-build directory
        if rel.startswith("agent-hq/"):
            rel = "pixel-agents-build/" + rel[len("agent-hq/"):]
        # Assets live under static/ directory
        fpath = os.path.join(os.path.dirname(__file__), "static", rel)
        # Serve index.html for directory paths (SPA routing)
        if os.path.isdir(fpath):
            fpath = os.path.join(fpath, "index.html")
        if not os.path.isfile(fpath):
            self.send_error(404)
            return
        ext = os.path.splitext(fpath)[1].lower()
        mt = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
        # Force pixel-perfect for PNGs
        self.send_response(200)
        self.send_header("Content-Type", mt)
        self.send_header("Cache-Control", "max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(fpath, "rb") as f:
            self.wfile.write(f.read())

    def _serve_html(self, html_str):
        """Serve a given HTML string (pixel art theme)."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(html_str.encode("utf-8"))

    def _serve_light_html(self):
        """Serve light theme from static/index.html."""
        html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        if os.path.exists(html_path):
            with open(html_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

    def _serve_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, *args):
        pass


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🤖 GOLD SNIPER AI</title>
<style>
/* === PIXEL ART THEME === */
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Prompt:wght@400;600;700&display=swap');

* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --bg: #0f0f23;
  --panel: #1a1a3e;
  --panel-alt: #161638;
  --border: #2a2a5a;
  --text: #c8d6e5;
  --dim: #576574;
  --green: #00ff88;
  --red: #ff4757;
  --gold: #ffd700;
  --blue: #4488ff;
  --purple: #a855f7;
  --pink: #ff66ff;
  --pixel: 'Press Start 2P', monospace;
  --font: 'Prompt', sans-serif;
  --tile: 48px;
}

html, body { height: 100%; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* CRT Scanlines */
body::after {
  content: '';
  position: fixed;
  inset: 0;
  background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.06) 2px, rgba(0,0,0,0.06) 4px);
  pointer-events: none;
  z-index: 9999;
}

/* === TOP BAR === */
.topbar {
  background: linear-gradient(180deg, #1a1a3e, #0f0f23);
  border-bottom: 3px solid var(--gold);
  padding: 8px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  z-index: 100;
  position: relative;
}

.topbar-title {
  font-family: var(--pixel);
  font-size: 11px;
  color: var(--gold);
  text-shadow: 0 0 12px rgba(255,215,0,0.4);
  letter-spacing: 1px;
}

.topbar-stats {
  display: flex;
  gap: 14px;
  font-size: 11px;
  align-items: center;
}

.topstat { display: flex; align-items: center; gap: 4px; }
.topstat .val { font-family: var(--pixel); font-size: 9px; color: var(--green); }
.topstat .lbl { color: var(--dim); font-size: 10px; }

.live-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.live-dot.on { background: var(--green); box-shadow: 0 0 10px var(--green); animation: pulse-dot 1.5s infinite; }
.live-dot.off { background: var(--red); }
@keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:0.3} }

/* === NAV TABS === */
.nav {
  display: flex;
  gap: 0;
  background: var(--panel-alt);
  border-bottom: 2px solid var(--border);
  flex-shrink: 0;
  overflow-x: auto;
}

.nav-btn {
  font-family: var(--pixel);
  font-size: 8px;
  padding: 10px 20px;
  background: transparent;
  border: none;
  color: var(--dim);
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 3px solid transparent;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 6px;
}
.nav-btn:hover { color: var(--text); background: rgba(255,255,255,0.03); }
.nav-btn.active { color: var(--gold); border-bottom-color: var(--gold); background: rgba(255,215,0,0.05); }

/* === CONTENT === */
.content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.page {
  display: none;
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 12px;
}
.page.active { display: block; }

/* === DASHBOARD PAGE === */
.dash-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.dash-card {
  background: var(--panel);
  border: 2px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  text-align: center;
  position: relative;
  overflow: hidden;
}
.dash-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--gold), transparent);
}
.dash-card .num {
  font-family: var(--pixel);
  font-size: 18px;
  margin-bottom: 4px;
}
.dash-card .lbl { font-size: 10px; color: var(--dim); }
.num.gold { color: var(--gold); }
.num.green { color: var(--green); }
.num.red { color: var(--red); }
.num.blue { color: var(--blue); }

.dash-panels {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 10px;
  margin-bottom: 12px;
}

.panel {
  background: var(--panel);
  border: 2px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  position: relative;
}
.panel::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--gold), transparent);
}
.panel-full { grid-column: 1 / -1; }

.panel-title {
  font-family: var(--pixel);
  font-size: 9px;
  color: var(--gold);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Bar chart */
.bar-chart { display: flex; align-items: flex-end; gap: 6px; height: 120px; padding: 0 4px; }
.bar-wrap { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end; }
.bar { width: 100%; max-width: 30px; border-radius: 2px 2px 0 0; min-height: 2px; }
.bar.green { background: linear-gradient(180deg, var(--green), #00cc66); }
.bar.red { background: linear-gradient(180deg, var(--red), #cc1133); }
.bar-val { font-size: 6px; color: var(--gold); font-family: var(--pixel); margin-bottom: 2px; }
.bar-lbl { font-size: 7px; color: var(--dim); margin-top: 2px; font-family: var(--pixel); }

/* Win rate circle */
.wr-circle {
  width: 70px; height: 70px;
  border-radius: 50%;
  border: 3px solid var(--border);
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  margin: 0 auto;
}
.wr-circle .pct { font-family: var(--pixel); font-size: 16px; }
.wr-circle .pct.green { color: var(--green); }
.wr-circle .pct.red { color: var(--red); }
.wr-circle .pct-lbl { font-size: 7px; color: var(--dim); font-family: var(--pixel); }

/* Tables */
.trade-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.trade-table th {
  font-family: var(--pixel); font-size: 7px; color: var(--gold);
  padding: 6px 8px; text-align: left; border-bottom: 1px solid var(--border);
}
.trade-table td { padding: 6px 8px; border-bottom: 1px solid rgba(42,42,90,0.3); font-size: 10px; }
.trade-table tr:hover td { background: rgba(255,215,0,0.03); }

.sig { display: inline-block; padding: 1px 6px; border-radius: 2px; font-family: var(--pixel); font-size: 7px; }
.sig.buy { background: rgba(0,255,136,0.15); color: var(--green); }
.sig.sell { background: rgba(255,71,87,0.15); color: var(--red); }
.res { display: inline-block; padding: 1px 6px; border-radius: 2px; font-family: var(--pixel); font-size: 7px; }
.res.tp { background: rgba(0,255,136,0.15); color: var(--green); }
.res.sl { background: rgba(255,71,87,0.15); color: var(--red); }
.res.be { background: rgba(255,215,0,0.15); color: var(--gold); }

.loading { text-align: center; padding: 30px; color: var(--dim); font-family: var(--pixel); font-size: 10px; }
.loading::after { content: ''; display: inline-block; width: 6px; height: 6px; background: var(--gold); margin-left: 6px; animation: blink 0.6s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

.loss-alert {
  background: rgba(255,71,87,0.1); border: 1px solid var(--red);
  border-radius: 6px; padding: 6px 10px; font-size: 10px;
  color: var(--red); margin-top: 6px; text-align: center;
  animation: pulse-alert 1.5s infinite;
}
@keyframes pulse-alert { 0%,100%{opacity:0.7} 50%{opacity:1} }

/* === AGENT HQ (CANVAS) === */
#agentHQ {
  display: flex;
  height: 100%;
  gap: 0;
}

#canvasWrap {
  flex: 1;
  position: relative;
  background: #0a0a1a;
  overflow: hidden;
}

#officeCanvas {
  display: block;
  width: 100%;
  height: 100%;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
}

/* Side Panel */
#sidePanel {
  width: 280px;
  background: var(--panel);
  border-left: 2px solid var(--border);
  overflow-y: auto;
  flex-shrink: 0;
  padding: 10px;
}

.sp-title {
  font-family: var(--pixel);
  font-size: 8px;
  color: var(--gold);
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

.sp-agent {
  background: var(--panel-alt);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.2s;
}
.sp-agent:hover { border-color: var(--gold); transform: translateX(-2px); }
.sp-agent.selected { border-color: var(--gold); box-shadow: 0 0 10px rgba(255,215,0,0.1); }

.sp-agent-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sp-agent-preview {
  width: 32px;
  height: 32px;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  background: var(--bg);
  border-radius: 4px;
  border: 1px solid var(--border);
  flex-shrink: 0;
}

.sp-agent-info { flex: 1; min-width: 0; }
.sp-agent-name {
  font-family: var(--pixel);
  font-size: 7px;
  color: var(--text);
  margin-bottom: 2px;
}
.sp-agent-title { font-size: 9px; color: var(--dim); }

.sp-agent-status {
  font-size: 7px;
  font-family: var(--pixel);
  padding: 1px 6px;
  border-radius: 8px;
  display: inline-block;
}
.sp-agent-status.active { background: rgba(0,255,136,0.15); color: var(--green); }
.sp-agent-status.idle { background: rgba(87,101,116,0.15); color: var(--dim); }

.sp-hp { margin-top: 6px; height: 4px; background: rgba(255,255,255,0.05); border-radius: 2px; overflow: hidden; }
.sp-hp-fill { height: 100%; border-radius: 2px; }

.sp-agent-duty {
  font-size: 9px;
  color: var(--dim);
  margin-top: 4px;
  padding-left: 40px;
}

/* Speech bubble on canvas */
.speech-bubble {
  position: absolute;
  background: rgba(26,26,62,0.95);
  border: 2px solid var(--gold);
  border-radius: 8px;
  padding: 6px 10px;
  font-family: var(--pixel);
  font-size: 7px;
  color: var(--text);
  pointer-events: none;
  z-index: 10;
  white-space: nowrap;
  transform: translate(-50%, -100%);
}
.speech-bubble::after {
  content: '';
  position: absolute;
  bottom: -8px;
  left: 50%;
  transform: translateX(-50%);
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-top: 8px solid var(--gold);
}

/* === TRADES PAGE === */
.trade-filters {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.trade-filters select, .trade-filters input {
  background: var(--panel);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 6px 10px;
  border-radius: 4px;
  font-family: var(--font);
  font-size: 11px;
}
.trade-filters select { cursor: pointer; }

/* === SETTINGS PAGE === */
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid rgba(42,42,90,0.3);
}
.setting-item .lbl { font-size: 11px; }
.setting-item .val { font-family: var(--pixel); font-size: 8px; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #3a3a6a; }

/* Responsive sidebar */
@media (max-width: 900px) {
  #sidePanel { width: 200px; }
}
@media (max-width: 700px) {
  #agentHQ { flex-direction: column; }
  #sidePanel { width: 100%; max-height: 200px; border-left: none; border-top: 2px solid var(--border); }
  .dash-panels { grid-template-columns: 1fr; }
  .dash-grid { grid-template-columns: repeat(2, 1fr); }
  .settings-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<!-- Top Bar -->
<div class="topbar">
  <div class="topbar-title">🔫 GOLD SNIPER AI <span style="color:var(--dim);font-size:8px">v3.0</span></div>
  <div class="topbar-stats">
    <div class="topstat">
      <span class="live-dot" id="botDot">●</span>
      <span id="botLabel" style="font-size:9px">Loading...</span>
    </div>
    <div class="topstat"><span class="lbl">Bal:</span><span class="val" id="hdrBal">$--</span></div>
    <div class="topstat"><span class="lbl">Growth:</span><span class="val" id="hdrGrowth">--%</span></div>
  </div>
</div>

<!-- Nav Tabs -->
<div class="nav" id="navTabs">
  <button class="nav-btn active" data-page="dash">📊 Dashboard</button>
  <button class="nav-btn" data-page="hq">🏢 Agent HQ</button>
  <button class="nav-btn" data-page="trades">📋 Trades</button>
  <button class="nav-btn" data-page="settings">⚙️ Settings</button>
</div>

<!-- Content -->
<div class="content">

  <!-- === DASHBOARD PAGE === -->
  <div class="page active" id="page-dash">
    <div class="dash-grid" id="statsGrid"><div class="loading">LOADING...</div></div>
    <div id="lossAlert"></div>
    <div class="dash-panels">
      <div class="panel">
        <div class="panel-title">📈 Monthly P&L</div>
        <div id="monthlyChart"><div class="loading">LOADING...</div></div>
      </div>
      <div class="panel">
        <div class="panel-title">🎯 Performance</div>
        <div id="perfPanel"><div class="loading">LOADING...</div></div>
      </div>
      <div class="panel">
        <div class="panel-title">🏷️ By Regime</div>
        <div id="regimePanel"><div class="loading">LOADING...</div></div>
      </div>
    </div>
    <div class="panel panel-full">
      <div class="panel-title">📋 Recent Trades</div>
      <div id="tradesPanel"><div class="loading">LOADING...</div></div>
    </div>
  </div>

  <!-- === AGENT HQ PAGE === -->
  <div class="page" id="page-hq">
    <div id="agentHQ">
      <div id="canvasWrap">
        <canvas id="officeCanvas"></canvas>
        <div id="bubble" class="speech-bubble" style="display:none"></div>
      </div>
      <div id="sidePanel">
        <div class="sp-title">👥 AGENT STATUS</div>
        <div id="agentList"></div>
        <div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border)">
          <div style="font-family:var(--pixel);font-size:7px;color:var(--dim);margin-bottom:6px">SYSTEM</div>
          <div style="font-size:10px;display:flex;justify-content:space-between">
            <span>Bot:</span>
            <span id="sysBot" style="color:var(--green);font-family:var(--pixel);font-size:7px">--</span>
          </div>
          <div style="font-size:10px;display:flex;justify-content:space-between;margin-top:4px">
            <span>Container:</span>
            <span id="sysContainer" style="color:var(--dim);font-family:var(--pixel);font-size:7px">--</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- === TRADES PAGE === -->
  <div class="page" id="page-trades">
    <div class="trade-filters">
      <select id="tfSig"><option value="">All Signals</option><option value="BUY">BUY</option><option value="SELL">SELL</option></select>
      <select id="tfRes"><option value="">All Results</option><option value="TP">TP</option><option value="SL">SL</option><option value="BREAKEVEN">BE</option></select>
      <input type="text" id="tfSearch" placeholder="🔍 Search..." style="flex:1;min-width:100px">
    </div>
    <div class="panel panel-full" style="border-radius:8px">
      <div class="panel-title">📋 Trade History</div>
      <div id="allTradesPanel"><div class="loading">LOADING...</div></div>
    </div>
  </div>

  <!-- === SETTINGS PAGE === -->
  <div class="page" id="page-settings">
    <div class="settings-grid">
      <div class="panel panel-full">
        <div class="panel-title">⚙️ System Status</div>
        <div id="sysSettings"><div class="loading">LOADING...</div></div>
      </div>
      <div class="panel panel-full">
        <div class="panel-title">📊 Confidence Buckets</div>
        <div id="confPanel"><div class="loading">LOADING...</div></div>
      </div>
      <div class="panel panel-full">
        <div class="panel-title">📈 Equity Curve</div>
        <div id="equityPanel"><div class="loading">LOADING...</div></div>
      </div>
    </div>
  </div>

</div>

<script>
// ============================================================
// NAVIGATION
// ============================================================
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('page-' + btn.dataset.page).classList.add('active');
    // If switching to HQ, resize canvas
    if (btn.dataset.page === 'hq' && officeState) { setupCanvas(); }
  });
});

// ============================================================
// FORMAT HELPERS
// ============================================================
function fmt(n) { return n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function fmtPct(n) { return n.toFixed(1) + '%'; }
function ss(n) { return n || 0; }

// ============================================================
// API
// ============================================================
async function api(url) {
  const r = await fetch(url);
  return r.json();
}

// ============================================================
// OFFICE CANVAS — PIXEL AGENTS
// ============================================================
const TILE = 16;
const SCALE = 48; // 3x pixel scale
const COLS = 24;
const ROWS = 16;

const DIRS = {
  DOWN: 0, LEFT: 1, RIGHT: 2, UP: 3
};

let canvas, ctx, animId;
let charSheets = {};  // {sheetIdx: Image}
let furnSheets = {};  // {name: Image}
let floorImg = null;

const agents = [];
const furnItems = [];
const OFFICE_GRID = [];

let selectedAgent = null;
let hoveredAgent = null;

class Agent {
  constructor(idx, name, title, duty, color, status) {
    this.idx = idx;
    this.name = name;
    this.title = title;
    this.duty = duty;
    this.color = color;
    this.status = status;
    this.level = 7;
    this.hp = 85;
    this.sheetIdx = idx % 6;

    // Position (tile coords)
    this.x = 3 + (idx % 6) * 3;
    this.y = 3 + Math.floor(idx / 3) * 3;

    // Movement
    this.targetX = this.x;
    this.targetY = this.y;
    this.px = this.x * TILE;
    this.py = this.y * TILE;
    this.speed = 24; // px/s
    this.walking = false;
    this.path = [];

    // Animation
    this.frame = 0;
    this.frameTimer = 0;
    this.frameSpeed = 0.15;
    this.dir = DIRS.DOWN;

    // Bubble
    this.bubble = '';
    this.bubbleTimer = 0;
    this.bubbleDuration = 0;

    // Status
    this.statusLabel = status || 'idle';
  }

  walkTo(tx, ty) {
    // Simple BFS pathfinding
    const path = findPath(Math.round(this.x), Math.round(this.y), tx, ty);
    if (path && path.length > 1) {
      this.path = path.slice(1); // skip current position
      this.targetX = this.path[this.path.length - 1][0];
      this.targetY = this.path[this.path.length - 1][1];
      this.walking = true;
    }
  }

  update(dt) {
    if (this.walking && this.path.length > 0) {
      const [nx, ny] = this.path[0];
      const targetPx = nx * TILE;
      const targetPy = ny * TILE;

      const dx = targetPx - this.px;
      const dy = targetPy - this.py;
      const dist = Math.sqrt(dx*dx + dy*dy);
      const step = this.speed * dt;

      if (step >= dist) {
        this.px = targetPx;
        this.py = targetPy;
        this.x = nx;
        this.y = ny;
        this.path.shift();

        // Update direction
        if (Math.abs(dx) > Math.abs(dy)) {
          this.dir = dx > 0 ? DIRS.RIGHT : DIRS.LEFT;
        } else {
          this.dir = dy > 0 ? DIRS.DOWN : DIRS.UP;
        }

        if (this.path.length === 0) {
          this.walking = false;
        }
      } else {
        this.px += (dx / dist) * step;
        this.py += (dy / dist) * step;

        // Update direction
        if (Math.abs(dx) > Math.abs(dy)) {
          this.dir = dx > 0 ? DIRS.RIGHT : DIRS.LEFT;
        } else {
          this.dir = dy > 0 ? DIRS.DOWN : DIRS.UP;
        }
      }
    }

    // Animation frame
    if (this.walking) {
      this.frameTimer += dt;
      if (this.frameTimer >= this.frameSpeed) {
        this.frame = (this.frame + 1) % 4;
        this.frameTimer = 0;
      }
    } else {
      this.frame = 0;
      this.frameTimer = 0;
    }

    // Bubble timer
    if (this.bubbleTimer > 0) {
      this.bubbleTimer -= dt;
      if (this.bubbleTimer <= 0) {
        this.bubble = '';
      }
    }
  }

  say(text, duration) {
    this.bubble = text;
    this.bubbleDuration = duration || 3;
    this.bubbleTimer = this.bubbleDuration;
  }

  draw(ctx, offsetX, offsetY) {
    const sx = this.px * SCALE / TILE + offsetX;
    const sy = this.py * SCALE / TILE + offsetY;
    const s = SCALE / TILE;

    // Draw shadow
    ctx.fillStyle = 'rgba(0,0,0,0.2)';
    ctx.fillRect(sx + 2, sy + s*12 - 2, s*12, 4);

    // Draw sprite from spritesheet
    const ss = 16;
    // Each row in spritesheet = 1 character (7 frames per row)
    // Frame layout: walk cycle frames 0-3, idle frames 4-6
    const frameCol = this.walking ? this.frame : 4;
    const frameRow = this.sheetIdx;

    if (charSheets[this.sheetIdx]) {
      ctx.drawImage(
        charSheets[this.sheetIdx],
        frameCol * ss, frameRow * ss, ss, ss,
        sx, sy, s * ss, s * ss
      );
    } else {
      // Fallback: colored square
      ctx.fillStyle = this.color;
      ctx.fillRect(sx, sy, s * ss, s * ss);
      ctx.fillStyle = '#fff';
      ctx.font = Math.floor(s * 8) + 'px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(this.name[0], sx + s * 8, sy + s * 12);
    }

    // HP bar above
    const barW = s * 14;
    const barH = 3;
    const barX = sx + (s * ss - barW) / 2;
    const barY = sy - 6;
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(barX, barY, barW, barH);
    ctx.fillStyle = this.hp > 50 ? this.color : (this.hp > 25 ? '#ffaa00' : '#ff4757');
    ctx.fillRect(barX, barY, barW * (this.hp / 100), barH);

    // Name label
    ctx.fillStyle = '#fff';
    ctx.font = Math.floor(s * 5) + 'px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(this.name, sx + s * 8, barY - 3);

    // Selection highlight
    if (selectedAgent === this) {
      ctx.strokeStyle = 'rgba(255,215,0,0.6)';
      ctx.lineWidth = 2;
      ctx.strokeRect(sx - 2, sy - 2, s * ss + 4, s * ss + 4);
    }

    // Hover highlight
    if (hoveredAgent === this && selectedAgent !== this) {
      ctx.strokeStyle = 'rgba(255,215,0,0.3)';
      ctx.lineWidth = 1;
      ctx.strokeRect(sx - 1, sy - 1, s * ss + 2, s * ss + 2);
    }
  }
}

// Simple BFS pathfinding
function findPath(sx, sy, ex, ey) {
  if (sx === ex && sy === ey) return [sx, sy];
  const queue = [[sx, sy]];
  const visited = {};
  const parent = {};
  const key = (x,y) => x+','+y;
  visited[key(sx,sy)] = true;

  while (queue.length > 0) {
    const [cx, cy] = queue.shift();
    const neighbors = [
      [cx+1, cy], [cx-1, cy], [cx, cy+1], [cx, cy-1]
    ];
    for (const [nx, ny] of neighbors) {
      const k = key(nx, ny);
      if (visited[k]) continue;
      if (nx < 0 || nx >= COLS || ny < 0 || ny >= ROWS) continue;
      // Check if walkable
      if (OFFICE_GRID[ny] && OFFICE_GRID[ny][nx] === '#') continue;

      visited[k] = true;
      parent[k] = [cx, cy];
      if (nx === ex && ny === ey) {
        // Reconstruct path
        const path = [[nx, ny]];
        let cur = k;
        while (parent[cur]) {
          const [px, py] = parent[cur];
          path.unshift([px, py]);
          cur = key(px, py);
        }
        return path;
      }
      queue.push([nx, ny]);
    }
  }
  return null;
}

// Office setup
function buildOffice() {
  furnItems.length = 0;
  for (let y = 0; y < ROWS; y++) {
    OFFICE_GRID[y] = [];
    for (let x = 0; x < COLS; x++) {
      OFFICE_GRID[y][x] = '.';
    }
  }

  // Floor walls
  for (let x = 0; x < COLS; x++) {
    OFFICE_GRID[0][x] = '#';
    OFFICE_GRID[ROWS-1][x] = '#';
  }
  for (let y = 0; y < ROWS; y++) {
    OFFICE_GRID[y][0] = '#';
    OFFICE_GRID[y][COLS-1] = '#';
  }

  // Place desks with PCs
  const desks = [
    // Row 1: desks facing up (agents sit bottom)
    {x: 3, y: 5, dir: 'front'},  // Desk 1
    {x: 7, y: 5, dir: 'front'},  // Desk 2
    {x: 11, y: 5, dir: 'front'}, // Desk 3
    {x: 15, y: 5, dir: 'front'}, // Desk 4
    // Row 2
    {x: 3, y: 10, dir: 'front'},
    {x: 7, y: 10, dir: 'front'},
    {x: 11, y: 10, dir: 'front'},
    {x: 15, y: 10, dir: 'front'},
  ];

  desks.forEach((d, i) => {
    // Desk is 48x32 (3x2 tiles)
    const dx = d.x, dy = d.y;
    // Mark desk tiles as blocked
    for (let ty = 0; ty < 2; ty++) {
      for (let tx = 0; tx < 3; tx++) {
        if (dy+ty < ROWS && dx+tx < COLS) OFFICE_GRID[dy+ty][dx+tx] = '#';
      }
    }
    furnItems.push({type: 'desk', x: dx, y: dy, sprite: 'DESK_FRONT', w: 3, h: 2,
                    offX: 0, offY: 0, sheetW: 48, sheetH: 32});

    // PC (16x32) on top of desk - 1 tile wide, 2 tile tall
    const pcX = dx + 1;
    const pcY = dy - 2;
    if (pcY >= 0) {
      furnItems.push({type: 'pc', x: pcX, y: pcY, sprite: 'PC_FRONT_ON_1', w: 1, h: 2,
                      offX: 0, offY: 0, sheetW: 16, sheetH: 32});
    }

    // Chair (16x32) below desk
    const chairX = dx + 1;
    const chairY = dy + 2;
    if (chairY < ROWS) {
      furnItems.push({type: 'chair', x: chairX, y: chairY, sprite: 'WOODEN_CHAIR', w: 1, h: 2,
                      offX: 0, offY: 0, sheetW: 16, sheetH: 32});
    }
  });

  // Plants
  furnItems.push({type: 'plant', x: 1, y: 2, sprite: 'LARGE_PLANT', w: 2, h: 3,
                  offX: 0, offY: 0, sheetW: 32, sheetH: 48});
  for (let ty = 0; ty < 3; ty++) {
    for (let tx = 0; tx < 2; tx++) {
      if (1+ty < ROWS && 1+tx < COLS) OFFICE_GRID[1+ty][1+tx] = '#';
    }
  }
  furnItems.push({type: 'plant', x: COLS-3, y: 2, sprite: 'LARGE_PLANT', w: 2, h: 3,
                  offX: 0, offY: 0, sheetW: 32, sheetH: 48});
  for (let ty = 0; ty < 3; ty++) {
    for (let tx = 0; tx < 2; tx++) {
      if (1+ty < ROWS && COLS-3+tx < COLS) OFFICE_GRID[1+ty][COLS-3+tx] = '#';
    }
  }
}

function loadSprites(cb) {
  let loaded = 0;
  const total = 7; // 6 characters + 1 floor
  const onload = () => { loaded++; if (loaded >= total) cb(); };

  for (let i = 0; i < 6; i++) {
    const img = new Image();
    img.onload = onload;
    img.onerror = () => { charSheets[i] = null; onload(); };
    img.src = '/assets/characters/char_' + i + '.png';
    charSheets[i] = img;
  }

  // Floor
  floorImg = new Image();
  floorImg.onload = onload;
  floorImg.onerror = () => { floorImg = null; onload(); };
  floorImg.src = '/assets/floors/floor_0.png';

  // Furniture
  const furnImgs = ['DESK_FRONT', 'PC_FRONT_ON_1', 'WOODEN_CHAIR', 'LARGE_PLANT'];
  furnImgs.forEach(name => {
    const img = new Image();
    img.onload = () => { furnSheets[name] = img; };
    img.onerror = () => { furnSheets[name] = null; };
    if (name === 'DESK_FRONT') img.src = '/assets/furniture/DESK/DESK_FRONT.png';
    else if (name.startsWith('PC')) img.src = '/assets/furniture/PC/PC_FRONT_ON_1.png';
    else if (name === 'WOODEN_CHAIR') img.src = '/assets/furniture/WOODEN_CHAIR/WOODEN_CHAIR_FRONT.png';
    else if (name === 'LARGE_PLANT') img.src = '/assets/furniture/LARGE_PLANT/LARGE_PLANT.png';
  });
}

function setupCanvas() {
  const wrap = document.getElementById('canvasWrap');
  canvas = document.getElementById('officeCanvas');
  const rect = wrap.getBoundingClientRect();
  canvas.width = rect.width;
  canvas.height = rect.height;
  ctx = canvas.getContext('2d');
}

function getCanvasOffset() {
  const cw = canvas.width;
  const ch = canvas.height;
  const mapW = COLS * SCALE;
  const mapH = ROWS * SCALE;
  return {
    x: Math.max(0, (cw - mapW) / 2),
    y: Math.max(0, (ch - mapH) / 2)
  };
}

function drawOffice() {
  const offset = getCanvasOffset();
  const s = SCALE;

  // Background
  ctx.fillStyle = '#0a0a1a';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Floor tiles
  for (let y = 0; y < ROWS; y++) {
    for (let x = 0; x < COLS; x++) {
      const px = x * s + offset.x;
      const py = y * s + offset.y;

      if (OFFICE_GRID[y][x] === '#') {
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(px, py, s, s);
        ctx.strokeStyle = 'rgba(42,42,90,0.3)';
        ctx.lineWidth = 1;
        ctx.strokeRect(px, py, s, s);
      } else if (floorImg && floorImg.complete && floorImg.naturalWidth > 0) {
        ctx.drawImage(floorImg, px, py, s, s);
      } else {
        const light = (x + y) % 2 === 0 ? '#1a1a2e' : '#1f1f35';
        ctx.fillStyle = light;
        ctx.fillRect(px, py, s, s);
      }
    }
  }

  // Furniture (behind characters)
  furnItems.forEach(f => {
    const px = f.x * s + offset.x;
    const py = f.y * s + offset.y;
    const img = furnSheets[f.sprite];
    if (img && img.complete && img.naturalWidth > 0) {
      ctx.drawImage(img, px, py, f.w * s, f.h * s);
    } else {
      // Fallback
      ctx.fillStyle = '#2a2a4a';
      ctx.fillRect(px, py, f.w * s, f.h * s);
      ctx.strokeStyle = '#3a3a5a';
      ctx.lineWidth = 1;
      ctx.strokeRect(px, py, f.w * s, f.h * s);
    }
  });

  // Agents
  agents.forEach(a => {
    if (a) a.draw(ctx, offset.x, offset.y);
  });
}

function renderOffice() {
  if (!canvas) return;
  ctx = canvas.getContext('2d');
  drawOffice();
}

let lastTime = 0;
function gameLoop(time) {
  if (!document.getElementById('page-hq').classList.contains('active')) {
    animId = requestAnimationFrame(gameLoop);
    return;
  }

  if (!canvas) { setupCanvas(); }

  const dt = lastTime ? Math.min((time - lastTime) / 1000, 0.1) : 0.016;
  lastTime = time;

  // Update agents
  agents.forEach(a => {
    if (a) a.update(dt);
  });

  renderOffice();

  // Update hover
  if (canvas) {
    const rect = canvas.getBoundingClientRect();
    // Handle mouse position for hover
  }

  animId = requestAnimationFrame(gameLoop);
}

function addAgentsFromAPI(data) {
  const agentData = data.agents || [];
  agentData.forEach((ad, i) => {
    if (!agents[i]) {
      const a = new Agent(i, ad.name, ad.title, ad.duty, ad.color, ad.status);
      a.level = ad.level || 7;
      a.hp = ad.hp || 85;
      agents[i] = a;
    } else {
      agents[i].status = ad.status;
      agents[i].hp = ad.hp || agents[i].hp;
      agents[i].level = ad.level || agents[i].level;
      agents[i].duty = ad.duty;
    }
  });
  updateSidePanel(agentData);
}

function updateSidePanel(agentData) {
  const list = document.getElementById('agentList');
  list.innerHTML = agentData.map((ad, i) => {
    const a = agents[i];
    const isSel = selectedAgent === a;
    return `<div class="sp-agent ${isSel ? 'selected' : ''}" data-idx="${i}">
      <div class="sp-agent-top">
        <canvas class="sp-agent-preview" id="preview${i}"></canvas>
        <div class="sp-agent-info">
          <div class="sp-agent-name">${ad.name}</div>
          <div class="sp-agent-title">${ad.title || ''}</div>
          <span class="sp-agent-status ${ad.status}">${ad.status === 'active' ? '🟢 WORKING' : '⚪ IDLE'}</span>
        </div>
      </div>
      <div class="sp-hp"><div class="sp-hp-fill" style="width:${a?.hp||85}%;background:${ad.color}"></div></div>
      <div class="sp-agent-duty">${ad.duty}</div>
    </div>`;
  }).join('');

  // Draw preview sprites
  agentData.forEach((ad, i) => {
    const pCanvas = document.getElementById('preview' + i);
    if (!pCanvas) return;
    const pc = pCanvas.getContext('2d');
    pc.clearRect(0, 0, 32, 32);
    const img = charSheets[agents[i]?.sheetIdx || i % 6];
    if (img && img.complete && img.naturalWidth > 0) {
      pc.drawImage(img, 4*16, (i%6)*16, 16, 16, 0, 0, 32, 32);
    } else {
      pc.fillStyle = ad.color || '#fff';
      pc.fillRect(4, 4, 24, 24);
      pc.fillStyle = '#fff';
      pc.font = '14px monospace';
      pc.textAlign = 'center';
      pc.fillText(ad.name[0], 16, 22);
    }
  });

  // Click handlers
  document.querySelectorAll('.sp-agent').forEach(el => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.idx);
      const a = agents[idx];
      if (a) {
        selectedAgent = a;
        // Walk to random tile near desk
        const deskX = 3 + (idx % 4) * 4;
        const deskY = idx < 4 ? 8 : 13;
        a.walkTo(deskX, deskY);
        a.say('📍 ' + a.name, 3);
        updateSidePanel(agentData);
      }
    });
  });
}

// Start game loop
loadSprites(() => {
  buildOffice();
  setupCanvas();

  // Initial agent positions
  const defaultAgents = [
    {name:'Quant Analyst', title:'', duty:'RSI, MACD, EMA', color:'#00ff88', status:'idle'},
    {name:'News Analyst', title:'', duty:'News & Sentiment', color:'#ffaa00', status:'idle'},
    {name:'Bull Agent', title:'', duty:'Long Signals', color:'#ff4444', status:'idle'},
    {name:'Bear Agent', title:'', duty:'Short Signals', color:'#4488ff', status:'idle'},
    {name:'CEO Agent', title:'', duty:'Final Decision', color:'#ffdd00', status:'idle'},
    {name:'Learning Engine', title:'', duty:'Optimizer', color:'#ff66ff', status:'idle'},
  ];

  defaultAgents.forEach((ad, i) => {
    const a = new Agent(i, ad.name, ad.title, ad.duty, ad.color, ad.status);
    a.level = 7;
    a.hp = 85;
    agents[i] = a;
  });

  // Start game loop
  if (animId) cancelAnimationFrame(animId);
  lastTime = 0;
  animId = requestAnimationFrame(gameLoop);
});

// Canvas mouse interactions
document.addEventListener('DOMContentLoaded', () => {
  const wrap = document.getElementById('canvasWrap');
  if (!wrap) return;

  wrap.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const offset = getCanvasOffset();
    const tileX = (mx - offset.x) / SCALE;
    const tileY = (my - offset.y) / SCALE;

    // Find agent under cursor
    let found = null;
    for (let i = agents.length - 1; i >= 0; i--) {
      const a = agents[i];
      if (!a) continue;
      const dx = tileX - a.px / TILE;
      const dy = tileY - a.py / TILE;
      if (dx > -0.5 && dx < 1.5 && dy > -0.5 && dy < 1.5) {
        found = a;
        break;
      }
    }
    hoveredAgent = found;
    canvas.style.cursor = found ? 'pointer' : 'default';
  });

  wrap.addEventListener('click', (e) => {
    if (e.target !== canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const offset = getCanvasOffset();
    const tileX = (mx - offset.x) / SCALE;
    const tileY = (my - offset.y) / SCALE;

    let clicked = null;
    for (let i = agents.length - 1; i >= 0; i--) {
      const a = agents[i];
      if (!a) continue;
      const dx = tileX - a.px / TILE;
      const dy = tileY - a.py / TILE;
      if (dx > -0.5 && dx < 1.5 && dy > -0.5 && dy < 1.5) {
        clicked = a;
        break;
      }
    }

    if (clicked) {
      selectedAgent = clicked;
      clicked.say('✅ Report ready!', 3);

      // Walk to random desk
      const di = clicked.idx % 4;
      const deskX = 3 + di * 4;
      const deskY = clicked.idx < 4 ? 7 : 12;
      clicked.walkTo(deskX, deskY);
    } else if (selectedAgent && tileX > 0 && tileX < COLS-1 && tileY > 0 && tileY < ROWS-1) {
      selectedAgent.walkTo(Math.floor(tileX), Math.floor(tileY));
    }

    // Update side panel
    const agentData = defaultAgents;
    updateSidePanel(agentData);
  });
});

// Canvas resize on window change
window.addEventListener('resize', () => {
  if (document.getElementById('page-hq').classList.contains('active')) {
    setupCanvas();
  }
});

// ============================================================
// DASHBOARD RENDER
// ============================================================
function renderStats(data) {
  const pnl = data.total_pnl;
  document.getElementById('statsGrid').innerHTML = `
    <div class="dash-card"><div class="num gold">${data.total_trades}</div><div class="lbl">Total Trades</div></div>
    <div class="dash-card"><div class="num green">${data.wins} (${fmtPct(data.winrate)})</div><div class="lbl">Win Rate</div></div>
    <div class="dash-card"><div class="num red">${data.losses}</div><div class="lbl">Losses</div></div>
    <div class="dash-card"><div class="num ${pnl>=0?'green':'red'}">${pnl>=0?'+':''}$${fmt(pnl)}</div><div class="lbl">Total P&L</div></div>
  `;
  if (data.consecutive_losses >= 2) {
    document.getElementById('lossAlert').innerHTML = `<div class="loss-alert">⚠️ ${data.consecutive_losses} consecutive losses! Risk reduced.</div>`;
  } else {
    document.getElementById('lossAlert').innerHTML = '';
  }
}

function renderPerf(data) {
  const wr = data.winrate;
  document.getElementById('perfPanel').innerHTML = `
    <div style="display:flex;gap:16px;align-items:center;justify-content:center;flex-wrap:wrap">
      <div style="text-align:center">
        <div class="wr-circle"><div class="pct ${wr>=50?'green':'red'}">${fmtPct(wr)}</div><div class="pct-lbl">WINRATE</div></div>
      </div>
      <div style="text-align:center">
        <div style="font-family:var(--pixel);font-size:20px;color:var(--blue)">${data.avg_r.toFixed(2)}</div>
        <div style="font-size:9px;color:var(--dim)">Avg R:R</div>
      </div>
      <div style="text-align:center">
        <div style="font-family:var(--pixel);font-size:16px;color:var(--gold)">${data.total_trades}</div>
        <div style="font-size:9px;color:var(--dim)">Total</div>
      </div>
    </div>`;
}

function renderMonthly(monthly) {
  if (!monthly || monthly.length === 0) {
    document.getElementById('monthlyChart').innerHTML = '<div style="text-align:center;padding:20px;color:var(--dim);font-size:10px">No data</div>';
    return;
  }
  const data = [...monthly].reverse();
  const maxPnl = Math.max(...data.map(d => Math.abs(d.pnl)), 1);
  let bars = data.map(d => {
    const pos = d.pnl >= 0;
    const h = Math.max(Math.abs(d.pnl)/maxPnl*100, 3);
    return `<div class="bar-wrap"><div class="bar-val">${pos?'+':''}$${Math.abs(d.pnl).toFixed(0)}</div><div class="bar ${pos?'green':'red'}" style="height:${h}%"></div><div class="bar-lbl">${d.month.slice(5)}</div></div>`;
  }).join('');
  document.getElementById('monthlyChart').innerHTML = `<div class="bar-chart">${bars}</div>`;
}

function renderRegime(rdata) {
  if (!rdata || rdata.length === 0) {
    document.getElementById('regimePanel').innerHTML = '<div style="padding:8px;color:var(--dim);font-size:10px">No data</div>';
    return;
  }
  document.getElementById('regimePanel').innerHTML = rdata.map(r => `
    <div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(42,42,90,0.2)">
      <span style="font-size:10px;color:var(--gold)">${r.regime||'?'}</span>
      <span style="font-size:10px"><span style="color:var(--green)">${r.wins}W</span><span style="color:var(--dim)">/${r.total}T </span>
      <span style="color:${r.pnl>=0?'var(--green)':'var(--red)'}">$${r.pnl.toFixed(0)}</span>
      <span style="font-family:var(--pixel);font-size:7px;color:var(--dim);margin-left:4px">${r.winrate}%</span></span>
    </div>
  `).join('');
}

function renderTrades(trades) {
  if (!trades || trades.length === 0) {
    document.getElementById('tradesPanel').innerHTML = '<div style="padding:10px;color:var(--dim);text-align:center;font-size:11px">No trades yet</div>';
    return;
  }
  let html = `<table class="trade-table"><thead><tr>
    <th>Signal</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Result</th><th>R:R</th><th>Conf</th>
  </tr></thead><tbody>`;
  html += trades.map(t => {
    const sc = (t.signal||'').toLowerCase() === 'buy' ? 'buy' : 'sell';
    const rc = (t.result||'').toLowerCase();
    const isWin = t.pnl >= 0;
    return `<tr>
      <td><span class="sig ${sc}">${t.signal||'?'}</span></td>
      <td>$${fmt(t.entry||0)}</td>
      <td>$${fmt(t.exit||0)}</td>
      <td style="color:${isWin?'var(--green)':'var(--red)'}">${isWin?'+':''}$${fmt(t.pnl)}</td>
      <td><span class="res ${rc}">${t.result||'?'}</span></td>
      <td style="font-family:var(--pixel);font-size:7px">${t.r.toFixed(1)}</td>
      <td style="font-size:9px">${t.confidence||0}%</td>
    </tr>`;
  }).join('');
  html += '</tbody></table>';
  document.getElementById('tradesPanel').innerHTML = html;
}

function renderAllTrades(trades) {
  if (!trades || trades.length === 0) {
    document.getElementById('allTradesPanel').innerHTML = '<div style="padding:10px;color:var(--dim);text-align:center;font-size:11px">No trades yet</div>';
    return;
  }
  let html = `<table class="trade-table"><thead><tr>
    <th>Time</th><th>Signal</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Result</th><th>R:R</th><th>Conf</th><th>Regime</th>
  </tr></thead><tbody>`;
  html += trades.map(t => {
    const sc = (t.signal||'').toLowerCase() === 'buy' ? 'buy' : 'sell';
    const rc = (t.result||'').toLowerCase();
    const isWin = t.pnl >= 0;
    return `<tr>
      <td style="font-size:9px;color:var(--dim)">${t.time?.slice(5,16)||'?'}</td>
      <td><span class="sig ${sc}">${t.signal||'?'}</span></td>
      <td>$${fmt(t.entry||0)}</td>
      <td>$${fmt(t.exit||0)}</td>
      <td style="color:${isWin?'var(--green)':'var(--red)'}">${isWin?'+':''}$${fmt(t.pnl)}</td>
      <td><span class="res ${rc}">${t.result||'?'}</span></td>
      <td style="font-family:var(--pixel);font-size:7px">${t.r.toFixed(1)}</td>
      <td style="font-size:9px">${t.confidence||0}%</td>
      <td style="font-size:9px;color:var(--dim)">${t.regime||'?'}</td>
    </tr>`;
  }).join('');
  html += '</tbody></table>';
  document.getElementById('allTradesPanel').innerHTML = html;
}

function renderSettings(data, agentsData, chartData) {
  // System status
  document.getElementById('sysSettings').innerHTML = `
    <div class="setting-item"><span class="lbl">Bot Status</span><span class="val" style="color:${agentsData.bot_running?'var(--green)':'var(--red)'}">${agentsData.bot_running?'RUNNING':'STOPPED'}</span></div>
    <div class="setting-item"><span class="lbl">MT5 Container</span><span class="val" style="color:var(--dim)">${agentsData.container_status||'unknown'}</span></div>
    <div class="setting-item"><span class="lbl">Current Balance</span><span class="val" style="color:var(--gold)">$${fmt(chartData.current_balance||0)}</span></div>
    <div class="setting-item"><span class="lbl">Total Growth</span><span class="val" style="color:${(chartData.total_growth||0)>=0?'var(--green)':'var(--red)'}">${(chartData.total_growth||0).toFixed(2)}%</span></div>
    <div class="setting-item"><span class="lbl">Total Trades</span><span class="val" style="color:var(--blue)">${data.total_trades}</span></div>
    <div class="setting-item"><span class="lbl">Win Rate</span><span class="val" style="color:${(data.winrate||0)>=50?'var(--green)':'var(--red)'}">${fmtPct(data.winrate||0)}</span></div>
    <div class="setting-item"><span class="lbl">Consecutive Losses</span><span class="val" style="color:${(data.consecutive_losses||0)>=2?'var(--red)':'var(--green)'}">${data.consecutive_losses||0}</span></div>
  `;

  // Confidence buckets
  if (data.by_confidence && data.by_confidence.length > 0) {
    document.getElementById('confPanel').innerHTML = data.by_confidence.map(c => `
      <div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(42,42,90,0.2)">
        <span style="font-family:var(--pixel);font-size:7px;color:var(--gold)">${c.bucket}</span>
        <span style="font-size:10px"><span style="color:var(--green)">${c.wins}W</span><span style="color:var(--dim)">/${c.total}T </span>
        <span style="font-family:var(--pixel);font-size:7px;color:${c.winrate>=50?'var(--green)':'var(--red)'}">${c.winrate}%</span></span>
      </div>
    `).join('');
  } else {
    document.getElementById('confPanel').innerHTML = '<div style="padding:8px;color:var(--dim);font-size:10px">No data</div>';
  }

  // Equity curve (mini bar chart)
  if (chartData.equity_curve && chartData.equity_curve.length > 0) {
    const eq = chartData.equity_curve;
    const maxBal = Math.max(...eq.map(e => e.balance));
    const minBal = Math.min(...eq.map(e => e.balance));
    const range = Math.max(maxBal - minBal, 1);
    // Show last 30 points
    const pts = eq.slice(-30);
    document.getElementById('equityPanel').innerHTML = `
      <div style="display:flex;align-items:flex-end;gap:2px;height:80px;padding:4px">
        ${pts.map(e => {
          const h = Math.max((e.balance - minBal) / range * 100, 2);
          const c = e.result === 'TP' ? 'var(--green)' : (e.result === 'SL' ? 'var(--red)' : 'var(--gold)');
          return `<div style="flex:1;background:${c};height:${h}%;border-radius:1px 1px 0 0;min-height:1px" title="$${e.balance}"></div>`;
        }).join('')}
      </div>
      <div style="display:flex;justify-content:space-between;font-size:7px;color:var(--dim);font-family:var(--pixel);margin-top:4px">
        <span>$${fmt(minBal)}</span>
        <span>$${fmt(maxBal)}</span>
      </div>
    `;
  } else {
    document.getElementById('equityPanel').innerHTML = '<div style="padding:8px;color:var(--dim);font-size:10px">No equity data</div>';
  }
}

// ============================================================
// MAIN LOAD
// ============================================================
async function loadAll() {
  try {
    const [overview, agentsData, chartData] = await Promise.all([
      api('/api/overview'), api('/api/agents'), api('/api/chart')
    ]);

    // Header
    if (chartData.current_balance) {
      document.getElementById('hdrBal').textContent = '$' + fmt(chartData.current_balance);
    }
    if (chartData.total_growth !== undefined) {
      const g = chartData.total_growth;
      document.getElementById('hdrGrowth').textContent = (g >= 0 ? '+' : '') + g.toFixed(1) + '%';
    }
    document.getElementById('botDot').className = 'live-dot ' + (agentsData.bot_running ? 'on' : 'off');
    document.getElementById('botLabel').textContent = agentsData.bot_running ? 'RUNNING' : 'IDLE';
    document.getElementById('botLabel').style.color = agentsData.bot_running ? 'var(--green)' : 'var(--red)';

    // Dashboard
    renderStats(overview);
    renderPerf(overview);
    renderMonthly(overview.monthly);
    renderRegime(overview.by_regime);
    renderTrades(overview.recent_trades);
    renderAllTrades(overview.recent_trades);

    // Agent HQ - update agents
    addAgentsFromAPI(agentsData);

    // System status
    document.getElementById('sysBot').textContent = agentsData.bot_running ? 'RUNNING' : 'STOPPED';
    document.getElementById('sysBot').style.color = agentsData.bot_running ? 'var(--green)' : 'var(--red)';
    document.getElementById('sysContainer').textContent = agentsData.container_status || 'unknown';

    // Settings
    renderSettings(overview, agentsData, chartData);

  } catch (err) {
    console.error('Load error:', err);
  }
}

// Initial load + auto-refresh
loadAll();
setInterval(loadAll, 15000); // every 15s

// Window resize
window.addEventListener('resize', () => {
  if (document.getElementById('page-hq').classList.contains('active')) {
    setupCanvas();
  }
});
</script>
</body>
</html>"""


def run_server():
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"🎮 Pixel Dashboard running at http://0.0.0.0:{PORT}")
    print(f"📊 API: http://0.0.0.0:{PORT}/api/overview")
    print(f"🏢 Agent HQ: http://0.0.0.0:{PORT}/")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    run_server()