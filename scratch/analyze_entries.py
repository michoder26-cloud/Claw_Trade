import sys
from pathlib import Path
import os
import json
import io

# Fix encoding on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add src path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    print("Analyzing executed entries from backtest_results.json...")
    
    results_path = Path("backtest_results.json")
    if not results_path.exists():
        print("Error: backtest_results.json not found! Please run the backtest first.")
        return
        
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # We want to inspect quant analyst metrics for executed trades
    executed_trades = []
    for item in data:
        if item.get("trade_executed", False):
            executed_trades.append(item)
            
    print(f"\nFound {len(executed_trades)} executed trades to analyze:")
    print("="*100)
    
    for i, item in enumerate(executed_trades, 1):
        ts = item.get("timestamp")
        price = item.get("price")
        regime = item.get("regime")
        ceo = item.get("agents_analysis", {}).get("ceo", {})
        quant = item.get("agents_analysis", {}).get("quant", {})
        
        print(f"TRADE #{i} | {ts} | PRICE: {price} | DECISION: {ceo.get('decision')} | CONFIDENCE: {ceo.get('confidence')}")
        print(f"  Regime: {regime} | Fibo Zone: {quant.get('fibo_zone')}")
        print(f"  RSI: {quant.get('rsi_value'):.2f} | MACD State: {quant.get('macd_state')} | MACD Cross: {quant.get('macd_cross')}")
        print(f"  EMA 50: {quant.get('ema_50'):.2f} | EMA 200: {quant.get('ema_200'):.2f} | Intraday Trend: {quant.get('trend')}")
        print(f"  BB Upper: {quant.get('bb_upper'):.2f} | BB Lower: {quant.get('bb_lower'):.2f}")
        print("-" * 100)

if __name__ == "__main__":
    main()
