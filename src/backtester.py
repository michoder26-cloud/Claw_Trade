"""Backtesting framework for multi-agent trading system"""
import pandas as pd
import numpy as np
import os
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
    trailing_trigger: float = 0.0
    trailing_lock: float = 0.0
    # Multi-Phase Trailing Stop fields
    trail_phase: str = "INITIAL"  # INITIAL, BREAKEVEN, LOCKED, TRAILING
    trail_highest: float = 0.0  # Highest price reached (for BUY trades)
    trail_lowest: float = 999999.0  # Lowest price reached (for SELL trades)
    original_sl_distance: float = 0.0  # Original SL distance for phase calculations

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
        self.total_deposited = initial_balance
        self.max_open_positions = max_open_positions
        self.trades: List[Trade] = []
        self.open_positions: List[Trade] = []
        self.equity_curve: List[float] = [initial_balance]
        self.balance_history: List[Dict] = []

    def deposit(self, amount: float):
        """Deposit funds into the account (e.g. monthly DCA)"""
        self.current_balance += amount
        self.total_deposited += amount
        self.equity_curve.append(self.current_balance)
        logger.info(f"💰 [DCA DEPOSIT]: Injected ${amount:,.2f} | Total Deposited: ${self.total_deposited:,.2f} | Current Balance: ${self.current_balance:,.2f}")

    def execute_trade(self, timestamp: str, price: float, signal: str,
                     position_size: float, stop_loss: float,
                     take_profit: float, trailing_trigger: float = 0.0,
                     trailing_lock: float = 0.0, original_sl_distance: float = 0.0) -> bool:
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
            take_profit=take_profit,
            trailing_trigger=trailing_trigger,
            trailing_lock=trailing_lock,
            original_sl_distance=original_sl_distance
        )

        self.open_positions.append(trade)
        logger.info(f"[{timestamp}] {signal} @ {price:.2f} | Size: {position_size:.2f} | SL: {stop_loss:.2f} | TP: {take_profit:.2f}")

        return True

    def check_stop_levels(self, timestamp: str, current_price: float, high_price: float, low_price: float):
        """Check if any open positions hit stop-loss or take-profit levels.
        Implements 3-phase progressive trailing stop:
        Phase 1 (BREAKEVEN): When profit >= 1.0x SL distance -> move SL to entry +/- 2
        Phase 2 (LOCKED): When profit >= 2.0x SL distance -> move SL to lock 50% of profit  
        Phase 3 (TRAILING): Progressive trail every TRAIL_STEP points
        """
        use_trailing = os.getenv("USE_TRAILING_STOP", "false").lower() == "true"
        # Read phase config from environment (with defaults)
        be_trigger_mult = float(os.getenv("TRAIL_BREAKEVEN_TRIGGER", 1.0))
        lock_trigger_mult = float(os.getenv("TRAIL_LOCK_TRIGGER", 2.0))
        trail_step = float(os.getenv("TRAIL_STEP", 10.0))

        # Legacy fallback values
        trigger_dist = float(os.getenv("TRAILING_STOP_TRIGGER", 10.0))
        lock_profit = float(os.getenv("TRAILING_STOP_LOCK", 6.0))

        closed_positions = []

        for trade in self.open_positions:
            # Skip checking stop levels for trades entered on this exact timestamp (prevent entry-exit collision)
            if trade.entry_time == timestamp:
                continue

            # Determine if this trade uses trailing stop
            trade_use_trailing = use_trailing or (trade.trailing_trigger > 0.0)

            # --- Multi-Phase Trailing Stop Logic ---
            if trade_use_trailing and trade.original_sl_distance > 0:
                sl_dist = trade.original_sl_distance
                be_threshold = sl_dist * be_trigger_mult
                lock_threshold = sl_dist * lock_trigger_mult

                if trade.signal == "BUY":
                    # Track highest price
                    if high_price > trade.trail_highest:
                        trade.trail_highest = high_price
                    unrealized = trade.trail_highest - trade.entry_price

                    # Phase 3: TRAILING (progressive trail)
                    if trade.trail_phase in ["LOCKED", "TRAILING"] and unrealized >= lock_threshold:
                        trail_sl = trade.entry_price + (unrealized - trail_step)
                        # Only move SL up, never down
                        if trail_sl > trade.stop_loss:
                            trade.stop_loss = trail_sl
                            trade.trail_phase = "TRAILING"

                    # Phase 2: LOCK 50% profit
                    if trade.trail_phase in ["BREAKEVEN", "INITIAL"] and unrealized >= lock_threshold:
                        new_sl = trade.entry_price + (unrealized * 0.5)
                        if new_sl > trade.stop_loss:
                            trade.stop_loss = new_sl
                            trade.trail_phase = "LOCKED"
                            trade.trailed = True
                            logger.info(f"   [PHASE 2 LOCK] [{timestamp}] BUY SL -> {trade.stop_loss:.2f} (locked 50% of +{unrealized:.1f})")

                    # Phase 1: BREAKEVEN
                    if trade.trail_phase == "INITIAL" and unrealized >= be_threshold:
                        new_sl = trade.entry_price + 2.0  # BE + $2 safety
                        if new_sl > trade.stop_loss:
                            trade.stop_loss = new_sl
                            trade.trail_phase = "BREAKEVEN"
                            trade.trailed = True
                            logger.info(f"   [PHASE 1 BE] [{timestamp}] BUY SL -> {trade.stop_loss:.2f} (breakeven at +{unrealized:.1f})")

                elif trade.signal == "SELL":
                    # Track lowest price
                    if low_price < trade.trail_lowest:
                        trade.trail_lowest = low_price
                    unrealized = trade.entry_price - trade.trail_lowest

                    # Phase 3: TRAILING
                    if trade.trail_phase in ["LOCKED", "TRAILING"] and unrealized >= lock_threshold:
                        trail_sl = trade.entry_price - (unrealized - trail_step)
                        if trail_sl < trade.stop_loss:
                            trade.stop_loss = trail_sl
                            trade.trail_phase = "TRAILING"

                    # Phase 2: LOCK 50%
                    if trade.trail_phase in ["BREAKEVEN", "INITIAL"] and unrealized >= lock_threshold:
                        new_sl = trade.entry_price - (unrealized * 0.5)
                        if new_sl < trade.stop_loss:
                            trade.stop_loss = new_sl
                            trade.trail_phase = "LOCKED"
                            trade.trailed = True
                            logger.info(f"   [PHASE 2 LOCK] [{timestamp}] SELL SL -> {trade.stop_loss:.2f} (locked 50% of +{unrealized:.1f})")

                    # Phase 1: BREAKEVEN
                    if trade.trail_phase == "INITIAL" and unrealized >= be_threshold:
                        new_sl = trade.entry_price - 2.0
                        if new_sl < trade.stop_loss:
                            trade.stop_loss = new_sl
                            trade.trail_phase = "BREAKEVEN"
                            trade.trailed = True
                            logger.info(f"   [PHASE 1 BE] [{timestamp}] SELL SL -> {trade.stop_loss:.2f} (breakeven at +{unrealized:.1f})")

            # --- Legacy single-phase fallback (when original_sl_distance is 0) ---
            elif trade_use_trailing and trade.original_sl_distance == 0:
                trade_trigger = trade.trailing_trigger if trade.trailing_trigger > 0.0 else trigger_dist
                trade_lock = trade.trailing_lock if trade.trailing_lock > 0.0 else lock_profit
                if not trade.trailed:
                    if trade.signal == "BUY" and (high_price - trade.entry_price) >= trade_trigger:
                        trade.stop_loss = trade.entry_price + trade_lock
                        trade.trailed = True
                    elif trade.signal == "SELL" and (trade.entry_price - low_price) >= trade_trigger:
                        trade.stop_loss = trade.entry_price - trade_lock
                        trade.trailed = True

            # --- Check SL/TP hits ---
            exit_price = None
            exit_reason = None

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
                logger.info(f"[{timestamp}] {exit_reason}: {trade.signal} closed @ {exit_price:.2f} | P&L: {trade.profit_loss:.2f} | Phase: {trade.trail_phase}")

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

        stats.net_profit = self.current_balance - self.total_deposited
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
            stats.max_drawdown = np.min(drawdown) * self.total_deposited
            stats.max_drawdown_pct = np.min(drawdown) * 100

        # Return percentage
        stats.return_pct = (stats.net_profit / self.total_deposited) * 100

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
        report += f"Total Deposited: ${self.total_deposited:,.2f}\n"
        report += f"Final Balance:   ${self.current_balance:,.2f}\n"
        report += f"Net Profit/Loss: ${stats.net_profit:,.2f} ({stats.return_pct:.2f}% of total deposited)\n\n"

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
