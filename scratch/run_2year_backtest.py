import os
import sys
from pathlib import Path
import json
import pandas as pd
from datetime import datetime, timedelta

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
    
    # Force override Config and BacktestConfig attributes directly in python to bypass caching!
    Config.POSITION_SIZE_PERCENT = 1.5 # 1.5% safe risk
    Config.USE_TRAILING_STOP = True
    Config.TRAIL_BREAKEVEN_TRIGGER = 1.0
    Config.TRAIL_LOCK_TRIGGER = 2.0
    Config.USE_FIXED_SL_TP = False
    
    BacktestConfig.POSITION_SIZE_PERCENT = 1.5
    BacktestConfig.USE_TRAILING_STOP = True
    BacktestConfig.TRAIL_BREAKEVEN_TRIGGER = 1.0
    BacktestConfig.TRAIL_LOCK_TRIGGER = 2.0
    BacktestConfig.USE_FIXED_SL_TP = False
    
    # Initialize one orchestrator for the entire run so memory carries over
    orch = MasterOrchestrator(mode="BACKTEST")
    orch.config.INITIAL_BALANCE = 10000.0
    
    # Generate 24 months sequence (June 2024 to May 2026)
    start_date = datetime(2024, 6, 1)
    months = []
    for i in range(24):
        current_month = start_date + pd.DateOffset(months=i)
        next_month = start_date + pd.DateOffset(months=i+1)
        months.append((
            current_month.strftime("%Y-%m"),
            current_month.strftime("%Y-%m-%d"),
            next_month.strftime("%Y-%m-%d")
        ))
        
    monthly_reports = []
    starting_balance = 10000.0
    
    print("Starting Safe 24-Month Continuous Training (Risk: 1.5%)...")
    
    for name, start, end in months:
        print("\n" + "-" * 50)
        print(f"Running Month: {name} | Account Balance: ${orch.backtester.current_balance:,.2f}")
        print("-" * 50)
        
        try:
            orch.load_market_data(
                symbol="GC=F",
                start=start,
                end=end,
                interval="1h"
            )
            
            if orch.market_data.empty:
                print(f"Warning: No market data for {name}, skipping.")
                continue
                
            # Reset trades for the month, but keep the current balance and learning_memory!
            orch.backtester.trades = []
            
            # Run backtest
            orch.run_backtest(sample_every_n=1)
            stats = orch.backtester.calculate_stats()
            
            monthly_reports.append({
                "month": name,
                "starting_balance": stats.net_profit + orch.backtester.current_balance - stats.net_profit,
                "net_profit": stats.net_profit,
                "return_pct": stats.return_pct,
                "total_trades": stats.total_trades,
                "win_rate": stats.win_rate,
                "winning_trades": stats.winning_trades,
                "losing_trades": stats.losing_trades,
                "max_drawdown_pct": stats.max_drawdown_pct
            })
            
            print(f"Finished {name}: P&L = ${stats.net_profit:,.2f} ({stats.return_pct:.2f}%) | WR = {stats.win_rate:.1f}%")
            
        except Exception as e:
            print(f"Error running month {name}: {e}")
            
    # Save final report to JSON
    report_file = project_root / "scratch" / "24month_training_results.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "monthly_reports": monthly_reports,
            "final_balance": orch.backtester.current_balance,
            "total_net_profit": orch.backtester.current_balance - starting_balance,
            "total_return_pct": ((orch.backtester.current_balance - starting_balance) / starting_balance) * 100,
            "learning_memory_size": len(orch.learning_memory),
            "learning_memory": orch.learning_memory
        }, f, indent=2, ensure_ascii=False)
        
    print("\n" + "=" * 50)
    print("Safe 24-Month Continuous Run Completed!")
    print(f"Saved results to {report_file}")
    print(f"Final Account Balance: ${orch.backtester.current_balance:,.2f}")
    print(f"Total Net P&L: ${orch.backtester.current_balance - starting_balance:,.2f}")
    print(f"Total Return: {((orch.backtester.current_balance - starting_balance) / starting_balance) * 100:.2f}%")
    print(f"Lessons Learned in Memory: {len(orch.learning_memory)}")
    print("=" * 50)

if __name__ == "__main__":
    main()
