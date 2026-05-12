"""Master Orchestrator - Coordinates all agents and trading execution"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
import time

from config import Config, BacktestConfig
from data_handler import DataHandler
from agents import QuantAnalyst, NewsAnalyst, BullAgent, BearAgent, CEOAgent
from backtester import Backtester
from mt5_connector import MT5Connector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MasterOrchestrator:
    """Master trading orchestrator - Coordinates the new hierarchical 5-Agent pipeline"""

    def __init__(self, mode: str = "BACKTEST"):
        self.mode = mode
        self.config = BacktestConfig if mode == "BACKTEST" else Config

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

        # Market data
        self.market_data: Optional[pd.DataFrame] = None
        self.analysis_history: List[Dict] = []
        
        # Track daily trades to reduce overtrading
        self.trades_today = 0
        self.last_trade_date: Optional[str] = None

        logger.info(f"Hierarchical Orchestrator initialized in {mode} mode")

    def load_market_data(self, symbol: str = "GC=F", start: str = None, end: str = None) -> pd.DataFrame:
        """Load and prepare market data"""
        logger.info("Loading market data...")
        self.market_data = self.data_handler.prepare_for_analysis(symbol, start, end)
        
        # Calculate EMA 50 & 200 for our Quant Analyst
        self.market_data['ema_50'] = self.market_data['close'].ewm(span=50, adjust=False).mean()
        self.market_data['ema_200'] = self.market_data['close'].ewm(span=200, adjust=False).mean()
        
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
        """Calculate standard Fibonacci Retracement levels from recent high/low"""
        if len(recent_data) < 50:
            return {}
        recent_window = recent_data.tail(50)
        high = recent_window['high'].max()
        low = recent_window['low'].min()
        diff = high - low
        
        return {
            "0.0% (High)": round(high, 2),
            "23.6%": round(high - 0.236 * diff, 2),
            "38.2%": round(high - 0.382 * diff, 2),
            "50.0%": round(high - 0.5 * diff, 2),
            "61.8%": round(high - 0.618 * diff, 2),
            "100.0% (Low)": round(low, 2)
        }

    def analyze_at_timestamp(self, timestamp: pd.Timestamp, row: pd.Series) -> Dict:
        """Runs the complete hierarchical 5-Agent pipeline at a given timestamp"""
        recent_data = self.market_data[:timestamp].tail(50)
        market_context = self.data_handler.format_market_context(recent_data, n_candles=10)
        
        # Determine regime and fibonacci levels in Python first
        regime = self._determine_regime(recent_data)
        fib_levels = self._calculate_fibonacci_levels(recent_data)
        
        current_date_str = str(timestamp)[:10]
        if self.last_trade_date != current_date_str:
            self.trades_today = 0
            self.last_trade_date = current_date_str

        analysis_record = {
            "timestamp": str(timestamp),
            "price": row['close'],
            "regime": regime,
            "agents_analysis": {}
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"📅 Analysis Time: {timestamp} | Regime: {regime}")
        logger.info(f"💰 Current Price: {row['close']:.2f}")

        # 🛡️ RULE 1: Block trades instantly in volatile/thin market regimes to safeguard winrate
        if regime in ["HIGH_VOLATILITY", "LOW_LIQUIDITY"]:
            logger.info(f"   ➜ Python Signal Engine blocked trade due to Regime: {regime}")
            analysis_record["trade_executed"] = False
            self.analysis_history.append(analysis_record)
            return analysis_record

        # 🛡️ RULE 2: Block trade if daily limit (3) reached
        if self.trades_today >= 3:
            logger.info("   ➜ Python Signal Engine blocked trade: Daily Trade Limit (3) reached!")
            analysis_record["trade_executed"] = False
            self.analysis_history.append(analysis_record)
            return analysis_record

        # Collect metrics for Quant Analyst
        indicators = {
            "close": row["close"],
            "rsi": row.get("rsi", 50.0),
            "macd": row.get("macd", 0.0),
            "macd_signal": row.get("macd_signal", 0.0),
            "ema_50": row.get("ema_50", row["close"]),
            "ema_200": row.get("ema_200", row["close"]),
            "fib_levels": fib_levels
        }

        # 1. Team Lead 1: Technical & Quant Analyst
        logger.info("🔍 Running Quant Technical Analysis (No trade decision)...")
        quant_res = self.quant_analyst.analyze(market_context, indicators)
        logger.info(f"   ➜ Quant Summary: {quant_res.get('technical_summary', '')[:80]}...")

        # 2. Team Lead 2: News & Fundamental Analyst
        logger.info("📰 Running Fundamental News Analysis (No trade decision)...")
        news_res = self.news_analyst.analyze()
        logger.info(f"   ➜ News Sentiment: {news_res.get('fundamental_bias', 'neutral')}")

        # 3. Advocate 1: Bull Agent (Argument FOR Buying)
        logger.info("🐂 Running Bull Agent (Biased BUY Advocate)...")
        bull_res = self.bull_agent.advocate(quant_res, news_res)
        logger.info(f"   ➜ Bull Conviction: {bull_res.get('conviction_score', 0.0)}")

        # 4. Advocate 2: Bear Agent (Argument FOR Selling)
        logger.info("🐻 Running Bear Agent (Biased SELL Advocate)...")
        bear_res = self.bear_agent.advocate(quant_res, news_res)
        logger.info(f"   ➜ Bear Conviction: {bear_res.get('conviction_score', 0.0)}")

        # 5. Supreme Decision Maker: Unbiased CEO
        logger.info("👔 CEO Agent balancing arguments and finalizing decision...")
        ceo_res = self.ceo_agent.decide(quant_res, news_res, bull_res, bear_res, regime)
        
        decision = ceo_res.get("decision", "NO_TRADE")
        confidence = ceo_res.get("confidence", 0.5)
        reasoning = ceo_res.get("reasoning", "")
        
        logger.info(f"   ➜ CEO Decision: {decision} | Confidence: {confidence:.2f}")
        logger.info(f"   ➜ CEO Reasoning: {reasoning}")

        analysis_record["agents_analysis"] = {
            "quant": quant_res,
            "news": news_res,
            "bull": bull_res,
            "bear": bear_res,
            "ceo": ceo_res
        }

        # Validate minimum decision confidence (60% threshold)
        if decision in ["BUY", "SELL"] and confidence >= 0.60:
            # S&R Risk Management Setup
            if getattr(self.config, "USE_FIXED_SL_TP", False):
                sl_distance = self.config.FIXED_SL_USD
                tp_distance = self.config.FIXED_TP_USD
            else:
                atr = row.get("atr", 2.0)
                sl_distance = max(atr * 3.5, 12.0)  # Institutional 3.5x ATR stop, min 12 USD
                tp_distance = sl_distance * self.config.RISK_REWARD_RATIO  # Use custom R:R Ratio from Config
            
            if decision == "BUY":
                sl_price = row['close'] - sl_distance
                tp_price = row['close'] + tp_distance
            else:
                sl_price = row['close'] + sl_distance
                tp_price = row['close'] - tp_distance

            # Dynamic lot calculation based on account balance and confidence
            balance = self.backtester.current_balance
            lot_size = max(0.01, self.config.BASE_LOT_SIZE * (confidence / 0.8))

            logger.info(f"   ➜ Executing {decision} | Sizing: {lot_size:.2f} | SL: {sl_price:.2f} | TP: {tp_price:.2f}")
            
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

        # Manage open backtest positions
        self.backtester.check_stop_levels(
            timestamp=str(timestamp),
            current_price=row['close'],
            high_price=row.get('high', row['close']),
            low_price=row.get('low', row['close'])
        )

        self.analysis_history.append(analysis_record)
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
        
        while True:
            try:
                prices = self.mt5_connector.get_price()
                if not prices:
                    logger.warning("Could not fetch current price. Retrying in 10 seconds...")
                    time.sleep(10)
                    continue
                
                current_price = prices["ask"]
                logger.info(f"\n[{datetime.now()}] Current Ask Price: {current_price:.2f}")

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
