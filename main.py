#!/usr/bin/env python3
"""
XAU/USD Multi-Agent Trading System
Main entry point for backtesting and live trading
"""
import sys
import argparse
from datetime import datetime
from pathlib import Path

# Add project root and src to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import Config, BacktestConfig, PaperTradingConfig
from orchestrator import MasterOrchestrator
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_system.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_backtest(args):
    """Run backtesting"""
    logger.info("🧪 Starting Backtest Mode")

    orchestrator = MasterOrchestrator(mode="BACKTEST")
    orchestrator.load_market_data(
        symbol=args.symbol or "GC=F",
        start=args.start_date,
        end=args.end_date
    )

    report = orchestrator.run_backtest(sample_every_n=args.sample_rate)

    # Export results
    output_file = args.output or "backtest_results.json"
    orchestrator.export_results(output_file)
    logger.info(f"✅ Backtest completed. Results saved to {output_file}")

    return orchestrator

def run_paper_trading(args):
    """Run paper trading (simulated live on MT5 Demo)"""
    logger.info("📄 Starting Paper Trading Mode (Simulated live on MT5 Demo Account)")

    orchestrator = MasterOrchestrator(mode="PAPER")
    interval = getattr(args, 'interval', 60)
    orchestrator.run_live_trading_loop(interval_minutes=interval)

def run_live_trading(args):
    """Run live trading"""
    logger.info("⚠️ STARTING LIVE TRADING MODE")
    logger.warning("This will execute real trades with real money!")

    if not args.confirm:
        logger.error("Live trading requires --confirm flag")
        sys.exit(1)

    orchestrator = MasterOrchestrator(mode="LIVE")
    interval = getattr(args, 'interval', 60)
    orchestrator.run_live_trading_loop(interval_minutes=interval)

def main():
    """Main CLI"""
    parser = argparse.ArgumentParser(
        description="XAU/USD Multi-Agent Trading System"
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Backtest command
    backtest_parser = subparsers.add_parser('backtest', help='Run backtesting')
    backtest_parser.add_argument('--symbol', default='GC=F', help='Trading symbol (default: GC=F)')
    backtest_parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    backtest_parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    backtest_parser.add_argument('--sample-rate', type=int, default=24, help='Sample every N candles (default: 24)')
    backtest_parser.add_argument('--output', help='Output file for results (default: backtest_results.json)')

    # Paper trading command
    paper_parser = subparsers.add_parser('paper', help='Run paper trading (MT5 Demo)')
    paper_parser.add_argument('--symbol', default='GC=F', help='Trading symbol')
    paper_parser.add_argument('--interval', type=int, default=60, help='Trading check interval in minutes (default: 60)')

    # Live trading command
    live_parser = subparsers.add_parser('live', help='Run live trading (⚠️ REAL MONEY)')
    live_parser.add_argument('--confirm', action='store_true', help='Confirm live trading')
    live_parser.add_argument('--symbol', default='GC=F', help='Trading symbol')
    live_parser.add_argument('--interval', type=int, default=60, help='Trading check interval in minutes (default: 60)')

    # Config command
    config_parser = subparsers.add_parser('config', help='Show configuration')

    args = parser.parse_args()

    # Validate config
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Handle commands
    if args.command == 'backtest':
        run_backtest(args)
    elif args.command == 'paper':
        run_paper_trading(args)
    elif args.command == 'live':
        run_live_trading(args)
    elif args.command == 'config':
        logger.info("Current Configuration:")
        logger.info(f"  API Key: {'✓ Set' if Config.ANTHROPIC_API_KEY else '✗ Not set'}")
        logger.info(f"  Trading Mode: {getattr(args, 'mode', 'BACKTEST')}")
        logger.info(f"  Initial Balance: ${Config.INITIAL_BALANCE:,.2f}")
        logger.info(f"  Max Drawdown: {Config.MAX_DRAWDOWN_PERCENT}%")
        logger.info(f"  Risk per Trade: {Config.POSITION_SIZE_PERCENT}%")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
