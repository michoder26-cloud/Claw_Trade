import sys
import os
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass
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
logger = logging.getLogger("Compare9Y")

class Custom9YOrchestrator(MasterOrchestrator):
    def __init__(self, mode="BACKTEST", risk_profile="constant", constant_risk=6.0):
        super().__init__(mode)
        self.risk_profile = risk_profile
        self.constant_risk = constant_risk
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

            # Adjust risk percentage dynamically based on profile
            if self.risk_profile == "constant":
                self.config.POSITION_SIZE_PERCENT = self.constant_risk
            elif self.risk_profile == "stepdown":
                # Step-down risk monthly: Jan: 25%, Feb: 20%, Mar: 15%, Apr: 10%, rest: 6%
                if current_month == 1:
                    risk = 25.0
                elif current_month == 2:
                    risk = 20.0
                elif current_month == 3:
                    risk = 15.0
                elif current_month == 4:
                    risk = 10.0
                else:
                    risk = 6.0
                self.config.POSITION_SIZE_PERCENT = risk

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

def analyze_yearly_stats(trades):
    """Summarize trades by year"""
    yearly_data = {}
    for t in trades:
        entry_dt = pd.to_datetime(t.entry_time)
        year = str(entry_dt.year)
        if year not in yearly_data:
            yearly_data[year] = {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl": 0.0
            }
        yearly_data[year]["trades"] += 1
        if t.profit_loss > 0:
            yearly_data[year]["wins"] += 1
        else:
            yearly_data[year]["losses"] += 1
        yearly_data[year]["pnl"] += t.profit_loss
    
    # Calculate win rate for each year
    for year in yearly_data:
        t_count = yearly_data[year]["trades"]
        if t_count > 0:
            yearly_data[year]["win_rate"] = (yearly_data[year]["wins"] / t_count) * 100
        else:
            yearly_data[year]["win_rate"] = 0.0
            
    return yearly_data

def run_all_experiments():
    # Force mock mode and mt5 data source
    os.environ["USE_MOCK_AI"] = "true"
    os.environ["DATA_SOURCE"] = "mt5"
    os.environ["USE_DCA"] = "true"
    os.environ["USE_TRAILING_STOP"] = "true"
    os.environ["TRAILING_STOP_TRIGGER"] = "10.0"
    os.environ["TRAILING_STOP_LOCK"] = "6.0"

    start_date = "2017-01-03"
    end_date = "2026-05-21"

    # Define experiments
    experiments = [
        {"name": "risk_2pct", "label": "Constant 2% Risk", "profile": "constant", "value": 2.0},
        {"name": "risk_6pct", "label": "Constant 6% Risk", "profile": "constant", "value": 6.0},
        {"name": "risk_15pct", "label": "Constant 15% Risk", "profile": "constant", "value": 15.0},
        {"name": "stepdown", "label": "Annual Step-Down Risk (Jan: 25% -> rest: 6%)", "profile": "stepdown", "value": 0.0}
    ]

    results = {}

    for exp in experiments:
        logger.info("=========================================")
        logger.info(f"RUNNING 9-YEAR BACKTEST: {exp['label']}")
        logger.info("=========================================")
        
        # Reset configuration before run
        BacktestConfig.INITIAL_BALANCE = 10000.0
        
        orch = Custom9YOrchestrator(
            mode="BACKTEST", 
            risk_profile=exp["profile"], 
            constant_risk=exp["value"]
        )
        
        orch.load_market_data(
            symbol="GC=F",
            start=start_date,
            end=end_date,
            interval="1d"
        )
        
        orch.run_backtest(sample_every_n=1)
        stats = orch.backtester.calculate_stats()
        trades = orch.backtester.trades
        
        yearly_breakdown = analyze_yearly_stats(trades)
        
        results[exp["name"]] = {
            "label": exp["label"],
            "initial_balance": orch.backtester.initial_balance,
            "total_deposited": orch.backtester.total_deposited,
            "final_balance": orch.backtester.current_balance,
            "net_profit": stats.net_profit,
            "return_pct": stats.return_pct,
            "total_trades": stats.total_trades,
            "win_rate": stats.win_rate,
            "winning_trades": stats.winning_trades,
            "losing_trades": stats.losing_trades,
            "profit_factor": stats.profit_factor if stats.profit_factor != float('inf') else 999.0,
            "max_drawdown": stats.max_drawdown,
            "max_drawdown_pct": stats.max_drawdown_pct,
            "yearly_breakdown": yearly_breakdown
        }
        
        logger.info(f"Finished {exp['label']}: Net Profit = ${stats.net_profit:,.2f}, Max Drawdown = {stats.max_drawdown_pct:.2f}%")

    # Save to file
    out_file = project_root / "compare_9y_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logger.info(f"✅ All 9-year experiments completed. Results saved to {out_file}")

if __name__ == "__main__":
    run_all_experiments()
