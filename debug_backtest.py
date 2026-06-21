
import sys
sys.path.insert(0, '/root/Claw_Trade')
sys.path.insert(0, '/root/Claw_Trade/src')
import os
os.environ["USE_MOCK_AI"] = "true"

from orchestrator import MasterOrchestrator
import pandas as pd

def main():
    orch = MasterOrchestrator(mode="BACKTEST")
    orch.load_market_data(symbol="GC=F", start="2025-01-01", end="2026-06-19", interval="1h")
    
    idx = 282
    timestamp = orch.market_data.index[idx]
    row = orch.market_data.iloc[idx]
    
    daily_data = orch.market_data[:timestamp].tail(1200)
    hourly_data = orch.market_data[:timestamp].tail(50)
    market_context = orch.data_handler.format_market_context(hourly_data, n_candles=10)
    regime = orch._determine_regime(daily_data)
    fib_levels = orch._calculate_fibonacci_levels(daily_data)
    fibo_circle_zone = orch._calculate_fibonacci_circles(daily_data, row['close'])
    
    d1_open, d1_high, d1_low, d1_close = row['open'], row['high'], row['low'], row['close']
    d1_upper_wick = d1_high - d1_close
    d1_lower_wick = d1_open - d1_low
    local_support = row['low']
    local_resistance = row['high']
    
    indicators = {
        "close": row["close"],
        "open": row["open"],
        "rsi": row.get("rsi", 50.0),
        "macd": row.get("macd", 0.0),
        "macd_signal": row.get("macd_signal", 0.0),
        "macd_cross": "neutral",
        "fibo_zone": "neutral",
        "fibo_circle_zone": fibo_circle_zone,
        "ema_5": row.get("ema_5", row["close"]),
        "sma_36": row.get("sma_36", row["close"]),
        "bb_upper": row.get("bb_upper", row["close"]),
        "bb_lower": row.get("bb_lower", row["close"]),
        "ema_50": row.get("ema_50", row["close"]),
        "ema_200": row.get("ema_200", row["close"]),
        "ema_macro": row.get("ema_macro", row["close"]),
        "fib_levels": fib_levels,
        "hour": timestamp.hour,
        "d1_upper_wick": d1_upper_wick,
        "d1_lower_wick": d1_lower_wick,
        "local_support": local_support,
        "local_resistance": local_resistance
    }
    
    quant_res = orch.quant_analyst.analyze(market_context, indicators)
    news_res = orch.news_analyst.analyze()
    
    print("fibo_circle_zone calculated on host:", fibo_circle_zone)
    print("quant_res['fibo_circle_zone']:", quant_res.get('fibo_circle_zone'))
    print("quant_res:", quant_res)

if __name__ == '__main__':
    main()
