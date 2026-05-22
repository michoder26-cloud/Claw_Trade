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

# Configure logging to warn level to avoid cluttering stdout
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("TrailingStopOpt")

class Custom9YOrchestrator(MasterOrchestrator):
    def __init__(self, mode="BACKTEST", risk_profile="constant", constant_risk=6.0):
        super().__init__(mode)
        self.risk_profile = risk_profile
        self.constant_risk = constant_risk
        
    def run_backtest(self, sample_every_n: int = 1) -> str:
        if self.market_data is None:
            self.load_market_data()

        last_month = None
        for idx in range(0, len(self.market_data), sample_every_n):
            timestamp = self.market_data.index[idx]
            row = self.market_data.iloc[idx]
            dt = pd.to_datetime(timestamp)
            current_month = dt.month

            if self.risk_profile == "constant":
                self.config.POSITION_SIZE_PERCENT = self.constant_risk
            elif self.risk_profile == "stepdown":
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

            if os.getenv("USE_DCA", "true").lower() == "true":
                if last_month is not None and current_month != last_month:
                    self.backtester.deposit(10000.0)
            last_month = current_month

            try:
                self.analyze_at_timestamp(timestamp, row)
            except Exception as e:
                continue

        if self.open_positions:
            last_price = self.market_data['close'].iloc[-1]
            self.backtester.close_all_positions(
                str(self.market_data.index[-1]),
                last_price
            )

        return self.backtester.get_report()

def run_experiment(risk_profile, constant_risk, use_trailing, trigger=10.0, lock=6.0):
    # Force mock mode and mt5 data source
    os.environ["USE_MOCK_AI"] = "true"
    os.environ["DATA_SOURCE"] = "mt5"
    os.environ["USE_DCA"] = "true"
    os.environ["USE_TRAILING_STOP"] = "true" if use_trailing else "false"
    os.environ["TRAILING_STOP_TRIGGER"] = str(trigger)
    os.environ["TRAILING_STOP_LOCK"] = str(lock)

    start_date = "2017-01-03"
    end_date = "2026-05-21"

    BacktestConfig.INITIAL_BALANCE = 10000.0
    
    orch = Custom9YOrchestrator(
        mode="BACKTEST", 
        risk_profile=risk_profile, 
        constant_risk=constant_risk
    )
    
    orch.load_market_data(
        symbol="GC=F",
        start=start_date,
        end=end_date,
        interval="1d"
    )
    
    orch.run_backtest(sample_every_n=1)
    stats = orch.backtester.calculate_stats()
    
    return {
        "net_profit": stats.net_profit,
        "return_pct": stats.return_pct,
        "win_rate": stats.win_rate,
        "max_drawdown_pct": stats.max_drawdown_pct,
        "total_trades": stats.total_trades,
        "winning_trades": stats.winning_trades,
        "losing_trades": stats.losing_trades,
        "profit_factor": stats.profit_factor if stats.profit_factor != float('inf') else 999.0
    }

def main():
    print("OPTIMIZING TRAILING STOP PARAMETERS FOR 9-YEAR BACKTEST (2017-2026)...")
    
    configs = [
        {"name": "No Trailing Stop", "use_trailing": False, "trigger": 0.0, "lock": 0.0},
        {"name": "Trigger 10 / Lock 6 (Tight)", "use_trailing": True, "trigger": 10.0, "lock": 6.0},
        {"name": "Trigger 15 / Lock 2 (BE+2)", "use_trailing": True, "trigger": 15.0, "lock": 2.0},
        {"name": "Trigger 20 / Lock 2 (BE+2)", "use_trailing": True, "trigger": 20.0, "lock": 2.0},
        {"name": "Trigger 25 / Lock 2 (BE+2)", "use_trailing": True, "trigger": 25.0, "lock": 2.0},
        {"name": "Trigger 30 / Lock 5", "use_trailing": True, "trigger": 30.0, "lock": 5.0},
        {"name": "Trigger 40 / Lock 10", "use_trailing": True, "trigger": 40.0, "lock": 10.0},
    ]

    profiles = [
        {"label": "Constant 6% Risk", "profile": "constant", "value": 6.0},
        {"label": "Annual Step-Down Risk", "profile": "stepdown", "value": 0.0}
    ]

    all_results = {}
    
    for p in profiles:
        print(f"\nEvaluating profile: {p['label']}...")
        all_results[p['label']] = []
        for c in configs:
            res = run_experiment(
                risk_profile=p['profile'],
                constant_risk=p['value'],
                use_trailing=c['use_trailing'],
                trigger=c['trigger'],
                lock=c['lock']
            )
            res["config_name"] = c["name"]
            all_results[p['label']].append(res)
            print(f"  - {c['name']}: Profit = ${res['net_profit']:,.2f} ({res['return_pct']:.2f}%), Win Rate = {res['win_rate']:.2f}%, Max DD = {res['max_drawdown_pct']:.2f}%")
            
    # Save results to JSON
    out_file = project_root / "trailing_stop_optimization_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
        
    print(f"\nOptimization complete! Results saved to {out_file}")
    
    # Generate Markdown Table Report
    print("\n================== GENERATED REPORT ==================")
    for label, results in all_results.items():
        print(f"\n### {label} Results Table")
        print(f"| Trailing Stop Configuration | Net Profit ($) | Return (%) | Win Rate (%) | Max Drawdown (%) | Trades (W/L) | Profit Factor |")
        print(f"| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
        for r in results:
            print(f"| {r['config_name']} | ${r['net_profit']:,.2f} | {r['return_pct']:.2f}% | {r['win_rate']:.2f}% | {r['max_drawdown_pct']:.2f}% | {r['total_trades']} ({r['winning_trades']}W/{r['losing_trades']}L) | {r['profit_factor']:.2f} |")

if __name__ == "__main__":
    main()
