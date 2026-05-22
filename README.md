# 🏆 XAU/USD MMTC v2.0: The Holy Grail Strategy

A sophisticated **multi-agent AI trading system** for Gold (XAU/USD). Codenamed **MMTC v2.0 (Market Maker Trap Catcher)**, this system combines Institutional Smart Money Concepts (SMC), dynamic Fibonacci Circles, and ruthless Risk Management to hunt for high-probability sniper entries.

---

## 🔥 The Holy Grail Strategy (SMC + Fibo Circles)
The core of MMTC v2.0 is built on identifying where retail traders lose and where Market Makers (Institutions) enter.

### 📐 Structural Mapping
1. **Dynamic CHoCH / BOS Detection:** The bot uses a 5-bar fractal algorithm to identify valid Swing Highs and Swing Lows, dynamically mapping Market Structure.
2. **Left-to-Right Wick Anchoring:** Fibonacci Retracements and Circles are drawn precisely from the origin swing to the completion swing, capturing 100% of the liquidity wicks.

### 🎯 The 3 Institutional Zones (Price Tiers)
*   **Tier 1: Equilibrium Zone (`23.6% - 38.2%`)** - Trend continuation. Triggers if MACD quickly confirms the pullback.
*   **Tier 2: Fair Value Pool (`50.0% - 61.8%`)** - The primary Day Trading zone. Discount for buyers, Premium for sellers.
*   **Tier 3: Market Maker All-In Zone (`78.6% - 88.7%`)** - The ultimate liquidity sweep zone. This is the final defense level before a CHoCH invalidates the trend.

### 💥 God Mode: Lot x3 Override
When the price enters the **Tier 3 (78.6% - 88.7%)** zone and momentum (RSI) confirms exhaustion:
1. **Aggressive Sizing:** The bot multiplies its normal lot size by **3x** (Risking 18% instead of 6%).
2. **Tight Stop Loss:** SL is compressed to a razor-thin 3.0 USD distance (just beyond the 100% Fibo invalidation line).
3. **1:10 Risk-Reward:** Targeting massive extensions (161.8%), a single winning trade in this zone can grow the portfolio by **180%**.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│          Master Orchestrator                            │
│  (รวมประสานงาน + ตัดสินใจสุดท้าย)                        │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┼───────────┬───────────┐
         ▼           ▼           ▼           ▼
    ┌────────┐  ┌────────┐ ┌────────┐ ┌──────────┐
    │ News   │  │ Bull   │ │ Bear   │ │ CEO      │
    │ Analyst│  │ Agent  │ │ Agent  │ │ Agent    │
    └────────┘  └────────┘ └────────┘ └──────────┘
         │           │           │           │
         └───────────┼───────────┴───────────┘
                     │
              ┌──────▼──────┐
              │ Backtester  │
              │ (MT5 Live)  │
              └─────────────┘
```

## 📋 Agents & Responsibilities

### 1. 📰 **News Analyst**
- Parses ForexFactory macroeconomic data (NFP, CPI, FOMC).
- Enforces "News Blackouts" to prevent trading during extreme volatility.

### 2. 🐂 **Bull Agent (The Prosecutor for Longs)**
- Searches exclusively for bullish SMC setups (FVG, Order Blocks, Liquidity Sweeps).
- Activates Setup E (Fibo Circle Support) to call for Lot x3 Longs.

### 3. 🐻 **Bear Agent (The Prosecutor for Shorts)**
- Searches exclusively for bearish setups.
- Activates Setup E (Fibo Circle Resistance) to call for Lot x3 Shorts.

### 4. 👔 **CEO Agent (The Ultimate Decision Maker)**
- Listens to both Bull and Bear cases.
- Requires a strict conviction score (>= 78%) to approve a trade.
- Reads `[OVERRIDE_LOT_MULTIPLIER=3.0]` flags to authorize aggressive execution.

---

## 🛡️ Advanced Risk & Trade Management

*   **Sniper Engine (Golden Hours):** Only trades during London/New York overlap sessions to avoid Asian session fakeouts.
*   **3-Phase Trailing Stop:** 
    1. **Breakeven:** Once profit reaches $10, SL moves to entry.
    2. **Lock 1:** At $15 profit, locks in $6.
    3. **Lock 2:** At $25 profit, locks in $12.
*   **ATR Dynamic SL:** During normal trades (Tier 1/2), SL distance expands/contracts based on current market volatility.

---

## 🚀 Quick Start

### Prerequisites
```bash
pip install -r requirements.txt
```

### Setup Environment
```bash
cp .env.example .env
# Edit .env with your OPENROUTER_API_KEY
```

### Run Backtest
```bash
python check_24_25_trailing_stop.py
```

### Run MT5 Live Execution
```bash
python main.py live
```

---

## ⚠️ Important Notes
**Disclaimer**: This is a highly aggressive, institutional-grade mathematical algorithm utilizing compounding risk. The "Lot x3 Override" carries extreme risk per trade. Use on a Cent Account first. Past performance does not guarantee future results.

**Created for elite XAU/USD trading.**
