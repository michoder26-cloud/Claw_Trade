"""
XAU/USD Backtest: 44-day backtest (May 15, 2026 → April 1, 2026)
ไม่ต้องปรับพารามิเตอร์ - ใช้ parameters ที่มีอยู่แล้ว
"""

# -*- coding: utf-8 -*-
import sys
import os
import io

# Fix Unicode output for Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_handler import DataHandler
from backtester import Backtester, Trade
from config import BacktestConfig
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def calculate_fibonacci_levels(df: pd.DataFrame) -> dict:
    """Calculate Fibonacci support/resistance levels for the period"""
    if df.empty:
        return {}
    
    high = df['high'].max()
    low = df['low'].min()
    diff = high - low
    
    return {
        'high': high,
        'low': low,
        'fib_38': low + diff * 0.382,
        'fib_50': low + diff * 0.5,
        'fib_61': low + diff * 0.618,
    }

def generate_trading_signals(df: pd.DataFrame, rsi_oversold=30, rsi_overbought=70, ema_period=10) -> list:
    """
    Generate trading signals based on technical indicators
    Using parameters from config: RSI level, EMA period, etc.
    """
    
    signals = []
    
    for idx in range(len(df)):
        if idx < max(14, ema_period):  # Need at least 14 for RSI, more for EMA
            continue
            
        row = df.iloc[idx]
        timestamp = str(row.name)
        price = float(row['close'])
        rsi = float(row.get('rsi', 50))
        
        # Simple signal generation
        signal = "HOLD"
        confidence = 0.0
        
        # RSI-based signals
        if rsi < rsi_oversold:
            signal = "BUY"
            confidence = 0.7 + (30 - rsi) / 100 * 0.2  # Higher confidence if deeper oversold
        elif rsi > rsi_overbought:
            signal = "SELL"
            confidence = 0.7 + (rsi - 70) / 100 * 0.2  # Higher confidence if deeper overbought
        
        # Store signal
        signals.append({
            'timestamp': timestamp,
            'price': price,
            'signal': signal,
            'rsi': rsi,
            'confidence': min(confidence, 0.95),
            'macd_hist': float(row.get('macd_hist', 0)),
            'ema_5': float(row.get('ema_5', 0)),
            'sma_36': float(row.get('sma_36', 0)),
        })
    
    return signals

