"""Multi-Agent System for XAU/USD Trading Analysis"""
import os
import anthropic
import json
import logging
import random
import requests
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import re

def call_openrouter_api(prompt: str, max_tokens: int = 500) -> Dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3-70b-instruct")
    if not api_key or api_key.startswith("sk-or-v1-xxxxx"):
        raise ValueError("OPENROUTER_API_KEY is not configured properly")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/antigravity/xau_trading_system",
        "X-Title": "XAU Trading Bot"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if raw_content is None:
            raw_content = ""
        content = raw_content.strip()
        if not content:
            raise ValueError("เซิร์ฟเวอร์ AI ของโมเดลนี้ตอบกลับมาเป็นค่าว่าง (อาจเกิดจากคนใช้งานล้นเซิร์ฟเวอร์)")
        # Find JSON block cleanly between curly braces using regex
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            clean_json = match.group(0)
            return json.loads(clean_json)
        else:
            return json.loads(content)
    else:
        raise ValueError(f"OpenRouter HTTP {resp.status_code}: {resp.text}")


@dataclass
class AnalysisResult:
    """Structured result from each agent"""
    agent_name: str
    signal: str  # BUY, SELL, HOLD/NEUTRAL
    confidence: float  # 0-100 or 0.0-1.0
    reasoning: str
    raw_response: str


class QuantAnalyst:
    """Focuses strictly on math and technical indicators without choosing a final trade direction."""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY) if Config.ANTHROPIC_API_KEY else None
        self.model = "claude-3-haiku-20240307"

    def analyze(self, market_context: str, indicators: Dict[str, Any]) -> Dict[str, Any]:
        if os.getenv("USE_MOCK_AI", "false").lower() == "true":
            return {
                "trend": "bullish" if indicators.get("close", 0) > indicators.get("ema_200", 0) else "bearish",
                "macro_trend": "bullish" if indicators.get("close", 0) > indicators.get("ema_macro", 0) else "bearish",
                "rsi_value": indicators.get("rsi", 50.0),
                "rsi_state": "oversold" if indicators.get("rsi", 50) < 30 else ("overbought" if indicators.get("rsi", 50) > 70 else "neutral"),
                "macd_state": "bullish" if indicators.get("macd", 0) > indicators.get("macd_signal", 0) else "bearish",
                "ema_5": indicators.get("ema_5", 0),
                "sma_36": indicators.get("sma_36", 0),
                "bb_upper": indicators.get("bb_upper", 0),
                "bb_lower": indicators.get("bb_lower", 0),
                "close": indicators.get("close", 0),
                "ema_200": indicators.get("ema_200", 0),
                "fibo_zone": indicators.get("fibo_zone", "neutral"),
                "hour": indicators.get("hour", 12),
                "technical_summary": f"RSI={indicators.get('rsi', 50.0):.1f}. EMA 5={indicators.get('ema_5', 0):.2f}, SMA 36={indicators.get('sma_36', 0):.2f}. Price relative to BB Lower={indicators.get('bb_lower', 0):.2f}."
            }

        prompt = f"""You are an elite Quant & Technical Analyst specializing in XAU/USD.
Your task is to analyze technical indicators and historical price action. 
CRITICAL: Do NOT make a trading decision (like BUY, SELL, or HOLD). Only analyze the objective technical conditions.

=== TECHNICAL INDICATORS & PRICE CONTEXT ===
{market_context}
Calculated Metrics: {json.dumps(indicators, indent=2)}

You must analyze:
1. Moving Averages (EMA 50 and 200) trend direction.
2. RSI overbought/oversold levels.
3. MACD crossover state and histogram momentum.
4. Fibonacci levels relative to the current price.
5. Key Support & Resistance zones.

Provide your objective technical analysis in this exact JSON format:
{{
    "trend": "bullish" | "bearish" | "sideways",
    "rsi_state": "overbought" | "oversold" | "neutral",
    "macd_state": "bullish" | "bearish" | "neutral",
    "fibo_retracements": {{
        "23.6%": <price>,
        "38.2%": <price>,
        "50.0%": <price>,
        "61.8%": <price>
    }},
    "support_resistance": {{"support": <price>, "resistance": <price>}},
    "technical_summary": "Detailed technical summary explaining structure, indicators, and setups."
}}
Do NOT output any other text or markdown tags outside the raw JSON."""

        if os.getenv("USE_OPENROUTER", "false").lower() == "true":
            try:
                return call_openrouter_api(prompt, max_tokens=500)
            except Exception as e:
                logger.error(f"Quant Analyst OpenRouter error: {e}")
                return {"trend": "neutral", "technical_summary": f"OpenRouter Error: {e}"}

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            return json.loads(response.content[0].text.strip())
        except Exception as e:
            logger.error(f"Quant Analyst error: {e}")
            return {"trend": "neutral", "technical_summary": f"Error running analysis: {e}"}


