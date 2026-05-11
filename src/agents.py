"""Multi-Agent System for XAU/USD Trading Analysis"""
import os
import anthropic
from typing import Dict, List, Tuple
from dataclasses import dataclass
from config import Config
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AnalysisResult:
    """Structured result from each agent"""
    agent_name: str
    signal: str  # BUY, SELL, HOLD
    confidence: float  # 0-100
    reasoning: str
    raw_response: str

class NewsAnalyst:
    """Analyzes news and fundamental factors affecting XAU/USD"""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.model = Config.ANALYST_MODEL

    def analyze(self, market_context: str, recent_news: str = "") -> AnalysisResult:
        """Analyze news impact on gold prices"""

        prompt = f"""You are an expert Forex analyst specializing in gold (XAU/USD) trading.
Analyze the following market context and news to provide trading signals.

{market_context}

Recent News Context:
{recent_news or "No specific news provided - use fundamental understanding of gold market drivers."}

Key factors affecting XAU/USD:
- US Dollar strength/weakness (inverse relationship)
- Fed interest rates and monetary policy
- Geopolitical tensions and safe-haven demand
- Real yields
- Risk appetite in markets
- Inflation expectations

Provide your analysis in this exact JSON format:
{{
    "signal": "BUY" or "SELL" or "HOLD",
    "confidence": <0-100>,
    "bullish_factors": [list of factors],
    "bearish_factors": [list of factors],
    "reasoning": "Brief explanation",
    "price_target": "Expected direction + target price range"
}}"""

        if os.getenv("USE_MOCK_AI", "false").lower() == "true":
            import random
            signal = random.choice(["BUY", "SELL", "HOLD"])
            return AnalysisResult(
                agent_name="News Analyst",
                signal=signal,
                confidence=random.randint(60, 85),
                reasoning=f"Mock: Geopolitical tensions and market sentiment suggest a potential {signal}.",
                raw_response="{}"
            )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text
            analysis = json.loads(content)

            return AnalysisResult(
                agent_name="News Analyst",
                signal=analysis["signal"],
                confidence=analysis["confidence"],
                reasoning=analysis["reasoning"],
                raw_response=content
            )

        except Exception as e:
            logger.error(f"News Analyst error: {e}")
            return AnalysisResult(
                agent_name="News Analyst",
                signal="HOLD",
                confidence=0,
                reasoning=f"Analysis failed: {str(e)}",
                raw_response=""
            )

class TechnicalAnalyst:
    """Analyzes price action and technical indicators"""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.model = Config.ANALYST_MODEL

    def analyze(self, market_context: str) -> AnalysisResult:
        """Analyze technical indicators"""

        prompt = f"""You are a professional technical analyst specializing in XAU/USD trading.
Analyze the following technical data to provide trading signals.

{market_context}

Technical Analysis Framework:
1. RSI (Relative Strength Index):
   - <30: Oversold (potential BUY)
   - 30-70: Normal range
   - >70: Overbought (potential SELL)

2. MACD (Moving Average Convergence Divergence):
   - MACD > Signal: Bullish
   - MACD < Signal: Bearish
   - Histogram momentum

3. Bollinger Bands:
   - Price > Upper Band: Overbought
   - Price < Lower Band: Oversold
   - Mean reversion signal

4. ATR (Average True Range):
   - Volatility measurement
   - Used for stop-loss and take-profit sizing

Provide analysis in this exact JSON format:
{{
    "signal": "BUY" or "SELL" or "HOLD",
    "confidence": <0-100>,
    "trend": "Uptrend" or "Downtrend" or "Ranging",
    "support_resistance": {{"support": <price>, "resistance": <price>}},
    "entry_points": [list of suggested entry prices],
    "technical_analysis": {{
        "rsi": "Overbought/Oversold/Normal",
        "macd": "Bullish/Bearish/Neutral",
        "bollinger": "Breakout/Reversal/Range",
        "volatility": "High/Medium/Low"
    }},
    "reasoning": "Detailed technical reasoning",
    "stop_loss_level": <suggested SL price>,
    "take_profit_levels": [<TP1>, <TP2>]
}}"""

        if os.getenv("USE_MOCK_AI", "false").lower() == "true":
            import random
            import re
            signal = random.choice(["BUY", "SELL", "HOLD"])
            
            # Try to extract the current gold price from the market context
            current_price = 2300.0
            match = re.search(r"C=(\d+\.?\d*)", market_context)
            if match:
                current_price = float(match.group(1))
            
            # Generate Formula A: Day Trading SL (0.2%) and TP (0.4%) relative to current price
            if signal == "BUY":
                sl = current_price * 0.998
                tp = current_price * 1.004
            elif signal == "SELL":
                sl = current_price * 1.002
                tp = current_price * 0.996
            else:
                sl = current_price * 0.998
                tp = current_price * 1.004
                
            return AnalysisResult(
                agent_name="Technical Analyst",
                signal=signal,
                confidence=random.randint(65, 90),
                reasoning=f"Mock: Technical indicators suggest intraday {signal} momentum.",
                raw_response=f'{{"stop_loss_level": {sl:.2f}, "take_profit_levels": [{tp:.2f}, {tp*1.002:.2f}]}}'
            )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text
            analysis = json.loads(content)

            return AnalysisResult(
                agent_name="Technical Analyst",
                signal=analysis["signal"],
                confidence=analysis["confidence"],
                reasoning=analysis["reasoning"],
                raw_response=content
            )

        except Exception as e:
            logger.error(f"Technical Analyst error: {e}")
            return AnalysisResult(
                agent_name="Technical Analyst",
                signal="HOLD",
                confidence=0,
                reasoning=f"Analysis failed: {str(e)}",
                raw_response=""
            )

