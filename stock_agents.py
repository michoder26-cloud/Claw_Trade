"""
Stock & ETF Investment Agents
==============================
5 specialized AI agents for long-term stock/ETF analysis.
Mirrors the n8n Quant Strategy workflow logic.
"""
import os
import json
import logging
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StockAgents")

# ── Watchlist ──
WATCHLIST = {
    "stocks": ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "ASML", "ORCL", "TSM"],
    "etfs": ["SPY", "QQQ", "VOO", "SMH"],
}


def get_all_tickers() -> List[str]:
    return WATCHLIST["stocks"] + WATCHLIST["etfs"]


# ──────────────────────────────────────────────
# DATA FETCHER: Real Stock Data + Indicators
# (Replicated from n8n "Fetch Real Stock Data + Indicators" node)
# ──────────────────────────────────────────────

def fetch_stock_data(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch real-time stock data and calculate technical indicators.
    Replicates the exact n8n Javascript calculation node."""
    try:
        stock = yf.Ticker(ticker)

        # Get 3 months of daily data for indicator calculations
        hist = stock.history(period="3mo", interval="1d")
        if hist.empty or len(hist) < 20:
            logger.warning(f"Not enough data for {ticker}")
            return None

        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else latest

        close = float(latest["Close"])
        volume = float(latest["Volume"])
        high = float(latest["High"])
        low = float(latest["Low"])
        prev_close = float(prev["Close"])

        # ── RSI 14 (n8n exact formula) ──
        delta = hist["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0

        # ── Moving Averages (MA20, MA50) ──
        ma20 = float(hist["Close"].rolling(20).mean().iloc[-1])
        ma50 = float(hist["Close"].rolling(50).mean().iloc[-1]) if len(hist) >= 50 else ma20

        # ── Bollinger Bands (20-period, 2 std) ──
        bb_middle = ma20
        bb_std = float(hist["Close"].rolling(20).std().iloc[-1])
        bb_upper = bb_middle + (2 * bb_std)
        bb_lower = bb_middle - (2 * bb_std)

        # ── MACD ──
        ema12 = hist["Close"].ewm(span=12, adjust=False).mean()
        ema26 = hist["Close"].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd = float(macd_line.iloc[-1])
        macd_sig = float(macd_signal.iloc[-1])

        # ── Volume Ratio (n8n: today volume / 20-day average) ──
        avg_volume_20 = float(hist["Volume"].tail(20).mean())
        volume_ratio = volume / avg_volume_20 if avg_volume_20 > 0 else 1.0

        # ── Annualized Volatility ──
        daily_returns = hist["Close"].pct_change().dropna()
        annual_volatility = float(daily_returns.std() * np.sqrt(252) * 100)

        # ── Price Change ──
        price_change_pct = ((close - prev_close) / prev_close) * 100

        # ── Get company info ──
        try:
            info = stock.info
            company_name = info.get("shortName", ticker)
            sector = info.get("sector", "N/A")
            pe_ratio = info.get("trailingPE", None)
            market_cap = info.get("marketCap", None)
            earnings_date = info.get("earningsTimestamp", None)
        except Exception:
            company_name = ticker
            sector = "N/A"
            pe_ratio = None
            market_cap = None
            earnings_date = None

        return {
            "ticker": ticker,
            "company_name": company_name,
            "sector": sector,
            "close": round(close, 2),
            "prev_close": round(prev_close, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "price_change_pct": round(price_change_pct, 2),
            "volume": int(volume),
            "avg_volume_20": int(avg_volume_20),
            "volume_ratio": round(volume_ratio, 2),
            "rsi": round(rsi, 1),
            "ma20": round(ma20, 2),
            "ma50": round(ma50, 2),
            "macd": round(macd, 4),
            "macd_signal": round(macd_sig, 4),
            "bb_upper": round(bb_upper, 2),
            "bb_middle": round(bb_middle, 2),
            "bb_lower": round(bb_lower, 2),
            "annual_volatility": round(annual_volatility, 1),
            "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
            "market_cap": market_cap,
            "earnings_date": earnings_date,
        }

    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return None


# ──────────────────────────────────────────────
# AGENT 1: QUANT ANALYST (📊)
# ──────────────────────────────────────────────

def quant_analyze(data: Dict) -> Dict:
    """Pure mathematical/technical analysis. Calculates Quant Score 0-100.
    Exactly mirrors the n8n Quant Agent scoring rules."""
    score = 50  # Start neutral
    signals = []

    # RSI Analysis
    rsi = data["rsi"]
    if rsi < 30:
        score += 15
        signals.append(f"🟢 RSI={rsi} (Oversold → สัญญาณซื้อ)")
    elif rsi > 70:
        score -= 15
        signals.append(f"🔴 RSI={rsi} (Overbought → สัญญาณขาย)")
    else:
        signals.append(f"⚪ RSI={rsi} (Neutral)")

    # MACD Analysis
    if data["macd"] > 0:
        score += 10
        signals.append("🟢 MACD > 0 (Positive momentum)")
    else:
        score -= 10
        signals.append("🔴 MACD < 0 (Negative momentum)")

    # Price vs MA50
    if data["close"] > data["ma50"]:
        score += 10
        signals.append(f"🟢 ราคา ${data['close']} > MA50 ${data['ma50']} (Uptrend)")
    else:
        score -= 10
        signals.append(f"🔴 ราคา ${data['close']} < MA50 ${data['ma50']} (Downtrend)")

    # Volume Analysis (n8n rules)
    vr = data["volume_ratio"]
    if vr > 2.0:
        score += 5
        signals.append(f"🔥 Volume Ratio={vr}x (Unusual High!)")
    elif vr > 1.5 and data["price_change_pct"] > 0:
        score += 10
        signals.append(f"🟢 Volume Ratio={vr}x + ราคาขึ้น (Strong Buying Pressure)")
    elif vr > 1.5 and data["price_change_pct"] < 0:
        score -= 10
        signals.append(f"🔴 Volume Ratio={vr}x + ราคาลง (Strong Selling Pressure)")
    elif vr < 0.5:
        score -= 5
        signals.append(f"⚪ Volume Ratio={vr}x (Low Interest/Sideways)")

    # Volatility
    vol = data["annual_volatility"]
    if vol > 50:
        score -= 5
        signals.append(f"⚠️ Volatility={vol}% (High Risk!)")
    elif vol < 20:
        score += 5
        signals.append(f"🛡️ Volatility={vol}% (Stable)")

    # Hidden Alpha: Mean Reversion
    if rsi < 30 and data["close"] <= data["bb_lower"] * 1.01:
        score += 15
        signals.append("⚡ HIDDEN ALPHA: Mean Reversion (RSI Oversold + Bollinger Lower → Bounce Signal!)")

    # Hidden Alpha: Momentum Breakout
    if data["close"] > data["ma50"] and vr > 1.5:
        score += 10
        signals.append("⚡ HIDDEN ALPHA: Momentum Breakout (Price > MA50 + High Volume)")

    # Hidden Alpha: Divergence (weakness)
    if data["price_change_pct"] > 0 and vr < 0.8:
        score -= 5
        signals.append("⚡ HIDDEN ALPHA: Divergence (ราคาขึ้นแต่ Volume หด → อ่อนแรง)")

    # Hidden Alpha: Bollinger Squeeze
    bb_width = (data["bb_upper"] - data["bb_lower"]) / data["bb_middle"] if data["bb_middle"] > 0 else 0
    if bb_width < 0.03:
        signals.append("⚡ HIDDEN ALPHA: Bollinger Squeeze (กรอบแคบมาก → รอ Breakout)")

    # Clamp score
    score = max(0, min(100, score))

    if score >= 80:
        verdict = "BUY"
    elif score >= 50:
        verdict = "HOLD"
    else:
        verdict = "SELL/AVOID"

    return {
        "ticker": data["ticker"],
        "quant_score": score,
        "verdict": verdict,
        "signals": signals,
        "summary": f"Quant Score: {score}/100 → {verdict}",
    }


# ──────────────────────────────────────────────
# AGENT 2: NEWS ANALYST (📰)
# ──────────────────────────────────────────────

def news_analyze(data: Dict) -> Dict:
    """Fundamental/sentiment analysis based on available data."""
    signals = []
    sentiment_score = 5  # Neutral (1-10 scale)

    # P/E Ratio analysis
    pe = data.get("pe_ratio")
    if pe:
        if pe < 15:
            sentiment_score += 1
            signals.append(f"🟢 P/E={pe} (Undervalued)")
        elif pe > 40:
            sentiment_score -= 1
            signals.append(f"🔴 P/E={pe} (Overvalued / Premium pricing)")
        else:
            signals.append(f"⚪ P/E={pe} (Fair Value)")
    else:
        signals.append("⚪ P/E: N/A")

    # Price momentum (proxy for sentiment)
    pct = data["price_change_pct"]
    if pct > 2:
        sentiment_score += 1
        signals.append(f"🟢 วันนี้ขึ้น {pct:+.1f}% (Positive momentum)")
    elif pct < -2:
        sentiment_score -= 1
        signals.append(f"🔴 วันนี้ลง {pct:+.1f}% (Negative momentum)")
    else:
        signals.append(f"⚪ วันนี้เปลี่ยน {pct:+.1f}% (Sideways)")

    # Market cap classification
    mc = data.get("market_cap")
    if mc:
        if mc > 1_000_000_000_000:
            signals.append("🏛️ Mega Cap (>$1T)")
        elif mc > 100_000_000_000:
            signals.append("🏢 Large Cap (>$100B)")

    sentiment_score = max(1, min(10, sentiment_score))

    return {
        "ticker": data["ticker"],
        "sentiment_score": sentiment_score,
        "signals": signals,
        "summary": f"Sentiment Score: {sentiment_score}/10",
    }


# ──────────────────────────────────────────────
# AGENT 3: BULL (🐂)
# ──────────────────────────────────────────────

def bull_analyze(data: Dict, quant: Dict, news: Dict) -> Dict:
    """Build the strongest case for BUYING this stock."""
    arguments = []

    if quant["quant_score"] >= 70:
        arguments.append(f"📊 Quant Score สูง {quant['quant_score']}/100 — สัญญาณทางเทคนิคเข้าข้างฝั่งซื้อ")

    if data["rsi"] < 40:
        arguments.append(f"🎯 RSI ต่ำ ({data['rsi']}) — มีโอกาสเด้งกลับสูง")

    if data["close"] > data["ma50"]:
        arguments.append(f"📈 ราคาอยู่เหนือ MA50 — แนวโน้มขาขึ้น")

    if data["volume_ratio"] > 1.3 and data["price_change_pct"] > 0:
        arguments.append(f"🔥 Volume สูงกว่าปกติ {data['volume_ratio']}x พร้อมราคาขึ้น — แรงซื้อหนุน")

    pe = data.get("pe_ratio")
    if pe and pe < 25:
        arguments.append(f"💰 P/E Ratio {pe} — ยังไม่แพงเกินไป")

    # Hidden alpha signals
    for sig in quant["signals"]:
        if "HIDDEN ALPHA" in sig and ("Bounce" in sig or "Breakout" in sig):
            arguments.append(f"⚡ {sig}")

    if not arguments:
        arguments.append("ไม่พบสัญญาณซื้อที่แข็งแกร่งในตอนนี้")

    conviction = min(1.0, quant["quant_score"] / 100 + 0.1)

    return {
        "ticker": data["ticker"],
        "conviction": round(conviction, 2),
        "arguments": arguments,
        "thesis": arguments[0] if arguments else "N/A",
    }


# ──────────────────────────────────────────────
# AGENT 4: BEAR (🐻)
# ──────────────────────────────────────────────

def bear_analyze(data: Dict, quant: Dict, news: Dict) -> Dict:
    """Build the strongest case for SELLING/AVOIDING this stock."""
    arguments = []

    if quant["quant_score"] < 50:
        arguments.append(f"📊 Quant Score ต่ำ {quant['quant_score']}/100 — สัญญาณเทคนิคอ่อนแอ")

    if data["rsi"] > 65:
        arguments.append(f"⚠️ RSI สูง ({data['rsi']}) — ใกล้ Overbought ระวังย่อ")

    if data["close"] < data["ma50"]:
        arguments.append(f"📉 ราคาต่ำกว่า MA50 — แนวโน้มขาลง")

    if data["volume_ratio"] > 1.3 and data["price_change_pct"] < 0:
        arguments.append(f"🔴 Volume สูง {data['volume_ratio']}x พร้อมราคาลง — แรงขายหนัก")

    pe = data.get("pe_ratio")
    if pe and pe > 35:
        arguments.append(f"💸 P/E Ratio {pe} — ราคาแพงเกินพื้นฐาน")

    if data["annual_volatility"] > 40:
        arguments.append(f"⚠️ Volatility สูง {data['annual_volatility']}% — ความเสี่ยงสูง")

    # Hidden alpha weakness signals
    for sig in quant["signals"]:
        if "HIDDEN ALPHA" in sig and ("Divergence" in sig or "อ่อนแรง" in sig):
            arguments.append(f"⚡ {sig}")

    if not arguments:
        arguments.append("ไม่พบสัญญาณเตือนที่ชัดเจนในตอนนี้")

    conviction = min(1.0, (100 - quant["quant_score"]) / 100 + 0.1)

    return {
        "ticker": data["ticker"],
        "conviction": round(conviction, 2),
        "arguments": arguments,
        "thesis": arguments[0] if arguments else "N/A",
    }


# ──────────────────────────────────────────────
# AGENT 5: CEO / JUDGE (👔)
# ──────────────────────────────────────────────

def ceo_judge(
    data: Dict, quant: Dict, news: Dict, bull: Dict, bear: Dict, lessons: str = ""
) -> Dict:
    """Final BUY/HOLD/SELL decision weighing all agents.
    Quant carries heavy weight (numbers don't lie)."""

    score = quant["quant_score"]
    sentiment = news["sentiment_score"]

    # Weighted decision: Quant 60%, Sentiment 20%, Bull/Bear debate 20%
    debate_score = (bull["conviction"] - bear["conviction"]) * 50  # -50 to +50
    final_score = (score * 0.6) + (sentiment * 2) + (debate_score * 0.2)

    if final_score >= 65:
        decision = "BUY"
        confidence = min(95, final_score)
    elif final_score >= 40:
        decision = "HOLD"
        confidence = 50
    else:
        decision = "SELL/AVOID"
        confidence = min(95, 100 - final_score)

    # Build reasoning
    reasoning_parts = []
    reasoning_parts.append(f"Quant Score: {score}/100")
    reasoning_parts.append(f"Sentiment: {sentiment}/10")
    reasoning_parts.append(f"Bull conviction: {bull['conviction']:.0%} vs Bear: {bear['conviction']:.0%}")

    if bull["conviction"] > bear["conviction"] + 0.2:
        reasoning_parts.append("ฝั่ง Bull ชนะดีเบต — เหตุผลซื้อแข็งแรงกว่า")
    elif bear["conviction"] > bull["conviction"] + 0.2:
        reasoning_parts.append("ฝั่ง Bear ชนะดีเบต — ความเสี่ยงสูงกว่าโอกาส")
    else:
        reasoning_parts.append("Bull/Bear สูสี — ไม่มีฝ่ายใดชนะเด็ดขาด")

    return {
        "ticker": data["ticker"],
        "company_name": data["company_name"],
        "close": data["close"],
        "decision": decision,
        "confidence": round(confidence),
        "reasoning": " | ".join(reasoning_parts),
        "quant_score": score,
        "sentiment_score": sentiment,
        "bull_thesis": bull["thesis"],
        "bear_thesis": bear["thesis"],
        "hidden_alphas": [s for s in quant["signals"] if "HIDDEN ALPHA" in s],
    }


# ──────────────────────────────────────────────
# FULL PIPELINE: Analyze all stocks
# ──────────────────────────────────────────────

def analyze_all_stocks(lessons: str = "") -> List[Dict]:
    """Run the complete 5-agent pipeline on all watchlist stocks."""
    results = []

    for ticker in get_all_tickers():
        logger.info(f"📊 Analyzing {ticker}...")

        data = fetch_stock_data(ticker)
        if not data:
            continue

        quant = quant_analyze(data)
        news = news_analyze(data)
        bull = bull_analyze(data, quant, news)
        bear = bear_analyze(data, quant, news)
        ceo = ceo_judge(data, quant, news, bull, bear, lessons)

        results.append({
            "data": data,
            "quant": quant,
            "news": news,
            "bull": bull,
            "bear": bear,
            "ceo": ceo,
        })

        logger.info(f"   → {ticker}: {ceo['decision']} (Score: {ceo['quant_score']}, Confidence: {ceo['confidence']}%)")

    # Sort by quant score (highest first)
    results.sort(key=lambda x: x["ceo"]["quant_score"], reverse=True)
    return results


def select_top_pick(results: List[Dict]) -> Optional[Dict]:
    """Select the #1 Top Pick of the Day (highest quant score with BUY verdict)."""
    buy_candidates = [r for r in results if r["ceo"]["decision"] == "BUY"]
    if buy_candidates:
        return buy_candidates[0]  # Already sorted by quant score

    # If no BUY, pick best HOLD
    hold_candidates = [r for r in results if r["ceo"]["decision"] == "HOLD"]
    if hold_candidates:
        return hold_candidates[0]

    return results[0] if results else None
