import json

try:
    with open('backtest_results.json', 'r') as f:
        res = json.load(f)
    
    if isinstance(res, dict):
        trades = res.get('trades', [])
    else:
        trades = res
        
    print(f"Total Trades: {len(trades)}")
    
    # Print last 30 trades
    for i, t in enumerate(trades[-30:], max(1, len(trades) - 29)):
        entry_price = t.get('entry_price')
        exit_price = t.get('exit_price')
        profit_loss = t.get('profit_loss')
        size = t.get('position_size')
        sl = t.get('stop_loss')
        tp = t.get('take_profit')
        
        entry_price_str = f"{entry_price:.2f}" if entry_price is not None else "N/A"
        exit_price_str = f"{exit_price:.2f}" if exit_price is not None else "N/A"
        pnl_str = f"{profit_loss:.2f}" if profit_loss is not None else "N/A"
        size_str = f"{size:.2f}" if size is not None else "N/A"
        sl_str = f"{sl:.2f}" if sl is not None else "N/A"
        tp_str = f"{tp:.2f}" if tp is not None else "N/A"
        
        print(f"{i:4d}. {t.get('entry_time')} | {t.get('signal')} @ {entry_price_str} | "
              f"Exit: {t.get('exit_time')} @ {exit_price_str} | "
              f"PnL: {pnl_str} | Size: {size_str} | SL: {sl_str} | TP: {tp_str}")
except Exception as e:
    import traceback
    traceback.print_exc()
