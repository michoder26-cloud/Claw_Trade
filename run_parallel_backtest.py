
import subprocess
import time
from datetime import datetime
import json
import os
from dotenv import load_dotenv

# Force load latest environment
load_dotenv(override=True)

def run_chunk(start, end, chunk_id):
    print(f"Starting Chunk {chunk_id}: {start} to {end}")
    log_file = open(f"chunk_{chunk_id}.log", "w", encoding="utf-8")
    cmd = [
        "python", "main.py", "backtest",
        "--start-date", start,
        "--end-date", end,
        "--interval", "1h",
        "--sample-rate", "1"
    ]
    # Pass current environment which now has the updated .env values
    env = os.environ.copy()
    return subprocess.Popen(cmd, env=env, stdout=log_file, stderr=log_file), log_file

if __name__ == "__main__":
    num_chunks = 1
    chunks = [
        ("2026-05-12", "2026-05-15")
    ]
    
    processes = []
    log_files = []
    for i, (start, end) in enumerate(chunks):
        p, lf = run_chunk(start, end, i+1)
        processes.append(p)
        log_files.append(lf)
        time.sleep(10) # Stagger more to avoid concurrent file access
        
    print("\nSniper Engine is running (Single process mode for 120B stability)!")
    print("Monitoring progress (Check chunk_*.log for details)...")
    
    # Wait and check status
    while any(p.poll() is None for p in processes):
        time.sleep(10)
        
    for lf in log_files:
        lf.close()
        
    print("\nAll parallel backtests finished!")