class RiskManager:
    """Manages position sizing, stop-loss, take-profit levels"""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.model = Config.ANALYST_MODEL

    def calculate(self, account_balance: float, signal: str, atr: float,
                  entry_price: float, stop_loss: float) -> Dict:
        """Calculate position size and risk metrics"""

        prompt = f"""You are an expert risk management specialist in Forex trading.

Portfolio Information:
- Account Balance: ${account_balance:,.2f}
- Current Signal: {signal}
- ATR (volatility): {atr:.2f}
- Entry Price: {entry_price:.2f}
- Suggested Stop Loss: {stop_loss:.2f}

Risk Management Rules:
- Max Risk per Trade: {Config.POSITION_SIZE_PERCENT}% of account
- Risk/Reward Ratio: {Config.RISK_REWARD_RATIO}:1
- Max Drawdown: {Config.MAX_DRAWDOWN_PERCENT}%
- Max Open Positions: {Config.MAX_OPEN_POSITIONS}

Calculate and provide in JSON format:
{{
    "position_size": <lot_size>,
    "risk_amount": <dollar_amount_at_risk>,
    "stop_loss": <SL_price>,
    "take_profit_1": <TP1_price>,
    "take_profit_2": <TP2_price>,
    "risk_reward_actual": <actual_RR_ratio>,
    "position_sizing_rule": "Kelly Criterion" or "Fixed Percentage" or "ATR-based",
    "reasoning": "Risk calculation explanation"
}}"""

        if os.getenv("USE_MOCK_AI", "false").lower() == "true":
            import random
            risk_pct = Config.POSITION_SIZE_PERCENT
            risk_amt = account_balance * (risk_pct / 100.0)
            return {
                "position_size": round(risk_amt / (atr * 100.0 if atr > 0 else 50.0), 2) or 0.1,
                "risk_amount": risk_amt,
                "stop_loss": stop_loss,
                "take_profit_1": entry_price + (entry_price - stop_loss) * Config.RISK_REWARD_RATIO if signal == "BUY" else entry_price - (stop_loss - entry_price) * Config.RISK_REWARD_RATIO,
                "take_profit_2": entry_price + (entry_price - stop_loss) * Config.RISK_REWARD_RATIO * 1.5 if signal == "BUY" else entry_price - (stop_loss - entry_price) * Config.RISK_REWARD_RATIO * 1.5,
                "risk_reward_actual": Config.RISK_REWARD_RATIO,
                "position_sizing_rule": "Fixed Percentage",
                "reasoning": "Mock: Calculated position sizing based on account balance and stop loss parameters."
            }

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text
            result = json.loads(content)
            return result

        except Exception as e:
            logger.error(f"Risk Manager error: {e}")
            return {"error": str(e), "position_size": 0}

class ConsensusEngine:
    """Aggregates analysis from multiple agents and decides final signal"""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.model = Config.ORCHESTRATOR_MODEL

    def decide(self, analyses: List[AnalysisResult]) -> Tuple[str, float, str]:
        """
        Combine multiple analyses to reach consensus decision

        Returns:
            Tuple of (signal, confidence, reasoning)
        """

        # Format all analyses
        analysis_text = ""
        for analysis in analyses:
            analysis_text += f"\n{analysis.agent_name}:\n"
            analysis_text += f"  Signal: {analysis.signal}\n"
            analysis_text += f"  Confidence: {analysis.confidence}%\n"
            analysis_text += f"  Reasoning: {analysis.reasoning}\n"

        prompt = f"""You are a master trading decision engine that synthesizes multiple analytical perspectives.

Individual Agent Analyses:
{analysis_text}

Decision Rules:
1. Consensus Threshold: If 2+ agents agree (same signal), weight heavily
2. Confidence Weighting: Average confidence across agreeing signals
3. Disagreement Protocol: When agents disagree, favor HOLD unless strong technical + fundamental alignment
4. Final Signal: BUY, SELL, or HOLD
5. Trading Action: Execute, Skip, or Monitor

Provide your consensus decision in JSON format:
{{
    "final_signal": "BUY" or "SELL" or "HOLD",
    "consensus_confidence": <0-100>,
    "consensus_reasoning": "Synthesis of all analyses",
    "agent_agreement": "Strong" or "Moderate" or "Weak",
    "trade_recommendation": "EXECUTE" or "SKIP" or "MONITOR",
    "rationale_for_decision": "Why this decision over others",
    "risk_alert": "Any major risks to consider"
}}"""

        if os.getenv("USE_MOCK_AI", "false").lower() == "true":
            import random
            signals = [a.signal for a in analyses if a.signal != "HOLD"]
            if not signals:
                final_signal = "HOLD"
            elif signals.count("BUY") > signals.count("SELL"):
                final_signal = "BUY"
            elif signals.count("SELL") > signals.count("BUY"):
                final_signal = "SELL"
            else:
                final_signal = "HOLD"
                
            conf = int(sum(a.confidence for a in analyses) / len(analyses)) if analyses else 0
            return (
                final_signal,
                conf or 75.0,
                f"Mock: Combined consensus based on technical and news alignment resulting in {final_signal}."
            )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text
            decision = json.loads(content)

            return (
                decision["final_signal"],
                decision["consensus_confidence"],
                decision["consensus_reasoning"]
            )

        except Exception as e:
            logger.error(f"Consensus Engine error: {e}")
            return ("HOLD", 0, f"Consensus failed: {str(e)}")
