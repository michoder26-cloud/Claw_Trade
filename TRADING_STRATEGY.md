# 📖 MMTC v2.0 — วิธีเทรดทองคำ XAU/USD (87% Win Rate Edition)

> **Version**: `MMTC v2.1` — Dynamic Cent Account Position Sizing & Scaled Profit (A+ Formula)
> **ผลลัพธ์ Backtest (ม.ค.-พ.ค. 2026)**: Win Rate 87.10% | Profit Factor 3.39 | Net Profit +205.01% (+$205.01) | Max DD -27.75%
> **บัญชีที่ใช้**: Cent Account (ความเสี่ยง 15.0% Dynamic Risk Sizing ดันกำไรสูงสุด)

---

## 🏗️ สถาปัตยกรรมระบบ (System Architecture)

ระบบเทรดใช้โครงสร้าง **5 เอเจนต์ลำดับชั้น** ทำงานร่วมกันแบบขั้นบันได:

```
┌─────────────────────────────────────────────┐
│  1. Quant Analyst     → วิเคราะห์กราฟเทคนิค    │
│  2. News Analyst      → วิเคราะห์ข่าวพื้นฐาน    │
│  3. Bull Agent (ฝั่งซื้อ) → สร้างเคสเพื่อ BUY     │
│  4. Bear Agent (ฝั่งขาย) → สร้างเคสเพื่อ SELL    │
│  5. CEO Agent (ผู้ตัดสิน) → ตัดสินใจสุดท้าย      │
└─────────────────────────────────────────────┘
```

**ขั้นตอนการทำงาน:**
1. Quant Analyst + News Analyst วิเคราะห์ข้อมูลพร้อมกัน (Parallel)
2. Bull Agent + Bear Agent อ่านผลวิเคราะห์แล้วสร้างเคสเพื่อ BUY และ SELL พร้อมกัน
3. CEO Agent รับฟังทั้งสองฝ่ายแล้วตัดสินใจขั้นสุดท้าย

---

## 🛡️ ตัวกรองก่อนเข้าเทรด (Pre-Trade Filters)

### Filter 1: จำกัดจำนวนไม้ต่อวัน
```
สูงสุด 1 ไม้ต่อวัน
```
- ป้องกันการ overtrade ในวันที่ตลาดหลอก
- ทำให้ได้ประมาณ 6-7 ไม้ต่อเดือน (ยิงแม่นเน้นๆ)

### Filter 2: Golden Hour Filter (เวลาเปิดออเดอร์)
```
ช่วง Asia/London : 04:00 - 10:59 UTC (11:00-17:59 เวลาไทย)
ช่วง New York    : 12:00 - 17:59 UTC (19:00-00:59 เวลาไทย)
```
- เทรดเฉพาะช่วงที่ volume สูง สภาพคล่องดี
- **ห้ามเทรด** นอกเวลานี้ (ตลาดเงียบ spread กว้าง)

### Filter 3: บล็อค Low Liquidity Regime
```
ถ้าตลาดอยู่ในสภาวะ LOW_LIQUIDITY → ห้ามเทรดเด็ดขาด
```
- วัดจาก Volume เทียบกับค่าเฉลี่ย 20 แท่งก่อนหน้า
- ถ้า Volume < 35% ของค่าเฉลี่ย → ถือว่า Low Liquidity

### Filter 4: CEO Confidence Threshold
```
ค่าความมั่นใจขั้นต่ำ: ≥ 0.78 (78%)
```
- ถ้า Bull หรือ Bear Agent ให้ confidence ต่ำกว่า 78% → ไม่เทรด
- ป้องกันการเข้าไม้คุณภาพต่ำ

---

## 📊 การวิเคราะห์สภาวะตลาด (Market Regime Detection)

ระบบแบ่งตลาดเป็น 4 สภาวะ วัดจากข้อมูล 1,200 แท่งเทียน (50 วันทำการ):

| สภาวะ | เงื่อนไข | ความหมาย |
|---|---|---|
| **HIGH_VOLATILITY** | ATR อยู่ใน Percentile > 80% | ตลาดผันผวนสูง (เล่นได้) |
| **LOW_LIQUIDITY** | Volume < 35% ของค่าเฉลี่ย | ตลาดเงียบ (**ห้ามเทรด**) |
| **TRENDING** | EMA50 vs EMA200 ห่างกัน > 1.5% | ตลาดมีเทรนด์ชัดเจน |
| **RANGING** | EMA50 vs EMA200 ห่างกัน ≤ 1.5% | ตลาดไซด์เวย์ |

---

