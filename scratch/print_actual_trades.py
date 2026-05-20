import sys
import os
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, 'src')
from orchestrator import MasterOrchestrator
import pandas as pd

orch = MasterOrchestrator(mode="BACKTEST")
orch.config.POSITION_SIZE_PERCENT = 2.0  # Safe risk

orch.load_market_data(
    symbol="GC=F",
    start="2024-01-01",
    end="2024-12-31",
    interval="1h"
)

orch.run_backtest(sample_every_n=1)

print("\n--- ACTUAL TRADES EXECUTED IN 2024 ---")
trades = orch.backtester.trades
print(f"Total trades: {len(trades)}")
for i, t in enumerate(trades, 1):
    pnl = t.profit_loss
    entry_p = t.entry_price
    exit_p = t.exit_price
    size = t.position_size
    entry_t = t.entry_time
    exit_t = t.exit_time
    sig = t.signal
    
    points = abs(exit_p - entry_p)
    print(f"Trade {i:2d}: {sig} | Entry: {entry_t} @ {entry_p:.2f} | Exit: {exit_t} @ {exit_p:.2f} | Size: {size:.2f} | PnL: ${pnl:,.2f} | Points: {points:.2f}")

print("\nDone!")
