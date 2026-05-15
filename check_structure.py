import json

with open('backtest_results.json', 'r') as f:
    results = json.load(f)

# Check structure
print("Sample backtest entry structure:")
print(json.dumps(results[0], indent=2)[:1500])
print("\n...")

# Check for trade metrics in entries
print("\nChecking for trade data...")
for i, entry in enumerate(results):
    if entry.get('trade_executed'):
        print(f"\nEntry {i} - TRADE EXECUTED:")
        print(json.dumps(entry, indent=2)[:2000])
        break

# Check all unique keys
keys = set()
for entry in results:
    keys.update(entry.keys())
print("\nAll available keys in entries:", keys)