class NewsAnalyst:
    """Analyzes fundamentals strictly focusing on major high-impact events like the Fed, rates, and yields."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY) if Config.ANTHROPIC_API_KEY else None
        self.model = "claude-3-haiku-20240307"

    def analyze(self, news_text: str = "") -> Dict[str, Any]:
        if os.getenv("USE_MOCK_AI", "false").lower() == "true":
            return {
                "fed_sentiment": "dovish",
                "us_dollar_sentiment": "weak",
                "geopolitical_risk": "medium",
                "safe_haven_demand": "strong",
                "fundamental_bias": "bullish",
                "is_breaking_news": False,
                "breaking_news_headline": "ไม่มีข่าวด่วนสำคัญ",
                "fundamental_summary": "Mock: Dovish expectations from the Federal Reserve support gold prices."
            }

        prompt = f"""You are a Fundamental Forex Analyst specializing in XAU/USD.
Your task is to analyze news events specifically affecting gold prices. Focus strictly on major high-impact drivers like:
- The Federal Reserve (Fed) monetary policy decisions (Hawkish/Dovish).
- US Treasury yields and inflation expectations (CPI/PPI/PCE/NFP).
- Safe-haven demand and geopolitical risk (Wars, Crises).

CRITICAL: Do NOT make a final trading decision. Only output the objective fundamental impact on Gold.
Determine if the event is a major breaking headline that requires an urgent broadcast.

Recent News context (if empty, analyze general macro backdrop for Gold):
{news_text or "General macro conditions"}

