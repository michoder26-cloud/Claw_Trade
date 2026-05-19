import sys
import os
sys.path.insert(0, 'src')
from discord_reporter import DiscordReporter
from agents import AnalysisResult

reporter = DiscordReporter()

# Create dummy objects resembling what the orchestrator uses
bull_res = AnalysisResult(
    agent_name="BullishStrategist",
    signal="BUY",
    confidence=0.92,
    reasoning="Test bullish case: price reached major order block support.",
    raw_response="{}"
)

bear_res = AnalysisResult(
    agent_name="BearishStrategist",
    signal="HOLD",
    confidence=0.40,
    reasoning="Test bearish case: no clear resistance breakout.",
    raw_response="{}"
)

# Test report_order_opened
print("Sending test order opened report to Discord...")
success = reporter.report_order_opened(
    signal="BUY",
    entry_price=4506.26,
    sl_price=4496.40,
    tp_price=4556.40,
    lot_size=3.34,
    ticket=1784418694,
    confidence=0.92,
    regime="RANGING",
    quant_summary="Quant indicators look oversold.",
    news_summary="News is neutral.",
    bull_argument=getattr(bull_res, 'reasoning', 'N/A'),
    bear_argument=getattr(bear_res, 'reasoning', 'N/A'),
    ceo_reasoning="CEO approved long entry based on discount zone."
)

if success:
    print("✅ Discord message sent successfully!")
else:
    print("❌ Failed to send Discord message.")
