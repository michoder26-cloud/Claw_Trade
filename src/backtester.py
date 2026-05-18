"""Backtesting framework for multi-agent trading system"""
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Trade:
    """Represents a single trade"""
    entry_time: str
    exit_time: str = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    signal: str = ""  # BUY or SELL
    position_size: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    profit_loss: float = 0.0
    profit_loss_pct: float = 0.0
    status: str = "OPEN"  # OPEN, CLOSED, STOPPED_OUT, TAKE_PROFIT
    trailed: bool = False

    def close(self, exit_price: float, exit_time: str, contract_size: float = 100.0):
        """Close the trade"""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.status = "CLOSED"

        if self.signal == "BUY":
            self.profit_loss = (exit_price - self.entry_price) * self.position_size * contract_size
        else:  # SELL
            self.profit_loss = (self.entry_price - exit_price) * self.position_size * contract_size

        self.profit_loss_pct = (self.profit_loss / (self.entry_price * self.position_size * contract_size)) * 100 if self.entry_price > 0 else 0

@dataclass
class BacktestStats:
    """Backtesting statistics"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_profit_per_trade: float = 0.0
    sharpe_ratio: float = 0.0
    return_pct: float = 0.0
    buy_trades: int = 0
    sell_trades: int = 0

class Backtester:
    """Simulates trading based on agent signals"""

    def __init__(self, initial_balance: float, max_open_positions: int = 2):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.max_open_positions = max_open_positions
        self.trades: List[Trade] = []
        self.open_positions: List[Trade] = []
        self.equity_curve: List[float] = [initial_balance]
        self.balance_history: List[Dict] = []

    def execute_trade(self, timestamp: str, price: float, signal: str,
                     position_size: float, stop_loss: float,
                     take_profit: float) -> bool:
        """
        Execute a trade signal

        Returns:
            True if trade was executed, False if rejected
        """
        if signal == "HOLD":
            return False

        # Check max open positions
        if signal in ["BUY", "SELL"] and len(self.open_positions) >= self.max_open_positions:
            logger.warning(f"Max open positions ({self.max_open_positions}) reached. Trade rejected.")
            return False

        # Check if we have enough balance
        required_margin = price * position_size * 0.02  # 2% margin
        if required_margin > self.current_balance:
            logger.warning(f"Insufficient balance for trade. Required: {required_margin:.2f}, Available: {self.current_balance:.2f}")
            return False

        trade = Trade(
            entry_time=timestamp,
            entry_price=price,
            signal=signal,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        self.open_positions.append(trade)
        logger.info(f"[{timestamp}] {signal} @ {price:.2f} | Size: {position_size:.2f} | SL: {stop_loss:.2f} | TP: {take_profit:.2f}")

        return True

    def check_stop_levels(self, timestamp: str, current_price: float, high_price: float, low_price: float):
        """Check if any open positions hit stop-loss or take-profit levels"""

        closed_positions = []

        for trade in self.open_positions:
            # 1. Update Trailing Stop / Breakeven Logic FIRST: If profit conditions met, move SL to entry + $6 (lock massive profit)
            if not trade.trailed:
                if trade.signal == "BUY" and (high_price - trade.entry_price) >= 10.0:
                    trade.stop_loss = trade.entry_price + 6.0
                    trade.trailed = True
                    logger.info(f"   🛡️ [{timestamp}] Trailing Stop Active: BUY SL moved to {trade.stop_loss:.2f} (Locked +$6)")
                elif trade.signal == "SELL" and (trade.entry_price - low_price) >= 10.0:
                    trade.stop_loss = trade.entry_price - 6.0
                    trade.trailed = True
                    logger.info(f"   🛡️ [{timestamp}] Trailing Stop Active: SELL SL moved to {trade.stop_loss:.2f} (Locked +$6)")

            exit_price = None
            exit_reason = None

            # 2. Check if open positions hit stop-loss or take-profit levels using the UPDATED stop_loss
            if trade.signal == "BUY":
                if low_price <= trade.stop_loss:
                    exit_price = trade.stop_loss
                    exit_reason = "STOP_LOSS"
                elif high_price >= trade.take_profit:
                    exit_price = trade.take_profit
                    exit_reason = "TAKE_PROFIT"

            elif trade.signal == "SELL":
                if high_price >= trade.stop_loss:
                    exit_price = trade.stop_loss
                    exit_reason = "STOP_LOSS"
                elif low_price <= trade.take_profit:
                    exit_price = trade.take_profit
                    exit_reason = "TAKE_PROFIT"

            if exit_price:
                trade.close(exit_price, timestamp)
                self.current_balance += trade.profit_loss
                closed_positions.append(trade)
                self.trades.append(trade)
                logger.info(f"[{timestamp}] {exit_reason}: {trade.signal} closed @ {exit_price:.2f} | P&L: {trade.profit_loss:.2f}")

        # Remove closed positions
        for trade in closed_positions:
            self.open_positions.remove(trade)

        self.equity_curve.append(self.current_balance)
        return [t.__dict__ for t in closed_positions]

    def close_all_positions(self, timestamp: str, current_price: float):
        """Force close all open positions at market price"""
        for trade in self.open_positions[:]:
            trade.close(current_price, timestamp)
            self.current_balance += trade.profit_loss
            self.trades.append(trade)
            self.open_positions.remove(trade)

    def calculate_stats(self) -> BacktestStats:
        """Calculate comprehensive trading statistics"""

        if not self.trades:
            return BacktestStats()

        stats = BacktestStats()
        stats.total_trades = len(self.trades)

        # Count trade types
        for trade in self.trades:
            if trade.signal == "BUY":
                stats.buy_trades += 1
            elif trade.signal == "SELL":
                stats.sell_trades += 1

        # Profitability metrics
        for trade in self.trades:
            if trade.profit_loss > 0:
                stats.winning_trades += 1
                stats.gross_profit += trade.profit_loss
            elif trade.profit_loss < 0:
                stats.losing_trades += 1
                stats.gross_loss += abs(trade.profit_loss)

        stats.net_profit = self.current_balance - self.initial_balance
        stats.win_rate = (stats.winning_trades / stats.total_trades * 100) if stats.total_trades > 0 else 0
        stats.avg_profit_per_trade = stats.net_profit / stats.total_trades if stats.total_trades > 0 else 0

        # Profit factor
        if stats.gross_loss > 0:
            stats.profit_factor = stats.gross_profit / stats.gross_loss
        else:
            stats.profit_factor = float('inf') if stats.gross_profit > 0 else 0

        # Max drawdown
        if self.equity_curve:
            running_max = np.maximum.accumulate(self.equity_curve)
            drawdown = (np.array(self.equity_curve) - running_max) / running_max
            stats.max_drawdown = np.min(drawdown) * self.initial_balance
            stats.max_drawdown_pct = np.min(drawdown) * 100

        # Return percentage
        stats.return_pct = (stats.net_profit / self.initial_balance) * 100

        # Sharpe Ratio (simplified - daily returns)
        if len(self.equity_curve) > 1:
            returns = np.diff(self.equity_curve) / self.equity_curve[:-1]
            if np.std(returns) > 0:
                stats.sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252)

        return stats

    def get_report(self) -> str:
        """Generate trading report"""
        stats = self.calculate_stats()

        report = "\n" + "="*60
        report += "\n📊 BACKTESTING REPORT\n"
        report += "="*60 + "\n"

        report += f"Initial Balance: ${self.initial_balance:,.2f}\n"
        report += f"Final Balance: ${self.current_balance:,.2f}\n"
        report += f"Net Profit/Loss: ${stats.net_profit:,.2f} ({stats.return_pct:.2f}%)\n\n"

        report += "TRADE STATISTICS:\n"
        report += f"Total Trades: {stats.total_trades}\n"
        report += f"  - Buy Trades: {stats.buy_trades}\n"
        report += f"  - Sell Trades: {stats.sell_trades}\n"
        report += f"Winning Trades: {stats.winning_trades}\n"
        report += f"Losing Trades: {stats.losing_trades}\n"
        report += f"Win Rate: {stats.win_rate:.2f}%\n"
        report += f"Profit Factor: {stats.profit_factor:.2f}\n\n"

        report += "PERFORMANCE METRICS:\n"
        report += f"Gross Profit: ${stats.gross_profit:,.2f}\n"
        report += f"Gross Loss: ${stats.gross_loss:,.2f}\n"
        report += f"Average P&L per Trade: ${stats.avg_profit_per_trade:,.2f}\n"
        report += f"Max Drawdown: ${stats.max_drawdown:,.2f} ({stats.max_drawdown_pct:.2f}%)\n"
        report += f"Sharpe Ratio: {stats.sharpe_ratio:.2f}\n"

        if self.open_positions:
            report += f"\n⚠️ OPEN POSITIONS: {len(self.open_positions)}\n"

        report += "\n" + "="*60 + "\n"

        return report
