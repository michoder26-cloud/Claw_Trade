"""Master Orchestrator - Coordinates all agents and trading execution"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
from concurrent.futures import ThreadPoolExecutor
import time
import os

from config import Config, BacktestConfig
from data_handler import DataHandler
from agents import QuantAnalyst, NewsAnalyst, BullAgent, BearAgent, CEOAgent, RiskCriticAgent
from backtester import Backtester
from mt5_connector import MT5Connector
from discord_reporter import DiscordReporter
from risk_manager import RiskManager, AdaptivePositionSizer
from trade_journal import TradeJournal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MasterOrchestrator:
    """Master trading orchestrator - Coordinates the new hierarchical 5-Agent pipeline"""

    def __init__(self, mode: str = "BACKTEST"):
        self.mode = mode
        if mode == "BACKTEST":
            self.config = BacktestConfig
            os.environ["USE_MOCK_AI"] = "true"
        else:
            self.config = Config
            # Ensure live/paper trading respects environment variable
            if "USE_MOCK_AI" in os.environ and os.environ["USE_MOCK_AI"] == "true" and os.getenv("USE_MOCK_AI_LIVE", "false").lower() != "true":
                os.environ["USE_MOCK_AI"] = "false"

        # Initialize the new hierarchical 5-Agent group
        self.quant_analyst = QuantAnalyst()
        self.news_analyst = NewsAnalyst()
        self.bull_agent = BullAgent()
        self.bear_agent = BearAgent()
        self.ceo_agent = CEOAgent()

        # ─── RISK & JOURNAL SUBSYSTEMS ───
        # All are wrapped in try/except so a failure in one subsystem never
        # prevents the orchestrator from starting. Each defaults to a safe
        # no-op-ish state when its feature flag is off or construction fails.
        # TradeJournal (in-memory ring buffer; SQLite DB optional)
        try:
            journal_db = None
            if getattr(self.config, "TRADE_JOURNAL_ENABLED", True):
                try:
                    from learning_engine import get_db
                    journal_db = get_db()
                except Exception:
                    journal_db = None
            self.trade_journal = TradeJournal(db=journal_db)
        except Exception as e:
            logger.warning(f"TradeJournal init failed (using lightweight fallback): {e}")
            self.trade_journal = TradeJournal(db=None)

        # RiskManager (kill switch + cooldown)
        try:
            self.risk_manager = RiskManager(
                journal=self.trade_journal,
                daily_loss_limit=getattr(self.config, "DAILY_LOSS_LIMIT", -100.0),
                cooldown_loss_threshold=getattr(self.config, "COOLDOWN_LOSS_THRESHOLD", 2),
                cooldown_base_hours=getattr(self.config, "COOLDOWN_BASE_HOURS", 2.0),
                cooldown_max_hours=getattr(self.config, "COOLDOWN_MAX_HOURS", 8.0),
            )
        except Exception as e:
            logger.warning(f"RiskManager init failed (using safe fallback): {e}")
            self.risk_manager = RiskManager(journal=None)

        # AdaptivePositionSizer (confidence/regime/streak/trajectory/critic)
        try:
            self.position_sizer = AdaptivePositionSizer(
                journal=self.trade_journal,
                optimizer=None,  # LearningOptimizer can be wired later
                max_risk_per_trade_pct=getattr(self.config, "MAX_RISK_PER_TRADE_PCT", 25.0),
            )
        except Exception as e:
            logger.warning(f"AdaptivePositionSizer init failed (using safe fallback): {e}")
            self.position_sizer = AdaptivePositionSizer(journal=None)

        # RiskCriticAgent (pre-trade adversarial review)
        try:
            self.risk_critic = RiskCriticAgent()
        except Exception as e:
            logger.warning(f"RiskCriticAgent init failed (review disabled): {e}")
            self.risk_critic = None

        if mode == "BACKTEST":
            # Initialize Backtester component
            self.backtester = Backtester(
                initial_balance=self.config.INITIAL_BALANCE,
                max_open_positions=self.config.MAX_OPEN_POSITIONS
            )

        # Data handler
        self.data_handler = DataHandler()

        # Initialize MT5 Connector (supports native + mt5linux Docker)
        self.mt5_connector = MT5Connector()

        # Initialize Discord Reporter
        self.discord_reporter = DiscordReporter()

        # Market data
        self.market_data: Optional[pd.DataFrame] = None
        self.analysis_history: List[Dict] = []
        
        # Learning Memory (Stores lessons from past trades)
        self.learning_memory: List[str] = []
        self.trades_today = 0
        self.last_trade_date: Optional[str] = None

        self.open_positions: List[Dict] = []
        self.last_trade_timestamp: Optional[str] = None
        if self.mode == "LIVE":
            self._load_live_positions()
            self._load_live_state()

        logger.info(f"Hierarchical Orchestrator initialized in {mode} mode")

    def _load_live_positions(self):
        """Loads open live positions from live_positions.json"""
        try:
            import json
            if os.path.exists("live_positions.json"):
                with open("live_positions.json", "r", encoding="utf-8") as f:
                    self.open_positions = json.load(f)
                logger.info(f"💾 Loaded {len(self.open_positions)} active positions from live_positions.json")
        except Exception as e:
            logger.error(f"Failed to load live_positions.json: {e}")

    def _save_live_positions(self):
        """Saves current open live positions to live_positions.json"""
        try:
            import json
            with open("live_positions.json", "w", encoding="utf-8") as f:
                json.dump(self.open_positions, f, indent=2, default=str)
            logger.info(f"💾 Saved {len(self.open_positions)} active positions to live_positions.json")
        except Exception as e:
            logger.error(f"Failed to save live_positions.json: {e}")

    def _load_live_state(self):
        """Loads live state parameters from live_state.json to persist across restarts"""
        try:
            import json
            if os.path.exists("live_state.json"):
                with open("live_state.json", "r", encoding="utf-8") as f:
                    state = json.load(f)
                    self.trades_today = state.get("trades_today", 0)
                    self.last_trade_date = state.get("last_trade_date", None)
                    self.last_trade_timestamp = state.get("last_trade_timestamp", None)
                    # Restore risk manager / journal state (fail-safe if absent)
                    try:
                        rm_state = state.get("risk_manager_state")
                        if rm_state and hasattr(self, "risk_manager"):
                            self.risk_manager.import_state(rm_state)
                    except Exception:
                        pass
                    try:
                        tj_state = state.get("trade_journal_state")
                        if tj_state and hasattr(self, "trade_journal"):
                            self.trade_journal.consecutive_losses = int(tj_state.get("consecutive_losses", 0))
                            self.trade_journal.consecutive_wins = int(tj_state.get("consecutive_wins", 0))
                            self.trade_journal.daily_pnl = dict(tj_state.get("daily_pnl", {}))
                    except Exception:
                        pass
                logger.info(f"💾 Loaded live state: trades_today={self.trades_today}, last_trade_date={self.last_trade_date}, last_trade_timestamp={self.last_trade_timestamp}")
        except Exception as e:
            logger.error(f"Failed to load live_state.json: {e}")

    def _save_live_state(self):
        """Saves current live state parameters to live_state.json"""
        try:
            import json
            state = {
                "trades_today": self.trades_today,
                "last_trade_date": self.last_trade_date,
                "last_trade_timestamp": self.last_trade_timestamp,
            }
            # Persist risk manager + journal state (fail-safe if absent)
            try:
                state["risk_manager_state"] = self.risk_manager.export_state()
            except Exception:
                pass
            try:
                state["trade_journal_state"] = {
                    "consecutive_losses": self.trade_journal.consecutive_losses,
                    "consecutive_wins": self.trade_journal.consecutive_wins,
                    "daily_pnl": self.trade_journal.daily_pnl,
                }
            except Exception:
                pass
            with open("live_state.json", "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            logger.info("💾 Saved live state to live_state.json")
        except Exception as e:
            logger.error(f"Failed to save live_state.json: {e}")

    def load_market_data(self, symbol: str = "GC=F", start: str = None, end: str = None, interval: str = None) -> pd.DataFrame:
        """Load and prepare market data with 30-day indicator warmup buffer"""
        logger.info(f"Loading market data with interval: {interval}...")
        fetch_start = start
        if start:
            try:
                fetch_start = (pd.to_datetime(start) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
            except Exception:
                fetch_start = start

        if not interval:
            interval = os.getenv("YFINANCE_INTERVAL", "5m")
        try:
            self.market_data = self.data_handler.prepare_for_analysis(symbol, fetch_start, end, interval=interval)
        except Exception as e:
            logger.warning(f"Failed to fetch {interval} data (likely Yahoo Finance 60-day limit): {e}. Falling back to 1h interval.")
            interval = "1h"
            self.market_data = self.data_handler.prepare_for_analysis(symbol, fetch_start, end, interval=interval)
        
        self.interval = interval
        
        # Calculate EMA 50, 200 & macro across the full warmup buffer
        self.market_data['ema_50'] = self.market_data['close'].ewm(span=50, adjust=False).mean()
        self.market_data['ema_200'] = self.market_data['close'].ewm(span=200, adjust=False).mean()
        self.market_data['ema_macro'] = self.market_data['close'].ewm(span=288, adjust=False).mean() # 12-day Daily Macro Trend Filter
        
        # Slice to requested start date
        if start and not self.market_data.empty:
            try:
                self.market_data = self.market_data.loc[start:]
            except Exception:
                pass
        
        logger.info(f"Loaded {len(self.market_data)} candles with technical extensions.")
        return self.market_data

    def _determine_regime(self, recent_data: pd.DataFrame) -> str:
        """Deterministically determine market regime in Python to protect winrate"""
        if len(recent_data) < 20:
            return "TRENDING"
            
        latest = recent_data.iloc[-1]
        
        # 1. Volatility check (using ATR percentile)
        atr_value = latest.get("atr", 2.0)
        atr_series = recent_data["atr"].dropna()
        if len(atr_series) > 10:
            atr_percentile = (atr_series < atr_value).mean()
            if atr_percentile > 0.80:
                return "HIGH_VOLATILITY"

        # 2. Liquidity / Volume check
        volume = latest.get("volume", 1000)
        avg_volume = recent_data["volume"].tail(20).mean()
        if avg_volume > 0 and (volume / avg_volume) < 0.35:
            return "LOW_LIQUIDITY"

        # 3. Trending vs Ranging check (using EMA 50/200 distance and slope)
        ema_50 = latest.get("ema_50", latest["close"])
        ema_200 = latest.get("ema_200", latest["close"])
        ema_diff = abs(ema_50 - ema_200) / ema_200
        
        if ema_diff > 0.015:
            return "TRENDING"
        else:
            return "RANGING"

    def _detect_market_structure(self, df: pd.DataFrame) -> tuple:
        """Detect the most recent major structural Swing High and Swing Low."""
        highs = df['high'].values
        lows = df['low'].values
        
        swing_highs = []
        swing_lows = []
        
        # 5-bar fractal detection
        for i in range(2, len(df) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                swing_highs.append((i, highs[i]))
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                swing_lows.append((i, lows[i]))
                
        if not swing_highs or not swing_lows:
            return df['high'].max(), df['low'].min()
            
        # Focus on the most recent structural swings (e.g., last 200 bars)
        recent_sh = [s for s in swing_highs if s[0] > len(df) - 200]
        recent_sl = [s for s in swing_lows if s[0] > len(df) - 200]
        
        if not recent_sh or not recent_sl:
            return df['high'].max(), df['low'].min()
            
        max_sh = max(recent_sh, key=lambda x: x[1])
        min_sl = min(recent_sl, key=lambda x: x[1])
        
        # We need to draw Left to Right. 
        # If Bullish (Low happened before High), anchor from Low to High.
        # If Bearish (High happened before Low), anchor from High to Low.
        # Returning absolute values is fine, we just need the levels.
        return max_sh[1], min_sl[1]

    def _calculate_fibonacci_levels(self, recent_data: pd.DataFrame) -> Dict[str, float]:
        """Calculate structural Fibonacci Retracement levels (Wick to Wick)"""
        if len(recent_data) < 50:
            return {}
            
        high, low = self._detect_market_structure(recent_data)
        diff = high - low
        
        if diff == 0:
            return {}
        
        return {
            "0.0% (High)": round(high, 2),
            "23.6%": round(high - 0.236 * diff, 2),
            "38.2%": round(high - 0.382 * diff, 2),
            "50.0%": round(high - 0.5 * diff, 2),
            "61.8%": round(high - 0.618 * diff, 2),
            "78.6%": round(high - 0.786 * diff, 2),
            "88.7%": round(high - 0.887 * diff, 2),
            "100.0% (Low)": round(low, 2)
        }

    def _calculate_fibonacci_circles(self, recent_data: pd.DataFrame, current_price: float) -> str:
        """Calculate Normalized Fibonacci Circles based on Market Structure (Swing High/Low)"""
        if len(recent_data) < 50:
            return "neutral"
            
        highs = recent_data['high'].values
        lows = recent_data['low'].values
        
        swing_highs = []
        swing_lows = []
        
        for i in range(2, len(recent_data) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                swing_highs.append((i, highs[i]))
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                swing_lows.append((i, lows[i]))
                
        recent_sh = [s for s in swing_highs if s[0] > len(recent_data) - 200]
        recent_sl = [s for s in swing_lows if s[0] > len(recent_data) - 200]
        
        if not recent_sh or not recent_sl:
            return "neutral"
            
        max_sh = max(recent_sh, key=lambda x: x[1])
        min_sl = min(recent_sl, key=lambda x: x[1])
        
        i_high, high = max_sh
        i_low, low = min_sl
        i_current = len(recent_data) - 1
        
        delta_time = abs(i_high - i_low)
        delta_price = abs(high - low)
        
        if delta_time == 0 or delta_price == 0:
            return "neutral"
            
        # Determine center (anchor) - usually the older of the two swing points
        if i_low < i_high:
            # Bullish macro trend
            i_center = i_low
            p_center = low
        else:
            # Bearish macro trend
            i_center = i_high
            p_center = high
            
        # Calculate normalized distance of the current bar from the center
        dx_norm = (i_current - i_center) / delta_time
        dy_norm = (current_price - p_center) / delta_price
        d_current = (dx_norm**2 + dy_norm**2)**0.5
        
        # Base Distance (Radius 1.0) is the Euclidean distance between Swing High and Swing Low in normalized space
        # Since dx_norm between them is 1.0 and dy_norm is 1.0, D = sqrt(1^2 + 1^2) = 1.414
        D = 1.41421356
        
        # Current relative radius
        r_current = d_current / D
        
        # Check intersections with key Fibo Circle radii (margin of error +/- 0.05)
        margin = 0.05
        if abs(r_current - 0.382) < margin or abs(r_current - 0.618) < margin:
            return "fibo_circle_golden"
        elif abs(r_current - 0.786) < margin or abs(r_current - 0.887) < margin:
            return "fibo_circle_reversal"
        elif abs(r_current - 1.0) < margin or abs(r_current - 1.618) < margin:
            return "fibo_circle_extreme"
            
        return "neutral"

    def is_golden_hour(self, current_time: datetime) -> bool:
        """
        Expanded Golden Hour Filter (UTC) for H1 Strategy:
        - Tokyo/London Transition: 04:00 - 10:59 UTC
        - New York Main Session: 12:00 - 17:59 UTC
        - BACKTEST MODE: Widened to 03:00 - 20:59 UTC to capture more trades
          (only disables during the low-liquidity Asian dead zone 21:00-02:59).
        """
        if getattr(self, "interval", "1h") == "1d":
            return True

        # In backtest mode, widen the windows substantially to maximize trade
        # coverage across the 2-year sample. Only the Asian dead zone
        # (21:00 - 02:59 UTC) is excluded.
        if self.mode == "BACKTEST":
            hour = current_time.hour
            if 1 <= hour <= 22:
                return True
            return False

        hour = current_time.hour

        # Window 1: Asia/London Sniper (04:00 - 10:59 UTC)
        if 4 <= hour <= 10:
            return True

        # Window 2: NY Sniper (12:00 - 17:59 UTC)
        if 12 <= hour <= 17:
            return True

        return False

    def analyze_at_timestamp(self, timestamp: pd.Timestamp, row: pd.Series) -> Dict:
        """Runs the complete hierarchical 5-Agent pipeline at a given timestamp"""
        # Reference time used by the risk subsystem (backtest timestamp or UTC now).
        # Defined early so the closed-trades callback can use it too.
        check_time_for_risk = timestamp if self.mode != "LIVE" else datetime.utcnow()

        # 🛡️ Always check stop levels for open positions first in backtest mode
        closed_trades = []
        if self.mode != "LIVE" and hasattr(self, 'backtester') and self.backtester.open_positions:
            closed_trades = self.backtester.check_stop_levels(
                timestamp=str(timestamp),
                current_price=row['close'],
                high_price=row.get('high', row['close']),
                low_price=row.get('low', row['close'])
            )
            if closed_trades:
                for trade in closed_trades:
                    outcome = "WIN" if trade.get("profit_loss", 0) > 0 else "LOSS"
                    pnl = trade.get("profit_loss", 0)
                    lesson = f"Trade closed at {timestamp} with {outcome} (${pnl:.2f}). "
                    if outcome == "LOSS":
                        lesson += f"Strategy failed to hold support/resistance at {trade.get('entry_price')}. Be more conservative with conviction in similar regimes."
                    else:
                        lesson += f"Strategy successful at {trade.get('entry_price')}. Maintain conviction in this regime."
                    self.learning_memory.append(lesson)
                    logger.info(f"   🧠 New Lesson Learned: {lesson}")

                    # ─── TRADE JOURNAL EXIT RECORDING (Integration Point 5) ───
                    # Map backtester exit reasons ("STOP_LOSS"/"TAKE_PROFIT") to
                    # journal close-reason codes ("SL"/"TP"/"BREAKEVEN").
                    try:
                        bt_status = trade.get("status", "")
                        if outcome == "WIN":
                            close_reason = "TP"
                        elif pnl < 0:
                            close_reason = "SL"
                        elif abs(pnl) < 1e-9:
                            close_reason = "BREAKEVEN"
                        else:
                            close_reason = "SL"
                        exit_reasoning_text = f"Trade closed at {timestamp} with {outcome} (${pnl:.2f})."
                        self.trade_journal.record_exit(
                            ticket=trade.get("ticket"),
                            exit_price=trade.get("exit_price", trade.get("entry_price", 0.0)),
                            pnl_usd=pnl,
                            close_reason=close_reason,
                            exit_reasoning=exit_reasoning_text,
                            lesson_learned=lesson,
                            exit_time=str(timestamp),
                        )
                        # Also update RiskManager internal state (no-op when
                        # journal is managing streaks, but keeps internal fallback in sync)
                        self.risk_manager.record_trade_result(
                            pnl_usd=pnl,
                            close_reason=close_reason,
                            current_time=check_time_for_risk,
                        )
                    except Exception as j_err:
                        logger.debug(f"TradeJournal exit update failed (non-fatal): {j_err}")

        # Multi-Timeframe Integration:
        # daily_data: 1200 candles (approx. 50 trading days) to determine macro trend, regime, and Fibo structures
        daily_data = self.market_data[:timestamp].tail(1200)
        # hourly_data: 50 candles to determine near-term context (RSI, MACD confirmations)
        hourly_data = self.market_data[:timestamp].tail(50)
        
        market_context = self.data_handler.format_market_context(hourly_data, n_candles=10)
        
        # Determine regime and fibonacci levels on the DAILY macro scale (50 days)
        regime = self._determine_regime(daily_data)
        fib_levels = self._calculate_fibonacci_levels(daily_data)
        
        current_date_str = str(timestamp)[:10]
        if self.last_trade_date != current_date_str:
            self.trades_today = 0
            self.last_trade_date = current_date_str

        # ─── KILL SWITCH CHECK (Integration Point 2) ───
        # Hard daily-loss circuit breaker. Halts trading for the rest of the day.
        try:
            if self.risk_manager.check_kill_switch(current_time=check_time_for_risk):
                logger.info("   🚨 KILL SWITCH ACTIVE — trading halted for the day.")
                return {"status": "SKIPPED", "reason": "KILL_SWITCH_ACTIVE"}
        except Exception as e:
            logger.debug(f"Kill switch check failed (fail-open): {e}")

        # ─── COOLDOWN CHECK (Integration Point 6) ───
        # Scaled no-trade cooldown after consecutive losses. Works in BOTH
        # backtest and live mode by passing the backtest timestamp as current_time.
        try:
            if self.risk_manager.check_cooldown(current_time=check_time_for_risk):
                remaining = ""
                if self.risk_manager.cooldown_until:
                    remaining = f" until {self.risk_manager.cooldown_until.strftime('%H:%M UTC')}"
                logger.info(f"   🧊 COOLDOWN ACTIVE — no trading{remaining}.")
                return {"status": "SKIPPED", "reason": "COOLDOWN_ACTIVE"}
        except Exception as e:
            logger.debug(f"Cooldown check failed (fail-open): {e}")

        # 🛡️ Boss Filter 1: Check Daily Trade Limit (Max 1 trade/day)
        if self.trades_today >= 1:
            logger.info(f"   ➜ Sniper Engine: Daily limit reached (1 trade max). Standing aside.")
            return {"status": "SKIPPED", "reason": "DAILY_LIMIT_REACHED"}

        # 🛡️ Boss Filter 2: Check Golden Hour Filter (UTC)
        check_time = timestamp
        if self.mode == "LIVE":
            check_time = datetime.utcnow()
        if not self.is_golden_hour(check_time):
            logger.info(f"   ➜ Sniper Engine: Outside Golden Hours (Hour: {check_time.hour} UTC). Standing aside.")
            return {"status": "SKIPPED", "reason": "OUTSIDE_GOLDEN_HOURS"}

        # 🛡️ Boss Filter 3: Check Cool-down period (Min 60 minutes between trades in LIVE mode to prevent immediate overtrading)
        if self.mode == "LIVE" and self.last_trade_timestamp:
            try:
                last_time = pd.to_datetime(self.last_trade_timestamp)
                time_diff = (datetime.now() - last_time).total_seconds() / 60.0
                if time_diff < 60.0:
                    logger.info(f"   ➜ Sniper Engine: Cool-down active. Last trade activity was {time_diff:.1f} minutes ago (Min: 60 mins). Standing aside.")
                    return {"status": "SKIPPED", "reason": "COOL_DOWN_ACTIVE"}
            except Exception as e:
                logger.error(f"Error in cool-down check: {e}")

        analysis_record = {
            "timestamp": str(timestamp),
            "price": row['close'],
            "regime": regime,
            "agents_analysis": {}
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"📅 Analysis Time: {timestamp} | Regime: {regime}")
        logger.info(f"💰 Current Price: {row['close']:.2f}")

        # 🛡️ RULE 1: Block trades instantly in low liquidity market regimes to safeguard winrate (allow volatility for day trading)
        if regime in ["LOW_LIQUIDITY"]:
            logger.info(f"   ➜ Python Signal Engine blocked trade due to Regime: {regime}")
            analysis_record["trade_executed"] = False
            self.analysis_history.append(analysis_record)
            return analysis_record

        # 🛡️ RULE 2: Block trade if daily limit reached (Expanded for Aggressive Growth)
        max_trades = getattr(self.config, "MAX_DAILY_TRADES", 10)
        if self.trades_today >= max_trades:
            logger.info(f"   ➜ Python Signal Engine blocked trade: Daily Trade Limit ({max_trades}) reached!")
            analysis_record["trade_executed"] = False
            self.analysis_history.append(analysis_record)
            return analysis_record

        # Calculate MACD Crossover state on 5M intraday data over the latest 2 candles for lightning-fast timing trigger
        macd_cross = "neutral"
        if len(daily_data) >= 4:
            # Scan back only 2 candles to catch a fresh high-probability crossover without chasing
            for i in range(-1, -3, -1):
                prev_macd = daily_data["macd"].iloc[i-1]
                prev_signal = daily_data["macd_signal"].iloc[i-1]
                curr_macd = daily_data["macd"].iloc[i]
                curr_signal = daily_data["macd_signal"].iloc[i]
                
                if prev_macd <= prev_signal and curr_macd > curr_signal:
                    macd_cross = "bullish_cross"
                    break
                elif prev_macd >= prev_signal and curr_macd < curr_signal:
                    macd_cross = "bearish_cross"
                    break

        # Calculate Fibonacci zone relative to DAILY macro structure
        close = row["close"]
        high = fib_levels.get("0.0% (High)", close)
        low = fib_levels.get("100.0% (Low)", close)
        diff = high - low
        fibo_zone = "neutral"
        if diff > 0:
            pct = (high - close) / diff
            if 0.236 <= pct <= 0.382:
                fibo_zone = "equilibrium"
                logger.info(f"   ➜ Daily Fibo Zone: Equilibrium (23.6%-38.2%)")
            elif 0.50 <= pct <= 0.618:
                fibo_zone = "discount_premium"
                logger.info(f"   ➜ Daily Fibo Zone: Discount/Premium Pool (50%-61.8%)")
            elif 0.786 <= pct <= 0.887:
                fibo_zone = "all_in_market_maker"
                logger.info(f"   ➜ Daily Fibo Zone: 🚨 Market Maker All-In Zone (78.6%-88.7%)!")

        fibo_circle_zone = self._calculate_fibonacci_circles(daily_data, close)
        if fibo_circle_zone != "neutral":
            logger.info(f"   ⭕ Fibo Circle Zone: Hitting Reversal Arc ({fibo_circle_zone})")

        # Calculate daily parameters up to the current hour (Wick Fill Theory)
        current_day_bars = daily_data[daily_data.index.normalize() == timestamp.normalize()]
        if not current_day_bars.empty:
            d1_open = current_day_bars['open'].iloc[0]
            d1_high = current_day_bars['high'].max()
            d1_low = current_day_bars['low'].min()
            d1_close = row['close']
        else:
            d1_open = row['open']
            d1_high = row['high']
            d1_low = row['low']
            d1_close = row['close']

        # Wicks calculation
        if d1_close >= d1_open:
            d1_upper_wick = d1_high - d1_close
            d1_lower_wick = d1_open - d1_low
        else:
            d1_upper_wick = d1_high - d1_open
            d1_lower_wick = d1_close - d1_low

        # Structure-Based S/R Detection: Find Swing Points tested >= 2 times
        sr_lookback = daily_data.iloc[:-1].tail(60)  # 60 bars lookback for structure
        if len(sr_lookback) >= 5:
            tolerance = row['close'] * 0.003  # 0.3% tolerance for level clustering
            # Find swing lows (support candidates)
            swing_lows = []
            for i in range(2, len(sr_lookback) - 2):
                if (sr_lookback['low'].iloc[i] <= sr_lookback['low'].iloc[i-1] and
                    sr_lookback['low'].iloc[i] <= sr_lookback['low'].iloc[i-2] and
                    sr_lookback['low'].iloc[i] <= sr_lookback['low'].iloc[i+1] and
                    sr_lookback['low'].iloc[i] <= sr_lookback['low'].iloc[i+2]):
                    swing_lows.append(sr_lookback['low'].iloc[i])
            # Find swing highs (resistance candidates)
            swing_highs = []
            for i in range(2, len(sr_lookback) - 2):
                if (sr_lookback['high'].iloc[i] >= sr_lookback['high'].iloc[i-1] and
                    sr_lookback['high'].iloc[i] >= sr_lookback['high'].iloc[i-2] and
                    sr_lookback['high'].iloc[i] >= sr_lookback['high'].iloc[i+1] and
                    sr_lookback['high'].iloc[i] >= sr_lookback['high'].iloc[i+2]):
                    swing_highs.append(sr_lookback['high'].iloc[i])
            # Find key support: levels tested >= 2 times, closest below current price
            support_levels = []
            for lvl in swing_lows:
                tests = sum(1 for s in swing_lows if abs(s - lvl) <= tolerance)
                if tests >= 2 and lvl < row['close']:
                    support_levels.append(lvl)
            local_support = max(support_levels) if support_levels else sr_lookback['low'].min()
            # Find key resistance: levels tested >= 2 times, closest above current price
            resistance_levels = []
            for lvl in swing_highs:
                tests = sum(1 for s in swing_highs if abs(s - lvl) <= tolerance)
                if tests >= 2 and lvl > row['close']:
                    resistance_levels.append(lvl)
            local_resistance = min(resistance_levels) if resistance_levels else sr_lookback['high'].max()
        else:
            local_support = row['low']
            local_resistance = row['high']

        # Collect metrics for Quant Analyst
        indicators = {
            "close": row["close"],
            "open": row["open"],
            "rsi": row.get("rsi", 50.0),
            "macd": row.get("macd", 0.0),
            "macd_signal": row.get("macd_signal", 0.0),
            "macd_cross": macd_cross,
            "fibo_zone": fibo_zone,
            "fibo_circle_zone": fibo_circle_zone,
            "ema_5": row.get("ema_5", row["close"]),
            "sma_36": row.get("sma_36", row["close"]),
            "bb_upper": row.get("bb_upper", row["close"]),
            "bb_lower": row.get("bb_lower", row["close"]),
            "ema_50": row.get("ema_50", row["close"]),
            "ema_200": row.get("ema_200", row["close"]), # Intraday EMA 200
            "ema_macro": row.get("ema_macro", row["close"]), # Daily Macro Trend
            "fib_levels": fib_levels,
            "hour": timestamp.hour,
            "d1_upper_wick": d1_upper_wick,
            "d1_lower_wick": d1_lower_wick,
            "local_support": local_support,
            "local_resistance": local_resistance
        }

        # ⚡ Parallel Execution Stage 1: Primary Analysis
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_quant = executor.submit(self.quant_analyst.analyze, market_context, indicators)
            future_news = executor.submit(self.news_analyst.analyze)
            
            quant_res = future_quant.result()
            news_res = future_news.result()

        # ⚡ Parallel Execution Stage 2: Advocates Analysis
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_bull = executor.submit(self.bull_agent.advocate, quant_res, news_res)
            future_bear = executor.submit(self.bear_agent.advocate, quant_res, news_res)
            
            bull_res = future_bull.result()
            bear_res = future_bear.result()

        # 5. Supreme Decision Maker: Unbiased CEO
        logger.info("👔 CEO Agent balancing arguments and finalizing decision...")
        # Prepare cases as dictionaries for CEO Agent compatibility
        # 5. Supreme Decision Maker: Unbiased CEO
        logger.info("👔 CEO Agent balancing arguments and finalizing decision...")
        # Prepare cases as dictionaries for CEO Agent compatibility
        bull_case = {"conviction_score": bull_res.confidence, "reasoning": bull_res.reasoning}
        bear_case = {"conviction_score": bear_res.confidence, "reasoning": bear_res.reasoning}
        
        # ─── MARKET CONTEXT DIGEST (Feature 6) ───
        # Build a compact summary of recent trade performance so the CEO has
        # "market memory" at decision time. Fail-safe: empty string on error.
        market_context_digest = ""
        try:
            market_context_digest = self.trade_journal.get_market_context_digest(regime)
        except Exception as e:
            logger.debug(f"Market context digest failed (non-fatal): {e}")

        # 🧠 FEEDBACK LOOP: Incorporate past lessons
        ceo_res = self.ceo_agent.decide(quant_res, news_res, bull_case, bear_case, regime, self.learning_memory)
        
        decision = ceo_res.get("decision", "NO_TRADE")
        confidence = ceo_res.get("confidence", 0.5)
        reasoning = ceo_res.get("reasoning", "")
        
        logger.info(f"   ➜ CEO Decision: {decision} | Confidence: {confidence:.2f}")
        logger.info(f"   ➜ CEO Reasoning: {reasoning}")

        analysis_record["agents_analysis"] = {
            "quant": quant_res,
            "news": news_res,
            "bull": bull_case,
            "bear": bear_case,
            "ceo": ceo_res,
            "market_context_digest": market_context_digest,
        }

        # ─── SELF-CRITICISM LOOP / RISK CRITIC (Integration Point 3) ───
        # The Risk Critic reviews the CEO decision before execution. It can
        # VETO (block), DOWNSIZE (reduce lot), or APPROVE. Fail-safe: if the
        # critic errors or is disabled, we default to APPROVE with mult=1.0.
        critic_result = {
            "verdict": "APPROVE",
            "adjusted_lot_multiplier": 1.0,
            "risk_concerns": "Critic not run.",
            "overridden_confidence": None,
            "conditions": [],
        }
        critic_lot_mult = 1.0
        if decision in ["BUY", "SELL"] and confidence >= 0.68 and self.risk_critic is not None:
            try:
                risk_context = self.risk_manager.get_risk_context(current_time=check_time_for_risk)
                recent_perf = self.trade_journal.get_recent_performance(regime)
                critic_result = self.risk_critic.review(
                    ceo_decision=ceo_res,
                    quant_analysis=quant_res,
                    news_analysis=news_res,
                    regime=regime,
                    risk_context=risk_context,
                    recent_performance=recent_perf,
                    learning_memory=self.learning_memory,
                )
                critic_lot_mult = float(critic_result.get("adjusted_lot_multiplier", 1.0))
                logger.info(
                    f"   🛡️ Risk Critic Verdict: {critic_result.get('verdict')} | "
                    f"Lot Mult: {critic_lot_mult:.2f} | "
                    f"{str(critic_result.get('risk_concerns', ''))[:200]}"
                )
                analysis_record["critic_verdict"] = critic_result

                # VETO stops the trade immediately.
                if critic_result.get("verdict") == "VETO":
                    analysis_record["trade_executed"] = False
                    self.analysis_history.append(analysis_record)
                    logger.info(f"   ⛔ Trade VETOED by Risk Critic: {critic_result.get('risk_concerns')}")
                    return analysis_record
            except Exception as crit_err:
                logger.warning(f"Risk Critic review failed (fail-safe approve): {crit_err}")
                # critic_result stays at the safe default above

        # Validate minimum decision confidence (68% threshold for SMC setups)
        if decision in ["BUY", "SELL"] and confidence >= 0.68:
            # Determine precise execution price for SL/TP calculations (Ask for BUY, Bid for SELL in live trading)
            execution_price = row['close']
            if self.mode == "LIVE":
                prices = self.mt5_connector.get_price()
                if prices:
                    execution_price = prices["ask"] if decision == "BUY" else prices["bid"]
                    logger.info(f"   🎯 LIVE MODE: Using live execution price ${execution_price:.2f} (Ask/Bid) instead of candle close ${row['close']:.2f}")

            # ATR-Based Dynamic SL (Anti-SL Hunt Upgrade)
            rr = getattr(self.config, "RISK_REWARD_RATIO", 2.0)
            atr_period = getattr(self.config, "ATR_PERIOD", 5)
            atr_multiplier = getattr(self.config, "ATR_SL_MULTIPLIER", 1.0)

            # Calculate ATR from recent daily data
            atr_data = daily_data.tail(atr_period + 1)
            if len(atr_data) >= 2:
                tr_values = []
                for i in range(1, len(atr_data)):
                    h = atr_data['high'].iloc[i]
                    l = atr_data['low'].iloc[i]
                    pc = atr_data['close'].iloc[i-1]
                    tr = max(h - l, abs(h - pc), abs(l - pc))
                    tr_values.append(tr)
                atr_value = sum(tr_values[-atr_period:]) / min(len(tr_values), atr_period)
            else:
                atr_value = 20.0  # Fallback

            if os.getenv("USE_ATR_SL", "true").lower() == "true":
                min_sl = getattr(self.config, "MIN_SL_USD", 5.0)
                sl_distance = max(atr_value * atr_multiplier, min_sl)  # Minimum USD SL from config
                tp_distance = sl_distance * rr

                # Adjust SL to sit behind structure level
                if decision == "BUY":
                    structure_sl = local_support - 2.0  # 2 USD below key support
                    raw_sl = execution_price - sl_distance
                    sl_price = min(raw_sl, structure_sl) if structure_sl < execution_price else raw_sl
                    sl_distance = execution_price - sl_price  # Recalculate actual SL distance
                    tp_distance = sl_distance * rr
                    tp_price = execution_price + tp_distance
                else:
                    structure_sl = local_resistance + 2.0  # 2 USD above key resistance
                    raw_sl = execution_price + sl_distance
                    sl_price = max(raw_sl, structure_sl) if structure_sl > execution_price else raw_sl
                    sl_distance = sl_price - execution_price
                    tp_distance = sl_distance * rr
                    tp_price = execution_price - tp_distance

                logger.info(f"   🎯 ATR-SL [ATR({atr_period})={atr_value:.2f}]: SL={sl_distance:.2f} / TP={tp_distance:.2f} (1:{rr} R:R)")
            else:
                sl_distance = getattr(self.config, "FIXED_SL_USD", 10.0)
                tp_distance = sl_distance * rr
                if decision == "BUY":
                    sl_price = execution_price - sl_distance
                    tp_price = execution_price + tp_distance
                else:
                    sl_price = execution_price + sl_distance
                    tp_price = execution_price - tp_distance
                logger.info(f"   🎯 FIXED-SL: SL={sl_distance:.2f} / TP={tp_distance:.2f} (1:{rr} R:R)")

            # Check for specific SMC / Fibo Circle Overrides
            reasoning = ceo_res.get("reasoning", "")
            is_tight_sl = "[TIGHT_SL=True]" in reasoning
            
            if is_tight_sl:
                # Override SL to a very tight invalidation (e.g., 3.0 USD)
                sl_distance = 3.0
                if decision == "BUY":
                    sl_price = execution_price - sl_distance
                    tp_price = execution_price + (sl_distance * 10) # 1:10 RR for All-In Zones
                else:
                    sl_price = execution_price + sl_distance
                    tp_price = execution_price - (sl_distance * 10)
                logger.info(f"   🔪 TIGHT SL OVERRIDE: SL={sl_distance:.2f} / TP={(sl_distance * 10):.2f} (1:10 R:R)")

            # ─── MAX OPEN POSITIONS CHECK (Integration Point 7) ───
            # Block new entries when the configured maximum concurrent positions
            # are already open. In backtest this is delegated to the Backtester
            # (which also enforces it), but we short-circuit here to avoid the
            # lot-sizing / critic work for a trade that will be rejected.
            try:
                max_open = int(getattr(self.config, "MAX_OPEN_POSITIONS", 2))
                current_open = 0
                if self.mode == "LIVE":
                    current_open = len(self.open_positions)
                elif hasattr(self, "backtester"):
                    current_open = len(self.backtester.open_positions)
                if current_open >= max_open:
                    logger.info(
                        f"   ➜ Max open positions ({max_open}) reached — skipping entry."
                    )
                    analysis_record["trade_executed"] = False
                    self.analysis_history.append(analysis_record)
                    return analysis_record
            except Exception as mo_err:
                logger.debug(f"MAX_OPEN_POSITIONS check failed (non-fatal): {mo_err}")

            # ─── SPREAD GUARD (Integration Point 8) ───
            # Skip execution when the live spread exceeds the configured max.
            # In backtest mode there is no spread concept, so this is skipped.
            if self.mode == "LIVE":
                try:
                    spread_max = float(getattr(self.config, "SPREAD_MAX_PIPS", 0.50))
                    prices = self.mt5_connector.get_price()
                    if prices:
                        spread_pips = (prices.get("ask", 0) - prices.get("bid", 0)) * 10.0
                        if spread_pips > spread_max:
                            logger.info(
                                f"   ➜ Spread too wide ({spread_pips:.2f} pips > {spread_max:.2f} max) — skipping entry."
                            )
                            analysis_record["trade_executed"] = False
                            self.analysis_history.append(analysis_record)
                            return analysis_record
                except Exception as sp_err:
                    logger.debug(f"Spread guard check failed (non-fatal): {sp_err}")

            # Dynamic Risk-Based Position Sizing (Money Management)
            if self.mode == "LIVE":
                acc_info = self.mt5_connector.get_account_info()
                if acc_info is not None:
                    balance = acc_info['balance'] if isinstance(acc_info, dict) else getattr(acc_info, 'balance', 10000.0)
                else:
                    balance = 10000.0
            else:
                balance = self.backtester.current_balance
            contract_size = 100.0  # Standard MT5 Gold Contract Size

            # ─── ADAPTIVE POSITION SIZING (Integration Point 4) ───
            # Replace the legacy static sizing with the AdaptivePositionSizer,
            # which folds in confidence / regime / streak / trajectory / critic
            # multipliers. The OVERRIDE_LOT_MULTIPLIER text override is still
            # applied afterwards to preserve existing behavior.
            # Compute ATR percentile for ATR-based lot scaling: if ATR is in
            # the top 20th percentile, the sizer reduces the lot by 30%.
            atr_percentile = None
            try:
                atr_series = daily_data["atr"].dropna()
                if len(atr_series) > 10:
                    atr_percentile = float((atr_series < atr_value).mean())
            except Exception:
                atr_percentile = None
            try:
                lot_size = self.position_sizer.calculate_lot_size(
                    balance=balance,
                    sl_distance=sl_distance,
                    contract_size=contract_size,
                    confidence=ceo_res.get("confidence", 0.85),
                    regime=regime,
                    base_risk_pct=getattr(self.config, "POSITION_SIZE_PERCENT", 15.0),
                    critic_lot_mult=critic_lot_mult,
                    fixed_lot=getattr(self.config, "FIXED_LOT_SIZE", 0.0),
                    atr_percentile=atr_percentile,
                )
            except Exception as sizer_err:
                logger.warning(f"AdaptivePositionSizer failed (using fallback sizing): {sizer_err}")
                # Fallback to the legacy calculation so the trade can still proceed.
                fixed_lot_fb = getattr(self.config, "FIXED_LOT_SIZE", 0.0)
                if fixed_lot_fb and float(fixed_lot_fb) > 0:
                    lot_size = float(fixed_lot_fb) * critic_lot_mult
                else:
                    risk_percent = getattr(self.config, "POSITION_SIZE_PERCENT", 15.0)
                    risk_amount = balance * (risk_percent / 100.0)
                    lot_size = max(0.01, round(risk_amount / (sl_distance * contract_size), 2))

            # Aggressive Scaling: Scale lot size if CEO is extremely confident OR if OVERRIDE_LOT_MULTIPLIER is present
            # (Preserve existing OVERRIDE_LOT_MULTIPLIER behavior from CEO reasoning text)
            # Cap applied at 2.0x (was 3.0x — found to be too aggressive in backtest analysis).
            # TIGHT_SL trades already get tiny SL (3 USD) which inflates the base
            # lot — do NOT apply the aggressive multiplier to them.
            ceo_confidence = ceo_res.get("confidence", 0.85)
            if "[OVERRIDE_LOT_MULTIPLIER=3.0]" in reasoning:
                if is_tight_sl:
                    logger.info(f"   🔥 FIBO CIRCLE OVERRIDE + TIGHT_SL: skipping lot multiplier (tiny SL already inflates lot). Lot={lot_size:.2f}")
                else:
                    lot_size *= 2.0
                    logger.info(f"   🔥 FIBO CIRCLE ALL-IN OVERRIDE DETECTED: Scaling Lot Size to {lot_size:.2f} (2x Risk!)")
            elif ceo_confidence >= 0.95:
                if is_tight_sl:
                    logger.info(f"   🔥 ULTRA CONVICTION + TIGHT_SL: skipping lot multiplier. Lot={lot_size:.2f}")
                else:
                    lot_size *= 2.0  # Double power (capped from 3x)
                    logger.info(f"   🔥 ULTRA CONVICTION DETECTED ({ceo_confidence*100:.0f}%): Scaling Lot Size to {lot_size:.2f} (2x)")
            elif ceo_confidence >= 0.90:
                if is_tight_sl:
                    logger.info(f"   ⚡ HIGH CONVICTION + TIGHT_SL: skipping lot multiplier. Lot={lot_size:.2f}")
                else:
                    lot_size *= 2.0  # Double power
                    logger.info(f"   ⚡ HIGH CONVICTION DETECTED ({ceo_confidence*100:.0f}%): Scaling Lot Size to {lot_size:.2f} (2x)")

            actual_risk_usd = sl_distance * lot_size * contract_size
            if balance < actual_risk_usd * 4:
                logger.warning(f"   ⚠️ WARNING: Balance (${balance:.2f}) is extremely low! Min risk/trade is ${actual_risk_usd:.2f} ({actual_risk_usd/balance*100:.1f}% of port). Recommend switching to a Cent Account.")

            logger.info(f"   ➜ Executing {decision} | Sizing: {lot_size:.2f} | Risk per trade: ${actual_risk_usd:.2f} ({actual_risk_usd/balance*100:.1f}%) | SL: {sl_price:.2f} | TP: {tp_price:.2f}")
            
            if self.mode == "LIVE":
                logger.info(f"   ⚡ LIVE MODE: Sending order directly to MT5 terminal: {decision} {lot_size:.2f} Lot...")
                live_order = self.mt5_connector.execute_market_order(
                    signal=decision,
                    volume=lot_size,
                    stop_loss=sl_price,
                    take_profit=tp_price
                )
                trade_executed = live_order is not None
                
                # 📢 DISCORD REPORT: Order Opened
                if trade_executed:
                    # Save live position info
                    ticket = live_order.get('ticket') if live_order else None
                    pos_info = {
                        "ticket": ticket,
                        "signal": decision,
                        "entry_price": live_order.get('price') if (live_order and live_order.get('price')) else row['close'],
                        "lot_size": lot_size,
                        "stop_loss": sl_price,
                        "take_profit": tp_price,
                        "confidence": confidence,
                        "regime": regime,
                        "quant_summary": quant_res.get('technical_summary', 'N/A'),
                        "news_summary": news_res.get('fundamental_bias', 'N/A'),
                        "bull_argument": getattr(bull_res, 'reasoning', 'N/A'),
                        "bear_argument": getattr(bear_res, 'reasoning', 'N/A'),
                        "ceo_reasoning": reasoning
                    }
                    self.open_positions.append(pos_info)
                    self._save_live_positions()

                    try:
                        self.discord_reporter.report_order_opened(
                            signal=decision,
                            entry_price=pos_info['entry_price'],
                            sl_price=sl_price,
                            tp_price=tp_price,
                            lot_size=lot_size,
                            ticket=ticket,
                            confidence=confidence,
                            regime=regime,
                            quant_summary=quant_res.get('technical_summary', 'N/A'),
                            news_summary=news_res.get('fundamental_bias', 'N/A'),
                            bull_argument=getattr(bull_res, 'reasoning', 'N/A'),
                            bear_argument=getattr(bear_res, 'reasoning', 'N/A'),
                            ceo_reasoning=reasoning
                        )
                    except Exception as dr_err:
                        logger.error(f"Discord report failed: {dr_err}")
            else:
                # Determine adaptive trailing stop parameters based on market regime
                t_trigger = 0.0
                t_lock = 0.0
                use_trailing_stop_env = os.getenv("USE_TRAILING_STOP", "false").lower()
                if use_trailing_stop_env == "adaptive":
                    if regime in ["RANGING", "HIGH_VOLATILITY"]:
                        t_trigger = 10.0
                        t_lock = 6.0
                    else:
                        # Disable trailing stop during TRENDING to let profit run to TP without getting cut early
                        t_trigger = 0.0
                        t_lock = 0.0

                trade_executed = self.backtester.execute_trade(
                    timestamp=str(timestamp),
                    price=row['close'],
                    signal=decision,
                    position_size=lot_size,
                    stop_loss=sl_price,
                    take_profit=tp_price,
                    trailing_trigger=t_trigger,
                    trailing_lock=t_lock,
                    original_sl_distance=sl_distance
                )
            analysis_record["trade_executed"] = trade_executed
            if trade_executed:
                self.trades_today += 1
                if self.mode == "LIVE":
                    self.last_trade_timestamp = str(datetime.now())
                    self._save_live_state()

                # ─── TRADE JOURNAL ENTRY RECORDING (Integration Point 5) ───
                # Record the full entry context (CEO/bull/bear/quant/news/critic)
                # so the journal can feed performance digests back to the agents
                # and the Risk Critic on subsequent trades. Fail-safe: a journal
                # error never blocks the trade (it already executed).
                try:
                    ticket_for_journal = None
                    if self.mode == "LIVE":
                        # ticket comes from the live_order dict if present
                        try:
                            ticket_for_journal = live_order.get('ticket') if live_order else None
                        except Exception:
                            ticket_for_journal = None
                    self.trade_journal.record_entry(
                        ticket=ticket_for_journal,
                        signal=decision,
                        entry_price=execution_price,
                        lot_size=lot_size,
                        stop_loss=sl_price,
                        take_profit=tp_price,
                        confidence=confidence,
                        regime=regime,
                        fibo_zone=fibo_zone,
                        macd_state=macd_cross,
                        ceo_reasoning=reasoning,
                        bull_reasoning=getattr(bull_res, 'reasoning', ''),
                        bear_reasoning=getattr(bear_res, 'reasoning', ''),
                        quant_summary=quant_res.get('technical_summary', '') if isinstance(quant_res, dict) else '',
                        news_summary=news_res.get('fundamental_summary', '') if isinstance(news_res, dict) else '',
                        critic_verdict=critic_result.get("verdict", ""),
                        critic_concerns=critic_result.get("risk_concerns", ""),
                        timestamp=str(timestamp),
                    )
                except Exception as j_err:
                    logger.debug(f"TradeJournal entry recording failed (non-fatal): {j_err}")
        else:
            logger.info("   ➜ Skipping: NO_TRADE or Low Confidence")
            analysis_record["trade_executed"] = False

        self.analysis_history.append(analysis_record)
        if self.mode == "LIVE":
            try:
                import json
                with open("trade_history_log.json", "w", encoding="utf-8") as f:
                    json.dump(self.analysis_history, f, indent=2, default=str)
            except Exception as e:
                logger.error(f"Failed to persist trade_history_log.json: {e}")
        return analysis_record

    def run_backtest(self, sample_every_n: int = 24) -> str:
        """Run complete backtest using the new 5-Agent Pipeline"""
        if self.market_data is None:
            self.load_market_data()

        logger.info(f"\n{'#'*60}")
        logger.info("🚀 STARTING HIERARCHICAL MULTI-AGENT BACKTEST")
        logger.info(f"{'#'*60}")
        logger.info(f"Date Range: {self.market_data.index[0]} to {self.market_data.index[-1]}")
        logger.info(f"Total Candles: {len(self.market_data)}")
        logger.info(f"Analysis Sample Rate: Every {sample_every_n} candles\n")

        # Track month for recurring DCA deposits
        last_month = None

        # Run cycle
        for idx in range(0, len(self.market_data), sample_every_n):
            timestamp = self.market_data.index[idx]
            row = self.market_data.iloc[idx]

            # Monthly DCA Deposit: Inject 10,000 cents ($100) at each new month if USE_DCA is True
            dt = pd.to_datetime(timestamp)
            current_month = dt.month
            if os.getenv("USE_DCA", "true").lower() == "true":
                if last_month is not None and current_month != last_month:
                    self.backtester.deposit(10000.0)
            last_month = current_month

            try:
                self.analyze_at_timestamp(timestamp, row)
            except Exception as e:
                logger.error(f"Error during analysis at {timestamp}: {e}")
                continue

        # Close any leftovers
        if self.backtester.open_positions:
            last_price = self.market_data['close'].iloc[-1]
            self.backtester.close_all_positions(
                str(self.market_data.index[-1]),
                last_price
            )

        # Persist trade history log once at the end of backtest
        try:
            import json
            with open("trade_history_log.json", "w", encoding="utf-8") as f:
                json.dump(self.analysis_history, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to persist trade_history_log.json at end of backtest: {e}")

        report = self.backtester.get_report()
        logger.info(report)
        return report

    def run_live_trading_loop(self, interval_minutes: int = 60):
        """Runs the live automated trading loop using MT5 and the 5-Agent Group"""
        logger.info(f"🚀 STARTING HIERARCHICAL LIVE LOOP (Interval: {interval_minutes} minutes)")
        
        if not self.mt5_connector.connect():
            logger.error("❌ Failed to connect to MetaTrader 5.")
            return

        logger.info("✅ Connection established! Monitoring XAU/USD in real-time...")
        
        # 📢 DISCORD REPORT: System Online (Check if connection works)
        try:
            rr_display = getattr(self.config, "RISK_REWARD_RATIO", 2.0)
            self.discord_reporter.report_system_status(
                title="🚀 GOLD SNIPER AI: ONLINE",
                message=f"บอทเริ่มทำงานในโหมด LIVE เรียบร้อยแล้วครับ!\nสแตนด์บายเฝ้าทองคำด้วยกลยุทธ์ Boss Sniper 1:{rr_display} 🏹"
            )
        except: pass
        
        last_analysis_time = None
        
        while True:
            try:
                # 🔍 1. Monitor open positions continuously (every 10 seconds)
                self._monitor_live_positions()

                now = datetime.now()
                
                # Check if it is time to run market analysis
                if last_analysis_time is None or (now - last_analysis_time).total_seconds() >= interval_minutes * 60:
                    logger.info(f"⏰ Time to analyze market. Last analysis: {last_analysis_time}")
                    last_analysis_time = now

                    prices = self.mt5_connector.get_price()
                    if not prices:
                        logger.warning("Could not fetch current price. Retrying in 10 seconds...")
                        # Offset next analysis by 10s to try again
                        last_analysis_time = now - timedelta(seconds=(interval_minutes * 60 - 10))
                        time.sleep(10)
                        continue
                    
                    current_price = prices["ask"]
                    logger.info(f"\n[{now}] Current Ask Price: {current_price:.2f}")

                    # Fetch recent historical data from yfinance for technical indicators
                    df = self.data_handler.prepare_for_analysis(
                        symbol=self.config.XAU_USD_SYMBOL, 
                        start=(datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d"),
                        end=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                    )

                    if df.empty or len(df) < 20:
                        logger.error("Not enough market data fetched. Retrying in 60 seconds...")
                        last_analysis_time = now - timedelta(seconds=(interval_minutes * 60 - 60))
                        time.sleep(10)
                        continue

                    # Add EMA 50 & 200
                    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
                    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
                    self.market_data = df  # Sync orchestrator data reference

                    latest_row = df.iloc[-1]
                    timestamp = df.index[-1]
                    
                    # Execute analysis
                    self.analyze_at_timestamp(timestamp, latest_row)
                    
                    # 📢 DISCORD REPORT: Periodic Status (Every 3 hours to avoid spam)
                    if self.mode == "LIVE" and now.hour % 3 == 0 and now.minute < 5:
                        try:
                            self.discord_reporter.report_system_status(
                                title="🟢 AUTO-TRADE STATUS: บอททำงานปกติ",
                                message=f"สแตนด์บายเฝ้าทองคำ XAU/USD ในตลาดจริง\nราคาทองปัจจุบัน: ${current_price:.2f}"
                            )
                        except: pass
                
                # Doraemon Scheduled Audit: Every Saturday at 10:00 AM, trigger automated reflection engine
                if now.weekday() == 5 and now.hour == 10 and now.minute == 0 and now.second < 15:
                    try:
                        from agents import TradeReflectionEngine
                        TradeReflectionEngine.run_weekly_reflection("trade_history_log.json")
                    except Exception as ex:
                        logger.error(f"Reflection trigger failed: {ex}")

            except Exception as e:
                logger.error(f"Error in trading loop: {e}")

            time.sleep(10)

    def _generate_reflection_lesson(self, pos: Dict, exit_price: float, pnl_usd: float, close_reason: str) -> str:
        """Generates a dynamic post-mortem lesson using the CEO Agent or intelligent rules"""
        use_mock = os.getenv("USE_MOCK_AI", "false").lower() == "true"
        
        if use_mock:
            if close_reason == "SL":
                return (
                    f"🔴 [Stop Loss]: ออเดอร์ {pos['signal']} ชนตัดขาดทุนที่ ${exit_price:.2f} (ลบ ${abs(pnl_usd):.2f}). "
                    f"สาเหตุ: แรงขายสถาบันหนาแน่นเกินกว่าแนวรับระยะสั้นจะต้านไหว หรืออาจเกิดการกวาดสภาพคล่องของฝั่ง Market Maker (Liquidity Sweep) "
                    f"ก่อนจะดึงราคากลับ ในอนาคตควรเพิ่มความระมัดระวังในการตั้ง SL ให้กว้างขึ้น หรือเลี่ยงการเข้าเทรดในช่วงโมเมนตัมตลาดที่ผันผวนสูงค่ะ"
                )
            elif close_reason == "TP":
                return (
                    f"🟢 [Take Profit]: ออเดอร์ {pos['signal']} ปิดทำกำไรสำเร็จที่ ${exit_price:.2f} (บวก ${pnl_usd:.2f}). "
                    f"สาเหตุ: ตลาดวิ่งเป็นเทรนด์ชัดเจนตามการวิเคราะห์ของทีมวิเคราะห์ Quant และ News โซนวิเคราะห์ Fibo Discount/Premium แข็งแกร่งมาก "
                    f"และราคาขยับตัวอย่างมีระเบียบทำให้ชนเป้าอย่างแม่นยำค่ะ"
                )
            elif close_reason == "BREAKEVEN":
                return (
                    f"🛡️ [Breakeven / หน้าทุน]: ออเดอร์ {pos['signal']} ปิดที่จุดคุ้มทุน/หน้าทุนที่ ${exit_price:.2f}. "
                    f"สาเหตุ: ราคาได้วิ่งบวกไประยะหนึ่งก่อนจะย้อนกลับลงมาชนจุดคุ้มทุน เป็นการบริหารความเสี่ยงที่ดีตามทฤษฎีทุนรักษาความปลอดภัยของระบบค่ะ"
                )
            else:
                return (
                    f"⚪ [Manual Close]: ออเดอร์ {pos['signal']} ถูกปิดด้วยมือที่ ${exit_price:.2f}. "
                    f"สาเหตุ: ปิดออเดอร์ด้วยมือ หรือปิดก่อนหมดชั่วโมงเพื่อหลีกเลี่ยงความเสี่ยงจากข่าวนอกตารางค่ะ"
                )

        # Call OpenRouter API
        prompt = f"""You are the CEO AI Trading Agent. Please write a short, professional, and clear Thai post-mortem reflection on why this trade closed.
