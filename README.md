# 🏆 XAU/USD Multi-Agent Trading System

A sophisticated **multi-agent trading system** for gold (XAU/USD) analysis using Claude AI agents that analyze news, technical indicators, and risk management to generate trading signals with consensus decision-making.

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
    │ News   │  │Technical│ Risk    │ Consensus│
    │Analyst │  │Analyst  │ Manager │ Engine   │
    └────────┘  └────────┘ └────────┘ └──────────┘
         │           │           │           │
         └───────────┼───────────┴───────────┘
                     │
              ┌──────▼──────┐
              │ Backtester  │
              │ (Execute)   │
              └─────────────┘
```

## 📋 Agents & Responsibilities

### 1. 📰 **News Analyst**
- Analyzes fundamental factors affecting XAU/USD
- Monitors geopolitical events, Fed policy, inflation
- Outputs: BUY/SELL/HOLD signal + Confidence score

### 2. 📊 **Technical Analyst**
- Analyzes price action and technical indicators:
  - RSI (Relative Strength Index)
  - MACD (Moving Average Convergence Divergence)
  - Bollinger Bands
  - ATR (Average True Range)
- Identifies support/resistance levels
- Outputs: BUY/SELL/HOLD + Entry/Exit levels

### 3. ⚖️ **Risk Manager**
- Calculates position sizing (Kelly Criterion, Fixed %)
- Determines stop-loss and take-profit levels
- Monitors portfolio risk and drawdown
- Outputs: Position size, SL/TP levels, Risk metrics

### 4. 🤝 **Consensus Engine**
- Aggregates signals from all agents
- Uses weighted voting system
- Resolves disagreements
- Outputs: Final signal + Confidence level

### 5. 🎯 **Master Orchestrator**
- Coordinates all agents
- Manages trading execution
- Logs analysis history
- Exports results

## 🚀 Quick Start

### Prerequisites
```bash
pip install -r requirements.txt
```

### Setup Environment
```bash
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY
```

### Run Backtest
```bash
python main.py backtest --start-date 2023-01-01 --end-date 2024-12-31 --sample-rate 24
```

### Check Configuration
```bash
python main.py config
```

## 📁 Project Structure

```
xau_trading_system/
├── config.py              # Configuration management
├── data_handler.py        # Data fetching & preprocessing
├── agents.py              # Individual AI agents
├── backtester.py          # Backtesting engine
├── orchestrator.py        # Master orchestrator
├── main.py                # CLI entry point
├── requirements.txt       # Dependencies
├── .env.example           # Environment template
└── README.md              # This file
```

## ⚙️ Configuration

Edit `.env` or modify `config.py`:

```env
# Trading Parameters
INITIAL_BALANCE=10000                 # Starting capital ($)
POSITION_SIZE_PERCENT=2               # Risk per trade (%)
MAX_DAILY_TRADES=3                    # Max trades per day
MAX_OPEN_POSITIONS=2                  # Concurrent positions
MAX_DRAWDOWN_PERCENT=10               # Portfolio drawdown limit (%)
RISK_REWARD_RATIO=1.5                 # Required RR ratio

# Backtesting
BACKTESTING_START_DATE=2023-01-01
BACKTESTING_END_DATE=2024-12-31

# API
ANTHROPIC_API_KEY=sk-...
```

## 📊 Output & Results

### Backtesting Report
```
==============================================================
📊 BACKTESTING REPORT
==============================================================
Initial Balance: $10,000.00
Final Balance: $12,450.50
Net Profit/Loss: $2,450.50 (24.51%)

TRADE STATISTICS:
Total Trades: 45
  - Buy Trades: 23
  - Sell Trades: 22
Winning Trades: 28
Losing Trades: 17
Win Rate: 62.22%
Profit Factor: 1.85

PERFORMANCE METRICS:
Gross Profit: $3,200.00
Gross Loss: $1,750.00
Average P&L per Trade: $54.46
Max Drawdown: -$1,200.00 (-12%)
Sharpe Ratio: 1.45
==============================================================
```

### Analysis Results (JSON)
Detailed analysis records saved to `backtest_results.json`:
- Timestamp & price
- Agent signals & confidence
- Risk calculations
- Trade execution details

## 🔄 Agent Workflow

1. **Data Preparation**: Load OHLCV data + calculate indicators
2. **Technical Analysis**: Evaluate technical signals
3. **News/Fundamental**: Assess market sentiment
4. **Risk Calculation**: Determine position size & levels
5. **Consensus**: Combine all signals
6. **Execution**: Execute trade or skip (HOLD)
7. **Monitoring**: Track open positions
8. **Exit Management**: Check SL/TP levels

## 🧪 Backtesting Features

✅ Historical data from Yahoo Finance  
✅ OHLC candle analysis  
✅ Multiple indicator calculations  
✅ Position sizing based on Kelly Criterion  
✅ Stop-loss and take-profit tracking  
✅ Trade statistics (win rate, profit factor, Sharpe ratio)  
✅ Drawdown analysis  
✅ Equity curve tracking  

## 📈 Performance Metrics

- **Win Rate**: % of profitable trades
- **Profit Factor**: Gross Profit / Gross Loss
- **Sharpe Ratio**: Risk-adjusted returns
- **Max Drawdown**: Largest peak-to-trough decline
- **Return %**: Total profit / Initial balance

## 🔐 Risk Management

- Position sizing follows Kelly Criterion
- Maximum risk per trade: 2% (configurable)
- Stop-loss and take-profit automation
- Portfolio heat monitoring
- Max drawdown enforcement
- Multiple position limit

## 🚀 Future Enhancements

- [ ] Real-time data feed integration
- [ ] Live broker API integration (Oanda, IG)
- [ ] Machine learning model integration
- [ ] Advanced risk analytics
- [ ] Telegram/Discord notifications
- [ ] Advanced pattern recognition
- [ ] Multi-timeframe analysis

## ⚠️ Important Notes

**Disclaimer**: This system is for educational and research purposes. Past performance does not guarantee future results. Always conduct proper risk management and never trade with money you can't afford to lose.

## 📞 Support

- 🐛 Issues: Check logs in `trading_system.log`
- 📚 Documentation: See inline code comments
- 💡 Ideas: Contribute improvements!

## 📄 License

Educational Use Only

---

**Created with ❤️ using Claude AI**
