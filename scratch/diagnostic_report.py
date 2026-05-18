import sys
from pathlib import Path
import os
import io

# Fix encoding on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add src path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orchestrator import MasterOrchestrator
import logging

# Disable general logs for a clean table report
logging.getLogger("orchestrator").setLevel(logging.WARNING)
logging.getLogger("backtester").setLevel(logging.WARNING)

def main():
    print("Running 2025 Quant Backtest Diagnostic Scanner...")
    
    orchestrator = MasterOrchestrator(mode="BACKTEST")
    orchestrator.load_market_data(
        symbol="GC=F",
        start="2025-01-01",
        end="2025-05-15",
        interval="1h"
    )
    
    # Run backtest
    orchestrator.run_backtest(sample_every_n=1)
    
    # Retrieve trades
    trades = orchestrator.backtester.trades
    
    print("\n" + "="*110)
    print(f" [2025 TRADING DIAGNOSTIC SCANNER: TOTAL {len(trades)} TRADES DETECTED]")
    print("="*110)
    print(f"{'#':<3} | {'TYPE':<4} | {'ENTRY TIME':<20} | {'ENTRY px':<9} | {'EXIT TIME':<20} | {'EXIT px':<9} | {'PnL ($)':<9} | {'STATUS':<12}")
    print("-"*110)
    
    for i, t in enumerate(trades, 1):
        pnl = t.profit_loss
        
        # Format times
        entry_time = str(t.entry_time)[:19]
        exit_time = str(t.exit_time)[:19] if t.exit_time else "STILL OPEN"
        exit_px = f"{t.exit_price:.2f}" if t.exit_price else "N/A"
        
        print(f"{i:<3} | {t.signal:<4} | {entry_time:<20} | {t.entry_price:<9.2f} | {exit_time:<20} | {exit_px:<9} | {pnl:<+9.2f} | {t.status:<12}")
        
    print("="*110)
    
    # Print Backtest Summary
    initial_bal = 10000.0
    final_bal = orchestrator.backtester.current_balance
    net_pnl = final_bal - initial_bal
    win_rate = (sum(1 for t in trades if t.profit_loss > 0) / len(trades)) * 100.0 if trades else 0.0
    
    print(f"Initial Balance: ${initial_bal:.2f}")
    print(f"Final Balance  : ${final_bal:.2f}")
    print(f"Net Profit/Loss: ${net_pnl:+.2f} ({net_pnl/initial_bal*100.0:+.2f}%)")
    print(f"Win Rate       : {win_rate:.2f}%")
    print("="*110)

if __name__ == "__main__":
    main()
