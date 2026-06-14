# 🐧 Running Claw_Trade (MT5 Trading Bot) on Linux

> **Complete guide:** How to run this MetaTrader 5 trading bot on Linux — no Windows VPS required.

---

## 🧠 The Problem

Claw_Trade uses the official `MetaTrader5` Python package to connect to MT5 for live/paper trading. **But** — the `MetaTrader5` pip package is **Windows-only**:

```
pip install MetaTrader5   # ❌ ERROR: only works on Windows
```

If you try `pip install MetaTrader5` on Linux, you get:

```
ERROR: Could not find a version that satisfies the requirement MetaTrader5
ERROR: No matching distribution found for MetaTrader5
```

This means the entire 5-agent AI trading system — `MT5Connector`, `MasterOrchestrator`, order execution, position monitoring — cannot run on Linux out of the box.

---

## 🎯 The Solution: Docker + mt5linux

We solve this with two key pieces:

| Component | Role | Where it runs |
|-----------|------|---------------|
| **MT5 Terminal** | The actual MetaTrader 5 trading platform | Inside Docker (Wine) |
| **mt5linux** | RPyC server that exposes MT5 API over TCP | Inside Docker (Wine Python) |
| **Your Bot** | Claw_Trade orchestration + AI agents | **Host Linux** |

### Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                      LINUX HOST (AWS EC2)                      │
│                                                                 │
│   ┌─────────────────────────────────────────┐                   │
│   │            Docker Container              │                   │
│   │  (gmag11/metatrader5_vnc)               │                   │
│   │                                         │                   │
│   │  ┌─────────────┐   ┌─────────────────┐  │  TCP :8001        │
│   │  │ MT5 Terminal │◄─►│ mt5linux RPyC   │◄─┼──────────────────┤
│   │  │ (Wine)       │   │ Server (Wine)   │  │                  │
│   │  └─────────────┘   └─────────────────┘  │                  │
│   │                                         │                  │
│   │  KasmVNC WebUI (:3000) ◄── Browser      │                  │
│   └─────────────────────────────────────────┘                  │
│                                                                 │
│   ┌─────────────────────────────────────────┐                   │
│   │  Claw_Trade Bot (Python)                │                   │
│   │  main.py live --confirm --interval 60   │                   │
│   │  from mt5linux import MetaTrader5       │                   │
│   └─────────────────────────────────────────┘                   │
└───────────────────────────────────────────────────────────────┘
```

### Why this approach?

| Approach | Cost | Complexity | Reliability |
|----------|------|------------|-------------|
| ❌ Windows VPS | ~$15-40/mo | Medium | ✅ Stable |
| ❌ MetaAPI.cloud API | **$30/mo** | Low | ✅ Stable |
| ❌ Wine directly on host | Free | High (crash-prone) | ❌ Unstable |
| ✅ **Docker + mt5linux** | **Free** | Medium | ✅ **Stable** |

---

## 🛠️ Step-by-Step Setup

### Step 1: Install Docker

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install docker.io docker-compose-v2 -y
sudo systemctl enable --now docker
```

### Step 2: Create Docker Compose File

Create `docker-compose.yml` in your project root:

```yaml
version: '3'
services:
  mt5:
    image: gmag11/metatrader5_vnc
    container_name: claw-trade-mt5
    restart: unless-stopped
    ports:
      - "3000:3000"   # KasmVNC Web UI (browser-based remote desktop)
      - "8001:8001"   # RPyC API (mt5linux connects here)
    volumes:
      - mt5_config:/config
    environment:
      - CUSTOM_USER=trader
      - PASSWORD=clawtrade2026   # Change this!
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s

volumes:
  mt5_config:
```

> **⚠️ Note:** This image is ~4-6GB and takes a while to download.

### Step 3: Start & Login to MT5

```bash
# Start container
docker compose up -d

# Open VNC in browser
# Go to: http://YOUR_SERVER_IP:3000
# Login: trader / clawtrade2026
```

Once inside the remote desktop:
1. Open **MetaTrader 5** (desktop shortcut)
2. Go to **File → Login to Trade Account**
3. Enter your broker credentials (login, password, server)
4. Make sure XAUUSD (or your symbol) is visible in **Market Watch** (Ctrl+M)
5. Go to **Tools → Options → Expert Advisors** → check **"Allow Algo Trading"**

