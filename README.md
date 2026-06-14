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

### 1. Prerequisites (ความต้องการของระบบ)
ระบบสามารถทำงานได้ 2 รูปแบบตามระบบปฏิบัติการของบอส:

*   **Windows Setup (Native):** รันตรง ๆ บน Windows (จำเป็นต้องเปิดโปรแกรม MT5 Terminal ควบคู่ไปด้วย)
*   **Linux Setup (Docker + mt5linux):** รันบน Linux VPS / Terminal-only (จำลองโปรแกรม MT5 ผ่าน Docker + Wine + mt5linux RPyC Bridge)

---

### 💻 2. วิธีการติดตั้งสำหรับ Windows (Native)
1. **ติดตั้ง MT5:** ดาวน์โหลดและติดตั้ง **MetaTrader 5 Desktop** และเข้าสู่ระบบบัญชีเทรดให้เรียบร้อย
2. **เปิดสิทธิ์บอท:** ไปที่ `Tools -> Options -> Expert Advisors` -> ติ๊กเลือก **"Allow Algo Trading"** และ **"Allow DLL imports"**
3. **แสดงสัญลักษณ์ทองคำ:** กด `Ctrl+M` (Market Watch) และคลิกขวาเลือกสัญลักษณ์ทองคำ (เช่น `XAUUSD` หรือ `GOLD` หรือ `XAUUSDc` ตามโบรกเกอร์)
4. **ติดตั้ง Python Packages:** เปิด Command Prompt ในโฟลเดอร์บอทแล้วพิมพ์:
   ```bash
   pip install -r requirements.txt
   ```

---

### 🐧 3. วิธีการติดตั้งสำหรับ Linux (Docker + mt5linux)
เหมาะสำหรับรันบน Linux VPS หรือระบบ Terminal-only โดยไม่ต้องเช่า Windows VPS ราคาแพงค่ะ

1. **ติดตั้ง Docker และ Docker Compose:**
   ```bash
   sudo apt update && sudo apt install docker.io docker-compose-v2 -y
   sudo systemctl enable --now docker
   ```
2. **เริ่มการทำงานคอนเทนเนอร์ MT5:**
   ```bash
   docker compose up -d
   ```
3. **ตั้งค่า MT5 ผ่าน VNC:**
   * เปิดเว็บบราวเซอร์ไปที่: `http://IP_VPSของบอส:3000`
   * เข้าสู่ระบบด้วยชื่อผู้ใช้: `trader` และรหัสผ่าน: `change_me_pls` (แก้ไขได้ใน [docker-compose.yml](file:///c:/Users/TKTF/Desktop/Sub_Agent/xau_trading_system/docker-compose.yml))
   * ดับเบิ้ลคลิกเปิด **MetaTrader 5** -> เข้าสู่ระบบบัญชีเทรด -> ไปที่ `Tools -> Options -> Expert Advisors` -> ติ๊กเลือก **"Allow Algo Trading"**
4. **ติดตั้งแพ็คเกจบน Linux Host:**
   ```bash
   pip install mt5linux rpyc -r requirements.txt
   ```
5. **เริ่มการทำงานของ API Bridge:**
   ในคอนเทนเนอร์จะเปิด RPyC Server ที่พอร์ต `8001` โดยอัตโนมัติ (สามารถเช็คสถานะการรันและระบบ Watchdog ตรวจสอบเพิ่มเติมได้ในคู่มือฉบับเต็มที่ [LINUX_SETUP.md](file:///c:/Users/TKTF/Desktop/Sub_Agent/xau_trading_system/LINUX_SETUP.md) ค่ะ)

---

### ⚙️ 4. Setup Environment (ตั้งค่าไฟล์ระบบ)
คัดลอกไฟล์ตัวอย่างไปสร้างเป็นไฟล์ `.env`:
```bash
cp .env.example .env
```
เปิดไฟล์ `.env` ขึ้นมาและกรอกรายละเอียด:
*   `OPENROUTER_API_KEY`: คีย์สำหรับ AI (CEO/News/Bull/Bear)
*   `DISCORD_WEBHOOK_URL`: ลิงก์แจ้งเตือนเข้าห้องเทรด Discord
*   **สำหรับ Windows:** ตั้งค่าบัญชี MT5 ทั่วไป
*   **สำหรับ Linux:** ระบุไอพีของ Bridge เพิ่มเติมใน `.env`:
    ```bash
    MT5_HOST=127.0.0.1
    MT5_PORT=8001
    MT5_SYMBOL=XAUUSDc  # ชื่อสัญลักษณ์ทองคำใน MT5 ของบอส
    ```

---

### 🏃 5. Running Commands (คำสั่งการใช้งาน)

#### 🧪 5.1 การรัน Backtest (ทดสอบย้อนหลัง)
รันวิเคราะห์ข้อมูลย้อนหลังเพื่อวิเคราะห์ประสิทธิภาพ:
```bash
python main.py backtest --start-date 2025-06-01 --end-date 2026-06-01 --interval 1h --risk-pct 1.5
```

#### 📄 5.2 การรัน Demo Trading (บัญชีจำลองสด)
วิเคราะห์ตลาดสดและเข้าจำลองการเทรดโดยใช้เงินในพอร์ตเดโม MT5:
```bash
python main.py paper --interval 60
```

#### ⚠️ 5.3 การรัน Live Trading (เทรดจริงเงินจริง)
รันบอทเข้าเทรดจริงบนพอร์ตเงินจริง (สับสวิตช์ปิด Mock AI ใน `.env` เป็น `USE_MOCK_AI=False` ก่อนรัน):
```bash
python main.py live --confirm --interval 60
```
> **ความปลอดภัย:** โหมด `live` จำเป็นต้องระบุแฟล็ก `--confirm` เสมอ เพื่อยืนยันการยอมรับความเสี่ยงของพอร์ตค่ะบอส

---

## ⚠️ Important Notes
**Disclaimer**: This is a highly aggressive, institutional-grade mathematical algorithm utilizing compounding risk. The "Lot x3 Override" carries extreme risk per trade. Use on a Cent Account first. Past performance does not guarantee future results.

**Created for elite XAU/USD trading.**
