#!/usr/bin/env python3
"""
ClawTrade Watchdog v2 — Silent health check + auto-recovery
Checks: container, MT5 terminal, mt5linux RPyC, bot process, MT5 login
Auto-fixes what it can. Only alerts (Telegram) when it CAN'T fix.
"""
import os, sys, time, json, subprocess, logging
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path("/root/Claw_Trade")
LOG_FILE = PROJECT_DIR / "watchdog_v2.log"
BOT_LOG = "/tmp/claw_live5.log"
PYTHON = sys.executable  # use same python that runs this

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - WD2 - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("watchdog")

CONTAINER = "claw-trade-mt5"
COMPOSE_FILE = PROJECT_DIR / "docker-compose.yml"

def run(cmd, timeout=15):
    """Run command, return (success, stdout)"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip()
    except Exception as e:
        return False, str(e)

def check_container():
    """Is Docker container running?"""
    ok, out = run(["docker", "inspect", CONTAINER, "--format", "{{.State.Status}}"])
    return ok and out == "running", out

def restart_container():
    log.warning("🔄 Restarting container...")
    run(["docker", "restart", CONTAINER], timeout=60)
    time.sleep(30)

def kill_xmrig():
    """Kill any xmrig processes inside container"""
    run(["docker", "exec", CONTAINER, "pkill", "-9", "-f", "xmrig"], timeout=8)
    run(["docker", "exec", CONTAINER, "pkill", "-9", "-f", "xmr_linux"], timeout=8)
    run(["docker", "exec", CONTAINER, "bash", "-c", "rm -rf /tmp/xmrig /tmp/xmr_linux_amd64"], timeout=8)

def check_mt5_terminal():
    """Is MT5 terminal64.exe running in Wine?"""
    ok, out = run([
        "docker", "exec", "-u", "abc", CONTAINER, "bash", "-c",
        'WINEPREFIX=/config/.wine wine tasklist 2>&1 | grep -i terminal64'
    ], timeout=15)
    return ok and "terminal64" in out.lower(), out

def start_mt5_terminal():
    """Launch MT5 terminal in Wine"""
    log.warning("🔄 Starting MT5 terminal in Wine...")
    subprocess.Popen([
        "docker", "exec", "-d", "-u", "abc",
        "-e", "DISPLAY=:1", "-e", "WINEPREFIX=/config/.wine",
        CONTAINER, "bash", "-c",
        'WINEDEBUG=-all wine "/config/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe" > /tmp/mt5_wd.log 2>&1'
    ])
    time.sleep(20)

def check_rpyc():
    """Is mt5linux RPyC server listening on 8001?"""
    ok, out = run([
        "docker", "exec", CONTAINER, "bash", "-c",
        "ss -tlnp | grep -q 8001 && echo alive || echo dead"
    ])
    return ok and "alive" in out, out

def start_rpyc():
    """Start mt5linux RPyC server manually"""
    log.warning("🔄 Starting mt5linux RPyC server...")
    subprocess.Popen([
        "docker", "exec", "-d", "-u", "abc",
        "-e", "WINEPREFIX=/config/.wine",
        CONTAINER, "bash", "-c",
        'wine "C:\\Program Files (x86)\\Python39-32\\python.exe" -m mt5linux --host 0.0.0.0 --port 8001 > /tmp/mt5linux_wd.log 2>&1'
    ])
    time.sleep(10)

def check_mt5_login():
    """Can we connect to MT5 and get account info?"""
    try:
        from dotenv import load_dotenv
        load_dotenv(str(PROJECT_DIR / ".env"))
        import sys as _sys
        _sys.path.insert(0, str(PROJECT_DIR / "src"))
        import mt5linux
        mt5 = mt5linux.MetaTrader5(host='localhost', port=8001)
        mt5.initialize(
            login=int(os.getenv('MT5_LOGIN', 0)),
            password=os.getenv('MT5_PASSWORD', ''),
            server=os.getenv('MT5_SERVER', '')
        )
        info = mt5.terminal_info()
        acc = mt5.account_info()
        if info and acc:
            return True, f"balance={acc.balance}"
        return False, "terminal_info or account_info is None"
    except Exception as e:
        return False, str(e)

def check_bot_process():
    """Is main.py live trading running?"""
    ok, out = run(["ps", "aux"])
    if not ok:
        return False, "cannot check ps"
    lines = [l for l in out.split("\n") if "main.py" in l and "live" in l and "grep" not in l]
    return len(lines) > 0, f"{len(lines)} process(es)"

def start_bot():
    """Start live trading bot"""
    log.warning("🚀 Starting live trading bot...")
    subprocess.Popen([
        PYTHON, "-u", str(PROJECT_DIR / "main.py"),
        "live", "--confirm", "--symbol", "XAUUSDc", "--interval", "5"
    ], cwd=str(PROJECT_DIR),
       stdout=open(BOT_LOG, "a"),
       stderr=subprocess.STDOUT,
       start_new_session=True,
       env={**os.environ, "PYTHONUNBUFFERED": "1"}
    )
    time.sleep(10)

def main():
    """Main watchdog check — returns (all_ok, alert_message)"""
    log.info("=" * 40)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Container
    ok, status = check_container()
    if not ok:
        log.warning(f"Container down ({status}). Restarting...")
        restart_container()
        kill_xmrig()
        ok, status = check_container()
        if not ok:
            return False, f"❌ Container ไม่รันและ restart ไม่ได้ ({status})"
    else:
        log.info("✅ Container running")

    # Kill xmrig silently
    kill_xmrig()

    # 2. MT5 terminal in Wine
    ok, _ = check_mt5_terminal()
    if not ok:
        log.warning("MT5 terminal not running. Starting...")
        start_mt5_terminal()
        ok, _ = check_mt5_terminal()
        if not ok:
            return False, "❌ MT5 terminal เปิดไม่ขึ้นใน Wine"
    else:
        log.info("✅ MT5 terminal running")

    # 3. RPyC server
    ok, _ = check_rpyc()
    if not ok:
        log.warning("RPyC not listening. Starting...")
        start_rpyc()
        ok, _ = check_rpyc()
        if not ok:
            return False, "❌ mt5linux RPyC server (port 8001) ไม่รัน"
    else:
        log.info("✅ RPyC server listening")

    # 4. MT5 login
    ok, detail = check_mt5_login()
    if not ok:
        log.warning(f"MT5 login failed ({detail}). Restarting MT5 terminal...")
        start_mt5_terminal()
        time.sleep(25)
        ok, detail = check_mt5_login()
        if not ok:
            return False, f"❌ MT5 ล็อกอินไม่ได้ ({detail})"
    else:
        log.info(f"✅ MT5 logged in ({detail})")

    # 5. Bot process
    ok, detail = check_bot_process()
    if not ok:
        log.warning("Bot not running. Starting...")
        start_bot()
        ok, detail = check_bot_process()
        if not ok:
            return False, "❌ Bot (main.py live) รันไม่ขึ้น"
    else:
        log.info(f"✅ Bot running ({detail})")

    log.info("All checks passed. Silent.")
    return True, ""  # All good — stay silent

if __name__ == "__main__":
    all_ok, alert = main()
    if not all_ok:
        # Print alert to stdout (cron job can capture and send)
        print(f"ALERT: {alert}")
        sys.exit(1)
    else:
        # Silent — everything is fine
        sys.exit(0)