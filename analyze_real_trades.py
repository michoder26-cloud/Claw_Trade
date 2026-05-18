import re

with open('chunk_1.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

current_regime = 'UNKNOWN'
wins_by_regime = {}
losses_by_regime = {}
last_signal = None

for l in lines:
    regime_m = re.search(r'Regime: ([A-Z_]+)', l)
    if regime_m:
        current_regime = regime_m.group(1)
        
    exit_m = re.search(r'\[(.*?)\] (TAKE_PROFIT|STOP_LOSS): (BUY|SELL) closed .*? P&L: (-?[\d\.]+)', l)
    if exit_m:
        pnl = float(exit_m.group(4))
        
        if pnl > 0:
            wins_by_regime[current_regime] = wins_by_regime.get(current_regime, 0) + 1
        else:
            losses_by_regime[current_regime] = losses_by_regime.get(current_regime, 0) + 1

print('\n--- AI BRAIN TRAINING ANALYSIS ---')
all_regimes = set(list(wins_by_regime.keys()) + list(losses_by_regime.keys()))

total_wins = 0
total_losses = 0

for r in all_regimes:
    w = wins_by_regime.get(r, 0)
    l = losses_by_regime.get(r, 0)
    t = w + l
    total_wins += w
    total_losses += l
    win_rate = (w/t)*100 if t > 0 else 0
    print(f'Market Regime: {r:<20} -> Trades: {t:<4} | Wins: {w:<3} | Win Rate: {win_rate:.2f}%')

print('-'*50)
total_t = total_wins + total_losses
total_wr = (total_wins/total_t)*100 if total_t > 0 else 0
print(f'TOTAL TRADES: {total_t} | WINS: {total_wins} | WIN RATE: {total_wr:.2f}%')