### Step 4: Install mt5linux on Host

```bash
# Using pip (on the Linux host, NOT inside container)
pip install mt5linux rpyc
```

The `mt5linux` package is a drop-in replacement for `MetaTrader5` that communicates through RPyC instead of directly calling the Windows DLL.

### Step 5: Start the mt5linux RPyC Server

```bash
docker exec --user abc claw-trade-mt5 bash -c '
  export WINEPREFIX=/config/.wine
  wine "C:\\Program Files (x86)\\Python39-32\\python.exe" -m mt5linux --host 0.0.0.0 --port 8001
'
```

**Test that it works:**
```bash
python3 -c "
from mt5linux import MetaTrader5
mt5 = MetaTrader5(host='127.0.0.1', port=8001)
mt5.initialize()
info = mt5.account_info()
print(f'Balance: {info[8]}, Server: {info[16]}')
"
```

### Step 6: Auto-start mt5linux (s6 service)

The container uses `s6-overlay` as its init system. Create a service to auto-start mt5linux:

```bash
docker exec --user root claw-trade-mt5 bash -c '
  mkdir -p /etc/services.d/mt5linux
  cat > /etc/services.d/mt5linux/run << '\''SCRIPT'\''
#!/usr/bin/with-contenv bash
export WINEPREFIX=/config/.wine
exec wine "C:\\Program Files (x86)\\Python39-32\\python.exe" -m mt5linux --host 0.0.0.0 --port 8001
SCRIPT
  chmod +x /etc/services.d/mt5linux/run
'
```

After this, any container restart will auto-start the mt5linux server.

---

## 📝 Code Changes Required

Now that Docker + mt5linux is running, you need these code changes:

### Change 1: `src/mt5_connector.py` — Dual-mode import

Replace the top-level import with a **try/except** that prefers mt5linux (Linux) and falls back to native MetaTrader5 (Windows):

```python
# At the top of mt5_connector.py, REPLACE:
# import MetaTrader5 as mt5

# WITH:
try:
    from mt5linux import MetaTrader5 as _MT5Client
    _MT5_HOST = os.getenv("MT5_HOST", "127.0.0.1")
    _MT5_PORT = int(os.getenv("MT5_PORT", "8001"))
    mt5 = _MT5Client(host=_MT5_HOST, port=_MT5_PORT)
    _USING_MT5LINUX = True
    logger.info("🐳 Using mt5linux (Linux Docker mode)")
except ImportError:
    try:
        import MetaTrader5 as mt5
        _USING_MT5LINUX = False
        logger.info("🪟 Using native MetaTrader5 (Windows mode)")
    except ImportError:
        mt5 = None
        _USING_MT5LINUX = False
```

> **Why?** This makes the same code work on both Windows and Linux. Windows users see no change. Linux users automatically get the Docker bridge.

### Change 2: `src/mt5_connector.py` — `get_account_info()` tuple handling

mt5linux returns `account_info()` as a **tuple**, not a named tuple like native MT5. Add handling:

```python
def get_account_info(self):
    ...
    info = mt5.account_info()
    if info is None:
        return None
    
    # mt5linux returns tuple, native MT5 returns named tuple
    if isinstance(info, (tuple, list)):
        return {
            'login': info[0],
            'balance': info[8],       # tuple index for balance
            'equity': info[11],
            'margin': info[12],
            'margin_free': info[13],
            'server': info[16],
            'currency': info[17],
            'name': info[18],
            'leverage': info[2],
            'trade_allowed': info[6],
        }
    else:
        # Native MT5 named tuple
        return {
            'login': info.login,
            'balance': info.balance,
            ...
        }
```

**Tuple index mapping for mt5linux `account_info()`:**
| Index | Field     |
|-------|-----------|
| 0     | login     |
| 1     | trade_mode |
| 2     | leverage  |
| 3-5   | (other)   |
| 6     | trade_allowed |
| 7     | (other)   |
| 8     | balance   |
| 9-10  | (other)   |
| 11    | equity    |
| 12    | margin    |
| 13    | margin_free |
| 14-15 | (other)   |
| 16    | server    |
| 17    | currency  |
| 18    | name      |

### Change 3: `src/orchestrator.py` — Fix `import MetaTrader5 as mt5`

