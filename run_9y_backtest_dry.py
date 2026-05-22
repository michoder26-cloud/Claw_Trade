import sys
import os
from pathlib import Path
import pandas as pd
import json

# Ensure project paths are in sys.path
project_root = Path(r"c:\Users\TKTF\Desktop\Sub_Agent\xau_trading_system")
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from orchestrator import MasterOrchestrator
from config import BacktestConfig

class Run9YBacktest:
    @staticmethod
    def run():
        os.environ["USE_MOCK_AI"] = "true"
        os.environ["DATA_SOURCE"] = "mt5" # loads mt5_historical_data.csv cache
        os.environ["USE_DCA"] = "true"
        os.environ["USE_TRAILING_STOP"] = "true"
        os.environ["TRAILING_STOP_TRIGGER"] = "10.0"
        os.environ["TRAILING_STOP_LOCK"] = "6.0"

        # Initialize orchestrator
        # Let's set position size risk percentage to 6% constant
        BacktestConfig.POSITION_SIZE_PERCENT = 6.0
        
        # Override initial balance if needed
        BacktestConfig.INITIAL_BALANCE = 10000.0

        orch = MasterOrchestrator(mode="BACKTEST")
        
        # Load data
        print("Loading market data...")
        orch.load_market_data(
            symbol="GC=F",
            start="2017-01-03",
            end="2026-05-21",
            interval="1d"
        )
        
        print(f"Loaded {len(orch.market_data)} daily bars.")
        
        # Run backtest
        print("Running backtest loop...")
        # Since interval is 1d, sample_every_n must be 1 to check every candle
        report = orch.run_backtest(sample_every_n=1)
        
        print(report)
        
        # Check stats
        stats = orch.backtester.calculate_stats()
        print(f"Total Trades: {stats.total_trades}")
        print(f"Win Rate: {stats.win_rate:.2f}%")
        print(f"Net Profit: ${stats.net_profit:,.2f}")
        print(f"Max Drawdown: ${stats.max_drawdown:,.2f} ({stats.max_drawdown_pct:.2f}%)")

if __name__ == "__main__":
    Run9YBacktest.run()
