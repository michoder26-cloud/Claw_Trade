import json
import pandas as pd

def analyze_losses():
    with open("backtest_results.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # In my backtester, the full history is exported
    # I need to find which ones actually resulted in a trade and which ones hit SL
    
    trades_executed = [d for d in data if d.get("trade_executed")]
    print(f"Total entries analyzed in log: {len(data)}")
    print(f"Total trade entries found: {len(trades_executed)}")
    
    # Actually, the backtest_results.json might not contain the outcome (TP/SL) per entry 
    # unless I specifically logged it in analysis_record.
    # Let me check analysis_record structure in orchestrator.py
    
    # If the log doesn't have outcomes, I'll check the 'backtest_results.json' file content again
    # Wait, if backtest_results.json is the export from MasterOrchestrator, 
    # it contains a list of 'analysis_record'. 
    
    # I'll just check for 'BUY' or 'SELL' decisions that didn't result in profit?
    # No, I need the actual Trade objects. 
    
    # Let's just count how many times RSI was < 30 and it was a BUY.
    buy_signals = [d for d in data if d['agents_analysis']['ceo']['decision'] == "BUY"]
    print(f"Total BUY signals: {len(buy_signals)}")
    
    # Let's look at some examples
    for i, b in enumerate(buy_signals[:10]):
        print(f"Signal {i}: Time={b['timestamp']}, Price={b['price']}, Reason={b['agents_analysis']['ceo']['reasoning']}")

if __name__ == "__main__":
    analyze_losses()