The `_monitor_live_positions()` method does `import MetaTrader5 as mt5` locally (line ~1006). This import will fail on Linux. Change it to use the existing mt5 module from `mt5_connector`:

```python
# In _monitor_live_positions(), REPLACE:
# import MetaTrader5 as mt5

# WITH:
from mt5_connector import mt5 as _mt5
```

Then update the two places that reference `mt5`:

```python
# Line ~1147: Change
if mt5.initialize():
    deals = mt5.history_deals_get(position=ticket)

# To:
if True:  # Already connected via mt5_connector
    deals = _mt5.history_deals_get(position=ticket)
```

```python
# Line ~1161: Change
if deal.entry == mt5.DEAL_ENTRY_OUT or deal.entry == 1:

# To:
if deal.entry == _mt5.DEAL_ENTRY_OUT or deal.entry == 1:
```

### Change 4: `.env` — Add mt5linux connection settings

Add these to your `.env`:

```bash
# MT5 Linux Bridge (Docker + mt5linux)
MT5_HOST=127.0.0.1
MT5_PORT=8001
MT5_SYMBOL=XAUUSDc   # FBS broker uses "XAUUSDc", not "XAUUSD"
```

> **Note:** Different brokers use different symbol names for Gold. Common ones: `XAUUSD`, `XAUUSDc`, `GOLD`, `XAUUSD.m`, `XAUUSD_i`. Check your broker's Market Watch in MT5.

---

## 🧪 Testing Your Setup

After all changes, verify end-to-end connectivity:

```bash
# 1. Check container is running
docker ps --filter name=claw-trade-mt5

# 2. Check mt5linux port is listening
docker exec claw-trade-mt5 bash -c 'ss -tlnp | grep 8001'
# Should show: LISTEN 0 4096 0.0.0.0:8001

# 3. Test Python connection
cd /root/Claw_Trade
source .venv/bin/activate
python3 -c "
from src.mt5_connector import MT5Connector
conn = MT5Connector()
if conn.connect():
    info = conn.get_account_info()
    price = conn.get_price()
    print(f'✅ Connected!')
    print(f'   Balance: \${info[\"balance\"]:,.2f}')
    print(f'   Server: {info[\"server\"]}')
    print(f'   Name: {info[\"name\"]}')
    print(f'   {conn.symbol}: Ask={price[\"ask\"]} Bid={price[\"bid\"]}')
else:
    print('❌ Connection failed')
"
```

Expected output:
```
🐳 Using mt5linux (Linux Docker mode)
Initializing MetaTrader 5...
✅ Successfully logged in to MT5 Demo Account!
✅ Connected!
   Balance: $10,450.96
   Server: FBSTradestone-Demo
   Name: Thanyathep Wattanasataporn
   XAUUSDc: Ask=4217.30 Bid=4217.02
```

---

## 🔄 Auto-Recovery Setup

Since this runs on a remote Linux server, you need uptime guarantees:

### Watchdog Script

Save as `watchdog.py` (in project root):

```python
#!/usr/bin/env python3
"""
Claw_Trade Watchdog — ensures live trading keeps running
"""
import os, time, subprocess, logging
from pathlib import Path

PROJECT_DIR = Path("/root/Claw_Trade")
LOG_FILE = PROJECT_DIR / "live_trading_watchdog.log"
PID_FILE = PROJECT_DIR / "live_trading.pid"

def is_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except:
        return False

def mt5linux_alive():
    result = subprocess.run(
        ["docker", "exec", "claw-trade-mt5", "bash", "-c",
         "ss -tlnp | grep -q 8001 && echo alive || echo dead"],
        capture_output=True, text=True, timeout=10
    )
    return "alive" in result.stdout

def start_live_trading():
    cmd = [str(PROJECT_DIR / ".venv/bin/python3"), "-u",
           str(PROJECT_DIR / "main.py"), "live", "--confirm", "--interval", "60"]
    log_fd = open(PROJECT_DIR / "live_trading_output.log", "a")
    proc = subprocess.Popen(cmd, cwd=str(PROJECT_DIR),
                            env={**os.environ, "PYTHONUNBUFFERED": "1"},
                            stdout=log_fd, stderr=subprocess.STDOUT,
                            start_new_session=True)
    PID_FILE.write_text(str(proc.pid))
    return proc

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(message)s',
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
    
    # Check container
    result = subprocess.run(["docker", "inspect", "claw-trade-mt5",
                            "--format", "{{.State.Status}}"],
                            capture_output=True, text=True, timeout=10)
    if result.stdout.strip() != "running":
        subprocess.run(["docker", "compose", "-f", str(PROJECT_DIR/"docker-compose.yml"), "up", "-d"])
        time.sleep(20)
    
    # Check mt5linux
    if not mt5linux_alive():
        subprocess.run(["docker", "compose", "restart", "-t", "30"])
        time.sleep(15)
    
    # Check/start live trading
    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        if is_running(pid):
            print(f"✅ Live trading already running (PID: {pid})")
            exit(0)
    
    start_live_trading()
```