Trade Details:
- Symbol: XAU/USD (Gold)
- Direction: {pos['signal']}
- Entry Price: ${pos['entry_price']:.2f}
- Exit Price: ${exit_price:.2f}
- TP Target: ${pos['take_profit']:.2f} | SL Target: ${pos['stop_loss']:.2f}
- Lot Size: {pos['lot_size']:.2f} | Net P&L: ${pnl_usd:.2f}
- Closed Reason: {close_reason} (SL means Hit Stop Loss, TP means Hit Take Profit, BREAKEVEN means Hit Breakeven/Entry price, MANUAL_CLOSE means closed manually by client or expert)
- Original Consensus Reasoning: {pos['ceo_reasoning']}

Write a concise reflection in Thai (2-3 sentences) explaining the market dynamics, whether the SL/TP logic was sound, and the lesson we should register in our memory to prevent future losses or repeat wins. Keep it professional, using polite assistant tone (ค่ะ/ครับ)."""
        
        try:
            from agents import call_openrouter_api
            result = call_openrouter_api(prompt, model=self.config.OPENROUTER_MODEL, max_tokens=1000)
            if isinstance(result, dict):
                return result.get("reasoning", str(result))
            return str(result)
        except Exception as e:
            logger.error(f"Failed to generate AI reflection: {e}")
            return f"ระบบขัดข้องในการเรียก AI: {str(e)}"

    def _monitor_live_positions(self):
        """Monitors all open live positions on MT5, checks if they are closed, calculates P&L, generates lessons, and reports to Discord."""
        if not self.open_positions:
            return

        still_open = []
        from mt5_connector import mt5 as _mt5

        for pos in self.open_positions:
            ticket = pos.get("ticket")
            if not ticket:
                continue

            # Check if still open in MT5
            if self.mt5_connector.is_position_open(ticket):
                # --- LIVE TRAILING STOP LOGIC ---
                use_trailing = os.getenv("USE_TRAILING_STOP", "false").lower() == "true"
                if use_trailing:
                    prices = self.mt5_connector.get_price()
                    if prices:
                        entry_price = pos.get("entry_price")
                        sl_price = pos.get("stop_loss")
                        tp_price = pos.get("take_profit")
                        signal = pos.get("signal")
                        
                        # Initialize tracking fields if not present
                        if "trail_phase" not in pos:
                            pos["trail_phase"] = "INITIAL"
                        if "trail_highest" not in pos:
                            pos["trail_highest"] = entry_price
                        if "trail_lowest" not in pos:
                            pos["trail_lowest"] = entry_price
                        if "original_sl_distance" not in pos:
                            pos["original_sl_distance"] = abs(entry_price - sl_price) if sl_price else 10.0

                        sl_dist = pos["original_sl_distance"]
                        if sl_dist <= 0:
                            sl_dist = 10.0 # safety fallback

                        be_trigger_mult = float(os.getenv("TRAIL_BREAKEVEN_TRIGGER", 1.0))
                        lock_trigger_mult = float(os.getenv("TRAIL_LOCK_TRIGGER", 2.0))
                        trail_step = float(os.getenv("TRAIL_STEP", 10.0))

                        be_threshold = sl_dist * be_trigger_mult
                        lock_threshold = sl_dist * lock_trigger_mult

                        new_sl = sl_price
                        modified = False

                        if signal == "BUY":
                            curr_price = prices["bid"]
                            if curr_price > pos["trail_highest"]:
                                pos["trail_highest"] = curr_price
                                modified = True
                            
                            unrealized = pos["trail_highest"] - entry_price

                            # Phase 3: TRAILING (progressive trail)
                            if pos["trail_phase"] in ["LOCKED", "TRAILING"] and unrealized >= lock_threshold:
                                trail_sl = entry_price + (unrealized - trail_step)
                                if trail_sl > new_sl:
                                    new_sl = trail_sl
                                    pos["trail_phase"] = "TRAILING"
                                    modified = True

                            # Phase 2: LOCK 50%
                            elif pos["trail_phase"] in ["BREAKEVEN", "INITIAL"] and unrealized >= lock_threshold:
                                trail_sl = entry_price + (unrealized * 0.5)
                                if trail_sl > new_sl:
                                    new_sl = trail_sl
                                    pos["trail_phase"] = "LOCKED"
                                    modified = True
                                    logger.info(f"🔥 [LIVE Phase 2 Lock] Ticket #{ticket} BUY SL -> {new_sl:.2f} (locked 50% of +{unrealized:.1f})")

                            # Phase 1: BREAKEVEN
                            elif pos["trail_phase"] == "INITIAL" and unrealized >= be_threshold:
                                trail_sl = entry_price + 2.0
                                if trail_sl > new_sl:
                                    new_sl = trail_sl
                                    pos["trail_phase"] = "BREAKEVEN"
                                    modified = True
                                    logger.info(f"🔥 [LIVE Phase 1 BE] Ticket #{ticket} BUY SL -> {new_sl:.2f} (breakeven at +{unrealized:.1f})")

                        elif signal == "SELL":
                            curr_price = prices["ask"]
                            if curr_price < pos["trail_lowest"]:
                                pos["trail_lowest"] = curr_price
                                modified = True
                            
                            unrealized = entry_price - pos["trail_lowest"]

                            # Phase 3: TRAILING (progressive trail)
                            if pos["trail_phase"] in ["LOCKED", "TRAILING"] and unrealized >= lock_threshold:
                                trail_sl = entry_price - (unrealized - trail_step)
                                if trail_sl < new_sl:
                                    new_sl = trail_sl
                                    pos["trail_phase"] = "TRAILING"
                                    modified = True

                            # Phase 2: LOCK 50%
                            elif pos["trail_phase"] in ["BREAKEVEN", "INITIAL"] and unrealized >= lock_threshold:
                                trail_sl = entry_price - (unrealized * 0.5)
                                if trail_sl < new_sl:
                                    new_sl = trail_sl
                                    pos["trail_phase"] = "LOCKED"
                                    modified = True
                                    logger.info(f"🔥 [LIVE Phase 2 Lock] Ticket #{ticket} SELL SL -> {new_sl:.2f} (locked 50% of +{unrealized:.1f})")

                            # Phase 1: BREAKEVEN
                            elif pos["trail_phase"] == "INITIAL" and unrealized >= be_threshold:
                                trail_sl = entry_price - 2.0
                                if trail_sl < new_sl:
                                    new_sl = trail_sl
                                    pos["trail_phase"] = "BREAKEVEN"
                                    modified = True
                                    logger.info(f"🔥 [LIVE Phase 1 BE] Ticket #{ticket} SELL SL -> {new_sl:.2f} (breakeven at +{unrealized:.1f})")

                        # If the target SL has changed, modify the position in MT5
                        if new_sl != sl_price:
                            success = self.mt5_connector.modify_position_sl_tp(ticket, new_sl, tp_price)
                            if success:
                                pos["stop_loss"] = new_sl
                                modified = True
                                try:
                                    self.discord_reporter.report_system_status(
                                        title=f"🔄 TRAILING STOP: ปรับจุดตัดขาดทุน (Phase: {pos['trail_phase']})",
                                        message=(
                                            f"Ticket: **#{ticket}** | สัญลักษณ์: **XAU/USD**\n"
                                            f"คำสั่ง: **{signal}** | ขนาด: **{pos['lot_size']:.2f} Lot**\n"
                                            f"ราคาเปิด: **${entry_price:.2f}**\n"
                                            f"ปรับ SL ใหม่: **${new_sl:.2f}**\n"
                                            f"ราคาตลาดปัจจุบัน: **${curr_price:.2f}**"
                                        ),
                                        color=16776960
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to send trailing stop Discord update: {e}")
                            else:
                                logger.error(f"Failed to modify SL on MT5 server for ticket #{ticket}")

                still_open.append(pos)
                continue

            # If not open, it has been closed! Let's get the deal details from MT5 history
            logger.info(f"🔔 Live Position #{ticket} has been closed! Querying history from MT5...")
            
            # Fetch history deals for this position
            if True:  # Already connected via mt5_connector
                deals = _mt5.history_deals_get(position=ticket)
            else:
                deals = None
            
            entry_price = pos["entry_price"]
            exit_price = pos["stop_loss"] # Fallback
            pnl_usd = 0.0
            close_comment = ""
            
            if deals:
                # Find the deal representing the exit (DEAL_ENTRY_OUT = 1)
                exit_deal = None
                for deal in deals:
                    if deal.entry == _mt5.DEAL_ENTRY_OUT or deal.entry == 1:
                        exit_deal = deal
                        break
                
                if exit_deal:
                    exit_price = exit_deal.price
                    pnl_usd = exit_deal.profit
                    close_comment = exit_deal.comment
                    logger.info(f"Found exit deal for #{ticket}: Price={exit_price:.2f}, Profit={pnl_usd:.2f}, Comment='{close_comment}'")
            else:
                logger.warning(f"Could not fetch deals for closed position #{ticket} from MT5 history. Using fallback calculations.")
                
            # Determine close reason
            close_reason = "MANUAL_CLOSE"
            
            # Check if comment contains sl/tp
            if close_comment and "[sl" in close_comment.lower():
                close_reason = "SL"
            elif close_comment and "[tp" in close_comment.lower():
                close_reason = "TP"
            # Or check distance to entry price for breakeven (within $1.50)
            elif abs(exit_price - entry_price) <= 1.5:
                close_reason = "BREAKEVEN"
            elif pos["signal"] == "BUY":
                if exit_price <= pos["stop_loss"] + 0.5:
                    close_reason = "SL"
                elif exit_price >= pos["take_profit"] - 0.5:
                    close_reason = "TP"
            elif pos["signal"] == "SELL":
                if exit_price >= pos["stop_loss"] - 0.5:
                    close_reason = "SL"
                elif exit_price <= pos["take_profit"] + 0.5:
                    close_reason = "TP"

            # Calculate pips
            pnl_pips = (exit_price - entry_price) * 10.0 if pos["signal"] == "BUY" else (entry_price - exit_price) * 10.0

            # Generate dynamic lesson learned using AI CEO or fallback
            lesson_learned = self._generate_reflection_lesson(pos, exit_price, pnl_usd, close_reason)

            # Append lesson to memory
            self.learning_memory.append(lesson_learned)
            logger.info(f"🧠 Live Trade Lesson Learned: {lesson_learned}")

            # ─── TRADE JOURNAL EXIT RECORDING (Integration Point 5 — live side) ───
            try:
                self.trade_journal.record_exit(
                    ticket=ticket,
                    exit_price=exit_price,
                    pnl_usd=pnl_usd,
                    close_reason=close_reason,
                    exit_reasoning=f"Live position #{ticket} closed: {close_reason}",
                    lesson_learned=lesson_learned,
                    exit_time=str(datetime.utcnow()),
                )
                # Keep RiskManager internal state in sync (no-op when journal
                # is managing streaks, but keeps fallback counters consistent).
                self.risk_manager.record_trade_result(
                    pnl_usd=pnl_usd,
                    close_reason=close_reason,
                    current_time=datetime.utcnow(),
                )
            except Exception as j_err:
                logger.debug(f"TradeJournal live exit update failed (non-fatal): {j_err}")

            # 📢 Send detailed closure report to Discord
            try:
                self.discord_reporter.report_order_closed(
                    signal=pos["signal"],
                    entry_price=entry_price,
                    close_price=exit_price,
                    lot_size=pos["lot_size"],
                    ticket=ticket,
                    pnl_usd=pnl_usd,
                    pnl_pips=pnl_pips,
                    close_reason=close_reason,
                    lesson_learned=lesson_learned
                )
            except Exception as e:
                logger.error(f"Failed to send Discord close report: {e}")

        # Update and save
        if len(still_open) < len(self.open_positions):
            if self.mode == "LIVE":
                self.last_trade_timestamp = str(datetime.now())
                self._save_live_state()
        self.open_positions = still_open
        self._save_live_positions()

    def export_results(self, filename: str = "backtest_results.json"):
        """Export analysis results to JSON"""
        import json
        with open(filename, 'w') as f:
            json.dump(self.analysis_history, f, indent=2, default=str)
        logger.info(f"Results exported to {filename}")
