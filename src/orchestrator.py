"""Master Orchestrator - Coordinates all agents and trading execution"""
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

from config import Config, BacktestConfig
from data_handler import DataHandler
from agents import NewsAnalyst, TechnicalAnalyst, RiskManager, ConsensusEngine
from backtester import Backtester
from mt5_connector import MT5Connector
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MasterOrchestrator:
    """Master trading orchestrator - Coordinates all analysis agents"""

    def __init__(self, mode: str = "BACKTEST"):
        self.mode = mode
        self.config = BacktestConfig if mode == "BACKTEST" else Config

        # Initialize agents
        self.news_analyst = NewsAnalyst()
        self.technical_analyst = TechnicalAnalyst()
        self.risk_manager = RiskManager()
        self.consensus_engine = ConsensusEngine()

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

        logger.info(f"Orchestrator initialized in {mode} mode")

    def load_market_data(self, symbol: str = "GC=F", start: str = None, end: str = None) -> pd.DataFrame:
        """Load and prepare market data"""
        logger.info("Loading market data...")
        self.market_data = self.data_handler.prepare_for_analysis(symbol, start, end)
        logger.info(f"Loaded {len(self.market_data)} candles")
        return self.market_data

    def analyze_at_timestamp(self, timestamp: pd.Timestamp, row: pd.Series) -> Dict:
        """Run complete analysis pipeline at a given timestamp"""

        # Prepare market context
        recent_data = self.data_handler.get_latest_candles(
            self.market_data[:timestamp], n=50
        )
        market_context = self.data_handler.format_market_context(recent_data, n_candles=10)

        analysis_record = {
            "timestamp": str(timestamp),
            "price": row['close'],
            "agents_analysis": {}
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"📅 Analysis Time: {timestamp}")
        logger.info(f"💰 Current Price: {row['close']:.2f}")

        # 1. Technical Analysis
        logger.info("🔍 Running Technical Analysis...")
        tech_result = self.technical_analyst.analyze(market_context)
        analysis_record["agents_analysis"]["technical"] = {
            "signal": tech_result.signal,
            "confidence": tech_result.confidence,
            "reasoning": tech_result.reasoning
        }
        logger.info(f"   ➜ Signal: {tech_result.signal} | Confidence: {tech_result.confidence}%")

        # 2. News/Fundamental Analysis
        logger.info("📰 Running News Analysis...")
        news_result = self.news_analyst.analyze(market_context)
        analysis_record["agents_analysis"]["news"] = {
            "signal": news_result.signal,
            "confidence": news_result.confidence,
            "reasoning": news_result.reasoning
        }
        logger.info(f"   ➜ Signal: {news_result.signal} | Confidence: {news_result.confidence}%")

        # 3. Consensus Decision
        logger.info("🤝 Running Consensus Engine...")
        final_signal, consensus_conf, consensus_reasoning = self.consensus_engine.decide(
            [tech_result, news_result]
        )
        analysis_record["agents_analysis"]["consensus"] = {
            "signal": final_signal,
            "confidence": consensus_conf,
            "reasoning": consensus_reasoning
        }
        logger.info(f"   ➜ Final Signal: {final_signal} | Confidence: {consensus_conf}%")

        # 4. Risk Management (only if signal is BUY or SELL)
        if final_signal in ["BUY", "SELL"]:
            logger.info("⚖️ Running Risk Manager...")

            # Get suggested stop loss from technical analyst response and validate direction
            sl_price = 0.0
            try:
                tech_data = eval(tech_result.raw_response)
                sl_price = tech_data.get("stop_loss_level", 0.0)
            except:
                pass

            # Safety validation: Ensure Stop Loss matches the direction of final_signal!
            if final_signal == "BUY":
                if sl_price <= 0.0 or sl_price >= row['close']:
                    sl_price = row['close'] * 0.99
            elif final_signal == "SELL":
                if sl_price <= 0.0 or sl_price <= row['close']:
                    sl_price = row['close'] * 1.01

            risk_calc = self.risk_manager.calculate(
                account_balance=self.backtester.current_balance,
                signal=final_signal,
                atr=row.get('atr', 0.5),
                entry_price=row['close'],
                stop_loss=sl_price
            )

            analysis_record["agents_analysis"]["risk"] = risk_calc

            if "error" not in risk_calc:
                logger.info(f"   ➜ Position Size: {risk_calc.get('position_size', 0):.2f}")
                logger.info(f"   ➜ SL: {risk_calc.get('stop_loss', 0):.2f} | TP1: {risk_calc.get('take_profit_1', 0):.2f}")

                # Execute trade
                trade_executed = self.backtester.execute_trade(
                    timestamp=str(timestamp),
                    price=row['close'],
                    signal=final_signal,
                    position_size=risk_calc.get('position_size', 1.0),
                    stop_loss=risk_calc.get('stop_loss', sl_price),
                    take_profit=risk_calc.get('take_profit_1', row['close'] * 1.05)
                )
                analysis_record["trade_executed"] = trade_executed
        else:
            logger.info("⏭️ Skipping trade execution (Signal: HOLD)")
            analysis_record["trade_executed"] = False

        # Check open positions
        self.backtester.check_stop_levels(
            timestamp=str(timestamp),
            current_price=row['close'],
            high_price=row.get('high', row['close']),
            low_price=row.get('low', row['close'])
        )

        self.analysis_history.append(analysis_record)
        return analysis_record

    def run_backtest(self, sample_every_n: int = 24) -> str:
        """Run complete backtest"""
        if self.market_data is None:
            self.load_market_data()

        logger.info(f"\n{'#'*60}")
        logger.info("🚀 STARTING BACKTEST")
        logger.info(f"{'#'*60}")
        logger.info(f"Date Range: {self.market_data.index[0]} to {self.market_data.index[-1]}")
        logger.info(f"Total Candles: {len(self.market_data)}")
        logger.info(f"Analysis Sample Rate: Every {sample_every_n} candles\n")

        # Run analysis every N candles (to save API calls)
        for idx in range(0, len(self.market_data), sample_every_n):
            timestamp = self.market_data.index[idx]
            row = self.market_data.iloc[idx]

            try:
                self.analyze_at_timestamp(timestamp, row)
            except Exception as e:
                logger.error(f"Error during analysis at {timestamp}: {e}")
                continue

        # Close all remaining positions at end of backtest
        if self.backtester.open_positions:
            last_price = self.market_data['close'].iloc[-1]
            self.backtester.close_all_positions(
                str(self.market_data.index[-1]),
                last_price
            )

        # Generate report
        report = self.backtester.get_report()
        logger.info(report)

        return report

    def run_live_trading_loop(self, interval_minutes: int = 60):
        """
        Runs the live trading or paper trading loop using MT5
        """
        logger.info(f"🚀 STARTING LIVE AUTOMATED TRADING LOOP (Interval: {interval_minutes} minutes)")
        logger.info("Initializing connection to MetaTrader 5...")
        
        if not self.mt5_connector.connect():
            logger.error("❌ Failed to connect to MetaTrader 5. Make sure the MT5 terminal app is open on your computer!")
            return

        logger.info("✅ Connection established! Monitoring XAU/USD in real-time...")
        
        while True:
            try:
                # Fetch latest prices from MT5
                prices = self.mt5_connector.get_price()
                if not prices:
                    logger.warning("Could not fetch current price. Retrying in 10 seconds...")
                    time.sleep(10)
                    continue
                
                current_price = prices["ask"]
                logger.info(f"\n[{datetime.now()}] Current Ask Price: {current_price:.2f}")

                # Fetch recent historical data (e.g. last 50 hours of 1-hour candles) from yfinance for technical indicators
                logger.info("Fetching recent chart data for indicators...")
                # Fetch slightly more days to ensure we have enough candles after dropping NA
                df = self.data_handler.prepare_for_analysis(
                    symbol=self.config.XAU_USD_SYMBOL, 
                    start=(datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
                    end=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                )

                if df.empty or len(df) < 20:
                    logger.error("Not enough market data fetched. Retrying in 60 seconds...")
                    time.sleep(60)
                    continue

                latest_row = df.iloc[-1]
                market_context = self.data_handler.format_market_context(df, n_candles=10)

                # 1. Technical Analysis
                logger.info("🔍 Running Technical Analysis...")
                tech_result = self.technical_analyst.analyze(market_context)
                logger.info(f"   ➜ Signal: {tech_result.signal} | Confidence: {tech_result.confidence}%")

                # 2. News/Fundamental Analysis
                logger.info("📰 Running News Analysis...")
                news_result = self.news_analyst.analyze(market_context)
                logger.info(f"   ➜ Signal: {news_result.signal} | Confidence: {news_result.confidence}%")

                # 3. Consensus Decision
                logger.info("🤝 Running Consensus Engine...")
                final_signal, consensus_conf, consensus_reasoning = self.consensus_engine.decide(
                    [tech_result, news_result]
                )
                logger.info(f"   ➜ Final Signal: {final_signal} | Confidence: {consensus_conf}%")

                # 4. Order Execution via MT5
                if final_signal in ["BUY", "SELL"]:
                    logger.info(f"⚖️ Running Risk Manager for {final_signal} signal...")
                    
                    # Calculate Stop Loss with safety validation
                    sl_price = 0.0
                    try:
                        tech_data = eval(tech_result.raw_response)
                        sl_price = tech_data.get("stop_loss_level", 0.0)
                    except:
                        pass

                    # Safety validation: Ensure Stop Loss matches the direction of final_signal!
                    if final_signal == "BUY":
                        if sl_price <= 0.0 or sl_price >= current_price:
                            sl_price = current_price * 0.99
                    elif final_signal == "SELL":
                        if sl_price <= 0.0 or sl_price <= current_price:
                            sl_price = current_price * 1.01

                    # Query account balance from MT5 or mock
                    balance = 10000.0  # Default demo balance
                    try:
                        import MetaTrader5 as mt5
                        account_info = mt5.account_info()
                        if account_info:
                            balance = account_info.balance
                    except:
                        pass

                    risk_calc = self.risk_manager.calculate(
                        account_balance=balance,
                        signal=final_signal,
                        atr=latest_row.get('atr', 2.0),
                        entry_price=current_price,
                        stop_loss=sl_price
                    )

                    if "error" not in risk_calc:
                        lot_size = risk_calc.get("position_size", 0.01)
                        # Ensure standard MT5 lot limits (min 0.01)
                        if lot_size < 0.01:
                            lot_size = 0.01
                        
                        tp_price = risk_calc.get("take_profit_1", current_price * 1.05 if final_signal == "BUY" else current_price * 0.95)
                        
                        logger.info(f"💰 Account Balance: ${balance:,.2f}")
                        logger.info(f"⚡ Executing on MetaTrader 5 Demo Account...")
                        logger.info(f"   ➜ Lot Size: {lot_size} | SL: {sl_price:.2f} | TP: {tp_price:.2f}")
                        
                        # Send trade to MT5!
                        result = self.mt5_connector.execute_market_order(
                            signal=final_signal,
                            volume=lot_size,
                            stop_loss=sl_price,
                            take_profit=tp_price
                        )
                        if result:
                            logger.info(f"🎉 Trade successfully placed! Ticket: {result.get('ticket')}")
                        else:
                            logger.error("❌ Trade order rejected by MT5 terminal.")
                else:
                    logger.info("⏭️ Signal is HOLD. No orders sent to MT5.")

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

def main():
    """Main execution"""
    # Validate config
    Config.validate()

    # Initialize orchestrator
    orchestrator = MasterOrchestrator(mode="BACKTEST")

    # Run backtest (sample every 24 hours to reduce API calls)
    orchestrator.run_backtest(sample_every_n=24)

    # Export results
    orchestrator.export_results("backtest_results.json")

if __name__ == "__main__":
    main()
