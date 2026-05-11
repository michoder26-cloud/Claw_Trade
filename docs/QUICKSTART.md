# 🚀 Quick Start Guide (5 minutes to first backtest!)

## Step 1: Install (1 min)

```bash
cd xau_trading_system
pip install -r requirements.txt
```

## Step 2: Configure (1 min)

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

**Windows**: `notepad .env`  
**Mac/Linux**: `nano .env`

```env
ANTHROPIC_API_KEY=sk-ant-... # Get from https://console.anthropic.com
```

## Step 3: Test Configuration (1 min)

```bash
python main.py config
```

Should show:
```
Current Configuration:
  API Key: ✓ Set
  Trading Mode: BACKTEST
  Initial Balance: $10,000.00
  ...
```

## Step 4: Run Backtest (2 min)

### Quick test (1 month)
```bash
python main.py backtest --start-date 2024-06-01 --end-date 2024-06-30
```

### Full year backtest
```bash
python main.py backtest --start-date 2023-01-01 --end-date 2024-12-31
```

## Step 5: Review Results

Check the output:

```
==============================================================
📊 BACKTESTING REPORT
==============================================================
Initial Balance: $10,000.00
Final Balance: $12,450.50
Net Profit/Loss: $2,450.50 (24.51%)

TRADE STATISTICS:
Total Trades: 45
Win Rate: 62.22%
Profit Factor: 1.85
==============================================================
```

## 📁 What You Got

```
xau_trading_system/
├── 📄 README.md                    # Full documentation
├── 📄 SETUP_GUIDE.md              # Detailed installation
├── 📄 MANAGED_AGENTS_GUIDE.md     # 24/7 cloud setup
├── 📄 QUICKSTART.md               # This file!
│
├── 🐍 main.py                      # Entry point (CLI)
├── 🐍 orchestrator.py             # Master agent coordinator
├── 🐍 agents.py                   # AI agents (News, Tech, Risk, Consensus)
├── 🐍 data_handler.py             # Data fetching & indicators
├── 🐍 backtester.py               # Backtesting engine
├── 🐍 config.py                   # Configuration management
├── 🐍 managed_agents_setup.py     # Cloud agent setup
│
├── ⚙️ requirements.txt             # Python dependencies
├── 🔑 .env.example                # Configuration template
├── .gitignore                      # Git ignore file
├── Dockerfile                      # Docker configuration
├── docker-compose.yml              # Docker Compose setup
```

## 🎯 Next Steps

1. **Customize Strategy**
   - Edit `.env` to change risk parameters
   - Modify agent instructions in `agents.py`

2. **Setup 24/7 Cloud Trading** (Advanced)
   ```bash
   python managed_agents_setup.py
   # Follow instructions in MANAGED_AGENTS_GUIDE.md
   ```

3. **Analyze Results**
   - Open `backtest_results.json`
   - Review `trading_system.log`

4. **Connect to Real Broker** (Future)
   - Add broker API keys
   - Implement live trading in `orchestrator.py`

## 📊 Example Commands

```bash
# Quick 1-month test
python main.py backtest --start-date 2024-01-01 --end-date 2024-01-31

# Full year with custom settings
python main.py backtest \
  --start-date 2023-01-01 \
  --end-date 2024-12-31 \
  --sample-rate 24 \
  --output results_2024.json

# View config
python main.py config

# Setup cloud agents
python managed_agents_setup.py
```

## 🔧 Troubleshooting

**Error: "ANTHROPIC_API_KEY is required"**
→ Make sure `.env` file exists and has your API key

**Error: "No data found for symbol"**
→ Check internet connection, try different dates

**Slow backtest?**
→ Increase `--sample-rate` (e.g., `--sample-rate 48`)

**High API costs?**
→ Reduce sample rate or use shorter date ranges

## 📞 Need Help?

1. **Check logs**: `cat trading_system.log`
2. **Read docs**: See `SETUP_GUIDE.md`
3. **Review code**: Comments in `agents.py`

---

**Ready to trade? Run:**
```bash
python main.py backtest --start-date 2023-01-01 --end-date 2024-12-31
```

**🎉 Happy Trading!**
