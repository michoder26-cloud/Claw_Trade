"""
Stock & ETF Investment System — Automated Daily & Weekly Reports
================================================================
Schedule:
  📈 ทุกวัน 10:00 น. → วิเคราะห์หุ้นทั้ง Watchlist + คัด Top Pick → ส่ง Discord ห้อง #daily-top-pick
  🧠 ทุกวันจันทร์ 08:00 น. → ทบทวนคำแนะนำสัปดาห์ที่แล้ว + สกัดบทเรียน → ส่ง Discord ห้อง #weekly-reflection

Features:
  - 5 Sub-Agents: Quant, News, Bull, Bear, CEO
  - Memory system: remembers past predictions & lessons learned
  - Learns from mistakes automatically
"""
import os
import sys
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Add project path
sys.path.insert(0, str(Path(__file__).parent))

from stock_agents import (
    analyze_all_stocks, select_top_pick, get_all_tickers, fetch_stock_data
)
from dotenv import load_dotenv

load_dotenv(os.path.join(str(Path(__file__).parent), ".env"), override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stock_invest.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("StockInvest")

# ── Config ──
DAILY_WEBHOOK = os.getenv("DISCORD_DAILY_STOCK_WEBHOOK", "")
WEEKLY_WEBHOOK = os.getenv("DISCORD_WEEKLY_REFLECTION_WEBHOOK", "")
MEMORY_FILE = os.path.join(str(Path(__file__).parent), "stock_memory.json")
PREDICTIONS_FILE = os.path.join(str(Path(__file__).parent), "stock_predictions.json")


# ──────────────────────────────────────────────
# MEMORY SYSTEM
# ──────────────────────────────────────────────

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_json(filepath, data):
    """Atomic save to prevent JSON corruption"""
    try:
        temp_file = f"{filepath}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, filepath)
    except Exception as e:
        logger.error(f"Failed to save JSON atomically: {e}")


def get_recent_lessons(n=10) -> str:
    lessons = load_json(MEMORY_FILE)
    if not lessons:
        return "ยังไม่มีบทเรียน (รอบแรก)"
    recent = lessons[-n:]
    return "\n".join([f"- [{l['date'][:10]}] {l['lesson']}" for l in recent])


def save_lesson(lesson: str, context: dict = None):
    lessons = load_json(MEMORY_FILE)
    lessons.append({
        "date": datetime.now().isoformat(),
        "lesson": lesson,
        "context": context or {},
    })
    save_json(MEMORY_FILE, lessons[-200:])  # Keep last 200
    logger.info(f"💡 Lesson saved: {lesson[:100]}")


def save_prediction(prediction: dict):
    preds = load_json(PREDICTIONS_FILE)
    preds.append(prediction)
    save_json(PREDICTIONS_FILE, preds[-500:])  # Keep last 500


# ──────────────────────────────────────────────
# DISCORD SENDER
# ──────────────────────────────────────────────

def send_discord(webhook_url: str, payload: dict) -> bool:
    if not webhook_url:
        logger.warning("⚠️ No webhook URL configured. Skipping.")
        return False
    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        if resp.status_code in [200, 204]:
            logger.info("✅ Discord message sent!")
            return True
        else:
            logger.error(f"❌ Discord error: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Discord exception: {e}")
        return False


# ──────────────────────────────────────────────
# DAILY TOP PICK REPORT (ทุกวัน 10:00 น.)
# ──────────────────────────────────────────────

def run_daily_analysis():
    """Run full 5-agent analysis and send daily top pick report."""
    logger.info("\n" + "=" * 60)
    logger.info("📈 DAILY STOCK ANALYSIS — Starting!")
    logger.info("=" * 60)

    # Get lessons for AI context
    lessons = get_recent_lessons()

    # Run analysis pipeline
    results = analyze_all_stocks(lessons)
    if not results:
        logger.error("No results from analysis!")
        return

    top_pick = select_top_pick(results)
    now = datetime.now().strftime("%d %b %Y | %H:%M น.")

    # ── Build watchlist summary table ──
    table_lines = []
    for r in results:
        ceo = r["ceo"]
        emoji = "🟢" if ceo["decision"] == "BUY" else ("🟡" if ceo["decision"] == "HOLD" else "🔴")
        table_lines.append(
            f"{emoji} **{ceo['ticker']}** ${ceo['close']} | "
            f"Score: {ceo['quant_score']} | "
            f"{ceo['decision']} ({ceo['confidence']}%)"
        )

    watchlist_text = "\n".join(table_lines)

    # ── Build top pick section ──
    top_section = "ไม่พบหุ้นที่แนะนำ BUY ในวันนี้"
    if top_pick:
        tc = top_pick["ceo"]
        td = top_pick["data"]
        tq = top_pick["quant"]
        tb = top_pick["bull"]
        tbr = top_pick["bear"]

        hidden_alpha_text = "\n".join(tc["hidden_alphas"]) if tc["hidden_alphas"] else "ไม่พบ Hidden Alpha วันนี้"

        top_section = (
            f"🏆 **{tc['ticker']} — {tc['company_name']}**\n"
            f"ราคาปัจจุบัน: **${tc['close']}** ({td['price_change_pct']:+.1f}%)\n"
            f"Quant Score: **{tc['quant_score']}/100** | Sentiment: **{tc['sentiment_score']}/10**\n"
            f"คำตัดสิน: **{tc['decision']}** (ความมั่นใจ {tc['confidence']}%)\n\n"
            f"📊 **พี่ควอนท์:**\n" + "\n".join(tq["signals"][:5]) + "\n\n"
            f"🐂 **พี่กระทิง:** {tb['thesis']}\n"
            f"🐻 **พี่หมี:** {tbr['thesis']}\n\n"
            f"⚡ **Hidden Alpha:**\n{hidden_alpha_text}"
        )

    # ── Save prediction for reflection ──
    for r in results:
        save_prediction({
            "date": datetime.now().isoformat(),
            "ticker": r["ceo"]["ticker"],
            "close_at_prediction": r["ceo"]["close"],
            "decision": r["ceo"]["decision"],
            "quant_score": r["ceo"]["quant_score"],
            "confidence": r["ceo"]["confidence"],
        })

    # ── Send to Discord ──
    payload = {
        "embeds": [
            {
                "title": "📈 Daily Stock Analysis — Watchlist Summary",
                "description": (
                    f"📅 **{now}**\n"
                    f"📚 บทเรียนในสมอง: {len(load_json(MEMORY_FILE))} ข้อ\n\n"
                    f"{watchlist_text}"
                ),
                "color": 3447003,
                "timestamp": datetime.utcnow().isoformat(),
            },
            {
                "title": "🏆 Top Pick of the Day",
                "description": top_section[:4000],
                "color": 15844367,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "Stock Investment AI • ไม่ใช่คำแนะนำการลงทุน • DYOR"},
            },
        ]
    }

    send_discord(DAILY_WEBHOOK, payload)
    logger.info("📈 Daily analysis complete!")


