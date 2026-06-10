"""Discord Reporter Module for XAU/USD Auto-Trading System
Sends formatted trade reports to Discord via webhook every time:
  - An order is OPENED (with full reasoning from 5 agents)
  - An order is CLOSED (with P&L analysis and lessons learned)
  - The system decides to HOLD/WAIT (with reasons)
"""
import os
import json
import logging
import time
import requests
from datetime import datetime
from typing import Dict, Optional, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DiscordReporter:
    """Sends beautifully formatted trade reports to Discord via webhook"""

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_TRADE_WEBHOOK_URL", "")
        if not self.webhook_url:
            logger.warning("⚠️ DISCORD_TRADE_WEBHOOK_URL not set. Discord reports will be skipped.")

    def _send_to_url(self, url: str, payload: Dict) -> bool:
        """Send a payload to a specific webhook URL with retries for transient errors"""
        if not url:
            return False

        max_retries = 5
        backoff = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                if resp.status_code in [200, 204]:
                    logger.info("✅ Discord report sent successfully!")
                    return True
                elif resp.status_code == 429:
                    try:
                        retry_after = float(resp.headers.get("Retry-After", backoff))
                    except:
                        retry_after = backoff
                    logger.warning(f"⚠️ Discord rate limited (429). Retrying after {retry_after} seconds...")
                    time.sleep(retry_after)
                else:
                    logger.error(f"❌ Discord webhook error: {resp.status_code} {resp.text}")
                    # 4xx errors (except 429) are usually client errors, no point retrying
                    if 400 <= resp.status_code < 500:
                        return False
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logger.warning(f"⚠️ Discord connection attempt {attempt}/{max_retries} failed: {e}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2.0
            except Exception as e:
                logger.error(f"❌ Unexpected Discord webhook exception: {e}")
                return False

        logger.error("❌ Failed to send Discord report after max retries.")
        return False

    def _send(self, payload: Dict) -> bool:
        """Send a payload to Discord webhook"""
        if not self.webhook_url:
            logger.info("[Discord Reporter] No webhook URL configured. Skipping.")
            return False
        return self._send_to_url(self.webhook_url, payload)

    # ──────────────────────────────────────────────
    # 1. REPORT: ORDER OPENED
    # ──────────────────────────────────────────────
    def report_order_opened(
        self,
        signal: str,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        lot_size: float,
        ticket: Optional[int],
        confidence: float,
        regime: str,
        quant_summary: str,
        news_summary: str,
        bull_argument: str,
        bear_argument: str,
        ceo_reasoning: str,
        is_cent_account: bool = False,
    ):
        """Send a detailed report when an auto-trade order is opened"""
        now = datetime.now().strftime("%d %b %Y | %H:%M:%S น.")
        signal_emoji = "🟢" if signal == "BUY" else "🔴"
        signal_color = 3066993 if signal == "BUY" else 15158332  # Green or Red

        sl_distance = abs(entry_price - sl_price)
        tp_distance = abs(tp_price - entry_price)
        rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0

        # Calculate estimated monetary P&L
        contract_size = 100.0  # Standard gold contract size
        if is_cent_account:
            # Cent account: profit in cents = distance * lot * 100. profit in USD = distance * lot.
            est_profit_usd = tp_distance * lot_size
            est_loss_usd = sl_distance * lot_size
            est_profit_cents = est_profit_usd * 100
            est_loss_cents = est_loss_usd * 100
            pnl_info = (
                f"💰 **ประมาณการกำไร (Est. Profit):** `+${est_profit_usd:.2f} USD` ({est_profit_cents:,.0f} Cents)\n"
                f"📉 **ประมาณการขาดทุน (Est. Risk):** `-${est_loss_usd:.2f} USD` ({est_loss_cents:,.0f} Cents)\n"
                f"ℹ️ **ประเภทบัญชี:** `Cent Account (บัญชีเซนต์)`"
            )
        else:
            est_profit_usd = tp_distance * lot_size * contract_size
            est_loss_usd = sl_distance * lot_size * contract_size
            pnl_info = (
                f"💰 **ประมาณการกำไร (Est. Profit):** `+${est_profit_usd:,.2f} USD`\n"
                f"📉 **ประมาณการขาดทุน (Est. Risk):** `-${est_loss_usd:,.2f} USD`\n"
                f"ℹ️ **ประเภทบัญชี:** `Standard Account (บัญชีปกติ)`"
            )

        payload = {
            "embeds": [
                {
                    "title": f"🚨 AUTO-TRADE: เปิดออเดอร์สำเร็จ",
                    "description": (
                        f"📅 **{now}**\n\n"
                        f"สัญลักษณ์: **ทองคำ (XAU/USD)**\n"
                        f"คำสั่ง: {signal_emoji} **{signal}** | ขนาด: **{lot_size:.2f} Lot**\n"
                        f"ราคาเปิด (Entry): **${entry_price:.2f}**\n"
                        f"เป้าทำกำไร (TP): **${tp_price:.2f}** (ระยะวิ่ง +${tp_distance:.2f})\n"
                        f"ตัดขาดทุน (SL): **${sl_price:.2f}** (ระยะวิ่ง -${sl_distance:.2f})\n"
                        f"Risk:Reward = **1:{rr_ratio:.1f}**\n"
                        f"ความมั่นใจ: **{confidence*100:.0f}%**\n"
                        f"Ticket: **#{ticket or 'N/A'}**\n\n"
                        f"{pnl_info}"
                    ),
                    "color": signal_color,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                {
                    "title": "📝 สรุปเหตุผลการเข้าเทรด (5-Agent Consensus)",
                    "description": (
                        f"🌐 **สภาพตลาด (Regime):** {regime}\n\n"
                        f"📊 **พี่ควอนท์ (Quant Analyst):**\n{quant_summary[:500]}\n\n"
                        f"📰 **พี่ข่าว (News Analyst):**\n{news_summary[:500]}\n\n"
                        f"🐂 **พี่กระทิง (Bull Agent):**\n{bull_argument[:400]}\n\n"
                        f"🐻 **พี่หมี (Bear Agent):**\n{bear_argument[:400]}\n\n"
                        f"👔 **ท่านประธาน (CEO Decision):**\n{ceo_reasoning[:500]}"
                    ),
                    "color": 5814783,
                    "footer": {"text": "Auto-Trade by Antigravity AI • ไม่ใช่คำแนะนำการลงทุน"},
                },
            ]
        }
        return self._send(payload)

    # ──────────────────────────────────────────────
    # 2. REPORT: ORDER CLOSED (WIN or LOSS)
    # ──────────────────────────────────────────────
    def report_order_closed(
        self,
        signal: str,
        entry_price: float,
        close_price: float,
        lot_size: float,
        ticket: Optional[int],
        pnl_usd: float,
        pnl_pips: float,
        close_reason: str,
        lesson_learned: str,
    ):
        """Send a detailed report when an order is closed (TP hit, SL hit, or manual close)"""
        now = datetime.now().strftime("%d %b %Y | %H:%M:%S น.")
        is_win = pnl_usd >= 0
        
        if close_reason == "BREAKEVEN":
            result_emoji = "🛡️"
            result_word = "ปิดจุดคุ้มทุน / หน้าทุน (Breakeven)"
            result_color = 16776960  # Yellow
            status_text = "🛡️ **BREAKEVEN**"
        else:
            result_emoji = "🎉" if is_win else "💔"
            result_word = "ปิดทำกำไรสำเร็จ (TP)" if close_reason == "TP" else (
                "ปิดตัดขาดทุน (SL)" if close_reason == "SL" else f"ปิดออเดอร์ ({close_reason})"
            )
            result_color = 3066993 if is_win else 15158332  # Green or Red
            status_text = "🟢 **WIN**" if is_win else "🔴 **LOSS**"

        pnl_sign = "+" if pnl_usd > 0 else ("" if pnl_usd == 0 else "-")
        abs_pnl_usd = abs(pnl_usd)

        payload = {
            "embeds": [
                {
                    "title": f"{result_emoji} AUTO-TRADE RESULT: {result_word}",
                    "description": (
                        f"📅 **{now}**\n\n"
                        f"หมายเลขตั๋ว: **#{ticket or 'N/A'}** | สัญลักษณ์: **XAU/USD**\n"
                        f"คำสั่งเดิม: **{signal}** | ขนาด: **{lot_size:.2f} Lot**\n"
                        f"ราคาเปิด: **${entry_price:.2f}** → ราคาปิด: **${close_price:.2f}**\n\n"
                        f"สถานะ: {status_text} ({pnl_pips:+.1f} Pips)\n"
                        f"กำไร/ขาดทุนสุทธิ: **{pnl_sign}${abs_pnl_usd:.2f}**"
                    ),
                    "color": result_color,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                {
                    "title": "📝 วิเคราะห์เหตุผล" + (" (ทำไมชนะ)" if close_reason == "TP" else (" (ทำไมถึงเสมอตัว)" if close_reason == "BREAKEVEN" else " (ทำไมขาดทุน)")),
                    "description": (
                        f"**สาเหตุการปิดออเดอร์:** {close_reason}\n\n"
                        f"**วิเคราะห์:** {lesson_learned[:1000]}\n\n"
                        f"💡 **บทเรียนบันทึกลง Memory:** {'กลยุทธ์นี้ทำงานได้ดี ให้คงใช้ต่อไป' if close_reason == 'TP' else ('เป็นการป้องกันความเสี่ยงที่ดีรักษาพอร์ตไว้ก่อน' if close_reason == 'BREAKEVEN' else 'บทเรียนนี้ถูกฝังลงสมองเพื่อป้องกันไม่ให้เกิดซ้ำ')}"
                    ),
                    "color": 10181046,
                    "footer": {"text": "AI grows wiser after every trade • Auto-Learning enabled"},
                },
            ]
        }
        return self._send(payload)

    # ──────────────────────────────────────────────
    # 3. REPORT: HOLD / WAITING
    # ──────────────────────────────────────────────
    def report_hold_status(
        self,
        regime: str,
        quant_summary: str,
        news_summary: str,
        ceo_reasoning: str,
    ):
        """Send a status update when the system decides to hold/wait"""
        now = datetime.now().strftime("%d %b %Y | %H:%M:%S น.")

        payload = {
            "embeds": [
                {
                    "title": "🟡 AUTO-TRADE STATUS: สแตนด์บายรอจังหวะ",
                    "description": (
                        f"📅 **{now}**\n"
                        f"สถานะ: **HOLD** (ยังไม่เปิดออเดอร์)\n\n"
                        f"🌐 **สภาพตลาด:** {regime}\n\n"
                        f"📊 **พี่ควอนท์:** {quant_summary[:400]}\n\n"
                        f"📰 **พี่ข่าว:** {news_summary[:400]}\n\n"
                        f"👔 **ท่านประธาน:** {ceo_reasoning[:500]}"
                    ),
                    "color": 16776960,  # Yellow
                    "timestamp": datetime.utcnow().isoformat(),
                    "footer": {"text": "Waiting for high-probability setup • Capital preserved"},
                }
            ]
        }
        return self._send(payload)

    # ──────────────────────────────────────────────
    # 4. REPORT: SYSTEM STATUS / ERROR
    # ──────────────────────────────────────────────
    def report_system_status(self, title: str, message: str, color: int = 5814783):
        """Send a system status or error message"""
        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": message[:4000],
                    "color": color,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ]
        }
        return self._send(payload)

    # ──────────────────────────────────────────────
    # 5. REPORT: BREAKING NEWS ALERT
    # ──────────────────────────────────────────────
    def report_breaking_news(self, headline: str, summary: str, bias: str):
        """Broadcast urgent breaking news alert to Discord"""
        now = datetime.now().strftime("%d %b %Y | %H:%M:%S น.")
        bias_emoji = "🟢" if bias == "bullish" else ("🔴" if bias == "bearish" else "🟡")
        color = 3066993 if bias == "bullish" else (15158332 if bias == "bearish" else 16776960)

        news_webhook = os.getenv("DISCORD_NEWS_WEBHOOK_URL", "")
        target_url = news_webhook if news_webhook else self.webhook_url

        if not target_url:
            logger.warning("⚠️ No webhook configured for Breaking News.")
            return False

        payload = {
            "embeds": [
                {
                    "title": f"🚨 📰 ข่าวด่วนสำคัญ (BREAKING NEWS): {headline}",
                    "description": (
                        f"📅 **{now}**\n\n"
                        f"**ผลกระทบต่อทองคำ (XAU/USD):** {bias_emoji} **{bias.upper()}**\n\n"
                        f"**รายละเอียดข่าว:**\n{summary[:2000]}"
                    ),
                    "color": color,
                    "timestamp": datetime.utcnow().isoformat(),
                    "footer": {"text": "High-Impact Macro Event • AI News Radar"},
                }
            ]
        }
        return self._send_to_url(target_url, payload)
