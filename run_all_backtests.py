import subprocess
import json
import os
import pandas as pd
from datetime import datetime

def run_backtest(interval, start_date, end_date):
    print(f"\nRunning Backtest for TF: {interval}...")
    cmd = [
        "python", "main.py", "backtest",
        "--interval", str(interval),
        "--start-date", start_date,
        "--end-date", end_date,
        "--sample-rate", "1"
    ]
    try:
        subprocess.run(cmd, check=True)
        # Summary results are saved to backtest_summary.json
        if os.path.exists("backtest_summary.json"):
            with open("backtest_summary.json", "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error running {interval}: {e}")
    return None

import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Boss Multi-TF Backtest Aggregator")
    parser.add_argument('--start-date', default="2026-05-01", help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', default="2026-05-14", help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    start_date = args.start_date
    end_date = args.end_date
    intervals = ["5m", "15m", "1h"]
    
    all_results = []
    
    for tf in intervals:
        res = run_backtest(tf, start_date, end_date)
        if res:
            res['tf'] = tf
            all_results.append(res)
            
    if not all_results:
        print("No results to show.")
        return

    print("\n" + "="*60)
    print(" BOSS MULTI-TF BACKTEST SUMMARY")
    print("="*60)
    
    summary_data = []
    for r in all_results:
        summary_data.append({
            "Timeframe": r['tf'],
            "Total Trades": r['total_trades'],
            "Win Rate": f"{r['win_rate']:.2f}%",
            "Net Profit": f"${r['net_profit_loss']:.2f}",
            "Return": f"{r['profit_loss_pct']:.2f}%",
            "Max Drawdown": f"{r['max_drawdown_pct']:.2f}%"
        })
        
    df = pd.DataFrame(summary_data)
    print(df.to_string(index=False))
    
    total_profit = sum(float(r['net_profit_loss']) for r in all_results)
    total_pct = sum(float(r['profit_loss_pct']) for r in all_results)
    
    print("="*60)
    print(f" COMBINED NET PROFIT: ${total_profit:.2f} ({total_pct:.2f}%)")
    print("="*60)
    print(" Tip: Run each TF in a separate terminal for live trading!")

if __name__ == "__main__":
    main()