# ──────────────────────────────────────────────
# WEEKLY REFLECTION (ทุกวันจันทร์ 08:00 น.)
# ──────────────────────────────────────────────

def run_weekly_reflection():
    """Review past week's predictions against actual prices, learn from mistakes."""
    logger.info("\n" + "=" * 60)
    logger.info("🧠 WEEKLY REFLECTION — Starting!")
    logger.info("=" * 60)

    predictions = load_json(PREDICTIONS_FILE)
    if not predictions:
        logger.info("No predictions to review yet.")
        return

    # Get predictions from last 7 days
    week_ago = datetime.now() - timedelta(days=7)
    recent_preds = [
        p for p in predictions
        if datetime.fromisoformat(p["date"]) >= week_ago
    ]

    if not recent_preds:
        logger.info("No predictions from last 7 days to review.")
        return

    # Group by ticker and get unique tickers
    tickers = list(set([p["ticker"] for p in recent_preds]))
    now = datetime.now().strftime("%d %b %Y | %H:%M น.")

    review_lines = []
    new_lessons = []
    total_correct = 0
    total_reviewed = 0

    for ticker in tickers:
        ticker_preds = [p for p in recent_preds if p["ticker"] == ticker]
        if not ticker_preds:
            continue

        # Get current price
        current_data = fetch_stock_data(ticker)
        if not current_data:
            continue

        current_price = current_data["close"]

        # Evaluate each prediction
        for pred in ticker_preds:
            pred_price = pred["close_at_prediction"]
            pred_decision = pred["decision"]
            pred_date = pred["date"][:10]
            price_change = ((current_price - pred_price) / pred_price) * 100

            total_reviewed += 1

            # Was the prediction correct?
            if pred_decision == "BUY" and price_change > 0:
                correct = True
                emoji = "✅"
                total_correct += 1
            elif pred_decision == "SELL/AVOID" and price_change < 0:
                correct = True
                emoji = "✅"
                total_correct += 1
            elif pred_decision == "HOLD":
                correct = abs(price_change) < 3  # HOLD correct if within ±3%
                emoji = "✅" if correct else "⚪"
                if correct:
                    total_correct += 1
            else:
                correct = False
                emoji = "❌"

            review_lines.append(
                f"{emoji} **{ticker}** [{pred_date}]: แนะนำ {pred_decision} "
                f"@ ${pred_price:.2f} → ตอนนี้ ${current_price:.2f} "
                f"({price_change:+.1f}%)"
            )

            # Generate lesson from mistakes
            if not correct:
                if pred_decision == "BUY" and price_change < -3:
                    lesson = (
                        f"[{pred_date}] แนะนำ BUY {ticker} @ ${pred_price:.2f} "
                        f"แต่ราคาลง {price_change:.1f}% เป็น ${current_price:.2f}. "
                        f"ต้องระมัดระวังมากขึ้นก่อนแนะนำ BUY"
                    )
                    new_lessons.append(lesson)
                    save_lesson(lesson, {"ticker": ticker, "error_type": "false_buy"})

                elif pred_decision == "SELL/AVOID" and price_change > 3:
                    lesson = (
                        f"[{pred_date}] แนะนำ SELL/AVOID {ticker} @ ${pred_price:.2f} "
                        f"แต่ราคาขึ้น {price_change:+.1f}% เป็น ${current_price:.2f}. "
                        f"พลาดโอกาสทำกำไร ต้องปรับเกณฑ์ให้แม่นขึ้น"
                    )
                    new_lessons.append(lesson)
                    save_lesson(lesson, {"ticker": ticker, "error_type": "missed_opportunity"})

    # Calculate accuracy
    accuracy = (total_correct / total_reviewed * 100) if total_reviewed > 0 else 0

    # ── Build Discord report ──
    review_text = "\n".join(review_lines[:25])  # Limit to 25 lines
    lessons_text = "\n".join([f"💡 {l}" for l in new_lessons[:10]]) if new_lessons else "ไม่มีข้อผิดพลาดใหม่ในสัปดาห์นี้ ทำได้ดีมาก! 🎉"

    accuracy_emoji = "🏆" if accuracy >= 70 else ("📊" if accuracy >= 50 else "📉")

    payload = {
        "embeds": [
            {
                "title": "🧠 Weekly Reflection — ทบทวนสัปดาห์ที่ผ่านมา",
                "description": (
                    f"📅 **{now}**\n"
                    f"📊 ตรวจสอบ: **{total_reviewed}** คำแนะนำ\n"
                    f"{accuracy_emoji} ความแม่นยำ: **{accuracy:.0f}%** "
                    f"(ถูก {total_correct}/{total_reviewed})\n\n"
                    f"{'─' * 30}\n\n"
                    f"{review_text}"
                ),
                "color": 10181046,
                "timestamp": datetime.utcnow().isoformat(),
            },
            {
                "title": "💡 บทเรียนใหม่ที่บันทึกลง Memory",
                "description": (
                    f"{lessons_text}\n\n"
                    f"📚 บทเรียนสะสมทั้งหมด: **{len(load_json(MEMORY_FILE))}** ข้อ\n"
                    f"บทเรียนเหล่านี้จะถูกนำไปใช้ในการวิเคราะห์ครั้งต่อไปอัตโนมัติ"
                ),
                "color": 5763719,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "AI grows wiser after every mistake • Auto-Learning enabled"},
            },
        ]
    }

    send_discord(WEEKLY_WEBHOOK, payload)
    logger.info(f"🧠 Weekly reflection complete! Accuracy: {accuracy:.0f}% | New lessons: {len(new_lessons)}")