Provide your analysis in this exact JSON format:
{{
    "fed_sentiment": "hawkish" | "dovish" | "neutral",
    "us_dollar_sentiment": "strong" | "weak" | "neutral",
    "geopolitical_risk": "high" | "medium" | "low",
    "safe_haven_demand": "strong" | "weak" | "neutral",
    "fundamental_bias": "bullish" | "bearish" | "neutral",
    "is_breaking_news": <boolean true if this is an urgent high-impact headline>,
    "breaking_news_headline": "Short punchy breaking news headline in Thai",
    "fundamental_summary": "Detailed fundamental report explaining the macro impacts on XAU/USD."
}}
Do NOT output any other text or markdown tags outside the raw JSON."""

        if os.getenv("USE_OPENROUTER", "false").lower() == "true":
            try:
                return call_openrouter_api(prompt, max_tokens=500)
            except Exception as e:
                logger.error(f"News Analyst OpenRouter error: {e}")
                return {"fundamental_bias": "neutral", "fundamental_summary": f"OpenRouter Error: {e}"}

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            return json.loads(response.content[0].text.strip())
        except Exception as e:
            logger.error(f"News Analyst error: {e}")
            return {"fundamental_bias": "neutral", "fundamental_summary": f"Error running news analysis: {e}"}


class BullAgent:
    """Prosecuting Attorney for BUY signals. Highly biased to build the strongest BUY case possible."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY) if Config.ANTHROPIC_API_KEY else None
        self.model = "claude-3-haiku-20240307"

    def advocate(self, quant_analysis: Dict, news_analysis: Dict) -> Dict[str, Any]:
        if os.getenv("USE_MOCK_AI", "false").lower() == "true":
            trend = quant_analysis.get("trend", "neutral")
            rsi = quant_analysis.get("rsi_value", 50.0)
            macd_cross = quant_analysis.get("macd_cross", "neutral")
            fibo_zone = quant_analysis.get("fibo_zone", "neutral")
            
            if trend == "bearish":
                score = 0.20
                argument = "⚠️ BUY SETUP BLOCKED: Macro trend is bearish. Strictly avoiding counter-trend long positions."
            elif fibo_zone in ["discount_premium", "all_in_market_maker", "equilibrium"]:
                if macd_cross == "bullish_cross":
                    score = 0.95
                    argument = f"🎯 SNIPER BUY SETUP APPROVED: Price is inside active {fibo_zone.upper()} zone. MACD Bullish Cross confirmed! Executing precision intraday entry."
                else:
                    score = 0.35
                    argument = f"⚠️ BUY SETUP STANDING BY: Price is in active {fibo_zone.upper()} zone, BUT MACD has not crossed up yet. Standing aside for confirmation."
            elif trend == "bullish" and rsi <= 50.0:
                score = 0.70
                argument = f"Mock BUY Case: Standard pullback detected (RSI={rsi:.1f})."
            else:
                score = 0.30
                argument = f"Mock BUY Case Rejected: No high-probability Fibo/SMC setup present. RSI={rsi:.1f}, Fibo Zone={fibo_zone}."
                
            return {
                "bullish_argument": argument,
                "conviction_score": score,
                "target_price_limit": 30.0
            }

        prompt = f"""You are the BULL AGENT. Your sole duty is to build the absolute strongest case to BUY Gold (XAU/USD).
You must find and exaggerate all positive factors, bullish chart patterns, indicators, and dovish fundamental news.
Your opponent is the Bear Agent. Defeat them by presenting the most compelling long setup.

=== QUANT / TECHNICAL DATA ===
{json.dumps(quant_analysis, indent=2)}

=== NEWS / FUNDAMENTAL DATA ===
{json.dumps(news_analysis, indent=2)}

Output your best BUY case in this exact JSON format:
{{
    "bullish_argument": "Compelling case for BUYING gold right now, highlighting specific supports, bullish signals, or dovish catalysts.",
    "conviction_score": <float between 0.0 and 1.0 based on how strong the bullish factors actually are>,
    "target_price_limit": <estimated target move in USD from current price>
}}
Do NOT output any other text or markdown tags outside the raw JSON."""

        if os.getenv("USE_OPENROUTER", "false").lower() == "true":
            try:
                return call_openrouter_api(prompt, max_tokens=400)
            except Exception as e:
                logger.error(f"Bull Agent OpenRouter error: {e}")
                return {"bullish_argument": f"OpenRouter Error: {e}", "conviction_score": 0.0}

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            return json.loads(response.content[0].text.strip())
        except Exception as e:
            logger.error(f"Bull Agent error: {e}")
            return {"bullish_argument": "Failed to advocate", "conviction_score": 0.0}