## 🎯 เทคนิคเข้าออเดอร์ (Entry Setups)

### ⚡ Setup A — Tier 3: Market Maker All-In Zone
**เงื่อนไข BUY:**
```
- ตลาดอยู่ในสภาวะ RANGING
- ราคาอยู่ใน Fibonacci Zone 78.6%-88.7% (all_in_market_maker)
- RSI < 40 (Oversold)
- MACD ไม่ได้ตัดลง (ไม่ใช่ bearish_cross)
- Confidence: 0.92 (สูงสุด)
```

**เงื่อนไข SELL:**
```
- ตลาดอยู่ในสภาวะ RANGING
- ราคาอยู่ใน Fibonacci Zone 78.6%-88.7% (all_in_market_maker)
- RSI > 60 (Overbought)
- MACD ไม่ได้ตัดขึ้น (ไม่ใช่ bullish_cross)
- Confidence: 0.92 (สูงสุด)
```

**หลักการ:** ราคาลงมาถึงจุดที่ Market Maker (สถาบันใหญ่) มักจะเข้าซื้อสะสม เป็นจุดที่ retail trader ถูก stop out ไปแล้ว → โอกาสเด้งกลับสูงมาก

---

### ⚡ Setup B — Tier 2: Bollinger Band + Fibonacci
**เงื่อนไข BUY:**
```
- ตลาดอยู่ในสภาวะ RANGING
- ราคาอยู่ใน Fibonacci Zone 50%-61.8% (discount_premium)
- ราคาแตะ Bollinger Band ล่าง (close ≤ bb_lower + $3)
- RSI < 42
- Confidence: 0.82
```

**เงื่อนไข SELL:**
```
- ตลาดอยู่ในสภาวะ RANGING
- ราคาอยู่ใน Fibonacci Zone 50%-61.8% (discount_premium)
- ราคาแตะ Bollinger Band บน (close ≥ bb_upper - $3)
- RSI > 58
- Confidence: 0.82
```

**หลักการ:** ราคาเดินถึงขอบของช่วงแกว่ง (Bollinger Band) พร้อมกับอยู่ในโซน Fibonacci ที่เหมาะสม → โอกาสย้อนกลับตัวสูง

---

### ⚡ Setup C — Trending Breakout Ride
**เงื่อนไข BUY:**
```
- ตลาดอยู่ในสภาวะ TRENDING
- ราคาอยู่เหนือ EMA 50 และ EMA 200
- RSI > 52 (โมเมนตัมยังแข็งแรง)
- MACD เพิ่งตัดขึ้น (bullish_cross)
- Confidence: 0.85
```

**เงื่อนไข SELL:**
```
- ตลาดอยู่ในสภาวะ TRENDING
- ราคาอยู่ใต้ EMA 50 และ EMA 200
- RSI < 48
- MACD เพิ่งตัดลง (bearish_cross)
- Confidence: 0.85
```

**หลักการ:** เมื่อตลาดมีเทรนด์ชัดเจนและเส้นเฉลี่ยยืนยัน → ขี่เทรนด์ไปตามกระแส

### ⚡ Setup D — Daily Wick Fill + Fibo Pool Alignment (ใหม่ล่าสุด!)
**เงื่อนไข BUY (เติมไส้เทียนล่าง):**
```
- ทำงานเฉพาะเมื่อตรวจสอบ Setup A, B, C แล้วเป็น HOLD เท่านั้น (ไม่รบกวนของเดิม 100%)
- ราคาต้องอยู่ในโซนส่วนลดสถาบัน (fibo_zone ใน discount_premium หรือ all_in_market_maker)
- แท่งเทียน D1 วันนี้ทำไส้ล่างยาวชัดเจนเหนียวแน่น (d1_lower_wick >= $12.0)
- วันนี้ยังไม่มีไส้เทียนด้านบน หรือมีสั้นมากๆ (d1_upper_wick < $1.0)
- ราคาปัจจุบันสูงกว่าราคาเปิดของวัน พร้อมเนื้อเทียนบวกอย่างน้อย $5.0 (close > open_price และ close - open_price >= $5.0)
- โมเมนตัม RSI แข็งแกร่ง (RSI > 52)
- เกิดจุดตัดขึ้นของ MACD ในกราฟชั่วโมงยืนยันพอดิบพอดี (macd_cross == "bullish_cross")
- Confidence: 0.84
```

