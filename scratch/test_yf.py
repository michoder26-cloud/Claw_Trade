import yfinance as yf
import pandas as pd
from datetime import datetime

symbol = "GC=F"
start = "2026-03-02"
end = "2026-05-14"

print(f"Fetching {symbol} from {start} to {end}...")
data = yf.download(symbol, start=start, end=end, interval="1h")
print(f"Fetched {len(data)} candles.")
if not data.empty:
    print(data.tail())
