# 🤖 Managed Agents Setup Guide (24/7 Cloud Trading)

## Overview

Transform your trading system into a **24/7 autonomous agent** running on Claude Cloud using Anthropic's Managed Agents API.

## Architecture

```
┌─────────────────────────────────────────────┐
│   Claude Cloud (Managed Agents - 24/7)      │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  Daily Analysis Agent (8 AM UTC)    │   │
│  │  - Comprehensive analysis           │   │
│  │  - Generate trading signals        │   │
│  │  - Execute trades                  │   │
│  └─────────────────────────────────────┘   │
│                    ↓                        │
│  ┌─────────────────────────────────────┐   │
│  │  Intraday Monitor (Every 4h)        │   │
│  │  - Quick price checks               │   │
│  │  - Manage open positions            │   │
│  │  - Alert on breakouts               │   │
│  └─────────────────────────────────────┘   │
│                    ↓                        │
│  ┌─────────────────────────────────────┐   │
│  │  Weekly Review (Sunday 8 PM UTC)    │   │
│  │  - Performance analysis             │   │
│  │  - Strategy review                  │   │
│  │  - Parameter optimization           │   │
│  └─────────────────────────────────────┘   │
│                                             │
└────────┬────────────────────────┬──────────┘
         │                        │
    ┌────▼──────┐          ┌──────▼────┐
    │ Database  │          │ Slack/    │
    │ (Results) │          │ Email     │
    └───────────┘          └───────────┘
```

## Setup Instructions

### Step 1: Create Daily Analysis Agent

**URL**: https://claude.ai/code/agents

**Name**: `XAU_USD_Daily_Analysis`

**Instructions** (Copy & Paste):

```
You are the Master Trading Orchestrator for XAU/USD daily analysis.

RESPONSIBILITIES:
1. Fetch latest gold price data (last 50-100 1H candles)
2. Coordinate multi-agent analysis:
   - Technical Analysis: RSI, MACD, Bollinger Bands, ATR
   - Fundamental Analysis: Fed policy, geopolitics, USD strength
   - Risk Management: Position sizing, SL/TP levels
   - Consensus Decision: Aggregate all signals

3. Analysis Framework:

   TECHNICAL ANALYSIS:
   - RSI: <30 oversold (BUY signal), >70 overbought (SELL signal)
   - MACD: Cross above signal = BUY, below = SELL
   - Bollinger Bands: Support/resistance levels
   - ATR: Volatility for position sizing
   
   FUNDAMENTAL FACTORS:
   - Fed interest rates (higher = weaker gold)
   - USD strength (stronger = weaker gold)
   - Real yields (key gold driver)
   - Geopolitical risk (higher = stronger gold)
   - Inflation expectations

   RISK MANAGEMENT:
   - Position size = Account * 2% / Risk per trade
   - Risk/Reward ratio: Minimum 1.5:1
   - Stop-loss: Based on recent support/resistance
   - Take-profit: Based on technical targets

   CONSENSUS:
   - If 2+ signals agree → Execute with high confidence
   - If signals diverge → HOLD and monitor
   - Final decision: BUY, SELL, or HOLD

4. Execute trading signal IF:
   - Consensus confidence > 60%
   - Risk/Reward ratio acceptable
   - Portfolio heat within limits

5. Output Format (JSON):
   {
     "timestamp": "2024-01-15T08:00:00Z",
     "analysis": {
       "price_current": 2050.50,
       "technical_signal": "BUY",
       "technical_confidence": 75,
       "technical_reasoning": "...",
       "fundamental_signal": "SELL",
       "fundamental_confidence": 65,
       "fundamental_reasoning": "...",
       "consensus_signal": "HOLD",
       "consensus_confidence": 45,
       "consensus_reasoning": "Mixed signals - monitoring"
     },
     "trade_decision": {
       "action": "HOLD",
       "position_size": 0,
       "entry_price": null,
       "stop_loss": null,
       "take_profit": null,
       "reasoning": "Awaiting clearer signal"
     },
     "risk_metrics": {
       "current_positions": 1,
       "portfolio_heat": 2.5,
       "max_drawdown": -8.5,
       "sharpe_ratio": 1.2
     }
   }
```

**Schedule**: Daily at **08:00 UTC** (Asia session open)

**Parameters**:
```json
{
  "symbol": "GC=F",
  "timeframe": "1h",
  "lookback_candles": 50,
  "max_open_positions": 2,
  "position_size_percent": 2.0
}
```

---

### Step 2: Create Intraday Monitor Agent

**Name**: `XAU_USD_Intraday_Monitor`

**Instructions** (Copy & Paste):

