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

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("StepDown2026")

class StepDownOrchestrator(MasterOrchestrator):
    def __init__(self, mode="BACKTEST"):
        super().__init__(mode)
        self.analysis_history = []
        
    def run_backtest(self, sample_every_n: int = 1) -> str:
        """Run complete backtest with step-down monthly risk sizing"""
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

            # Step-down risk logic for 2026
            if dt.year == 2026:
                if current_month == 1:
                    risk = 25.0
                elif current_month == 2:
                    risk = 20.0
                elif current_month == 3:
                    risk = 15.0
                elif current_month == 4:
                    risk = 10.0
                elif current_month == 5:
                    risk = 6.0
                else:
                    risk = 6.0
            else:
                risk = 6.0 # Fallback/warmup

            self.config.POSITION_SIZE_PERCENT = risk

            # Monthly DCA Deposit
            if os.getenv("USE_DCA", "true").lower() == "true":
                if last_month is not None and current_month != last_month:
                    self.backtester.deposit(10000.0)
            last_month = current_month

            try:
                self.analyze_at_timestamp(timestamp, row)
            except Exception as e:
                continue

        # Close leftovers
        if self.backtester.open_positions:
            last_price = self.market_data['close'].iloc[-1]
            self.backtester.close_all_positions(
                str(self.market_data.index[-1]),
                last_price
            )

        report = self.backtester.get_report()
        return report

def run_experiment():
    os.environ["USE_MOCK_AI"] = "true"
    os.environ["DATA_SOURCE"] = "mt5"
    os.environ["USE_DCA"] = "true"
    os.environ["USE_TRAILING_STOP"] = "true"
    os.environ["TRAILING_STOP_TRIGGER"] = "10.0"
    os.environ["TRAILING_STOP_LOCK"] = "6.0"

    start_date = "2026-01-02"
    end_date = "2026-05-18"

    logger.info("=========================================")
    logger.info("RUNNING STEP-DOWN RISK BACKTEST")
    logger.info("=========================================")
    
    orch_stepdown = StepDownOrchestrator(mode="BACKTEST")
    orch_stepdown.load_market_data(
        symbol="GC=F",
        start=start_date,
        end=end_date,
        interval="1h"
    )
    orch_stepdown.run_backtest(sample_every_n=1)
    stats_stepdown = orch_stepdown.backtester.calculate_stats()
    trades_stepdown = orch_stepdown.backtester.trades

    # Extract monthly performance metrics
    monthly_performance = {}
    for t in trades_stepdown:
        entry_dt = pd.to_datetime(t.entry_time)
        month_name = entry_dt.strftime("%Y-%m")
        if month_name not in monthly_performance:
            monthly_performance[month_name] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        
        monthly_performance[month_name]["trades"] += 1
        if t.profit_loss > 0:
            monthly_performance[month_name]["wins"] += 1
        else:
            monthly_performance[month_name]["losses"] += 1
        monthly_performance[month_name]["pnl"] += t.profit_loss

    # Load baseline from previous test if exists
    baseline_stats = {}
    if os.path.exists("compare_2026_detailed_results.json"):
        try:
            with open("compare_2026_detailed_results.json", "r", encoding="utf-8") as f:
                prev_results = json.load(f)
                baseline_stats = prev_results.get("baseline", {})
        except Exception:
            pass

    comparison = {
        "stepdown": {
            "label": "Step-Down Risk (Jan: 25% -> Feb: 20% -> Mar: 15% -> Apr: 10% -> May: 6%)",
            "initial_balance": orch_stepdown.backtester.initial_balance,
            "total_deposited": orch_stepdown.backtester.total_deposited,
            "final_balance": orch_stepdown.backtester.current_balance,
            "net_profit": stats_stepdown.net_profit,
            "return_pct": stats_stepdown.return_pct,
            "total_trades": stats_stepdown.total_trades,
            "win_rate": stats_stepdown.win_rate,
            "winning_trades": stats_stepdown.winning_trades,
            "losing_trades": stats_stepdown.losing_trades,
            "profit_factor": stats_stepdown.profit_factor if stats_stepdown.profit_factor != float('inf') else 999,
            "max_drawdown": stats_stepdown.max_drawdown,
            "max_drawdown_pct": stats_stepdown.max_drawdown_pct,
            "monthly_breakdown": monthly_performance
        },
        "baseline": baseline_stats
    }

    # Save to file
    with open("compare_2026_stepdown_results.json", "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    logger.info("✅ Step-down results saved to compare_2026_stepdown_results.json")

if __name__ == "__main__":
    run_experiment()
