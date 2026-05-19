import sys
import os
sys.path.insert(0, 'src')
from orchestrator import MasterOrchestrator

# Initialize orchestrator in LIVE mode (so it has mt5 and discord set up)
orch = MasterOrchestrator(mode="LIVE")

# Mock the position that just hit SL
orch.open_positions = [{
    "ticket": 1784418694,
    "signal": "BUY",
    "entry_price": 4506.26,
    "lot_size": 3.34,
    "stop_loss": 4496.40,
    "take_profit": 4556.40,
    "confidence": 0.92,
    "regime": "RANGING",
    "quant_summary": "MMTC v2.0 Quant: Price in Market Maker All-In Zone (78.6%-88.7% Daily Retracement). RSI is oversold at 34.2.",
    "news_summary": "Macro environment is quiet with neutral USD sentiment.",
    "bull_argument": "Price reached extreme discount range, high probability bullish liquidity sweep expected.",
    "bear_argument": "Downside momentum is strong, but daily support is near.",
    "ceo_reasoning": "Approved BUY setup: MMTC v2.0 [Tier 3]: Price in Market Maker All-In Zone (all_in_market_maker) during Ranging regime. RSI (34.2) is oversold. Strong institutional liquidity sweep expected."
}]

print("Running live position monitor to process the closed trade...")
orch._monitor_live_positions()
print("Done!")
orch.mt5_connector.shutdown()