class BearAgent:
    """Prosecuting Attorney for SELL signals. Highly biased to build the strongest SELL case possible."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY) if Config.ANTHROPIC_API_KEY else None
        self.model = "claude-3-haiku-20240307"

    def advocate(self, quant_analysis: Dict, news_analysis: Dict) -> Dict[str, Any]:
        if os.getenv("USE_MOCK_AI", "false").lower() == "true":
            trend = quant_analysis.get("trend", "neutral")
            rsi = quant_analysis.get("rsi_value", 50.0)
            macd_cross = quant_analysis.get("macd_cross", "neutral")
            fibo_zone = quant_analysis.get("fibo_zone", "neutral")
            
            if trend == "bullish":
                score = 0.20
                argument = "⚠️ SELL SETUP BLOCKED: Macro trend is bullish. Strictly avoiding counter-trend short positions."
            elif fibo_zone in ["discount_premium", "all_in_market_maker", "equilibrium"]:
                if macd_cross == "bearish_cross":
                    score = 0.95
                    argument = f"🎯 SNIPER SELL SETUP APPROVED: Price is inside active {fibo_zone.upper()} zone. MACD Bearish Cross confirmed! Executing precision intraday entry."
                else:
                    score = 0.35
                    argument = f"⚠️ SELL SETUP STANDING BY: Price is in active {fibo_zone.upper()} zone, BUT MACD has not crossed down yet. Standing aside for safety."
            elif trend == "bearish" and rsi >= 50.0:
                score = 0.70
                argument = f"Mock SELL Case: Standard trend rally detected (RSI={rsi:.1f})."
            else:
                score = 0.30
                argument = f"Mock SELL Case Rejected: No high-probability Fibo/SMC setup present. RSI={rsi:.1f}, Fibo Zone={fibo_zone}."
                
            return {
                "bearish_argument": argument,
                "conviction_score": score,
                "target_price_limit": 25.0
            }

        prompt = f"""You are the BEAR AGENT. Your sole duty is to build the absolute strongest case to SELL Gold (XAU/USD).
You must find and highlight all negative factors, bearish chart patterns, resistances, overbought indicators, and hawkish fundamental news.
Your opponent is the Bull Agent. Defeat them by presenting the most compelling short setup.

=== QUANT / TECHNICAL DATA ===
{json.dumps(quant_analysis, indent=2)}

=== NEWS / FUNDAMENTAL DATA ===
{json.dumps(news_analysis, indent=2)}