# ──────────────────────────────────────────────
# SCHEDULER LOOP
# ──────────────────────────────────────────────

def should_run_daily(now: datetime) -> bool:
    """Check if it's time for daily report (10:00 AM)"""
    return now.hour == 10 and now.minute < 5


def should_run_weekly(now: datetime) -> bool:
    """Check if it's time for weekly reflection (Monday 08:00 AM)"""
    return now.weekday() == 0 and now.hour == 8 and now.minute < 5


def main_loop():
    """Main scheduling loop"""
    logger.info("\n" + "🚀" * 20)
    logger.info("  STOCK INVESTMENT SYSTEM — STARTED!")
    logger.info("🚀" * 20)
    logger.info(f"  📈 Daily Top Pick: ทุกวัน 10:00 น.")
    logger.info(f"  🧠 Weekly Reflection: ทุกวันจันทร์ 08:00 น.")
    logger.info(f"  📚 Lessons in memory: {len(load_json(MEMORY_FILE))}")

    # Send startup notification
    send_discord(DAILY_WEBHOOK, {
        "embeds": [{
            "title": "🤖 Stock Investment System Started!",
            "description": (
                f"🟢 ระบบวิเคราะห์หุ้นอัตโนมัติเริ่มทำงานแล้วครับ!\n\n"
                f"📈 **รายงานประจำวัน:** ทุกวัน 10:00 น.\n"
                f"🧠 **ทบทวนสัปดาห์:** ทุกวันจันทร์ 08:00 น.\n"
                f"👥 **ทีมงาน:** 5 Sub-Agents (Quant, News, Bull, Bear, CEO)\n"
                f"📊 **Watchlist:** AAPL, MSFT, NVDA, TSLA, GOOGL, ASML, ORCL, TSM, SPY, QQQ, VOO, SMH\n"
                f"📚 **บทเรียนในสมอง:** {len(load_json(MEMORY_FILE))} ข้อ"
            ),
            "color": 3066993,
            "timestamp": datetime.utcnow().isoformat(),
        }]
    })

    daily_ran_today = False
    weekly_ran_today = False

    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # Reset flags at midnight
            if now.hour == 0 and now.minute < 5:
                daily_ran_today = False
                weekly_ran_today = False

            # Daily 10:00 AM
            if should_run_daily(now) and not daily_ran_today:
                logger.info("⏰ Time for daily analysis!")
                run_daily_analysis()
                daily_ran_today = True

            # Weekly Monday 08:00 AM
            if should_run_weekly(now) and not weekly_ran_today:
                logger.info("⏰ Time for weekly reflection!")
                run_weekly_reflection()
                weekly_ran_today = True

        except Exception as e:
            logger.error(f"❌ Error in main loop: {e}")

        # Check every 1 minute
        time.sleep(60)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stock Investment Analysis System")
    parser.add_argument("--mode", choices=["auto", "daily", "weekly", "test"],
                        default="auto", help="Run mode")
    args = parser.parse_args()

    if args.mode == "daily":
        run_daily_analysis()
    elif args.mode == "weekly":
        run_weekly_reflection()
    elif args.mode == "test":
        # Quick test: run daily analysis immediately
        logger.info("🧪 TEST MODE — Running daily analysis NOW...")
        run_daily_analysis()
        logger.info("🧪 TEST MODE — Running weekly reflection NOW...")
        run_weekly_reflection()
    else:
        main_loop()
