import json
import pandas as pd
from collections import defaultdict
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load backtest results
with open('backtest_results.json', 'r') as f:
    results = json.load(f)

# Extract trades
trades = []
for entry in results:
    if entry.get('trade_executed'):
        decision = entry['agents_analysis']['ceo']['decision']
        if decision in ['BUY', 'SELL']:
            trades.append({
                'timestamp': entry['timestamp'],
                'price': entry['price'],
                'signal': decision,
                'regime': entry.get('regime', 'UNKNOWN')
            })

# Calculate basic stats
total_entries = len(results)
total_trades = len(trades)
buy_trades = len([t for t in trades if t['signal'] == 'BUY'])
sell_trades = len([t for t in trades if t['signal'] == 'SELL'])

# Analyze regimes
regime_counts = defaultdict(int)
for entry in results:
    regime = entry.get('regime', 'UNKNOWN')
    regime_counts[regime] += 1

# Print report
print("\n" + "="*60)
print("DORAEMON BACKTEST ANALYSIS - XAU/USD Trading System")
print("="*60)
print(f"\nTotal Historical Periods: {total_entries}")
print(f"Total Trades Executed: {total_trades}")
print(f"  - BUY Trades: {buy_trades}")
print(f"  - SELL Trades: {sell_trades}")
print(f"\nMarket Regimes:")
for regime, count in sorted(regime_counts.items()):
    pct = (count / total_entries) * 100
    print(f"  - {regime}: {count} ({pct:.1f}%)")

print("\nTRADE DISTRIBUTION:")
if total_trades > 0:
    buy_pct = (buy_trades / total_trades) * 100
    sell_pct = (sell_trades / total_trades) * 100
    print(f"  - BUY: {buy_pct:.1f}%")
    print(f"  - SELL: {sell_pct:.1f}%")
else:
    print("  - No trades executed")

# Analyze CEO decisions
ceo_decisions = defaultdict(int)
for entry in results:
    try:
        decision = entry['agents_analysis']['ceo']['decision']
        ceo_decisions[decision] += 1
    except (KeyError, TypeError):
        ceo_decisions['UNKNOWN'] += 1

print("\nCEO DECISION BREAKDOWN:")
for decision, count in sorted(ceo_decisions.items(), key=lambda x: x[1], reverse=True):
    pct = (count / total_entries) * 100
    print(f"  - {decision}: {count} ({pct:.1f}%)")

print("\n" + "="*60)
print(f"System Status: {total_trades} trades in {total_entries} periods")
print(f"Trade Frequency: {(total_trades/total_entries)*100:.2f}% of all periods")
print("="*60 + "\n")

# Save results to file for Discord
with open('backtest_analysis.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total Periods: {total_entries}\n")
    f.write(f"Total Trades: {total_trades}\n")
    f.write(f"BUY Trades: {buy_trades}\n")
    f.write(f"SELL Trades: {sell_trades}\n")
    if total_trades > 0:
        f.write(f"Trade Frequency: {(total_trades/total_entries)*100:.2f}%\n")
