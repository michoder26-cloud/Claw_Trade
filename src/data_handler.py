"""Data fetching and preprocessing for XAU/USD"""
import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Tuple
from config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataHandler:
    """Handles data fetching, cleaning, and preprocessing"""

    @staticmethod
    def fetch_gold_price(symbol: str = "GC=F", start: str = None, end: str = None, interval: str = "1h") -> pd.DataFrame:
        """
        Fetch gold (XAU/USD) price data from Yahoo Finance

        Args:
            symbol: Ticker symbol (default: GC=F for gold futures)
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            interval: Interval (1m, 5m, 15m, 1h, 1d)

        Returns:
            DataFrame with OHLCV data
        """
        try:
            start = start or Config.BACKTESTING_START_DATE
            end = end or Config.BACKTESTING_END_DATE
            data_source = os.getenv("DATA_SOURCE", "yfinance").lower()

            # 1. Check if MT5 data source is requested
            if data_source == "mt5":
                logger.info(f"Attempting to fetch {interval} historical data from MetaTrader 5 server...")
                try:
                    from mt5_connector import MT5Connector
                    mt5_conn = MT5Connector()
                    df = mt5_conn.fetch_historical_data(start, end, timeframe=interval)
                    if df is not None and not df.empty:
                        logger.info(f"✅ Successfully fetched {len(df)} candles from MT5 server!")
                        # Optionally save to CSV for future offline backtesting
                        df.to_csv("mt5_historical_data.csv")
                        return df
                except Exception as ex:
                    logger.warning(f"MT5 historical fetch failed: {ex}. Checking local CSV cache...")

                # 2. Check local CSV cache for offline MT5 backtesting
                if os.path.exists("mt5_historical_data.csv"):
                    logger.info("Loading historical data from local mt5_historical_data.csv cache...")
                    df = pd.read_csv("mt5_historical_data.csv", index_col=0, parse_dates=True)
                    # Filter by requested date range
                    try:
                        df = df.loc[start:end]
                    except Exception:
                        pass
                    if not df.empty:
                        logger.info(f"✅ Loaded {len(df)} cached MT5 candles.")
                        return df

            # 3. Fallback to Yahoo Finance (yfinance)
            if symbol.upper() in ["XAU/USD", "XAUUSD", "GOLD", "GC=F"]:
                symbol = "GC=F"

            logger.info(f"Fetching {symbol} data from Yahoo Finance ({start} -> {end})...")
            data = yf.download(
                symbol,
                start=start,
                end=end,
                interval=interval,
                progress=False
            )

            if data is None or len(data) == 0:
                raise ValueError(f"No data found for {symbol} on Yahoo Finance (possibly out of interval range).")

            # Flatten MultiIndex columns if present (e.g. from yfinance downloads)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [col[0].lower() for col in data.columns]
            else:
                data.columns = [col.lower() for col in data.columns]

            logger.info(f"Fetched {len(data)} candles from Yahoo Finance.")
            return data

        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            raise

    @staticmethod
    def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate common technical indicators"""

        # RSI (14-period)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # Bollinger Bands (14-period, 2 std dev - per boss screenshot)
        bb_period = 14
        bb_std = 2
        df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
        bb_std_dev = df['close'].rolling(window=bb_period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std_dev * bb_std)
        df['bb_lower'] = df['bb_middle'] - (bb_std_dev * bb_std)

        # Boss Specific Moving Averages
        df['ema_5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['sma_36'] = df['close'].rolling(window=36).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
        df['ema_macro'] = df['close'].ewm(span=288, adjust=False).mean()
        
        # ATR (Average True Range) - 14 period
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = abs(df['high'] - df['close'].shift())
        df['low_close'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=14).mean()

        # Volume indicators
        df['volume_sma'] = df['volume'].rolling(window=20).mean()

        return df.dropna()

    @staticmethod
    def prepare_for_analysis(symbol: str = "GC=F", start: str = None, end: str = None, interval: str = "1h") -> pd.DataFrame:
        """
        Complete pipeline: fetch + calculate indicators

        Returns:
            DataFrame ready for analysis
        """
        df = DataHandler.fetch_gold_price(symbol, start, end, interval=interval)
        df = DataHandler.calculate_technical_indicators(df)
        return df

    @staticmethod
    def get_latest_candles(df: pd.DataFrame, n: int = 50) -> pd.DataFrame:
        """Get latest N candles for analysis"""
        return df.tail(n)

    @staticmethod
    def format_market_context(df: pd.DataFrame, n_candles: int = 10) -> str:
        """Format recent market data as readable context"""
        recent = df.tail(n_candles).copy()
        context = "📊 Recent Market Context (XAU/USD):\n"
        context += f"Latest {n_candles} candles:\n"

        for idx, row in recent.iterrows():
            context += f"  {idx}: O={row['open']:.2f}, H={row['high']:.2f}, L={row['low']:.2f}, C={row['close']:.2f} | "
            context += f"RSI={row.get('rsi', 0):.1f}, MACD={row.get('macd', 0):.4f}, ATR={row.get('atr', 0):.2f}\n"

        return context
