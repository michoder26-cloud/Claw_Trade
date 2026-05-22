import sys
import os
from pathlib import Path
import pandas as pd

# Ensure project paths are in sys.path
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from orchestrator import MasterOrchestrator
from config import BacktestConfig

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

def run_experiment(risk_profile, constant_risk, use_trailing, trigger, lock):
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
    
    # Filter 2026 trades
    trades_2026 = [t for t in orch.backtester.trades if pd.to_datetime(t.entry_time).year == 2026]
    pnl_2026 = sum(t.profit_loss for t in trades_2026)
    wins_2026 = sum(1 for t in trades_2026 if t.profit_loss > 0)
    
    return pnl_2026, len(trades_2026), wins_2026

def main():
    print("Checking 2026 PnL specifically for different Trailing Stop settings...")
    configs = [
        {"name": "No Trailing Stop", "use_trailing": False, "trigger": 0.0, "lock": 0.0},
        {"name": "Trigger 10 / Lock 6 (Tight)", "use_trailing": True, "trigger": 10.0, "lock": 6.0},
        {"name": "Trigger 25 / Lock 2 (BE+2)", "use_trailing": True, "trigger": 25.0, "lock": 2.0},
    ]
    
    for c in configs:
        pnl_step, count_step, wins_step = run_experiment("stepdown", 0.0, c["use_trailing"], c["trigger"], c["lock"])
        pnl_const, count_const, wins_const = run_experiment("constant", 6.0, c["use_trailing"], c["trigger"], c["lock"])
        print(f"\nConfiguration: {c['name']}")
        print(f"  Step-down Risk 2026 PnL: ${pnl_step:,.2f} ({count_step} trades, {wins_step} wins)")
        print(f"  Constant 6% Risk 2026 PnL: ${pnl_const:,.2f} ({count_const} trades, {wins_const} wins)")

if __name__ == "__main__":
    main()