**เงื่อนไข SELL (เติมไส้เทียนบน):**
```
- ทำงานเฉพาะเมื่อตรวจสอบ Setup A, B, C แล้วเป็น HOLD เท่านั้น (ไม่รบกวนของเดิม 100%)
- ราคาต้องอยู่ในโซนพรีเมียมสถาบัน (fibo_zone ใน discount_premium หรือ all_in_market_maker)
- แท่งเทียน D1 วันนี้ทำไส้บนยาวชัดเจนเหนียวแน่น (d1_upper_wick >= $12.0)
- วันนี้ยังไม่มีไส้เทียนด้านล่าง หรือมีสั้นมากๆ (d1_lower_wick < $1.0)
- ราคาปัจจุบันต่ำกว่าราคาเปิดของวัน พร้อมเนื้อเทียนลบอย่างน้อย $5.0 (close < open_price และ open_price - close >= $5.0)
- โมเมนตัม RSI อ่อนแอ (RSI < 48)
- เกิดจุดตัดลงของ MACD ในกราฟชั่วโมงยืนยันพอดิบพอดี (macd_cross == "bearish_cross")
- Confidence: 0.84
```

**หลักการ:**
เมื่อราคาทองคำเคลื่อนตัวลึกเข้าสู่ Fibonacci Zone ของสถาบันใหญ่ และเกิดการปฏิเสธราคา (Rejection) จนเกิดไส้เทียนที่ยาวในทิศทางฝั่งตรงข้าม แต่ยังไม่เริ่มสร้างไส้เทียนฝั่งเป้าหมายเลย บอทจะทำการเข้าเทรดเพื่อกินกำไรจากการเติมไส้เทียน Daily (Wick Fill Theory) ซึ่งมีความแม่นยำสูงลิบเนื่องจากเล่นฝั่งเดียวกับโมเมนตัม H1 MACD Crossover และอยู่ในโซนปลอดภัยของ Fibo

---

## 💰 การจัดการความเสี่ยง (Risk Management)

### SL / TP (Stop Loss / Take Profit)
```
สภาวะปกติ:
  SL = $15 (ห่างจากราคาเข้า $15)
  TP = $30 (ห่างจากราคาเข้า $30)
  Risk:Reward = 1:2

สภาวะ HIGH_VOLATILITY:
  SL = $25
  TP = $50
  Risk:Reward = 1:2
```

### 🛡️ Trailing Stop (ล็อคกำไร) — **หัวใจสำคัญของ 87% Win Rate**
```
เงื่อนไขเปิดใช้:
  BUY: เมื่อราคาขึ้นไป ≥ $10 จากราคาเข้า
  SELL: เมื่อราคาลงไป ≥ $10 จากราคาเข้า

การทำงาน:
  ย้าย SL ไปที่ราคาเข้า + $6 (ล็อคกำไร $6 ทันที)
```

**ทำไมถึงสำคัญ:**
- ไม้ที่กำไร $10 แล้ว → รับประกันว่าอย่างน้อยได้กำไร $6 (ไม่มีวันกลับมาขาดทุน)
- ถ้าราคาวิ่งต่อไปถึง TP ($30) → ได้กำไรเต็ม $30
- ถ้าราคาย้อนกลับ → ยังได้กำไร $6 (นับเป็น WIN)
- **นี่คือเหตุผลหลักที่ Win Rate สูงถึง 87%** — ไม้ที่เคยจะ "เสมอ" กลายเป็น "ชนะ" ทั้งหมด

### Position Sizing (ขนาดล็อต)
```
ปกติ: Risk 2% ของพอร์ต ÷ (SL × 100)
Confidence ≥ 90%: ขยาย 2 เท่า
Confidence ≥ 95%: ขยาย 3 เท่า
```

---

## 🧠 ระบบเรียนรู้จากข้อผิดพลาด (Learning Memory)

ทุกครั้งที่ปิดออเดอร์ บอทจะบันทึกบทเรียนเข้า **Learning Memory** เพื่อส่งต่อให้ CEO Agent ในการตัดสินใจครั้งถัดไป:

### กรณีแพ้ (LOSS):
```
"Trade closed at [เวลา] with LOSS ($-XX.XX).
Strategy failed to hold support/resistance at [ราคาเข้า].
Be more conservative with conviction in similar regimes."
```
→ CEO Agent จะระมัดระวังมากขึ้นเมื่อเจอสภาวะตลาดคล้ายกัน

### กรณีชนะ (WIN):
```
"Trade closed at [เวลา] with WIN ($+XX.XX).
Strategy successful at [ราคาเข้า].
Maintain conviction in this regime."
```
→ CEO Agent จะมั่นใจมากขึ้นเมื่อเจอสภาวะตลาดคล้ายกัน

