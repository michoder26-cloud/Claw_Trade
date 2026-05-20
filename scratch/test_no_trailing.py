import sys
import os
# Force utf-8 stdout encoding for Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, 'src')
from orchestrator import MasterOrchestrator
from backtester import Backtester, Trade
import logging

# Set logging level to warning to keep it quiet
logging.getLogger('orchestrator').setLevel(logging.WARNING)
logging.getLogger('backtester').setLevel(logging.WARNING)

# Subclass Backtester to override check_stop_levels and remove trailing stop
class NoTrailingBacktester(Backtester):
    def check_stop_levels(self, timestamp: str, current_price: float, high_price: float, low_price: float):
        closed_positions = []
        for trade in self.open_positions:
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

        for trade in closed_positions:
            self.open_positions.remove(trade)

        self.equity_curve.append(self.current_balance)
        return [t.__dict__ for t in closed_positions]

# Initialize orchestrator
orch = MasterOrchestrator(mode="BACKTEST")
orch.config.POSITION_SIZE_PERCENT = 2.0  # Safe risk

# Swap the backtester
orch.backtester = NoTrailingBacktester(initial_balance=10000.0, max_open_positions=2)

# Load data
orch.load_market_data(
    symbol="GC=F",
    start="2024-06-20",
    end="2024-12-31",
    interval="1h"
)

# Run backtest
orch.run_backtest(sample_every_n=1)

print("\n--- BACKTEST REPORT (NO TRAILING STOP) ---")
print(orch.backtester.get_report())

print("\n--- ACTUAL TRADES EXECUTED ---")
for i, t in enumerate(orch.backtester.trades, 1):
    print(f"Trade {i:2d}: {t.signal} | Entry: {t.entry_time} @ {t.entry_price:.2f} | Exit: {t.exit_time} @ {t.exit_price:.2f} | PnL: ${t.profit_loss:.2f}")