### Cron Job (every 5 hours)

```bash
# Run watchdog every 5 hours
0 */5 * * * cd /root/Claw_Trade && python3 watchdog.py 2>&1
```

Or use the built-in cron system:
```bash
# Check every 5h, only report on failure
hermes cron create \
  --name "Claw_Trade Watchdog" \
  --schedule "every 5h" \
  --prompt "Check container, mt5linux, and live trading process. Only report if something is wrong." \
  --deliver "origin"
```

---

## 🐛 Common Issues & Fixes

### Issue: `pip install MetaTrader5` fails on Linux
**This is expected.** Don't install it. Use `mt5linux` instead.

### Issue: `import MetaTrader5` fails inside orchestrator.py
The `_monitor_live_positions()` method has a direct `import MetaTrader5 as mt5`. Change it to `from mt5_connector import mt5 as _mt5` (see Change 3 above).

### Issue: `mt5.initialize()` returns False
MT5 must be **logged into an account** inside the VNC desktop. Open the MT5 app via VNC and log in manually. The `gmag11/metatrader5_vnc` image does NOT auto-login.

### Issue: Container uses 2-4GB RAM
This is normal. MT5 running under Wine + KasmVNC desktop + mt5linux uses significant memory. Consider a server with at least **4GB RAM**.

### Issue: Symbol "XAUUSD" not found on FBS
FBS uses `XAUUSDc` (with suffix "c"). Check your broker's Market Watch for the exact symbol name. Set `MT5_SYMBOL=XAUUSDc` in `.env`.

### Issue: `tz_convert()` error when fetching MT5 history
This is an mt5linux compatibility issue with `copy_rates_range`. The code falls back to Yahoo Finance automatically, so this is **non-critical**. The bot works fine.

### Issue: Container gets restarted — mt5linux not responding
The s6 service auto-starts mt5linux, but MT5 terminal itself needs MT5 to be logged in. If you set up the FBS credentials in the VNC session, the terminal will stay logged in across restarts (the Wine prefix persists via the Docker volume).

However, if the container is fully rebuilt (e.g., `docker compose down && docker compose up`), you'll need to **re-login via VNC**.

---

## 🚀 Quick Summary: What You Gotta Do

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Install Docker                                              │
│ 2. docker compose up -d                                        │
│ 3. Open VNC :3000 → Login MT5 into your broker                 │
│ 4. pip install mt5linux rpyc                                   │
│ 5. Start mt5linux inside container                             │
│ 6. Create s6 service for auto-start                            │
│ 7. Patch mt5_connector.py (try/except import)                  │
│ 8. Patch orchestrator.py (import fix)                          │
│ 9. Set USE_MOCK_AI=false in .env                               │
│ 10. python main.py live --confirm --interval 60                │
└─────────────────────────────────────────────────────────────────┘
```
---
## 📁 Files Modified from Original

| File | Change | Why |
|------|--------|-----|
| `docker-compose.yml` | **New file** | Runs MT5 in Docker with Wine |
| `src/mt5_connector.py` | try/except import + tuple handling | Supports both Windows native and Linux mt5linux |
| `src/orchestrator.py` | Changed `import MetaTrader5 as mt5` → `from mt5_connector import mt5 as _mt5` | Linux doesn't have MetaTrader5 pip package |
| `.env` | Added `MT5_HOST`, `MT5_PORT`, `USE_MOCK_AI=false` | Config for mt5linux bridge + real AI mode |
| `watchdog.py` | **New file** | Auto-recovery for container/process failures |

---

> **Made with 🐧 for Linux traders who don't want to pay $30/mo for MetaAPI or $40/mo for a Windows VPS.**