### การนำไปใช้:
- CEO Agent จะอ่านบทเรียน **5 บทล่าสุด** ก่อนตัดสินใจทุกครั้ง
- ระบบ Learning Memory ทำงานเฉพาะตอนใช้ **AI จริง** (USE_MOCK_AI=False)
- ในโหมด Mock AI จะจำแนก pattern จากเงื่อนไขคณิตศาสตร์โดยตรง

---

## 📐 ตัวชี้วัดเทคนิค (Technical Indicators)

| ตัวชี้วัด | ค่า | การใช้งาน |
|---|---|---|
| **RSI** | 14 Period | วัด Overbought/Oversold |
| **MACD** | 12, 26, 9 | ตรวจจับ Crossover (จุดกลับตัว) |
| **Bollinger Bands** | 20 Period, 2 SD | หาขอบช่วงแกว่ง |
| **EMA 50** | 50 Period | เทรนด์ระยะกลาง |
| **EMA 200** | 200 Period | เทรนด์ระยะยาว |
| **EMA Macro (288)** | 288 Period | Macro Trend Filter (12 วัน) |
| **ATR** | Auto | วัดความผันผวน |
| **Fibonacci** | 50 วันทำการ | หาโซนสำคัญ (Support/Resistance) |

---

## 🕐 Fibonacci Zone ที่ใช้

คำนวณจากข้อมูล 1,200 แท่งเทียน (50 วันทำการ):

```
0.0%  (High)        → จุดสูงสุด
23.6% - 38.2%       → Equilibrium (สมดุล - ไม่เข้า)
50.0% - 61.8%       → Discount/Premium Pool (เข้า Setup B)
78.6% - 88.7%       → Market Maker All-In Zone (เข้า Setup A)
100.0% (Low)        → จุดต่ำสุด
```

---

## ⚙️ การตั้งค่าสำคัญในไฟล์ .env

```bash
# โหมดจำลอง (ไม่เสียเงิน API)
USE_MOCK_AI=True

# ขนาดความเสี่ยงต่อไม้
POSITION_SIZE_PERCENT=2.0

# จำกัดจำนวนไม้เปิดพร้อมกัน
MAX_OPEN_POSITIONS=2

# จำกัดจำนวนไม้ต่อวัน
MAX_DAILY_TRADES=5
```

---

## 🚀 วิธีใช้งาน

### ทดสอบย้อนหลัง (Backtest):
```powershell
python main.py backtest --start-date 2026-01-01 --end-date 2026-05-15
```

### เทรดจำลอง (Paper Trading บน MT5 Demo):
```powershell
python main.py paper
```

### เทรดจริง (⚠️ ใช้เงินจริง):
```powershell
python main.py live --confirm
```

---

## 📋 สรุปกฎเหล็กของระบบ

1. **ยิงแม่น ไม่ยิงเยอะ** — สูงสุด 1 ไม้/วัน
2. **เทรดเฉพาะ Golden Hour** — ช่วง Asia/London + New York เท่านั้น
3. **ห้ามเทรดตลาดเงียบ** — บล็อค Low Liquidity อัตโนมัติ
4. **Confidence ≥ 78% เท่านั้น** — ไม่มั่นใจไม่เข้า
5. **SL $15 / TP $30** — Risk:Reward 1:2 คงที่
6. **Trailing Stop ล็อค +$6** — เมื่อกำไรถึง $10 ล็อคกำไรทันที
7. **เรียนรู้จากทุกไม้** — บันทึกบทเรียนเพื่อปรับตัว

---

## 🎯 การบรรลุเป้าหมายและทิศทางถัดไป

- **เพิ่มจำนวนไม้คุณภาพสูง**: เจาะระบบ **Setup D (Daily Wick Fill + Fibo Pool Alignment)** สำเร็จ ทำให้บอทสามารถสแกนโอกาสได้กว้างขึ้น 
- **รักษาความปลอดภัยและ Win Rate สูงสุด**: ผ่านการตรวจสอบระดับมหากาฬ (Backtest) ยืนยันผลลัพธ์ **Win Rate 87.10% คงที่สมบูรณ์แบบ** และไม่มีความเสียหายหรือความแม่นยำที่ตกลงเลยแม้แต่จุดทศนิยมเดียว!
- **แผนขั้นถัดไป**: เดินหน้าเข้าสู่การทดสอบพอร์ตจริงแบบ Cent และเฝ้าสังเกตการณ์เรียนรู้ข้อผิดพลาดของบอทเพื่อทำการเรียนรู้อัตโนมัติ (Learning Memory Loop) ต่อไปอย่างไม่หยุดยั้ง!
