#!/usr/bin/env python3
"""
Claw_Trade Live Trading Launcher & Watchdog
- Starts live trading if not running
- Restarts if the process dies
- Works with docker-compose restart
"""
import os
import sys
import time
import logging
import subprocess
from pathlib import Path

PROJECT_DIR = Path("/root/Claw_Trade")
VENV_PYTHON = PROJECT_DIR / ".venv" / "bin" / "python3"
LOG_FILE = PROJECT_DIR / "live_trading_watchdog.log"
PID_FILE = PROJECT_DIR / "live_trading.pid"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - WATCHDOG - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def is_process_running(pid):
    """Check if process with given PID is running"""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False

def is_mt5linux_alive():
    """Check if mt5linux server in Docker responds"""
    try:
        # Use timeout to avoid hanging
        result = subprocess.run(
            ["docker", "exec", "claw-trade-mt5", "bash", "-c",
             "ss -tlnp | grep -q 8001 && echo alive || echo dead"],
            capture_output=True, text=True, timeout=10
        )
        return "alive" in result.stdout
    except Exception:
        return False

def restart_container():
    """Restart the MT5 Docker container"""
    logging.warning("🔄 Restarting claw-trade-mt5 container...")
    subprocess.run(
        ["docker", "compose", "-f", str(PROJECT_DIR / "docker-compose.yml"), "restart", "-t", "30"],
        capture_output=True, text=True, timeout=60
    )
    # Wait for container to be ready
    time.sleep(15)
    # Check if mt5linux starts (s6 service handles this)
    for i in range(30):
        if is_mt5linux_alive():
            logging.info("✅ mt5linux server is alive after restart!")
            return True
        time.sleep(5)
    logging.error("❌ mt5linux did not start after container restart")
    return False

def start_live_trading():
    """Start the live trading process"""
    cmd = [
        str(VENV_PYTHON), "-u",
        str(PROJECT_DIR / "main.py"),
        "live", "--confirm", "--interval", "60"
    ]
    
    log_fd = open(PROJECT_DIR / "live_trading_output.log", "a")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_DIR),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True
    )
    
    # Write PID file
    PID_FILE.write_text(str(proc.pid))
    logging.info(f"🚀 Live trading started (PID: {proc.pid})")
    return proc

def main():
    logging.info("=" * 50)
    logging.info("🐶 Claw_Trade Watchdog starting...")
    
    # Step 1: Ensure Docker container is running
    result = subprocess.run(
        ["docker", "inspect", "claw-trade-mt5", "--format", "{{.State.Status}}"],
        capture_output=True, text=True, timeout=10
    )
    container_status = result.stdout.strip()
    
    if container_status != "running":
        logging.warning(f"Container status: {container_status}. Starting...")
        subprocess.run(
            ["docker", "compose", "-f", str(PROJECT_DIR / "docker-compose.yml"), "up", "-d"],
            capture_output=True, text=True, timeout=60
        )
        time.sleep(20)
    
    # Step 2: Ensure mt5linux is running inside container
    if not is_mt5linux_alive():
        logging.warning("mt5linux not responding. Restarting container...")
        restart_container()
    else:
        logging.info("✅ mt5linux server is alive")
    
    # Step 3: Start or verify live trading process
    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        if is_process_running(pid):
            logging.info(f"✅ Live trading already running (PID: {pid})")
            return
        
        logging.warning(f"Old PID {pid} not running. Starting new process.")
        PID_FILE.unlink(missing_ok=True)
    
    # Start live trading
    start_live_trading()

if __name__ == "__main__":
    main()
