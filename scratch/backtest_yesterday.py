import os
import sys
from pathlib import Path
import json
import pandas as pd
from datetime import datetime

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from orchestrator import MasterOrchestrator
from config import Config, BacktestConfig

def main():
    # Force mock mode and yfinance locally
    os.environ["USE_MOCK_AI"] = "true"
    os.environ["DATA_SOURCE"] = "yfinance"
    os.environ["USE_DCA"] = "false"
    
    # Configure backtest settings to match safe run parameters
    Config.POSITION_SIZE_PERCENT = 1.5
    Config.USE_TRAILING_STOP = True
    Config.TRAIL_BREAKEVEN_TRIGGER = 1.0
    Config.TRAIL_LOCK_TRIGGER = 2.0
    Config.USE_FIXED_SL_TP = False
    
    BacktestConfig.POSITION_SIZE_PERCENT = 1.5
    BacktestConfig.USE_TRAILING_STOP = True
    BacktestConfig.TRAIL_BREAKEVEN_TRIGGER = 1.0
    BacktestConfig.TRAIL_LOCK_TRIGGER = 2.0
    BacktestConfig.USE_FIXED_SL_TP = False
    
    orch = MasterOrchestrator(mode="BACKTEST")
    orch.config.INITIAL_BALANCE = 10000.0
    
    # Yesterday's date range (June 8, 2026 to June 9, 2026)
    start = "2026-06-08"
    end = "2026-06-09"
    
    print(f"Running backtest for yesterday: {start} -> {end}")
    
    try:
        orch.load_market_data(
            symbol="GC=F",
            start=start,
            end=end,
            interval="1h"
        )
        
        if orch.market_data.empty:
            print("Error: No data loaded.")
            return
            
        print(f"Loaded {len(orch.market_data)} candles (including technical extensions).")
        
        orch.run_backtest(sample_every_n=1)
        stats = orch.backtester.calculate_stats()
        
        print("\n" + "="*50)
        print("📊 BACKTEST RESULT FOR YESTERDAY")
        print("="*50)
        print(f"Total Trades Executed: {stats.total_trades}")
        print(f"Net Profit/Loss: ${stats.net_profit:,.2f}")
        
        if stats.total_trades > 0:
            print(f"Win Rate: {stats.win_rate:.1f}%")
            print("\nTrade details:")
            for i, t in enumerate(orch.backtester.trades):
                print(f"  [{i+1}] {t.signal} entered at {t.entry_time} @ ${t.entry_price:.2f}")
                print(f"      closed at {t.exit_time} @ ${t.exit_price:.2f} | Outcome: {'WIN' if t.profit_loss > 0 else 'LOSS'} (${t.profit_loss:.2f})")
        else:
            print("No trades were opened yesterday. The system stood aside.")
            
    except Exception as e:
        print(f"Error executing backtest: {e}")

if __name__ == "__main__":
    main()
