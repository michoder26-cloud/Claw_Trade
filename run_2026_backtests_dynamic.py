import sys
import os
from pathlib import Path
import pandas as pd
import json
import logging

# Ensure project paths are in sys.path
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from orchestrator import MasterOrchestrator
from config import BacktestConfig

# Configure logging to console only
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("Compare2026")

class CustomOrchestrator(MasterOrchestrator):
    def __init__(self, mode="BACKTEST", dynamic_risk=False, jan_risk=25.0, default_risk=6.0):
        super().__init__(mode)
        self.dynamic_risk = dynamic_risk
        self.jan_risk = jan_risk
        self.default_risk = default_risk
        # Reset any state
        self.analysis_history = []
        
    def run_backtest(self, sample_every_n: int = 1) -> str:
        """Run complete backtest with custom dynamic/constant risk sizing"""
        if self.market_data is None:
            self.load_market_data()

        # Track month for recurring DCA deposits
        last_month = None

        # Run cycle
        for idx in range(0, len(self.market_data), sample_every_n):
            timestamp = self.market_data.index[idx]
            row = self.market_data.iloc[idx]
            dt = pd.to_datetime(timestamp)
            current_month = dt.month

            # Adjust risk percentage dynamically if enabled
            if self.dynamic_risk:
                if dt.year == 2026 and current_month == 1:
                    self.config.POSITION_SIZE_PERCENT = self.jan_risk
                else:
                    self.config.POSITION_SIZE_PERCENT = self.default_risk
            else:
                self.config.POSITION_SIZE_PERCENT = self.default_risk

            # Monthly DCA Deposit: Injected at each new month if USE_DCA is True
            if os.getenv("USE_DCA", "true").lower() == "true":
                if last_month is not None and current_month != last_month:
                    self.backtester.deposit(10000.0)
            last_month = current_month

            try:
                self.analyze_at_timestamp(timestamp, row)
            except Exception as e:
                # Silent skip for warmup periods or data fetch anomalies
                continue

        # Close any leftovers at the very last price
        if self.backtester.open_positions:
            last_price = self.market_data['close'].iloc[-1]
            self.backtester.close_all_positions(
                str(self.market_data.index[-1]),
                last_price
            )

        report = self.backtester.get_report()
        return report

def run_experiment():
    # Force mock mode and mt5 data source
    os.environ["USE_MOCK_AI"] = "true"
    os.environ["DATA_SOURCE"] = "mt5"
    os.environ["USE_DCA"] = "true"
    os.environ["USE_TRAILING_STOP"] = "true"
    os.environ["TRAILING_STOP_TRIGGER"] = "10.0"
    os.environ["TRAILING_STOP_LOCK"] = "6.0"

    start_date = "2026-01-02"
    end_date = "2026-05-18"

    logger.info("=========================================")
    logger.info("RUNNING BASELINE BACKTEST: Constant 6% Risk")
    logger.info("=========================================")
    
    orch_baseline = CustomOrchestrator(
        mode="BACKTEST", 
        dynamic_risk=False, 
        jan_risk=25.0, 
        default_risk=6.0
    )
    orch_baseline.load_market_data(
        symbol="GC=F",
        start=start_date,
        end=end_date,
        interval="1h"
    )
    orch_baseline.run_backtest(sample_every_n=1)
    stats_baseline = orch_baseline.backtester.calculate_stats()
    trades_baseline = orch_baseline.backtester.trades

    logger.info("=========================================")
    logger.info("RUNNING EXPERIMENTAL BACKTEST: Jan 25% | Rest 6%")
    logger.info("=========================================")
    
    orch_dynamic = CustomOrchestrator(
        mode="BACKTEST", 
        dynamic_risk=True, 
        jan_risk=25.0, 
        default_risk=6.0
    )
    orch_dynamic.load_market_data(
        symbol="GC=F",
        start=start_date,
        end=end_date,
        interval="1h"
    )
    orch_dynamic.run_backtest(sample_every_n=1)
    stats_dynamic = orch_dynamic.backtester.calculate_stats()
    trades_dynamic = orch_dynamic.backtester.trades

    # Extract January 2026 trades to show the user details of the high risk period
    jan_trades_baseline = []
    jan_trades_dynamic = []

    for t in trades_baseline:
        entry_dt = pd.to_datetime(t.entry_time)
        if entry_dt.year == 2026 and entry_dt.month == 1:
            jan_trades_baseline.append(t)

    for t in trades_dynamic:
        entry_dt = pd.to_datetime(t.entry_time)
        if entry_dt.year == 2026 and entry_dt.month == 1:
            jan_trades_dynamic.append(t)

    # Format output results
    comparison = {
        "baseline": {
            "label": "Constant Risk (6% Constant)",
            "initial_balance": orch_baseline.backtester.initial_balance,
            "total_deposited": orch_baseline.backtester.total_deposited,
            "final_balance": orch_baseline.backtester.current_balance,
            "net_profit": stats_baseline.net_profit,
            "return_pct": stats_baseline.return_pct,
            "total_trades": stats_baseline.total_trades,
            "win_rate": stats_baseline.win_rate,
            "winning_trades": stats_baseline.winning_trades,
            "losing_trades": stats_baseline.losing_trades,
            "profit_factor": stats_baseline.profit_factor if stats_baseline.profit_factor != float('inf') else 999,
            "max_drawdown": stats_baseline.max_drawdown,
            "max_drawdown_pct": stats_baseline.max_drawdown_pct,
            "jan_trades": [
                {
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "signal": t.signal,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "position_size": t.position_size,
                    "profit_loss": t.profit_loss,
                    "status": t.status
                } for t in jan_trades_baseline
            ]
        },
        "dynamic": {
            "label": "Dynamic Risk (Jan: 25% | Feb+: 6%)",
            "initial_balance": orch_dynamic.backtester.initial_balance,
            "total_deposited": orch_dynamic.backtester.total_deposited,
            "final_balance": orch_dynamic.backtester.current_balance,
            "net_profit": stats_dynamic.net_profit,
            "return_pct": stats_dynamic.return_pct,
            "total_trades": stats_dynamic.total_trades,
            "win_rate": stats_dynamic.win_rate,
            "winning_trades": stats_dynamic.winning_trades,
            "losing_trades": stats_dynamic.losing_trades,
            "profit_factor": stats_dynamic.profit_factor if stats_dynamic.profit_factor != float('inf') else 999,
            "max_drawdown": stats_dynamic.max_drawdown,
            "max_drawdown_pct": stats_dynamic.max_drawdown_pct,
            "jan_trades": [
                {
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "signal": t.signal,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "position_size": t.position_size,
                    "profit_loss": t.profit_loss,
                    "status": t.status
                } for t in jan_trades_dynamic
            ]
        }
    }

    # Save to file
    with open("compare_2026_detailed_results.json", "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    logger.info("✅ Detailed comparison saved to compare_2026_detailed_results.json")

if __name__ == "__main__":
    run_experiment()
