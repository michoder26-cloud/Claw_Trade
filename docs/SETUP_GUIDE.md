# 🚀 Installation & Setup Guide

## Prerequisites

- **Python 3.8+**
- **Anthropic API Key** (from https://console.anthropic.com)
- **pip** (Python package manager)

## Step 1: Clone/Download Project

```bash
cd xau_trading_system
```

## Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

Verify installation:
```bash
python -c "import anthropic; print('✅ Anthropic SDK installed')"
python -c "import yfinance; print('✅ YFinance installed')"
python -c "import pandas; print('✅ Pandas installed')"
```

## Step 3: Configure Environment

### Create `.env` file

```bash
cp .env.example .env
```

### Edit `.env` with your settings

```bash
# Windows (PowerShell)
notepad .env

# Or macOS/Linux
nano .env
```

### Required values:

```env
ANTHROPIC_API_KEY=sk-ant-...your-api-key-here...

# Trading Settings (adjust as needed)
INITIAL_BALANCE=10000
POSITION_SIZE_PERCENT=2
MAX_DAILY_TRADES=3
RISK_REWARD_RATIO=1.5
MAX_DRAWDOWN_PERCENT=10

# Backtesting dates
BACKTESTING_START_DATE=2023-01-01
BACKTESTING_END_DATE=2024-12-31
```

**⚠️ IMPORTANT**: Never commit `.env` to git. Keep it in `.gitignore`.

## Step 4: Verify Configuration

```bash
python main.py config
```

Expected output:
```
Current Configuration:
  API Key: ✓ Set
  Trading Mode: BACKTEST
  Initial Balance: $10,000.00
  Max Drawdown: 10%
  Risk per Trade: 2%
```

## Step 5: Run First Backtest

### Quick Test (1 month of data)
```bash
python main.py backtest \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --sample-rate 24
```

### Full Backtest (1 year)
```bash
python main.py backtest \
  --start-date 2023-01-01 \
  --end-date 2024-12-31 \
  --sample-rate 24
```

### Custom Parameters
```bash
python main.py backtest \
  --symbol GC=F \
  --start-date 2023-06-01 \
  --end-date 2023-12-31 \
  --sample-rate 12 \
  --output my_results.json
```

## Step 6: Review Results

### Backtest Report

The system generates:
- **Console output**: Real-time analysis progress
- **backtest_results.json**: Detailed analysis records
- **trading_system.log**: Complete execution log

Example output:
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
Max Drawdown: -12%
Sharpe Ratio: 1.45
==============================================================
```

## Step 7: Setup Managed Agents (24/7 Cloud)

### Option A: Manual Setup

1. Go to https://claude.ai/code/agents
2. Create 3 new agents:
   - **Daily Analysis** (8 AM UTC daily)
   - **Intraday Monitor** (every 4 hours)
   - **Weekly Review** (Sundays 8 PM UTC)
3. Copy instructions from `managed_agents_setup.py`

### Option B: Automatic Setup (Recommended)

```bash
python managed_agents_setup.py
```

This creates:
- Agent configurations in `managed_agents_config.json`
- Setup instructions displayed in console
- Ready-to-use agent prompts

Then copy configurations to Claude.ai manually.

## Step 8: Monitor Agent Executions

### Check Logs
```bash
# View last 50 lines
tail -n 50 trading_system.log

# Windows PowerShell
Get-Content trading_system.log -Tail 50
```

### Analyze Results
```bash
# View backtest JSON results
python -m json.tool backtest_results.json | head -100
```

## 🎯 Common Commands

### Run entire backtesting suite
```bash
python main.py backtest --start-date 2022-01-01 --end-date 2024-12-31
```

### Run quick analysis
```bash
python main.py backtest --start-date 2024-06-01 --end-date 2024-06-30 --sample-rate 48
```

### Show configuration
```bash
python main.py config
```

### Generate agent setup
```bash
python managed_agents_setup.py
```

## 🔧 Troubleshooting

### Error: "ANTHROPIC_API_KEY is required"
```bash
# Check if .env exists
ls .env  # or: dir .env (Windows)

# Check if key is set
grep ANTHROPIC_API_KEY .env
```

### Error: "No data found for symbol"
- Verify internet connection
- Check if symbol "GC=F" is valid
- Try different date range
- Yahoo Finance might be down (use yfinance-ng as alternative)

### Error: "Max open positions exceeded"
- This is normal - means the strategy is risk-appropriate
- Adjust `MAX_OPEN_POSITIONS` in `.env` if needed

### Error: "Insufficient balance for trade"
- Increase `INITIAL_BALANCE` in `.env`
- Reduce `POSITION_SIZE_PERCENT`
- Reduce `sample_rate` to trade less frequently

### Error: "Analysis failed: API rate limit"
- Reduce `sample_rate` (trade less frequently)
- Add delays between agent calls
- Upgrade Anthropic API plan

## 📊 Performance Optimization

### Reduce API Costs
```bash
# Sample every 48 hours instead of 24
python main.py backtest --sample-rate 48

# This reduces API calls by 50%
```

### Faster Backtests
```bash
# Use shorter date ranges
python main.py backtest --start-date 2024-06-01 --end-date 2024-09-30
```

### Better Results
```bash
# Lower sample rate for more frequent analysis
python main.py backtest --sample-rate 12  # Every 12 hours

# But this increases API costs
```

## 🔐 Security Best Practices

1. **Never commit `.env` to git**
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Use environment variables**
   ```bash
   # Set API key via environment variable
   export ANTHROPIC_API_KEY="sk-ant-..."
   python main.py backtest
   ```

3. **Rotate API keys regularly**
   - Go to https://console.anthropic.com
   - Delete old keys, create new ones
   - Update `.env`

4. **Limit API key permissions**
   - Only enable necessary endpoints
   - Use separate keys for testing and production

## 📈 Next Steps

1. **Customize Strategy**
   - Adjust risk parameters in `.env`
   - Modify agent instructions in `agents.py`
   - Add new technical indicators

2. **Paper Trading**
   ```bash
   python main.py paper --symbol GC=F
   ```

3. **Live Trading** (⚠️ ADVANCED)
   ```bash
   # Not implemented yet - requires broker integration
   # Add broker API keys to .env
   # Implement in orchestrator.py
   ```

4. **Monitoring & Alerts**
   - Set up Slack notifications
   - Configure email alerts
   - Create Telegram bot for alerts

## 📞 Support

- **Check logs**: `cat trading_system.log`
- **Review code**: See inline comments
- **Test incrementally**: Start with backtesting before live trading

---

**Ready to start? Run:**
```bash
python main.py backtest --start-date 2024-01-01 --end-date 2024-12-31
```
