#!/usr/bin/env python3
"""Run multiple backtests with different parameter sets to find optimal config"""
import subprocess
import json
import os
from pathlib import Path

RESULTS_DIR = Path("/root/Claw_Trade/backtest_results")
RESULTS_DIR.mkdir(exist_ok=True)

# Different configurations to test
configs = [
    # (name, risk_pct, max_daily)
    ("default-6pct", 6.0, 3),
    ("safe-2pct", 2.0, 1),
    ("conservative-1pct", 1.0, 2),
    ("moderate-3pct", 3.0, 2),
    ("aggressive-4pct", 4.0, 3),
]

env = os.environ.copy()
env["USE_MOCK_AI"] = "true"
env["DATA_SOURCE"] = "yfinance"

print("=" * 70)
print("🚀 Running Parameter Optimization Backtests (May 2026)")
print("=" * 70)

results = []

for name, risk_pct, max_daily in configs:
    print(f"\n{'─'*70}")
    print(f"📊 Testing: {name} (Risk: {risk_pct}%, Max Daily: {max_daily})")
    print(f"{'─'*70}")
    
    # Create temp .env override
    os.environ["POSITION_SIZE_PERCENT"] = str(risk_pct)
    os.environ["MAX_DAILY_TRADES"] = str(max_daily)
    
    cmd = [
        "python3", "/root/Claw_Trade/main.py",
        "backtest",
        "--start-date", "2026-05-01",
        "--end-date", "2026-05-31",
        "--interval", "1h",
        "--risk-pct", str(risk_pct),
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
    
    # Extract summary
    output_file = "/root/Claw_Trade/backtest_summary.json"
    if os.path.exists(output_file):
        with open(output_file) as f:
            summary = json.load(f)
        summary["config_name"] = name
        summary["risk_pct"] = risk_pct
        summary["max_daily"] = max_daily
        
        # Save individual result
        with open(RESULTS_DIR / f"{name}.json", "w") as f:
            json.dump(summary, f, indent=2)
        
        results.append(summary)
        print(f"   ✅ Trades: {summary['total_trades']} | WinRate: {summary['win_rate']:.1f}% | PnL: ${summary['net_profit_loss']:,.2f} ({summary['profit_loss_pct']:.1f}%)")

# Sort by best net profit
results.sort(key=lambda r: r.get("net_profit_loss", 0), reverse=True)

print(f"\n{'='*70}")
print("🏆 RANKING BY NET PROFIT:")
print(f"{'='*70}")
for i, r in enumerate(results, 1):
    print(f"  {i}. {r['config_name']:25s} | PnL: ${r['net_profit_loss']:>8,.2f} | WinRate: {r['win_rate']:5.1f}% | PF: {r['profit_factor']:5.2f} | Trades: {r['total_trades']}")

# Save full ranking
with open(RESULTS_DIR / "_ranking.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\n📁 All results saved to: {RESULTS_DIR}/")
print(f"🏆 Best config saved to: {RESULTS_DIR}/_ranking.json")