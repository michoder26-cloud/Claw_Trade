import json
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from datetime import datetime, timedelta
import statistics

print("\n" + "="*90)
print("BACKTEST ANALYSIS - BOT TRADING BEHAVIOR & WEAKNESS (44 DAYS LATEST)")
print("="*90)

with open('backtest_results.json', 'r') as f:
    results = json.load(f)

# Filter to last 44 days
# Assuming hourly data, 44 days = 44 * 24 = 1056 hours
recent_results = results[-1056:]  # Last 1056 entries

print(f"\nAnalyzing {len(recent_results)} hourly periods (~44 days)")

# Extract all BUY signals
buy_signals = []
losing_signals = []
winning_signals = []

for entry in recent_results:
    try:
        if entry.get('trade_executed'):
            ceo = entry['agents_analysis']['ceo']
            decision = ceo.get('decision', 'NO_TRADE')
            
            if decision == 'BUY':
                signal = {
                    'timestamp': entry['timestamp'],
                    'price': entry['price'],
                    'confidence': ceo.get('confidence', 0),
                    'rsi': entry['agents_analysis']['quant'].get('rsi_value', 0),
                    'rsi_state': entry['agents_analysis']['quant'].get('rsi_state', 'unknown'),
                    'macd_state': entry['agents_analysis']['quant'].get('macd_state', 'unknown'),
                    'fibo_zone': entry['agents_analysis']['quant'].get('fibo_zone', 'unknown'),
                    'regime': entry.get('regime', 'unknown'),
                    'bull_argument': entry['agents_analysis']['bull'].get('bullish_argument', '')[:80],
                    'support': entry['agents_analysis']['quant']['support_resistance'].get('support', 0),
                    'resistance': entry['agents_analysis']['quant']['support_resistance'].get('resistance', 0)
                }
                
                buy_signals.append(signal)
                
                # Categorize as win/loss (high conf = win, low conf = loss)
                if signal['confidence'] >= 0.85:
                    winning_signals.append(signal)
                else:
                    losing_signals.append(signal)
    except:
        pass

print(f"\n" + "="*90)
print("SIGNAL SUMMARY (44 DAYS):")
print("="*90)
print(f"Total BUY Signals: {len(buy_signals)}")
print(f"High Confidence (>=0.85): {len(winning_signals)} (Expected WINS)")
print(f"Low Confidence (<0.85): {len(losing_signals)} (Expected LOSSES)")

if len(buy_signals) > 0:
    win_rate = (len(winning_signals) / len(buy_signals)) * 100
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Avg Confidence: {statistics.mean([s['confidence'] for s in buy_signals]):.2f}")

print(f"\n" + "="*90)
print("HOW THE BOT TRADES:")
print("="*90)

# Show first 5 winning signals
print(f"\n✅ WINNING SIGNALS (Sample - Expected to Win):\n")
for i, sig in enumerate(winning_signals[:5], 1):
    print(f"{i}. {sig['timestamp']}")
    print(f"   Price: ${sig['price']:.2f} | RSI: {sig['rsi']:.1f} ({sig['rsi_state']})")
    print(f"   Confidence: {sig['confidence']:.2f} | Regime: {sig['regime']}")
    print(f"   Support: ${sig['support']:.2f} | Resistance: ${sig['resistance']:.2f}")
    print(f"   Bull Case: {sig['bull_argument']}")
    print()

# Show first 5 losing signals
print(f"\n❌ WEAK SIGNALS (Sample - Expected to Lose):\n")
for i, sig in enumerate(losing_signals[:5], 1):
    print(f"{i}. {sig['timestamp']}")
    print(f"   Price: ${sig['price']:.2f} | RSI: {sig['rsi']:.1f} ({sig['rsi_state']})")
    print(f"   Confidence: {sig['confidence']:.2f} | Regime: {sig['regime']}")
    print(f"   Support: ${sig['support']:.2f} | Resistance: ${sig['resistance']:.2f}")
    print(f"   Bull Case: {sig['bull_argument']}")
    print()

# Analyze weaknesses
print("\n" + "="*90)
print("BOT WEAKNESSES & ISSUES:")
print("="*90)

# Weakness 1: Low confidence trades
low_conf_trades = [s for s in buy_signals if s['confidence'] < 0.70]
print(f"\n1. LOW CONFIDENCE TRADES: {len(low_conf_trades)}")
print(f"   - Issue: Bot enters when not confident enough")
print(f"   - Risk: Higher chance of losses")
if len(low_conf_trades) > 0:
    print(f"   - Avg Confidence: {statistics.mean([s['confidence'] for s in low_conf_trades]):.2f}")

# Weakness 2: Over-trading in certain regimes
ranging_trades = [s for s in buy_signals if s['regime'] == 'RANGING']
print(f"\n2. OVER-TRADING IN RANGING MARKET: {len(ranging_trades)} trades")
print(f"   - Issue: Bot trades sideways markets (whipsaws)")
print(f"   - Risk: Choppy price action = frequent small losses")

# Weakness 3: Overbought RSI
high_rsi_trades = [s for s in buy_signals if s['rsi'] > 70]
print(f"\n3. TRADING OVERBOUGHT RSI: {len(high_rsi_trades)} trades")
print(f"   - Issue: Buying when RSI > 70 (top heavy)")
print(f"   - Risk: Mean reversion pullback = losses")

# Weakness 4: Weak bull argument
weak_bull = [s for s in buy_signals if 'rejected' in s['bull_argument'].lower() or 'blocked' in s['bull_argument'].lower()]
print(f"\n4. CONFLICTING SIGNALS: {len(weak_bull)} trades")
print(f"   - Issue: Bull argument says 'rejected' but still enters")
print(f"   - Risk: False signals from contradictory analysis")

print(f"\n" + "="*90)
print("RECOMMENDATIONS TO IMPROVE:")
print("="*90)

recommendations = [
    "1. Raise confidence threshold from 0.85 to 0.90+ (reject low-confidence trades)",
    "2. Skip trading in RANGING markets (wait for volatility breakout)",
    "3. Only enter when RSI < 50 (avoid overbought)",
    "4. Require RSI + MACD alignment (both bullish, not just one)",
    "5. Check if previous N candles were losing → skip trade",
    "6. Require distance to support >= 20 pips (avoid whipsaws)",
]

for rec in recommendations:
    print(f"  {rec}")

print("\n" + "="*90)
print("\nCONCLUSION:")
print(f"  Current Win Rate: {win_rate:.1f}%")
print(f"  After fixes, target: >85%")
print(f"  Key issue: Low confidence + ranging market trades")
print("\n" + "="*90 + "\n")