```
You are the Intraday Monitor for XAU/USD - Quick decision maker.

RESPONSIBILITIES:
1. Monitor price every 4 hours
2. Quick assessment (5-10 minutes max):
   - Current price vs key levels
   - Any breaking news?
   - RSI/MACD quick check
   - Open positions status

3. Quick Signal Generation:
   - Strong break above/below key level? → Action signal
   - News event impacting gold? → Alert
   - Any open positions hit SL/TP? → Manage

4. Output JSON:
   {
     "timestamp": "2024-01-15T12:00:00Z",
     "price": 2051.25,
     "quick_assessment": "Price consolidating, RSI 45-55 (neutral)",
     "key_levels": {
       "support": 2045.00,
       "resistance": 2055.00,
       "broken_level": null
     },
     "news_impact": "Minor US inflation data - slight USD weakness",
     "open_positions": 1,
     "action_required": false,
     "recommendations": "Hold current position, monitor 2055 resistance"
   }
```

**Schedule**: Every **4 hours** (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC)

---

### Step 3: Create Weekly Strategy Review

**Name**: `XAU_USD_Weekly_Review`

**Instructions** (Copy & Paste):

```
You are the Weekly Strategy Reviewer - Deep analysis mode.

RESPONSIBILITIES:
1. Every Sunday evening, analyze:

   PERFORMANCE METRICS:
   - Week's trades: Count, win rate, profit factor
   - Best/worst trades: Price, reasoning
   - Total profit/loss, sharpe ratio
   
   MARKET REGIME ANALYSIS:
   - Trend: Strong UP/DOWN or Ranging?
   - Volatility: High/Normal/Low (vs historical)
   - Correlation: Gold vs USD, bonds, equities
   
   STRATEGIC ASSESSMENT:
   - Risk parameters still optimal?
   - Position sizing appropriate?
   - Any parameter tuning needed?
   
   NEXT WEEK PREVIEW:
   - Economic calendar: NFP, Fed, inflation data
   - Key price levels for the week
   - Potential catalysts

2. Output detailed JSON with metrics and recommendations
```

**Schedule**: Every **Sunday at 20:00 UTC**

---

## How to Deploy

### Option A: Manual (Recommended for First Time)

1. Go to https://claude.ai/code/agents
2. Click "Create New Agent"
3. Fill in:
   - **Name**: Copy from above
   - **Instructions**: Copy the full instruction text
   - **Schedule**: Set frequency and time
4. Click "Save Agent"
5. Repeat for all 3 agents

### Option B: Automated (Using API)

```bash
python managed_agents_setup.py
```

This generates configuration file ready to import.

### Option C: Docker Deployment

```bash
docker-compose up -d xau-trading-system
```

---

## Monitoring & Management

### Check Agent Execution History

1. Go to https://claude.ai/code/agents
2. Click on each agent
3. View "Execution History" tab
4. Check logs and outputs

### Receive Notifications

Set up alerts for:
- **New BUY/SELL signals** → Slack
- **Daily summary** → Email
- **Errors/failures** → Phone alert

**Configure in agent settings**:
```json
{
  "notifications": {
    "slack": {
      "enabled": true,
      "webhook": "https://hooks.slack.com/...",
      "channels": ["trading-alerts", "daily-summary"]
    },
    "email": {
      "enabled": true,
      "recipients": ["your@email.com"]
    }
  }
}
```

---

## Expected Execution Timeline (UTC)

```
00:00 → Intraday Monitor (4h check)
04:00 → Intraday Monitor (4h check)
08:00 → 🎯 DAILY ANALYSIS (Main signal generation)
12:00 → Intraday Monitor (4h check)
16:00 → Intraday Monitor (4h check)
20:00 → Intraday Monitor (4h check)
       (+ Every Sunday 20:00 → Weekly Review)
```

---

## Cost Optimization

- **Sample Rate**: Reduce frequency to cut API costs
  - Every 8 hours instead of 4 → 50% less cost
  - Daily instead of 4-hourly → 75% less cost

- **Token Optimization**:
  - Use concise analysis instructions
  - Limit historical lookback period
  - Pre-calculate indicators (don't ask Claude to do it)

## Troubleshooting

### Agent didn't run at scheduled time
- Check Claude Cloud status page
- Verify agent is "Active" (not "Paused")
- Review execution logs for errors

### Output format is wrong
- Verify instructions are copied exactly
- Check for special characters or formatting issues
- Test with manual agent trigger first

### Too many API calls / High costs
- Increase schedule intervals
- Reduce agent execution frequency
- Optimize instruction length

---

## ✅ Checklist

- [ ] Created Daily Analysis Agent
- [ ] Created Intraday Monitor Agent  
- [ ] Created Weekly Review Agent
- [ ] Set up Slack notifications (optional)
- [ ] Set up email notifications (optional)
- [ ] Verified first execution in logs
- [ ] Reviewed backtest results
- [ ] Monitored for 1 week before going live

---

## Next Steps

1. **Monitor for 1-2 weeks**: Verify agent execution quality
2. **Optimize parameters**: Adjust based on results
3. **Add notifications**: Get alerts on important events
4. **Go live** (optional): Connect to real trading broker

**Happy automated trading! 🚀**