def run_backtest(start_date: str, end_date: str, initial_balance: float = 10000.0):
    """
    Run 44-day backtest from end_date back to start_date
    """
    
    print("\n" + "="*80)
    print("[BACKTEST] XAU/USD - 44 DAYS")
    print("="*80)
    print(f"Period: {start_date} -> {end_date}")
    print(f"Initial Balance: ${initial_balance:,.2f}")
    print("="*80 + "\n")
    
    # Fetch historical data
    print(f"Fetching XAU/USD historical data (hourly candles)...")
    try:
        df = DataHandler.prepare_for_analysis(
            symbol="GC=F",
            start=start_date,
            end=end_date,
            interval="1h"
        )
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return None
    
    if df.empty:
        print(f"❌ No data available for period {start_date} → {end_date}")
        return None
    
    print(f"OK: Fetched {len(df)} hourly candles")
    print(f"   Date range: {df.index[0]} -> {df.index[-1]}\n")
    
    # Calculate Fibonacci levels
    fib_levels = calculate_fibonacci_levels(df)
    print(f"Fibonacci Levels:")
    print(f"   High: ${fib_levels.get('high', 0):.2f}")
    print(f"   Low: ${fib_levels.get('low', 0):.2f}")
    print(f"   38.2%: ${fib_levels.get('fib_38', 0):.2f}")
    print(f"   50%: ${fib_levels.get('fib_50', 0):.2f}")
    print(f"   61.8%: ${fib_levels.get('fib_61', 0):.2f}\n")
    
    # Generate signals
    print(f"Generating trading signals...")
    signals = generate_trading_signals(df, rsi_oversold=30, rsi_overbought=70, ema_period=10)
    print(f"OK: Generated {len(signals)} signal data points\n")
    
    # Initialize backtester with fixed SL/TP
    backtester = Backtester(initial_balance=initial_balance, max_open_positions=2)
    
    print(f"Risk Management Settings:")
    print(f"   Fixed SL: $5.00")
    print(f"   Fixed TP: $10.00")
    print(f"   Position Size: 0.1 lot")
    print(f"   Max Open Positions: 2\n")
    
    print(f"TRADING LOG:\n")
    
    # Execute trades
    entry_count = 0
    for idx, signal_data in enumerate(signals):
        timestamp = signal_data['timestamp']
        price = signal_data['price']
        signal = signal_data['signal']
        
        # Get OHLC for this candle
        row = df.iloc[idx]
        high = float(row['high'])
        low = float(row['low'])
        
        # Execute signal
        if signal in ["BUY", "SELL"]:
            # Fixed SL/TP
            sl = 5.0
            tp = 10.0
            
            if signal == "BUY":
                stop_loss = price - sl
                take_profit = price + tp
            else:  # SELL
                stop_loss = price + sl
                take_profit = price - tp
            
            executed = backtester.execute_trade(
                timestamp=timestamp,
                price=price,
                signal=signal,
                position_size=0.1,  # Fixed lot size
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if executed:
                entry_count += 1
                print(f"[Entry #{entry_count}] {timestamp} | {signal} @ ${price:.2f} | SL=${stop_loss:.2f} | TP=${take_profit:.2f}")
        
        # Check stop-loss / take-profit levels
        backtester.check_stop_levels(timestamp, price, high, low)
    
    # Close any remaining open positions
    if backtester.open_positions:
        print(f"\nClosing {len(backtester.open_positions)} open position(s) at market close...")
        final_price = float(df.iloc[-1]['close'])
        backtester.close_all_positions(str(df.index[-1]), final_price)
    
    # Print report
    report = backtester.get_report()
    print(report)
    
    # Calculate detailed stats
    stats = backtester.calculate_stats()
    
    print("\n" + "="*80)
    print("DETAILED BACKTEST RESULTS")
    print("="*80)
    print(f"\nTrade Summary:")
    print(f"  Total Trades: {stats.total_trades}")
    print(f"  Buy Trades: {stats.buy_trades}")
    print(f"  Sell Trades: {stats.sell_trades}")
    print(f"  Winning Trades: {stats.winning_trades}")
    print(f"  Losing Trades: {stats.losing_trades}")
    print(f"  Win Rate: {stats.win_rate:.2f}%")
    
    print(f"\nProfit & Loss:")
    print(f"  Gross Profit: ${stats.gross_profit:,.2f}")
    print(f"  Gross Loss: ${stats.gross_loss:,.2f}")
    print(f"  Net Profit/Loss: ${stats.net_profit:,.2f}")
    print(f"  Return %: {stats.return_pct:.2f}%")
    print(f"  Avg Profit per Trade: ${stats.avg_profit_per_trade:,.2f}")
    
    print(f"\nRisk Metrics:")
    print(f"  Max Drawdown: ${stats.max_drawdown:,.2f} ({stats.max_drawdown_pct:.2f}%)")
    print(f"  Profit Factor: {stats.profit_factor:.2f}")
    print(f"  Sharpe Ratio: {stats.sharpe_ratio:.2f}")
    
    print(f"\nAccount:")
    print(f"  Initial Balance: ${backtester.initial_balance:,.2f}")
    print(f"  Final Balance: ${backtester.current_balance:,.2f}")
    
    print("\n" + "="*80 + "\n")
    
    # Save results to JSON
    results = {
        "backtest_period": {
            "start_date": start_date,
            "end_date": end_date,
            "duration_days": 44,
        },
        "account": {
            "initial_balance": backtester.initial_balance,
            "final_balance": backtester.current_balance,
            "net_profit": stats.net_profit,
            "return_pct": stats.return_pct,
        },
        "trade_statistics": {
            "total_trades": stats.total_trades,
            "winning_trades": stats.winning_trades,
            "losing_trades": stats.losing_trades,
            "buy_trades": stats.buy_trades,
            "sell_trades": stats.sell_trades,
            "win_rate_pct": stats.win_rate,
        },
        "performance_metrics": {
            "gross_profit": stats.gross_profit,
            "gross_loss": stats.gross_loss,
            "avg_profit_per_trade": stats.avg_profit_per_trade,
            "profit_factor": stats.profit_factor,
        },
        "risk_metrics": {
            "max_drawdown_usd": stats.max_drawdown,
            "max_drawdown_pct": stats.max_drawdown_pct,
            "sharpe_ratio": stats.sharpe_ratio,
        },
        "trades": [
            {
                "entry_time": trade.entry_time,
                "exit_time": trade.exit_time,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "signal": trade.signal,
                "position_size": trade.position_size,
                "profit_loss": trade.profit_loss,
                "profit_loss_pct": trade.profit_loss_pct,
                "status": trade.status,
            }
            for trade in backtester.trades
        ]
    }
    
    # Save to file
    output_file = "backtest_44days_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"OK: Results saved to {output_file}\n")
    
    return results

if __name__ == "__main__":
    # 44 days from May 15, 2026 backwards to April 1, 2026
    end_date = "2026-05-15"      # Today (ตามโจทย์)
    start_date = "2026-04-01"    # 44 days ago
    
    results = run_backtest(start_date=start_date, end_date=end_date, initial_balance=10000.0)
    
    if results:
        print("OK: Backtest completed successfully!")
    else:
        print("ERROR: Backtest failed")
        sys.exit(1)
