"""Multi-Agent System for XAU/USD Trading Analysis"""
import os
import anthropic
import json
import logging
import random
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        if os.getenv("USE_MOCK_AI", "false").lower() == "true" or not self.client:
            # Return a realistic mock technical analysis
            return {
                "trend": "bullish" if indicators.get("close", 0) > indicators.get("ema_200", 0) else "bearish",
                "rsi_value": indicators.get("rsi", 50.0),
                "rsi_state": "oversold" if indicators.get("rsi", 50) < 30 else ("overbought" if indicators.get("rsi", 50) > 70 else "neutral"),
                "macd_state": "bullish" if indicators.get("macd", 0) > indicators.get("macd_signal", 0) else "bearish",
                "fibo_retracements": indicators.get("fib_levels", {}),
                "support_resistance": {
                    "support": indicators.get("close", 0) * 0.99,
                    "resistance": indicators.get("close", 0) * 1.01
                },
                "technical_summary": f"RSI is at {indicators.get('rsi', 50.0):.1f}. Price is trading relative to EMA 200."
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
        if os.getenv("USE_MOCK_AI", "false").lower() == "true" or not self.client:
            return {
                "fed_sentiment": "dovish",
                "us_dollar_sentiment": "weak",
                "geopolitical_risk": "medium",
                "safe_haven_demand": "strong",
                "fundamental_bias": "bullish",
                "fundamental_summary": "Mock: Dovish expectations from the Federal Reserve support gold prices."
            }

        prompt = f"""You are a Fundamental Forex Analyst specializing in XAU/USD.
Your task is to analyze news events specifically affecting gold prices. Focus strictly on major high-impact drivers like:
- The Federal Reserve (Fed) monetary policy decisions (Hawkish/Dovish).
- US Treasury yields and inflation expectations.
- Safe-haven demand and geopolitical risk.

CRITICAL: Do NOT make a final trading decision. Only output the objective fundamental impact on Gold.

Recent News context (if empty, analyze general macro backdrop for Gold):
{news_text or "General macro conditions"}

Provide your analysis in this exact JSON format:
{{
    "fed_sentiment": "hawkish" | "dovish" | "neutral",
    "us_dollar_sentiment": "strong" | "weak" | "neutral",
    "geopolitical_risk": "high" | "medium" | "low",
    "safe_haven_demand": "strong" | "weak" | "neutral",
    "fundamental_bias": "bullish" | "bearish" | "neutral",
    "fundamental_summary": "Detailed fundamental report explaining the macro impacts on XAU/USD."
}}
Do NOT output any other text or markdown tags outside the raw JSON."""

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
        if os.getenv("USE_MOCK_AI", "false").lower() == "true" or not self.client:
            trend = quant_analysis.get("trend", "neutral")
            rsi = quant_analysis.get("rsi_value", 50.0)
            
            # Pullback Strategy: In an uptrend, only buy when price pulls back (RSI <= 50)
            if trend == "bullish" and rsi <= 50.0:
                score = 0.85
                argument = f"Mock BUY Case: Uptrend pullback detected (RSI={rsi:.1f}). Favorable long entry."
            elif trend == "bearish" and rsi < 30.0:
                score = 0.75  # Deep oversold bounce play
                argument = f"Mock BUY Case: Extreme oversold bounce in downtrend (RSI={rsi:.1f})."
            else:
                score = 0.40  # Avoid buying when price is overextended or trending down
                argument = f"Mock BUY Case: High risk entry (RSI={rsi:.1f}, Trend={trend}). Standing aside."
                
            return {
                "bullish_argument": argument,
                "conviction_score": score,
                "target_price_limit": 25.0
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
        if os.getenv("USE_MOCK_AI", "false").lower() == "true" or not self.client:
            trend = quant_analysis.get("trend", "neutral")
            rsi = quant_analysis.get("rsi_value", 50.0)
            
            # Pullback Strategy: In a downtrend, only sell when price rallies (RSI >= 50)
            if trend == "bearish" and rsi >= 50.0:
                score = 0.85
                argument = f"Mock SELL Case: Downtrend rally detected (RSI={rsi:.1f}). Favorable short entry."
            elif trend == "bullish" and rsi > 70.0:
                score = 0.75  # Overbought correction play
                argument = f"Mock SELL Case: Extreme overbought pullback in uptrend (RSI={rsi:.1f})."
            else:
                score = 0.40  # Avoid selling when price is at bottoms
                argument = f"Mock SELL Case: High risk entry (RSI={rsi:.1f}, Trend={trend}). Standing aside."
                
            return {
                "bearish_argument": argument,
                "conviction_score": score,
                "target_price_limit": 20.0
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
    """The Ultimate Decision Maker. Acts as an unbiased, highly experienced mediator. Combines objective facts, past learnings, and debates to choose the best trade path."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY) if Config.ANTHROPIC_API_KEY else None
        self.model = "claude-3-haiku-20240307"

    def decide(self, quant_data: Dict, news_data: Dict, bull_case: Dict, bear_case: Dict, market_regime: str) -> Dict[str, Any]:
        if os.getenv("USE_MOCK_AI", "false").lower() == "true" or not self.client:
            # Mock decision making
            bull_score = bull_case.get("conviction_score", 0.5)
            bear_score = bear_case.get("conviction_score", 0.5)
            
            if market_regime in ["HIGH_VOLATILITY", "LOW_LIQUIDITY"]:
                decision = "NO_TRADE"
                reason = f"Mock CEO: Standing aside due to unsafe market regime: {market_regime}."
            elif bull_score > bear_score + 0.01:
                decision = "BUY"
                reason = "Mock CEO: Approving BUY as the technical/fundamental bull case outweighs the bear case."
            elif bear_score > bull_score + 0.01:
                decision = "SELL"
                reason = "Mock CEO: Approving SELL as the technical/fundamental bear case outweighs the bull case."
            else:
                decision = "NO_TRADE"
                reason = "Mock CEO: Insufficient edge or conflicting signals. Standing aside."
                
            return {
                "decision": decision,
                "confidence": round(max(bull_score, bear_score), 2) if decision != "NO_TRADE" else 0.50,
                "reasoning": reason,
                "executive_summary": "Mock CEO has balanced the cases neutrally."
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
1. Trend Alignment: Always prioritize the primary trend. Fading a strong trend has low probability.
2. S&R Validation: Do not buy directly into major resistance, nor sell directly into major support.
3. Volatility Management: In extremely volatile (HIGH_VOLATILITY) or quiet (LOW_LIQUIDITY) periods, stand aside immediately.
4. Objective Neutrality: Do not get emotional about the arguments. Weigh the Bull and Bear conviction objectively.

Determine the final trading action.
Provide your final decision in this exact JSON format:
{{
    "decision": "BUY" | "SELL" | "NO_TRADE",
    "confidence": <float between 0.0 and 1.0 indicating conviction level>,
    "reasoning": "Unbiased, detailed explanation of how you evaluated both cases and reached this decision.",
    "executive_summary": "Brief executive memo to the fund board."
}}
Do NOT output any other text or markdown tags outside the raw JSON."""

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
