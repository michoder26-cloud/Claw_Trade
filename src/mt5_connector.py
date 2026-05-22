"""MetaTrader 5 Connector for XAU/USD Trading Automation"""
import os
import logging
import pandas as pd
from typing import Dict, Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MT5Connector:
    """Manages connection and order execution on MetaTrader 5"""

    def __init__(self):
        # Priority: 1. MT5_SYMBOL, 2. XAU_USD_SYMBOL (with cleanup), 3. Default "XAUUSD"
        self.symbol = os.getenv("MT5_SYMBOL") or os.getenv("XAU_USD_SYMBOL", "XAUUSD").replace("/", "").replace("GC=F", "XAUUSD")
        self.login_id = os.getenv("MT5_LOGIN")
        self.password = os.getenv("MT5_PASSWORD")
        self.server = os.getenv("MT5_SERVER")
        self.magic_number = 20260511  # Unique ID for this bot's trades
        self.initialized = False

    def connect(self) -> bool:
        """Initialize connection and login to MT5"""
        if mt5 is None:
            logger.error("MetaTrader5 library is not installed. Run 'pip install MetaTrader5'")
            return False

        if self.initialized:
            return True

        logger.info("Initializing MetaTrader 5...")
        if not mt5.initialize():
            logger.error(f"mt5.initialize() failed. Error code: {mt5.last_error()}")
            return False

        # If credentials are provided in .env, log in.
        # Otherwise, MT5 will just use the currently active account in the opened MT5 app!
        if self.login_id and self.password and self.server:
            logger.info(f"Logging in to MT5 Server: {self.server} (Account: {self.login_id})...")
            try:
                login_num = int(self.login_id)
                authorized = mt5.login(
                    login=login_num,
                    password=self.password,
                    server=self.server
                )
                if not authorized:
                    logger.error(f"MT5 login failed. Error code: {mt5.last_error()}")
                    return False
                logger.info("✅ Successfully logged in to MT5 Demo Account!")
            except ValueError:
                logger.error("MT5_LOGIN in .env must be a number.")
                return False
        else:
            logger.info("ℹ️ No login credentials in .env. MT5 will use the currently active terminal account.")

        self.initialized = True
        return True

    def get_price(self) -> Optional[Dict[str, float]]:
        """Get current live Ask and Bid prices for gold symbol"""
        if not self.connect():
            return None

        # Select symbol
        if not mt5.symbol_select(self.symbol, True):
            logger.warning(f"Symbol '{self.symbol}' not found in MetaTrader 5. Trying alternative gold symbols...")
            alternatives = ["XAUUSD", "GOLD", "XAUUSD.m", "XAUUSD.", "XAUUSD.i", "XAUUSD_"]
            found = False
            for alt in alternatives:
                if mt5.symbol_select(alt, True):
                    logger.info(f"✅ Found and selected alternative gold symbol: '{alt}'")
                    self.symbol = alt
                    found = True
                    break
            if not found:
                logger.error("❌ Could not find any valid Gold symbol in MT5. Please make sure XAUUSD or GOLD is added to your MT5 'Market Watch' window!")
                return None

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            logger.error(f"Failed to get tick info for {self.symbol}. Error: {mt5.last_error()}")
            return None

        return {
            "ask": tick.ask,
            "bid": tick.bid,
            "last": tick.last
        }

    def execute_market_order(self, signal: str, volume: float = 0.01,
                             stop_loss: float = 0.0, take_profit: float = 0.0) -> Optional[Dict]:
        """
        Send a market buy or sell order to MT5

        Args:
            signal: "BUY" or "SELL"
            volume: Lot size (e.g. 0.01, 0.10)
            stop_loss: Price level for SL
            take_profit: Price level for TP
        """
        if not self.connect():
            return None

        prices = self.get_price()
        if not prices:
            return None

        order_type = mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL
        price = prices["ask"] if signal == "BUY" else prices["bid"]

        # Prepare trade request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": float(stop_loss) if stop_loss > 0 else 0.0,
            "tp": float(take_profit) if take_profit > 0 else 0.0,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": "Antigravity AI Trading Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,  # Standard filling type
        }

        logger.info(f"Sending MT5 Order: {signal} {volume} Lot at {price:.2f} (SL: {stop_loss:.2f}, TP: {take_profit:.2f})...")
        result = mt5.order_send(request)

        if result is None:
            logger.error(f"MT5 Order execution failed entirely. Error: {mt5.last_error()}")
            return None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"MT5 Order rejected. Retcode: {result.retcode}. Error details: {result.comment}")
            # Try with alternative filling type if rejected due to filling
            if "filling" in result.comment.lower() or result.retcode in [10030, 10029]:
                logger.info("Retrying with ORDER_FILLING_FOK...")
                request["type_filling"] = mt5.ORDER_FILLING_FOK
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info("✅ Order successful on second attempt with FOK filling!")
                    return self._format_result(result)
            return None

        logger.info(f"✅ MT5 Order executed successfully! Ticket: {result.order}")
        return self._format_result(result)

    def close_all_bot_positions(self) -> int:
        """Close all positions opened by this bot (filtering by magic number)"""
        if not self.connect():
            return 0

        positions = mt5.positions_get(magic=self.magic_number)
        if positions is None or len(positions) == 0:
            logger.info("No open positions found for this bot.")
            return 0

        closed_count = 0
        for pos in positions:
            symbol = pos.symbol
            volume = pos.volume
            ticket = pos.ticket
            pos_type = pos.type  # 0 for BUY, 1 for SELL

            prices = self.get_price()
            if not prices:
                continue

            # Opposite trade to close
            close_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            close_price = prices["bid"] if pos_type == mt5.ORDER_TYPE_BUY else prices["ask"]

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": close_type,
                "position": ticket,
                "price": close_price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": "Close Position",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            logger.info(f"Closing position #{ticket} ({volume} Lot)...")
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                closed_count += 1
                logger.info(f"✅ Closed position #{ticket} successfully!")
            else:
                logger.error(f"Failed to close position #{ticket}. Error: {mt5.last_error()}")

        return closed_count

    def modify_position_sl_tp(self, ticket: int, stop_loss: float, take_profit: float) -> bool:
        """Modify stop loss and take profit for an open position on MT5"""
        if not self.connect() or mt5 is None:
            return False

        # Fetch position details to verify it exists and get its symbol
        position = mt5.positions_get(ticket=ticket)
        if position is None or len(position) == 0:
            logger.error(f"Position ticket #{ticket} not found on MT5 server.")
            return False

        pos = position[0]
        symbol = pos.symbol

        # Prepare modification request
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": float(stop_loss),
            "tp": float(take_profit),
        }

        logger.info(f"Modifying position #{ticket} on MT5 (SL: {pos.sl:.2f} -> {stop_loss:.2f}, TP: {pos.tp:.2f} -> {take_profit:.2f})...")
        result = mt5.order_send(request)

        if result is None:
            logger.error(f"MT5 position modification failed entirely. Error: {mt5.last_error()}")
            return False

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"MT5 position modification rejected. Retcode: {result.retcode}. Comment: {result.comment}")
            return False

        logger.info(f"✅ MT5 Position #{ticket} modified successfully!")
        return True

    def get_account_info(self):
        """Fetch MT5 account information"""
        if not self.connect() or mt5 is None:
            return None
        return mt5.account_info()

    def is_position_open(self, ticket: int) -> bool:
        """Check if a specific position ticket is still active in MT5"""
        if not self.connect() or mt5 is None:
            return False
        pos = mt5.positions_get(ticket=ticket)
        return pos is not None and len(pos) > 0

    def _format_result(self, result) -> Dict:
        """Format order execution result to standard dictionary"""
        return {
            "ticket": result.order,
            "retcode": result.retcode,
            "volume": result.volume,
            "price": result.price,
            "comment": result.comment
        }

    def fetch_historical_data(self, start_date: str, end_date: str, timeframe: str = "5m") -> Optional[pd.DataFrame]:
        """Fetch historical rates from MT5 broker servers"""
        if not self.connect() or mt5 is None:
            return None

        timeframe_map = {
            "1m": mt5.TIMEFRAME_M1,
            "5m": mt5.TIMEFRAME_M5,
            "15m": mt5.TIMEFRAME_M15,
            "1h": mt5.TIMEFRAME_H1,
            "1d": mt5.TIMEFRAME_D1
        }
        tf = timeframe_map.get(timeframe, mt5.TIMEFRAME_M5)

        try:
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            rates = mt5.copy_rates_range(self.symbol, tf, start_dt, end_dt)
            if rates is None or len(rates) == 0:
                logger.warning(f"No historical rates found on MT5 server for {self.symbol} ({timeframe}).")
                return None

            df = pd.DataFrame(rates)
            df['datetime'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('datetime', inplace=True)
            
            # Rename MT5 columns to match yfinance expected column names
            df.rename(columns={"tick_volume": "volume"}, inplace=True)
            return df[['open', 'high', 'low', 'close', 'volume']]
        except Exception as e:
            logger.error(f"Error fetching MT5 historical data: {e}")
            return None

    def shutdown(self):
        """Disconnect from MT5"""
        if self.initialized and mt5 is not None:
            mt5.shutdown()
            self.initialized = False
            logger.info("MetaTrader 5 connection closed.")
