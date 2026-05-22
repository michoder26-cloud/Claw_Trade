"""Configuration for XAU/USD Trading System"""
import os
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

class Config:
    """Base configuration"""
    # OpenRouter Configuration
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3-70b-instruct")

    # Trading Settings
    XAU_USD_SYMBOL = os.getenv("XAU_USD_SYMBOL", "GC=F")
    MT5_SYMBOL = os.getenv("MT5_SYMBOL", "XAUUSD")
    BACKTESTING_START_DATE = os.getenv("BACKTESTING_START_DATE", "2023-01-01")
    BACKTESTING_END_DATE = os.getenv("BACKTESTING_END_DATE", "2024-12-31")
    INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", 10000))
    POSITION_SIZE_PERCENT = float(os.getenv("POSITION_SIZE_PERCENT", 6.0))
    FIXED_LOT_SIZE = float(os.getenv("FIXED_LOT_SIZE", 0.0)) # Use 0 to enable dynamic scaling
    MAX_DAILY_TRADES = int(os.getenv("MAX_DAILY_TRADES", 10))

    # Risk Management
    MAX_DRAWDOWN_PERCENT = float(os.getenv("MAX_DRAWDOWN_PERCENT", 10.0))
    RISK_REWARD_RATIO = float(os.getenv("RISK_REWARD_RATIO", 1.5))
    MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", 2))
    BASE_LOT_SIZE = float(os.getenv("BASE_LOT_SIZE", 0.1))
    USE_FIXED_SL_TP = os.getenv("USE_FIXED_SL_TP", "false").lower() == "true"
    FIXED_SL_USD = float(os.getenv("FIXED_SL_USD", 10.0))
    FIXED_TP_USD = float(os.getenv("FIXED_TP_USD", 20.0))

    # ATR-Based Dynamic SL (Anti-SL Hunt Upgrade)
    ATR_PERIOD = int(os.getenv("ATR_PERIOD", 5))
    ATR_SL_MULTIPLIER = float(os.getenv("ATR_SL_MULTIPLIER", 1.0))

    # Multi-Phase Trailing Stop
    TRAIL_BREAKEVEN_TRIGGER = float(os.getenv("TRAIL_BREAKEVEN_TRIGGER", 1.0))  # Move SL to breakeven when profit >= 1.0x SL distance
    TRAIL_LOCK_TRIGGER = float(os.getenv("TRAIL_LOCK_TRIGGER", 2.0))  # Lock 50% profit when profit >= 2.0x SL distance
    TRAIL_STEP = float(os.getenv("TRAIL_STEP", 10.0))  # Progressive trail step size in USD

    # Data
    DATA_SOURCE = os.getenv("DATA_SOURCE", "yfinance")
    YFINANCE_INTERVAL = os.getenv("YFINANCE_INTERVAL", "1h")

    # Notifications
    SLACK_WEBHOOK_URL: Optional[str] = os.getenv("SLACK_WEBHOOK_URL")
    EMAIL_RECIPIENT: Optional[str] = os.getenv("EMAIL_RECIPIENT")

    @classmethod
    def validate(cls) -> bool:
        """Validate required configurations"""
        if not cls.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is required")
        return True

class BacktestConfig(Config):
    """Backtesting specific configuration"""
    MODE = "BACKTEST"
    PAPER_TRADING = False
    REAL_TRADING = False

class PaperTradingConfig(Config):
    """Paper trading configuration (simulated)"""
    MODE = "PAPER"
    PAPER_TRADING = True
    REAL_TRADING = False

class LiveTradingConfig(Config):
    """Live trading configuration"""
    MODE = "LIVE"
    PAPER_TRADING = False
    REAL_TRADING = True
    BROKER_API_KEY = os.getenv("BROKER_API_KEY")
    BROKER_ACCOUNT_ID = os.getenv("BROKER_ACCOUNT_ID")
