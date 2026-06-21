"""MetaApi Cloud Connector for XAU/USD Trading Automation
Drop-in replacement for mt5_connector.py that works on Linux via MetaAPI.cloud

Prerequisites:
1. Sign up at https://metaapi.cloud (free tier available)
2. Get your API token from the dashboard
3. Set in .env: METAAPI_TOKEN, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
"""
import os
import logging
import pandas as pd
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MetaApiConnector:
    """Manages connection and order execution via MetaAPI.cloud (MT5 cloud API)
    
    Works on any OS (Linux, Mac, Windows). No local MT5 terminal needed.
    """

    def __init__(self):
        self.token = os.getenv("METAAPI_TOKEN", "")
        self.login_id = os.getenv("MT5_LOGIN")
        self.password = os.getenv("MT5_PASSWORD")
        self.server = os.getenv("MT5_SERVER", "FBS")
        self.symbol = os.getenv("MT5_SYMBOL", "XAUUSD").replace("/", "")
        self.magic_number = 20260511
        self.initialized = False
        
        # MetaAPI internal state
        self._api = None
        self._account = None
        self._connection = None
        self._deployed = False

    def _ensure_api(self):
        """Lazy-import MetaApi to avoid crash if SDK not installed"""
        from metaapi_cloud_sdk import MetaApi
        if self._api is None:
            if not self.token:
                raise ValueError(
                    "METAAPI_TOKEN is required. Get it from https://metaapi.cloud\n"
                    "Set it in .env as: METAAPI_TOKEN=your_token_here"
                )
            self._api = MetaApi(self.token)
        return self._api

    def connect(self) -> bool:
        """Initialize MetaAPI connection and deploy MT5 account in cloud"""
        if self.initialized and self._deployed:
            return True

        try:
            result = asyncio.run(self._async_connect())
            self.initialized = result
            return result
        except Exception as e:
            logger.error(f"MetaAPI connection failed: {e}")
            return False

    async def _async_connect(self):
        """Async: Find or create MetaAPI account, deploy, connect"""
        api = self._ensure_api()
        
        if not self.login_id or not self.password:
            logger.error("MT5_LOGIN and MT5_PASSWORD required in .env")
            return False

        # Step 1: Find existing account or create new one
        accounts = await api.metatrader_account_api.get_accounts_with_infinite_scroll_pagination()
        existing = [a for a in accounts if a.login == str(self.login_id)]
        
        if existing:
            self._account = existing[0]
            logger.info(f"✅ Found existing MetaAPI account: {self._account.id}")
        else:
            logger.info(f"🆕 Creating new MetaAPI cloud account for {self.login_id} @ {self.server}...")
            self._account = await api.metatrader_account_api.create_account({
                'name': f'Claw_Trade_{self.login_id}',
                'type': 'cloud',
                'login': str(self.login_id),
                'password': self.password,
                'server': self.server,
                'platform': 'mt5',
                'application': 'MetaApi',
                'magic': self.magic_number,
            })
            logger.info(f"✅ Created MetaAPI account: {self._account.id}")

        # Step 2: Deploy (start the cloud MT5 terminal)
        if not self._deployed:
            logger.info("🚀 Deploying cloud MT5 terminal (may take 1-2 minutes)...")
            state = self._account.state
            if state != 'DEPLOYED':
                await self._account.deploy()
            
            logger.info("⏳ Waiting for cloud terminal to connect to broker...")
            await self._account.wait_connected()
            self._deployed = True
            logger.info("✅ Cloud MT5 terminal connected!")

        # Step 3: Get RPC connection (for trading operations)
        self._connection = self._account.get_rpc_connection()
        await self._connection.connect()
        await self._connection.wait_synchronized()
        logger.info(f"✅ RPC connection synchronized for {self.symbol}")
        
        return True

    def get_price(self) -> Optional[Dict[str, float]]:
        """Get current live Ask and Bid prices via MetaAPI"""
        if not self.connect():
            return None

        try:
            return asyncio.run(self._async_get_price())
        except Exception as e:
            logger.error(f"Failed to get price: {e}")
            return None

    async def _async_get_price(self):
        """Async: Get current price from MetaAPI"""
        # Subscribe to market data for our symbol
        try:
            await self._connection.subscribe_to_market_data(self.symbol)
        except Exception:
            # Might already be subscribed
            pass

        # Get price from terminal state
        state = self._connection.terminal_state
        try:
            price = state.price(self.symbol)
        except Exception:
            logger.warning(f"Symbol '{self.symbol}' not found. Trying alternatives...")
            alternatives = ["XAUUSD", "GOLD", "XAUUSD.m", "XAUUSD.", "XAUUSD.i"]
            for alt in alternatives:
                try:
                    price = state.price(alt)
                    self.symbol = alt
                    logger.info(f"✅ Found alternative symbol: '{alt}'")
                    break
                except Exception:
                    continue
            else:
                logger.error("❌ Could not find any valid Gold symbol")
                return None

        return {
            "ask": price.get('ask', 0),
            "bid": price.get('bid', 0),
            "last": price.get('last', 0),
        }

    def get_account_info(self) -> Optional[Dict]:
        """Fetch MT5 account information"""
        if not self.connect():
            return None
        try:
            return asyncio.run(self._async_get_account_info())
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return None

    async def _async_get_account_info(self):
        """Async: Get account information"""
        info = await self._connection.get_account_information()
        return {
            'balance': info['balance'],
            'equity': info['equity'],
            'margin': info.get('margin', 0),
            'free_margin': info.get('marginFree', 0),
            'leverage': info.get('leverage', 0),
            'currency': info.get('currency', 'USD'),
        }

    def execute_market_order(self, signal: str, volume: float = 0.01,
                             stop_loss: float = 0.0, take_profit: float = 0.0) -> Optional[Dict]:
        """Send a market buy or sell order via MetaAPI"""
        if not self.connect():
            return None

        try:
            return asyncio.run(self._async_execute_market_order(signal, volume, stop_loss, take_profit))
        except Exception as e:
            logger.error(f"Order execution failed: {e}")
            return None

    async def _async_execute_market_order(self, signal: str, volume: float,
                                          stop_loss: float, take_profit: float):
        """Async: Execute market order via MetaAPI"""
        options = {
            'comment': 'Claw_Trade AI Bot',
            'clientId': f'CLAW_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        }

        logger.info(f"Sending order: {signal} {volume} Lot XAUUSD "
                    f"(SL: {stop_loss:.2f}, TP: {take_profit:.2f})...")

        if signal == "BUY":
            result = await self._connection.create_market_buy_order(
                self.symbol, volume, 
                float(stop_loss) if stop_loss > 0 else None,
                float(take_profit) if take_profit > 0 else None,
                options
            )
        elif signal == "SELL":
            result = await self._connection.create_market_sell_order(
                self.symbol, volume,
                float(stop_loss) if stop_loss > 0 else None,
                float(take_profit) if take_profit > 0 else None,
                options
            )
        else:
            logger.error(f"Unknown signal: {signal}")
            return None

        if result and result.get('stringCode'):
            logger.info(f"✅ Order executed! ID: {result['stringCode']}")
            return {
                "ticket": result.get('stringCode'),
                "retcode": 10009,  # TRADE_RETCODE_DONE equivalent
                "volume": volume,
                "price": result.get('price', 0),
                "comment": result.get('comment', ''),
            }
        else:
            logger.error(f"Order rejected: {result}")
            return None

    def modify_position_sl_tp(self, ticket: int or str, stop_loss: float, take_profit: float) -> bool:
        """Modify stop loss and take profit for an open position"""
        if not self.connect():
            return False

        try:
            return asyncio.run(self._async_modify_sl_tp(str(ticket), stop_loss, take_profit))
        except Exception as e:
            logger.error(f"Failed to modify SL/TP: {e}")
            return False

    async def _async_modify_sl_tp(self, position_id: str, stop_loss: float, take_profit: float):
        """Async: Modify position SL/TP"""
        await self._connection.modify_position(
            position_id,
            stop_loss if stop_loss > 0 else None,
            take_profit if take_profit > 0 else None
        )
        logger.info(f"✅ Position {position_id} SL/TP modified")
        return True

    def close_all_bot_positions(self) -> int:
        """Close all positions opened by this bot"""
        if not self.connect():
            return 0

        try:
            return asyncio.run(self._async_close_all())
        except Exception as e:
            logger.error(f"Failed to close positions: {e}")
            return 0

    async def _async_close_all(self):
        """Async: Close all positions"""
        positions = await self._connection.get_positions()
        closed = 0
        
        for pos in positions:
            try:
                if pos.get('magic', 0) == self.magic_number:
                    await self._connection.close_position(pos['id'])
                    closed += 1
                    logger.info(f"✅ Closed position {pos['id']}")
            except Exception as e:
                logger.error(f"Failed to close position {pos.get('id')}: {e}")

        return closed

    def is_position_open(self, ticket: str) -> bool:
        """Check if a specific position is still active"""
        if not self.connect():
            return False

        try:
            return asyncio.run(self._async_is_open(str(ticket)))
        except Exception:
            return False

    async def _async_is_open(self, position_id: str):
        """Async: Check if position is open"""
        positions = await self._connection.get_positions()
        return any(p['id'] == position_id for p in positions)

    def fetch_historical_data(self, start_date: str, end_date: str, 
                              timeframe: str = "1h") -> Optional[pd.DataFrame]:
        """Fetch historical rates from MetaAPI"""
        if not self.connect():
            return None

        try:
            return asyncio.run(self._async_fetch_historical(start_date, end_date, timeframe))
        except Exception as e:
            logger.error(f"Failed to fetch historical data: {e}")
            return None

    async def _async_fetch_historical(self, start_date: str, end_date: str, timeframe: str):
        """Async: Fetch historical candles from MetaAPI"""
        timeframe_map = {
            "1m": "1m", "5m": "5m", "15m": "15m",
            "1h": "1h", "4h": "4h", "1d": "1d",
        }
        tf = timeframe_map.get(timeframe, "1h")

        start_dt = pd.to_datetime(start_date).to_pydatetime()
        end_dt = pd.to_datetime(end_date).to_pydatetime()

        # Get historical candles
        rates = await self._connection.get_historical_candles(
            self.symbol, tf, start_dt, end_dt
        )

        if not rates:
            logger.warning(f"No historical data found for {self.symbol} ({timeframe})")
            return None

        df = pd.DataFrame(rates)
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('datetime', inplace=True)
        df.rename(columns={"tickVolume": "volume"}, inplace=True)

        return df[['open', 'high', 'low', 'close', 'volume']]

    def shutdown(self):
        """Disconnect from MetaAPI and undeploy account to save resources"""
        if self._deployed and self._account:
            try:
                asyncio.run(self._async_shutdown())
            except Exception as e:
                logger.warning(f"Shutdown warning: {e}")
        self.initialized = False
        self._deployed = False
        logger.info("MetaAPI connection closed.")

    async def _async_shutdown(self):
        """Async: Close connection and undeploy"""
        if self._connection:
            await self._connection.close()
        if self._account:
            await self._account.undeploy()
        logger.info("MetaAPI account undeployed.")


# ===== Factory function: returns the right connector =====
def create_connector():
    """Factory: Create MetaApiConnector if METAAPI_TOKEN is set, else MT5Connector"""
    if os.getenv("METAAPI_TOKEN"):
        logger.info("🔌 Using MetaApiConnector (cloud MT5)")
        return MetaApiConnector()
    else:
        logger.info("🔌 Using local MT5Connector (Windows-only)")
        from mt5_connector import MT5Connector
        return MT5Connector()