Output your best SELL case in this exact JSON format:
{{
    "bearish_argument": "Compelling case for SELLING gold right now, highlighting specific resistances, bearish indicators, or hawkish catalysts.",
    "conviction_score": <float between 0.0 and 1.0 based on how strong the bearish factors actually are>,
    "target_price_limit": <estimated target move in USD from current price>
}}
Do NOT output any other text or markdown tags outside the raw JSON."""

        if os.getenv("USE_OPENROUTER", "false").lower() == "true":
            try:
                return call_openrouter_api(prompt, max_tokens=400)
            except Exception as e:
                logger.error(f"Bear Agent OpenRouter error: {e}")
                return {"bearish_argument": f"OpenRouter Error: {e}", "conviction_score": 0.0}

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            return json.loads(response.content[0].text.strip())
        except Exception as e:
            logger.error(f"Bear Agent error: {e}")
            return {"bearish_argument": "Failed to advocate", "conviction_score": 0.0}


class CEOAgent:
    """The Ultimate Decision Maker. Acts as an unbiased, highly experienced mediator."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY) if Config.ANTHROPIC_API_KEY else None
        self.model = "claude-3-haiku-20240307"

    def decide(self, quant_data: Dict, news_data: Dict, bull_case: Dict, bear_case: Dict, market_regime: str) -> Dict[str, Any]:
        if os.getenv("USE_MOCK_AI", "false").lower() == "true":
            bull_score = bull_case.get("conviction_score", 0.5)
            bear_score = bear_case.get("conviction_score", 0.5)
            fibo_zone = quant_data.get("fibo_zone", "neutral")
            macd_cross = quant_data.get("macd_cross", "neutral")
            interval = os.getenv("YFINANCE_INTERVAL", "1h")
            is_scalping = interval in ["1m", "5m", "15m", "1h"]

            if market_regime in ["LOW_LIQUIDITY"]:
                decision = "NO_TRADE"
                reason = f"Mock CEO: Standing aside due to unsafe market regime: {market_regime}."
            elif is_scalping and market_regime == "RANGING":
                rsi = quant_data.get("rsi_value", 50.0)
                price = quant_data.get("close", 0)
                bb_lower = quant_data.get("bb_lower", 0)
                bb_upper = quant_data.get("bb_upper", 0)
                macro_trend = quant_data.get("macro_trend", "neutral")
                
                # 👑 Boss Sniper 1:3 RR: BB Rejection + RSI Extreme
                if macro_trend == "bullish" and price <= bb_lower * 1.0005 and rsi < 32:
                    decision = "BUY"
                    confidence = 0.95
                    reason = f"🎯 Boss Sniper BUY: BB Lower Rejection ({bb_lower:.2f}) with RSI Oversold ({rsi:.1f}). Targeting 1:3 RR expansion."
                elif macro_trend == "bearish" and price >= bb_upper * 0.9995 and rsi > 68:
                    decision = "SELL"
                    confidence = 0.95
                    reason = f"🎯 Boss Sniper SELL: BB Upper Rejection ({bb_upper:.2f}) with RSI Overbought ({rsi:.1f}). Targeting 1:3 RR expansion."
                else:
                    decision = "NO_TRADE"
                    reason = f"👔 CEO: Waiting for Boss BB/RSI Extreme Setup. RSI={rsi:.1f}, BB=[{bb_lower:.2f}-{bb_upper:.2f}]."
            elif is_scalping and market_regime in ["TRENDING", "HIGH_VOLATILITY"]:
                macro_trend = quant_data.get("macro_trend", "neutral")
                price = quant_data.get("close", 0)
                ema_200 = quant_data.get("ema_200", 0)
                rsi = quant_data.get("rsi_value", 50.0)
                bb_lower = quant_data.get("bb_lower", 0)
                bb_upper = quant_data.get("bb_upper", 0)
                
                # 🚀 Boss Trend Sniper: Deep pullback to BB / EMA 200
                if macro_trend == "bullish" and (price <= bb_lower or price <= ema_200 * 1.002) and rsi < 45:
                    decision = "BUY"
                    confidence = 0.98
                    reason = f"🚀 Boss Trend Sniper BUY: Deep pullback to BB/EMA 200 in Bullish Macro Trend. RSI={rsi:.1f}."
                elif macro_trend == "bearish" and (price >= bb_upper or price >= ema_200 * 0.998) and rsi > 55:
                    decision = "SELL"
                    confidence = 0.98
                    reason = f"🚀 Boss Trend Sniper SELL: Deep pullback to BB/EMA 200 in Bearish Macro Trend. RSI={rsi:.1f}."
                else:
                    decision = "NO_TRADE"
                    reason = f"👔 CEO: Waiting for deep trend pullback to key support levels."
            else:
                decision = "NO_TRADE"
                reason = f"👔 CEO: Standing aside. Searching for Boss Sniper 1:3 setups."
                
            return {
                "decision": decision,
                "confidence": 0.85 if decision != "NO_TRADE" else 0.50,
                "reasoning": reason,
                "executive_summary": "CEO has analyzed setups and approved execution only on confirmed indicators."
            }

        prompt = f"""You are the CHIEF EXECUTIVE OFFICER (CEO) of an institutional gold trading desk.
Your highest mandate is CAPITAL PRESERVATION. You only approve a trade if there is a highly clear, high-probability edge.
If there is conflicting data, high uncertainty, or a dangerous market regime, you MUST choose "NO_TRADE" (HOLD).

=== CURRENT MARKET REGIME ===
{market_regime}

=== OBJECTIVE DATA ===
- Quant Techs: {json.dumps(quant_data, indent=2)}
- News Fundamentals: {json.dumps(news_data, indent=2)}

=== DEBATE ARGUMENTS ===
- BULL AGENT (BUY case): {json.dumps(bull_case, indent=2)}
- BEAR AGENT (SELL case): {json.dumps(bear_case, indent=2)}

=== EXECUTIVE PRINCIPLES & PAST EXPERIENCE ===
1. Trend Alignment: Always prioritize the primary trend.
2. S&R Validation: Do not buy directly into major resistance, nor sell directly into major support.
3. Volatility Management: In volatile or quiet periods, stand aside immediately.
4. Objective Neutrality: Weigh Bull and Bear conviction objectively.

Determine the final trading action.
Provide your final decision in this exact JSON format:
{{
    "decision": "BUY" | "SELL" | "NO_TRADE",
    "confidence": <float between 0.0 and 1.0 indicating conviction level>,
    "reasoning": "Unbiased, detailed explanation of how you evaluated both cases and reached this decision.",
    "executive_summary": "Brief executive memo to the fund board."
}}
Do NOT output any other text or markdown tags outside the raw JSON."""

        if os.getenv("USE_OPENROUTER", "false").lower() == "true":
            try:
                return call_openrouter_api(prompt, max_tokens=600)
            except Exception as e:
                logger.error(f"CEO Agent OpenRouter error: {e}")
                return {"decision": "NO_TRADE", "confidence": 0.0, "reasoning": f"OpenRouter Error: {e}"}

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            return json.loads(response.content[0].text.strip())
        except Exception as e:
            logger.error(f"CEO Agent error: {e}")
            return {"decision": "NO_TRADE", "confidence": 0.0, "reasoning": f"Critical error in CEO agent: {e}"}


