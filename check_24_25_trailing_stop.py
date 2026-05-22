import sys
import os
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass
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
                import traceback
                print(f"Exception at {timestamp}: {e}")
                traceback.print_exc()
                continue

        if self.open_positions:
            last_price = self.market_data['close'].iloc[-1]
            self.backtester.close_all_positions(
                str(self.market_data.index[-1]),
                last_price
            )

        return self.backtester.get_report()

def run_experiment(risk_profile="stepdown", constant_risk=6.0, use_trailing=True, trigger=25.0, lock=2.0, use_atr_sl=True, target_year=2024):
    os.environ["USE_MOCK_AI"] = "true"
    os.environ["DATA_SOURCE"] = "mt5"
    os.environ["USE_DCA"] = "true"
    os.environ["USE_TRAILING_STOP"] = "true" if use_trailing else "false"
    os.environ["TRAILING_STOP_TRIGGER"] = str(trigger)
    os.environ["TRAILING_STOP_LOCK"] = str(lock)
    os.environ["USE_ATR_SL"] = "true" if use_atr_sl else "false"

    start_date = "2024-05-21"  # yfinance 730d limit for 1h data
    end_date = "2026-05-21"

    BacktestConfig.INITIAL_BALANCE = 50000.0
    
    orch = Custom9YOrchestrator(
        mode="BACKTEST", 
        risk_profile=risk_profile, 
        constant_risk=constant_risk
    )
    
    orch.load_market_data(
        symbol="GC=F",
        start=start_date,
        end=end_date,
        interval="1h"
    )
    
    orch.run_backtest(sample_every_n=1)
    
    # Filter trades for target year
    trades_year = [t for t in orch.backtester.trades if pd.to_datetime(t.entry_time).year == target_year]
    pnl_year = sum(t.profit_loss for t in trades_year)
    wins_year = sum(1 for t in trades_year if t.profit_loss > 0)
    total_trades = len(trades_year)
    win_rate = (wins_year / total_trades * 100) if total_trades > 0 else 0
    
    return pnl_year, total_trades, wins_year, win_rate

def main():
    configs = [
        {"name": "Old System (Fixed SL/TP, No Structure)", "use_trailing": True, "trigger": 10.0, "lock": 6.0, "use_atr_sl": False},
        {"name": "New System (ATR + S/R + Fibo Circles + Trail)", "use_trailing": True, "trigger": 25.0, "lock": 2.0, "use_atr_sl": True},
    ]
    
    years = [2024, 2025, 2026]
    profiles = [
        {"label": "Best System (6% Risk + Compounding)", "profile": "constant", "value": 6.0}
    ]
    
    print("Backtest results comparing Year 2024 and Year 2025 (separately):")
    
    for year in years:
        print(f"\n==========================================")
        print(f"               YEAR {year}")
        print(f"==========================================")
        for p in profiles:
            print(f"\nProfile: {p['label']}")
            for c in configs:
                pnl, count, wins, wr = run_experiment(
                    risk_profile=p["profile"],
                    constant_risk=p["value"],
                    use_trailing=c["use_trailing"],
                    trigger=c["trigger"],
                    lock=c["lock"],
                    use_atr_sl=c["use_atr_sl"],
                    target_year=year
                )
                print(f"  * {c['name']}: PnL = ${pnl:,.2f} | Trades = {count} (Wins: {wins}, Win Rate: {wr:.2f}%)")

if __name__ == "__main__":
    main()
