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

### 1. Prerequisites (สเปกและความต้องการของระบบ)
- **ระบบปฏิบัติการ (OS)**: บอทนี้ใช้งานไลบรารี `MetaTrader5` สำหรับ Python ซึ่งจะ**รองรับเฉพาะบน Windows เท่านั้น**
- **แอปพลิเคชัน MT5**: ต้องติดตั้งโปรแกรม **MetaTrader 5 Terminal** ลงบนเครื่อง Windows และล็อกอินเข้าบัญชีเทรด (เดโม หรือ พอร์ตจริง) ไว้เรียบร้อยแล้ว
- **การตั้งค่าใน MT5**: 
  1. ไปที่ `Tools -> Options -> Expert Advisors`
  2. ติ๊กเลือก **"Allow Algo Trading"** (อนุญาตให้บอทส่งคำสั่งซื้อขาย) และ **"Allow DLL imports"**
  3. เพิ่มสัญลักษณ์ทองคำ (เช่น `XAUUSD` หรือสัญลักษณ์ Gold ของโบรกเกอร์คุณ เช่น `GOLD`, `XAUUSD.m`) เข้ามาในหน้าต่าง **Market Watch** ใน MT5
- **การติดตั้งแพ็กเกจ**:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Setup Environment (ตั้งค่าไฟล์ระบบ)
ก๊อบปี้ไฟล์ตัวอย่างการตั้งค่าไปสร้างเป็นไฟล์ `.env`:
```bash
cp .env.example .env
```
เปิดไฟล์ `.env` ขึ้นมาเพื่อกรอกข้อมูลที่จำเป็น:
*   `OPENROUTER_API_KEY`: คีย์สำหรับเชื่อมต่อ AI ของ OpenRouter (ใช้ขับเคลื่อนการวิเคราะห์ตัดสินใจของ CEO, Bull, Bear และประเมินบทเรียนเทรด)
*   `DISCORD_WEBHOOK_URL`: ลิงก์ Discord Webhook สำหรับรับการรายงานแบบเรียลไทม์ (แจ้งเตือนเปิดออเดอร์, ปิดออเดอร์, การลาก Trailing Stop, รายงานรายสัปดาห์)
*   **การตั้งค่า MT5 (Live / Paper Trading เท่านั้น)**:
    *   `MT5_LOGIN`: รหัสสมาชิกบัญชีเทรด MT5 (เช่น `106123714`) *หากเว้นไว้ บอทจะใช้บัญชีที่ล็อกอินอยู่ปัจจุบันในโปรแกรม MT5*
    *   `MT5_PASSWORD`: รหัสผ่านบัญชี MT5
    *   `MT5_SERVER`: ชื่อเซิร์ฟเวอร์โบรกเกอร์ (เช่น `FBSTradestone-Demo`)
    *   `MT5_SYMBOL`: สัญลักษณ์ทองคำบนโบรกเกอร์ของคุณ (เช่น `XAUUSD` หรือ `GOLD`)
*   **การตั้งค่า Trailing Stop**:
    *   `USE_TRAILING_STOP`: ตั้งเป็น `true` เพื่อเปิดใช้ Trailing Stop แบบ 3 ระยะ
    *   `TRAIL_BREAKEVEN_TRIGGER`: สัดส่วนการขยับ SL ไปหน้าทุน (ค่าเริ่มต้น: `1.0` เท่าของระยะ SL)
    *   `TRAIL_LOCK_TRIGGER`: สัดส่วนการขยับ SL ไปล็อกกำไร 50% (ค่าเริ่มต้น: `2.0` เท่าของระยะ SL)

### 3. Running Commands (คำสั่งการใช้งาน)

#### 🧪 3.1 การรัน Backtest (ทดสอบย้อนหลัง)
คุณสามารถรันตัวทดสอบย้อนหลังเพื่อวิเคราะห์ประสิทธิภาพของบอทด้วยสถิติต่างๆ:
```bash
# แบบรันการทดสอบเบื้องต้น (ใช้ไฟล์เช็ค Trailing Stop)
python check_24_25_trailing_stop.py

# หรือรันผ่าน main.py เพื่อกำหนดช่วงเวลาและสัญลักษณ์เอง:
python main.py backtest --start-date 2026-01-01 --end-date 2026-05-01 --interval 1h --risk-pct 15.0
```

#### 📄 3.2 การรัน Paper Trading (จำลองการเทรดสดบนบัญชี Demo)
รันบอทวิเคราะห์ตลาดสดและจำลองการเทรดโดยใช้ยอดเงินและพอร์ตของ MT5 Demo Account:
```bash
python main.py paper --interval 60
```

#### ⚠️ 3.3 การรัน Live Trading (เทรดจริงบนพอร์ตเงินจริง)
รันบอทให้เข้าคุมพอร์ตและเปิดออเดอร์ส่งคำสั่งซื้อขายจริงด้วยเงินจริงบนบัญชีจริง:
```bash
python main.py live --confirm --interval 60
```
> **หมายเหตุความปลอดภัย**: การรันโหมด `live` จำเป็นต้องระบุแฟล็ก `--confirm` เสมอ เพื่อเป็นการยืนยันความเสี่ยงก่อนที่ระบบจะเริ่มทำงาน

---

## ⚠️ Important Notes
**Disclaimer**: This is a highly aggressive, institutional-grade mathematical algorithm utilizing compounding risk. The "Lot x3 Override" carries extreme risk per trade. Use on a Cent Account first. Past performance does not guarantee future results.

**Created for elite XAU/USD trading.**