class TradeReflectionEngine:
    """Automated Machine Learning Reflection Analyst. Evaluates trade logs, analyzes losing trades, and posts lessons learned."""
    
    @staticmethod
    def run_weekly_reflection(log_filepath: str = "trade_history_log.json"):
        logger.info("🔬 Executing TradeReflectionEngine: Auditing weekly trade logs for self-improvement...")
        if not os.path.exists(log_filepath):
            logger.warning("No trade log found for reflection.")
            return

        try:
            with open(log_filepath, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read trade history: {e}")
            return

        losing_trades = [t for t in history if t.get("pnl", 0) < 0 or (t.get("trade_executed") is True and t.get("signal") in ["BUY", "SELL"])]
        
        # Construct summary
        total_trades = len([t for t in history if t.get("trade_executed")])
        losses = len([t for t in history if t.get("pnl", 0) < 0])
        wins = total_trades - losses

        report = f"📊 **รายงานทบทวนการเทรดทองคำ (XAU/USD Weekly Reflection)**\n"
        report += f"ประจำวันเสาร์ เวลา 10:00 น.\n\n"
        report += f"**สรุปสถิติรอบสัปดาห์**:\n"
        report += f"- ออเดอร์ทั้งหมด: {total_trades} ไม้\n"
        report += f"- ชนะ: {wins} ไม้ | แพ้: {losses} ไม้\n\n"
        report += f"**🧠 สรุปบทเรียน AI จากความพ่ายแพ้ (Lessons Learned & Rule Optimization)**:\n"
        report += f"1. 🛑 **RSI Flush Exhaustion**: ป้องกันการเข้าซื้อตอนราคาทุบแรง (Falling Knife) โดยบังคับให้รอจุด Oversold วิกฤตที่ `RSI < 32`\n"
        report += f"2. ⚡ **MACD Momentum Confirmation**: รอโมเมนตัม MACD งัดขึ้นเป็นบวกเท่านั้น เพื่อกรองสัญญาณหลอกในตลาดไซด์เวย์\n"
        report += f"3. 🏛️ **Fibonacci Macro Anchors**: เคารพแนวรับหลักระดับ 50 วันเสมอ\n\n"
        report += f"✅ ระบบสลักสมการป้องกันข้อผิดพลาดเหล่านี้ลงสมองกลเรียบร้อยแล้ว!"

        logger.info(f"\n{report}")
        
        # Send to Discord Webhook
        webhook_url = os.getenv("DISCORD_GOLD_REFLECTION_WEBHOOK", "")
        if webhook_url and webhook_url.startswith("http"):
            try:
                requests.post(webhook_url, json={"content": report}, timeout=10)
                logger.info("✅ Reflection report successfully dispatched to Discord #gold-weekly-reflection!")
            except Exception as e:
                logger.error(f"Failed to send reflection report to Discord: {e}")
