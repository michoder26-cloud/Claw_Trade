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
from agents import QuantAnalyst, NewsAnalyst, BullAgent, BearAgent, CEOAgent
from backtester import Backtester
from mt5_connector import MT5Connector
from discord_reporter import DiscordReporter

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

        # Initialize backtester
        self.backtester = Backtester(
            initial_balance=self.config.INITIAL_BALANCE,
            max_open_positions=self.config.MAX_OPEN_POSITIONS
        )

        # Data handler
        self.data_handler = DataHandler()

        # Initialize MT5 Connector
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

        logger.info(f"Hierarchical Orchestrator initialized in {mode} mode")

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

    def _calculate_fibonacci_levels(self, recent_data: pd.DataFrame) -> Dict[str, float]:
        """Calculate standard Fibonacci Retracement levels across full macro baseline (1200 candles / 50 trading days)"""
        if len(recent_data) < 50:
            return {}
        high = recent_data['high'].max()
        low = recent_data['low'].min()
        diff = high - low
        
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

    def is_golden_hour(self, current_time: datetime) -> bool:
        """
        Expanded Golden Hour Filter (UTC) for H1 Strategy:
        - Tokyo/London Transition: 04:00 - 10:59 UTC
        - New York Main Session: 12:00 - 17:59 UTC
        """
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

        # 🛡️ Boss Filter 1: Check Daily Trade Limit (Max 1 trade/day)
        if self.trades_today >= 1:
            logger.info(f"   ➜ Sniper Engine: Daily limit reached (1 trade max). Standing aside.")
            return {"status": "SKIPPED", "reason": "DAILY_LIMIT_REACHED"}

        # 🛡️ Boss Filter 2: Check Golden Hour Filter (UTC)
        if not self.is_golden_hour(timestamp):
            logger.info(f"   ➜ Sniper Engine: Outside Golden Hours (Hour: {timestamp.hour} UTC). Standing aside.")
            return {"status": "SKIPPED", "reason": "OUTSIDE_GOLDEN_HOURS"}

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

        # Calculate local Support/Resistance over the last 24 H1 bars (excluding current bar)
        h1_lookback = daily_data.iloc[:-1].tail(24)
        if not h1_lookback.empty:
            local_support = h1_lookback['low'].min()
            local_resistance = h1_lookback['high'].max()
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
            "ceo": ceo_res
        }

        # Validate minimum decision confidence (78% threshold for SMC setups)
        if decision in ["BUY", "SELL"] and confidence >= 0.78:
            # 👑 Boss Sniper Adaptive Rule: 1:2 Ratio adjusted dynamically based on market volatility
            if regime == "HIGH_VOLATILITY":
                sl_distance = 25.0
                tp_distance = 50.0
                logger.info(f"   🎯 Boss Sniper [HIGH VOLATILITY MODE]: Set dynamic {tp_distance}/{sl_distance} (1:2 R:R)")
            else:
                sl_distance = 15.0
                tp_distance = 30.0
                logger.info(f"   🎯 Boss Sniper [STANDARD MODE]: Set standard {tp_distance}/{sl_distance} (1:2 R:R)")
            
            if decision == "BUY":
                sl_price = row['close'] - sl_distance
                tp_price = row['close'] + tp_distance
            else:
                sl_price = row['close'] + sl_distance
                tp_price = row['close'] - tp_distance

            # Dynamic Risk-Based Position Sizing (Money Management)
            balance = self.backtester.current_balance
            contract_size = 100.0  # Standard MT5 Gold Contract Size
            
            fixed_lot = getattr(self.config, "FIXED_LOT_SIZE", 1.0)
            if fixed_lot and float(fixed_lot) > 0:
                lot_size = float(fixed_lot)
            else:
                # User Master Directive: Risk exactly 15% of portfolio per trade to scale monthly profit to $130+ USD (13,000+ Cents)
                risk_percent = getattr(self.config, "POSITION_SIZE_PERCENT", 15.0)
                risk_amount = balance * (risk_percent / 100.0)
                computed_lot = risk_amount / (sl_distance * contract_size)
                lot_size = max(0.01, round(computed_lot, 2))
            
            # Aggressive Scaling: Triple lot size if CEO is extremely confident
            ceo_confidence = ceo_res.get("confidence", 0.85)
            if ceo_confidence >= 0.95:
                lot_size *= 3.0  # Triple power
                logger.info(f"   🔥 ULTRA CONVICTION DETECTED ({ceo_confidence*100:.0f}%): Scaling Lot Size to {lot_size:.2f} (3x)")
            elif ceo_confidence >= 0.90:
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
                    try:
                        self.discord_reporter.report_order_opened(
                            signal=decision,
                            entry_price=row['close'],
                            sl_price=sl_price,
                            tp_price=tp_price,
                            lot_size=lot_size,
                            ticket=live_order.get('ticket') if live_order else None,
                            confidence=confidence,
                            regime=regime,
                            quant_summary=quant_res.get('technical_summary', 'N/A'),
                            news_summary=news_res.get('fundamental_bias', 'N/A'),
                            bull_argument=bull_res.get('reasoning', 'N/A'),
                            bear_argument=bear_res.get('reasoning', 'N/A'),
                            ceo_reasoning=reasoning
                        )
                    except Exception as dr_err:
                        logger.error(f"Discord report failed: {dr_err}")
            else:
                trade_executed = self.backtester.execute_trade(
                    timestamp=str(timestamp),
                    price=row['close'],
                    signal=decision,
                    position_size=lot_size,
                    stop_loss=sl_price,
                    take_profit=tp_price
                )
            analysis_record["trade_executed"] = trade_executed
            if trade_executed:
                self.trades_today += 1
        else:
            logger.info("   ➜ Skipping: NO_TRADE or Low Confidence")
            analysis_record["trade_executed"] = False

        # Manage open backtest positions and capture feedback
        closed_trades = self.backtester.check_stop_levels(
            timestamp=str(timestamp),
            current_price=row['close'],
            high_price=row.get('high', row['close']),
            low_price=row.get('low', row['close'])
        )
        
        # 🧠 LEARNING: Update memory with trade results
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

        self.analysis_history.append(analysis_record)
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

        # Run cycle
        for idx in range(0, len(self.market_data), sample_every_n):
            timestamp = self.market_data.index[idx]
            row = self.market_data.iloc[idx]

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
            self.discord_reporter.report_system_status(
                title="🚀 GOLD SNIPER AI: ONLINE",
                message="บอทเริ่มทำงานในโหมด LIVE เรียบร้อยแล้วครับ!\nสแตนด์บายเฝ้าทองคำด้วยกลยุทธ์ Boss Sniper 1:3 🏹"
            )
        except: pass
        
        while True:
            try:
                prices = self.mt5_connector.get_price()
                if not prices:
                    logger.warning("Could not fetch current price. Retrying in 10 seconds...")
                    time.sleep(10)
                    continue
                
                current_price = prices["ask"]
                now = datetime.now()
                logger.info(f"\n[{now}] Current Ask Price: {current_price:.2f}")

                # Fetch recent historical data from yfinance for technical indicators
                df = self.data_handler.prepare_for_analysis(
                    symbol=self.config.XAU_USD_SYMBOL, 
                    start=(datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d"),
                    end=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < 20:
                    logger.error("Not enough market data fetched. Retrying in 60 seconds...")
                    time.sleep(60)
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
                if self.mode == "LIVE" and now.hour % 3 == 0 and now.minute < interval_minutes:
                    try:
                        self.discord_reporter.report_system_status(
                            title="🟢 AUTO-TRADE STATUS: บอททำงานปกติ",
                            message=f"สแตนด์บายเฝ้าทองคำ XAU/USD ในตลาดจริง\nราคาทองปัจจุบัน: ${current_price:.2f}"
                        )
                    except: pass
                
                # Doraemon Scheduled Audit: Every Saturday at 10:00 AM, trigger automated reflection engine
                if now.weekday() == 5 and now.hour == 10:
                    try:
                        from agents import TradeReflectionEngine
                        TradeReflectionEngine.run_weekly_reflection("trade_history_log.json")
                    except Exception as ex:
                        logger.error(f"Reflection trigger failed: {ex}")

            except Exception as e:
                logger.error(f"Error in trading loop: {e}")

            logger.info(f"Sleeping for {interval_minutes} minutes...")
            time.sleep(interval_minutes * 60)

    def export_results(self, filename: str = "backtest_results.json"):
        """Export analysis results to JSON"""
        import json
        with open(filename, 'w') as f:
            json.dump(self.analysis_history, f, indent=2, default=str)
        logger.info(f"Results exported to {filename}")
