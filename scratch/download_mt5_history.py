import sys
import os
from dotenv import load_dotenv
load_dotenv()  # Load environmental variables from .env

sys.path.insert(0, 'src')
from mt5_connector import MT5Connector
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

# Initialize and connect
conn = MT5Connector()
if not conn.connect():
    print("Failed to connect to MT5!")
    sys.exit(1)

symbol = conn.symbol
print(f"Connected to MT5. Symbol configured: {symbol}")

# We want hourly data (H1)
timeframe = mt5.TIMEFRAME_H1
# Request last 25,000 bars (covering more than 2.5 years of H1 data)
count = 25000

print(f"Requesting {count} H1 bars for {symbol}...")
rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)

if rates is None or len(rates) == 0:
    print(f"Failed to copy rates for {symbol}! Error: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

print(f"Successfully copied {len(rates)} bars.")

# Convert to DataFrame
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)

# Keep standard columns and convert names to lowercase as expected by DataHandler
df = df[['open', 'high', 'low', 'close', 'tick_volume']]
df.rename(columns={'tick_volume': 'volume'}, inplace=True)

# Save to CSV
output_file = "mt5_historical_data.csv"
df.to_csv(output_file)
print(f"Saved MT5 historical data to {output_file}!")

# Shutdown connection
mt5.shutdown()
