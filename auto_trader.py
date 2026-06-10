"""
XAU/USD Fully Automated Live Trading System
============================================
- Runs continuously in the background
- 5 Sub-Agents analyze market every cycle (Quant, News, Bull, Bear, CEO)
- CEO makes final BUY/SELL/HOLD decision autonomously
- MT5 Connector executes orders automatically
- Discord Reporter sends full trade reports (open/close/hold) to Discord
- Monitors open positions for TP/SL hits and reports P&L with analysis
- Learns from mistakes via post-mortem analysis
"""
import sys
import os
import time
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

# Add project paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import Config, LiveTradingConfig
from data_handler import DataHandler
from agents import QuantAnalyst, NewsAnalyst, BullAgent, BearAgent, CEOAgent
from mt5_connector import MT5Connector
from discord_reporter import DiscordReporter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('auto_trade_live.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AutoTrader")


@dataclass
class LivePosition:
    """Tracks a live position opened by this bot"""
    ticket: int
    signal: str          # BUY or SELL
    entry_price: float
    lot_size: float
    stop_loss: float
    take_profit: float
    opened_at: str       # timestamp
    confidence: float
    regime: str
    quant_summary: str
    news_summary: str
    bull_argument: str
    bear_argument: str
    ceo_reasoning: str


class AutoTrader:
    """Fully automated XAU/USD trading system with Discord reporting"""

    def __init__(self, interval_minutes: int = 30):
        self.interval_minutes = interval_minutes
        self.config = Config

        # Initialize 5-Agent Team
        self.quant_analyst = QuantAnalyst()
        self.news_analyst = NewsAnalyst()
        self.bull_agent = BullAgent()
        self.bear_agent = BearAgent()
        self.ceo_agent = CEOAgent()

        # Initialize MT5
        self.mt5 = MT5Connector()

        # Initialize Discord Reporter
        self.discord = DiscordReporter()

        # Initialize Data Handler
        self.data_handler = DataHandler()

        # Track positions & daily trades
        self.open_positions: List[LivePosition] = []
        self.trades_today = 0
        self.last_trade_date: Optional[str] = None
        self.trade_history: List[Dict] = []
        self.is_cent_account = False

        # Memory file for lessons learned
        self.memory_file = os.path.join(
            str(Path(__file__).parent), "trade_memory.json"
        )
        self.lessons: List[Dict] = self._load_memory()

        logger.info("=" * 60)
        logger.info("🤖 AutoTrader Initialized!")
        logger.info(f"   Interval: {interval_minutes} minutes")
        logger.info(f"   Max Daily Trades: {self.config.MAX_DAILY_TRADES}")
        logger.info(f"   Risk per Trade: {self.config.POSITION_SIZE_PERCENT}%")
        logger.info(f"   Loaded {len(self.lessons)} lessons from memory")
        logger.info("=" * 60)

    # ──────────────────────────────────────────────
    # MEMORY SYSTEM (Lessons Learned)
    # ──────────────────────────────────────────────

    def _load_memory(self) -> List[Dict]:
        """Load lessons from disk"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_memory(self):
        """Save lessons to disk atomically to prevent corruption"""
        try:
            # 1. Prune to keep max 100 lessons
            self.lessons = self.lessons[-100:]
            temp_file = f"{self.memory_file}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.lessons, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, self.memory_file)
        except Exception as e:
            logger.error(f"Failed to save memory atomically: {e}")

    def _add_lesson(self, lesson: str, trade_data: Dict):
        """Add a new lesson to memory"""
        entry = {
            "date": datetime.now().isoformat(),
            "lesson": lesson,
            "trade": trade_data,
        }
        self.lessons.append(entry)
        self._save_memory()
        logger.info(f"💡 New lesson saved: {lesson[:100]}...")

    def _get_recent_lessons(self, n: int = 10) -> str:
        """Get last N lessons as text for AI context"""
        if not self.lessons:
            return "ยังไม่มีบทเรียนจากการเทรด (รอบแรก)"
        recent = self.lessons[-n:]
        return "\n".join([
            f"- [{l['date'][:10]}] {l['lesson']}"
            for l in recent
        ])

    # ──────────────────────────────────────────────
    # MARKET REGIME DETECTION
    # ──────────────────────────────────────────────

    def _determine_regime(self, df) -> str:
        """Determine market regime from recent data"""
        if len(df) < 20:
            return "TRENDING"

        latest = df.iloc[-1]

        # Volatility check
        atr_value = latest.get("atr", 2.0)
        atr_series = df["atr"].dropna()
        if len(atr_series) > 10:
            atr_percentile = (atr_series < atr_value).mean()
            if atr_percentile > 0.80:
                return "HIGH_VOLATILITY"

        # Volume check
        volume = latest.get("volume", 1000)
        avg_volume = df["volume"].tail(20).mean()
        interval = getattr(self.config, "YFINANCE_INTERVAL", "1h")
        min_vol_ratio = 0.15 if interval in ["1m", "5m", "15m"] else 0.35

        if avg_volume > 0 and (volume / avg_volume) < min_vol_ratio:
            return "LOW_LIQUIDITY"

        # Trend vs Range
        ema_50 = latest.get("ema_50", latest["close"])
        ema_200 = latest.get("ema_200", latest["close"])
        ema_diff = abs(ema_50 - ema_200) / ema_200 if ema_200 > 0 else 0

        if ema_diff > 0.015:
            return "TRENDING"
        else:
            return "RANGING"

    # ──────────────────────────────────────────────
    # POSITION MONITORING
    # ──────────────────────────────────────────────

    def _check_open_positions(self, current_price: float, high_price: float, low_price: float):
        """Check if any open positions hit TP or SL, and report to Discord"""
        closed = []

        for pos in self.open_positions:
            exit_price = None
            close_reason = None

            # ── Check if position was closed manually in MT5 terminal ──
            manually_closed = False
            if hasattr(self.mt5, "is_position_open"):
                if not self.mt5.is_position_open(pos.ticket):
                    manually_closed = True

            if manually_closed:
                exit_price = current_price
                close_reason = "MANUAL_CLOSE"
            elif pos.signal == "BUY":
                if low_price <= pos.stop_loss:
                    exit_price = pos.stop_loss
                    close_reason = "SL"
                elif high_price >= pos.take_profit:
                    exit_price = pos.take_profit
                    close_reason = "TP"
            elif pos.signal == "SELL":
                if high_price >= pos.stop_loss:
                    exit_price = pos.stop_loss
                    close_reason = "SL"
                elif low_price <= pos.take_profit:
                    exit_price = pos.take_profit
                    close_reason = "TP"

            if exit_price and close_reason:
                # Calculate P&L
                contract_size = 100.0
                if pos.signal == "BUY":
                    pnl_raw = (exit_price - pos.entry_price) * pos.lot_size * contract_size
                    pnl_pips = (exit_price - pos.entry_price) * 10
                else:
                    pnl_raw = (pos.entry_price - exit_price) * pos.lot_size * contract_size
                    pnl_pips = (pos.entry_price - exit_price) * 10

                pnl_usd = pnl_raw / 100.0 if self.is_cent_account else pnl_raw

                is_win = pnl_usd >= 0

                # Generate lesson learned
                if is_win:
                    lesson = (
                        f"เทรด {pos.signal} ชนะ +${pnl_usd:.2f} "
                        f"(Entry ${pos.entry_price:.2f} → TP ${exit_price:.2f}). "
                        f"สภาพตลาด: {pos.regime}. "
                        f"เหตุผล: {pos.ceo_reasoning[:200]}"
                    )
                else:
                    lesson = (
                        f"เทรด {pos.signal} ขาดทุน -${abs(pnl_usd):.2f} "
                        f"(Entry ${pos.entry_price:.2f} → SL ${exit_price:.2f}). "
                        f"สภาพตลาด: {pos.regime}. "
                        f"ข้อผิดพลาด: ต้องปรับปรุงเรื่อง SL หรือรอสัญญาณที่แม่นยำขึ้น"
                    )

                # Save lesson to memory
                self._add_lesson(lesson, {
                    "signal": pos.signal,
                    "entry": pos.entry_price,
                    "exit": exit_price,
                    "pnl": pnl_usd,
                    "reason": close_reason,
                    "regime": pos.regime,
                })

                # Report to Discord
                self.discord.report_order_closed(
                    signal=pos.signal,
                    entry_price=pos.entry_price,
                    close_price=exit_price,
                    lot_size=pos.lot_size,
                    ticket=pos.ticket,
                    pnl_usd=pnl_usd,
                    pnl_pips=pnl_pips,
                    close_reason=close_reason,
                    lesson_learned=lesson,
                )

                logger.info(
                    f"{'🎉' if is_win else '💔'} Position #{pos.ticket} closed: "
                    f"{close_reason} | P&L: ${pnl_usd:+.2f}"
                )
                closed.append(pos)

        for pos in closed:
            self.open_positions.remove(pos)

    # ──────────────────────────────────────────────
    # MAIN ANALYSIS & EXECUTION CYCLE
    # ──────────────────────────────────────────────

    def _run_analysis_cycle(self):
        """Run one complete analysis cycle: Analyze → Decide → Execute → Report"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 New Analysis Cycle: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")

        # ── Step 1: Get live price from MT5 ──
        prices = self.mt5.get_price()
        if not prices:
            logger.warning("⚠️ Could not fetch MT5 price. Skipping cycle.")
            return

        current_price = prices["ask"]
        bid_price = prices["bid"]
        logger.info(f"💰 Live Price: Ask=${current_price:.2f} | Bid=${bid_price:.2f}")

        # ── Step 2: Fetch recent data for technicals ──
        try:
            df = self.data_handler.prepare_for_analysis(
                symbol=self.config.XAU_USD_SYMBOL,
                start=(datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d"),
                end=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                interval=getattr(self.config, "YFINANCE_INTERVAL", "1h"),
            )
            if df.empty or len(df) < 20:
                logger.error("Not enough market data. Skipping cycle.")
                return

            df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
            df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
        except Exception as e:
            logger.error(f"Data fetch error: {e}")
            return

        latest = df.iloc[-1]

        # ── Step 3: Check open positions for TP/SL ──
        self._check_open_positions(
            current_price=current_price,
            high_price=latest.get("high", current_price),
            low_price=latest.get("low", current_price),
        )

        # ── Step 4: Reset daily trade counter ──
        today_str = datetime.now().strftime("%Y-%m-%d")
        if self.last_trade_date != today_str:
            self.trades_today = 0
            self.last_trade_date = today_str

        # ── Step 5: Determine regime ──
        regime = self._determine_regime(df)
        logger.info(f"🌐 Market Regime: {regime}")

        # Block trades in low liquidity
        if regime == "LOW_LIQUIDITY":
            logger.info("🛡️ Blocked: LOW_LIQUIDITY regime. Standing aside.")
            self.discord.report_hold_status(
                regime=regime,
                quant_summary="ตลาดผันผวนต่ำ (Low Liquidity)",
                news_summary="งดเข้าเทรดชั่วคราวเพื่อความปลอดภัย",
                ceo_reasoning="Standing aside due to LOW_LIQUIDITY market regime.",
            )
            return

        # Block if daily limit reached
        if self.trades_today >= self.config.MAX_DAILY_TRADES:
            logger.info("🛡️ Blocked: Daily trade limit reached.")
            self.discord.report_hold_status(
                regime=regime,
                quant_summary="โควต้าเทรดรายวันเต็ม (Daily Limit Reached)",
                news_summary=f"วันนี้เทรดครบ {self.config.MAX_DAILY_TRADES} ครั้งแล้ว",
                ceo_reasoning="Daily trade limit reached. Preserving capital until tomorrow.",
            )
            return

        # Block if max open positions
        if len(self.open_positions) >= self.config.MAX_OPEN_POSITIONS:
            logger.info("🛡️ Blocked: Max open positions reached.")
            self.discord.report_hold_status(
                regime=regime,
                quant_summary="โควต้าออเดอร์เปิดค้างเต็ม (Max Open Positions)",
                news_summary="กำลังรอออเดอร์ปัจจุบันชน TP หรือ SL",
                ceo_reasoning="Max open positions reached. Managing active trades.",
            )
            return

        # ── Step 6: Run 5-Agent Pipeline ──
        market_context = self.data_handler.format_market_context(df.tail(50), n_candles=10)

        # Calculate MACD cross
        macd_cross = "neutral"
        if len(df) >= 8:
            for i in range(-1, -7, -1):
                prev_macd = df["macd"].iloc[i - 1]
                prev_sig = df["macd_signal"].iloc[i - 1]
                curr_macd = df["macd"].iloc[i]
                curr_sig = df["macd_signal"].iloc[i]
                if prev_macd <= prev_sig and curr_macd > curr_sig:
                    macd_cross = "bullish_cross"
                    break
                elif prev_macd >= prev_sig and curr_macd < curr_sig:
                    macd_cross = "bearish_cross"
                    break

        indicators = {
            "close": latest["close"],
            "rsi": latest.get("rsi", 50.0),
            "macd": latest.get("macd", 0.0),
            "macd_signal": latest.get("macd_signal", 0.0),
            "macd_cross": macd_cross,
            "fibo_zone": "neutral",
            "ema_50": latest.get("ema_50", latest["close"]),
            "ema_200": latest.get("ema_200", latest["close"]),
            "fib_levels": {},
        }

        # 1. Quant Analysis
        logger.info("📊 Running Quant Analyst...")
        quant_res = self.quant_analyst.analyze(market_context, indicators)
        quant_summary = quant_res.get("technical_summary", "N/A")

        # 2. News Analysis
        logger.info("📰 Running News Analyst...")
        news_res = self.news_analyst.analyze()
        news_summary = news_res.get("fundamental_summary", "N/A")

        if news_res.get("is_breaking_news"):
            logger.info("🚨 BREAKING NEWS DETECTED! Sending urgent Discord broadcast...")
            self.discord.report_breaking_news(
                headline=news_res.get("breaking_news_headline", "แจ้งเตือนข่าวเศรษฐกิจสำคัญ"),
                summary=news_summary,
                bias=news_res.get("fundamental_bias", "neutral"),
            )

        # 3. Bull Agent
        logger.info("🐂 Running Bull Agent...")
        bull_res = self.bull_agent.advocate(quant_res, news_res)
        bull_argument = bull_res.reasoning
        bull_case = {"conviction_score": bull_res.confidence, "reasoning": bull_res.reasoning}
        
        # 4. Bear Agent
        logger.info("🐻 Running Bear Agent...")
        bear_res = self.bear_agent.advocate(quant_res, news_res)
        bear_argument = bear_res.reasoning
        bear_case = {"conviction_score": bear_res.confidence, "reasoning": bear_res.reasoning}
        
        # 5. CEO Decision
        logger.info("👔 Running CEO Agent (Final Decision)...")
        # Extract recent lessons from memory as List[str]
        learning_memory = [l["lesson"] for l in self.lessons]
        ceo_res = self.ceo_agent.decide(quant_res, news_res, bull_case, bear_case, regime, learning_memory)
        
        decision = ceo_res.get("decision", "NO_TRADE")
        confidence = ceo_res.get("confidence", 0.5)
        ceo_reasoning = ceo_res.get("reasoning", "N/A")

        logger.info(f"⚖️ CEO Decision: {decision} | Confidence: {confidence:.0%}")
        logger.info(f"   Reasoning: {ceo_reasoning[:200]}")

        # ── Step 7: Execute or Hold ──
        if decision in ["BUY", "SELL"] and confidence >= 0.60:
            # ── Dynamic Strategy Routing: Sniper Scalping vs Trend Following ──
            interval = getattr(self.config, "YFINANCE_INTERVAL", "1h")
            is_scalping_tf = interval in ["1m", "5m", "15m"]

            if is_scalping_tf and regime == "RANGING":
                # 🎯 Sniper Scalping Mode (Sideways / 15m): 1:1 Ratio (100-200 จุด)
                sl_distance = 2.0  # $2 USD (200 จุด)
                tp_distance = 2.0  # $2 USD (200 จุด)
                logger.info(f"🎯 Sniper Scalping Mode (Sideways): TP/SL Locked at 1:1 Ratio (${sl_distance:.2f})")
            elif getattr(self.config, "USE_FIXED_SL_TP", False):
                sl_distance = self.config.FIXED_SL_USD
                tp_distance = self.config.FIXED_TP_USD
            else:
                atr = latest.get("atr", 2.0)
                atr_multiplier = getattr(self.config, "ATR_SL_MULTIPLIER", 1.0)
                sl_distance = max(atr * atr_multiplier, 5.0)
                tp_distance = sl_distance * self.config.RISK_REWARD_RATIO

            if decision == "BUY":
                entry_price = current_price
                sl_price = entry_price - sl_distance
                tp_price = entry_price + tp_distance
            else:
                entry_price = bid_price
                sl_price = entry_price + sl_distance
                tp_price = entry_price - tp_distance

            # Dynamic Risk-Based Position Sizing (Money Management)
            balance = 10000.0  # fallback
            contract_size = 100.0  # Default standard contract size
            is_cent_account = False
            
            try:
                import MetaTrader5 as mt5_lib
                if self.mt5.initialized and mt5_lib is not None:
                    acc_info = mt5_lib.account_info()
                    if acc_info is not None:
                        balance = acc_info.balance
                        currency = getattr(acc_info, "currency", "")
                        if "CENT" in currency.upper() or self.mt5.symbol.endswith("c"):
                            is_cent_account = True
                            self.is_cent_account = True
                            logger.info(f"   🪙 Cent Account Detected (Currency: {currency}, Symbol: {self.mt5.symbol}). Converting balance for sizing.")
                    sym_info = mt5_lib.symbol_info(self.mt5.symbol)
                    if sym_info is not None:
                        contract_size = float(sym_info.trade_contract_size)
            except Exception as e:
                logger.warning(f"Could not retrieve live MT5 account/symbol info for sizing: {e}. Using defaults.")

            fixed_lot = getattr(self.config, "FIXED_LOT_SIZE", 0.0)
            if fixed_lot and float(fixed_lot) > 0:
                lot_size = float(fixed_lot)
                logger.info(f"   ℹ️ Using FIXED_LOT_SIZE from config: {lot_size}")
            else:
                risk_percent = getattr(self.config, "POSITION_SIZE_PERCENT", 15.0)
                # Convert balance to USD base if it is a Cent Account to match sl_distance in USD
                calc_balance = balance / 100.0 if is_cent_account else balance
                risk_amount = calc_balance * (risk_percent / 100.0)
                computed_lot = risk_amount / (sl_distance * contract_size)
                lot_size = max(0.01, round(computed_lot, 2))
                
                # Regime risk adjustment (Only reduce if not standard high confidence)
                if regime == "RANGING":
                    lot_size = max(0.01, round(lot_size * 0.5, 2))
                    logger.info(f"   🛡️ RANGING regime: Lot reduced by 50% to {lot_size}")
                
                logger.info(f"   ℹ️ Calculated Dynamic Lot Size: {lot_size} (Risking {risk_percent}% of balance ${calc_balance:.2f} with {sl_distance:.2f} SL, contract size: {contract_size})")

            # ── Execute on MT5 ──
            logger.info(f"🚀 Executing {decision} {lot_size} Lot @ ${entry_price:.2f} | SL=${sl_price:.2f} TP=${tp_price:.2f}")

            result = self.mt5.execute_market_order(
                signal=decision,
                volume=lot_size,
                stop_loss=sl_price,
                take_profit=tp_price,
            )

            if result:
                ticket = result.get("ticket", 0)
                actual_price = result.get("price", entry_price)

                # Track position
                position = LivePosition(
                    ticket=ticket,
                    signal=decision,
                    entry_price=actual_price,
                    lot_size=lot_size,
                    stop_loss=sl_price,
                    take_profit=tp_price,
                    opened_at=datetime.now().isoformat(),
                    confidence=confidence,
                    regime=regime,
                    quant_summary=quant_summary,
                    news_summary=news_summary,
                    bull_argument=bull_argument,
                    bear_argument=bear_argument,
                    ceo_reasoning=ceo_reasoning,
                )
                self.open_positions.append(position)
                self.trades_today += 1

                # ── Report to Discord: ORDER OPENED ──
                self.discord.report_order_opened(
                    signal=decision,
                    entry_price=actual_price,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    lot_size=lot_size,
                    ticket=ticket,
                    confidence=confidence,
                    regime=regime,
                    quant_summary=quant_summary,
                    news_summary=news_summary,
                    bull_argument=bull_argument,
                    bear_argument=bear_argument,
                    ceo_reasoning=ceo_reasoning,
                    is_cent_account=is_cent_account,
                )

                logger.info(f"✅ Order executed! Ticket #{ticket} | Discord report sent!")
            else:
                logger.error("❌ MT5 order execution failed!")
                self.discord.report_system_status(
                    "❌ Order Execution Failed",
                    f"คำสั่ง {decision} {lot_size} Lot @ ${entry_price:.2f} ไม่สามารถส่งเข้า MT5 ได้\n\nกรุณาตรวจสอบการเชื่อมต่อ MetaTrader 5",
                    color=15158332,
                )
        else:
            # ── Report to Discord: HOLD STATUS ──
            self.discord.report_hold_status(
                regime=regime,
                quant_summary=quant_summary,
                news_summary=news_summary,
                ceo_reasoning=ceo_reasoning,
            )
            logger.info("🟡 HOLD: No trade executed this cycle.")

    # ──────────────────────────────────────────────
    # MAIN LOOP
    # ──────────────────────────────────────────────

    def start(self):
        """Start the fully automated trading loop"""
        logger.info("\n" + "🚀" * 20)
        logger.info("  STARTING FULLY AUTOMATED XAU/USD TRADING SYSTEM")
        logger.info("🚀" * 20)

        # Connect to MT5
        if not self.mt5.connect():
            error_msg = "❌ Failed to connect to MetaTrader 5. Please ensure MT5 is running."
            logger.error(error_msg)
            self.discord.report_system_status("❌ MT5 Connection Failed", error_msg, color=15158332)
            return

        # Announce startup
        self.discord.report_system_status(
            "🤖 Auto-Trade System Started!",
            (
                f"🟢 ระบบเทรดทองคำอัตโนมัติเริ่มทำงานแล้วครับ!\n\n"
                f"⏱️ **รอบการวิเคราะห์:** ทุก {self.interval_minutes} นาที\n"
                f"📊 **ทีมงาน:** 5 Sub-Agents (Quant, News, Bull, Bear, CEO)\n"
                f"📈 **สินทรัพย์:** XAU/USD (ทองคำ)\n"
                f"🛡️ **Risk per Trade:** {self.config.POSITION_SIZE_PERCENT}%\n"
                f"📚 **บทเรียนในสมอง:** {len(self.lessons)} ข้อ\n\n"
                f"ผมจะพิมพ์รายงานสรุปเหตุผลทุกครั้งที่เปิดหรือปิดออเดอร์ครับบอส!"
            ),
            color=3066993,
        )

        logger.info("✅ MT5 connected! Starting analysis loop...\n")

        # Main loop
        while True:
            try:
                self._run_analysis_cycle()
            except KeyboardInterrupt:
                logger.info("🛑 Shutting down by user request...")
                self.discord.report_system_status(
                    "🛑 Auto-Trade System Stopped",
                    "ระบบเทรดอัตโนมัติถูกปิดโดยผู้ใช้ครับ",
                    color=16776960,
                )
                break
            except Exception as e:
                logger.error(f"❌ Critical error in analysis cycle: {e}")
                self.discord.report_system_status(
                    "⚠️ System Error",
                    f"เกิดข้อผิดพลาดในรอบการวิเคราะห์:\n```\n{str(e)[:1500]}\n```",
                    color=15158332,
                )

            logger.info(f"⏳ Sleeping {self.interval_minutes} minutes until next cycle...\n")
            time.sleep(self.interval_minutes * 60)

        # Cleanup
        self.mt5.shutdown()
        logger.info("👋 AutoTrader shutdown complete.")


# ──────────────────────────────────────────────
# CLI ENTRY POINT
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="XAU/USD Fully Automated Trading System")
    parser.add_argument(
        "--interval", type=int, default=5,
        help="Analysis interval in minutes (default: 5)"
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Confirm that you want to run auto-trading with real money"
    )
    args = parser.parse_args()

    if not args.confirm:
        print("⚠️  WARNING: This will execute REAL trades on MetaTrader 5!")
        print("    Add --confirm flag to proceed.")
        print("    Example: python auto_trader.py --interval 30 --confirm")
        sys.exit(1)

    trader = AutoTrader(interval_minutes=args.interval)
    trader.start()
