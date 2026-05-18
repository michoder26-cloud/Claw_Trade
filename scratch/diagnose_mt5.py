import os
import sys
import io
import json
from pathlib import Path
from dotenv import load_dotenv

# Fix encoding on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv(override=True)
symbol = os.getenv("MT5_SYMBOL", "XAUUSDc")

try:
    import MetaTrader5 as mt5
    print("MetaTrader5 package imported successfully.")
except ImportError:
    print("Error: MetaTrader5 package is not installed.")
    sys.exit(1)

# 1. Connect to MT5
if not mt5.initialize():
    print(f"Failed to connect to MetaTrader 5. Error: {mt5.last_error()}")
    sys.exit(1)

print("\n✅ MT5 Connection: SUCCESSFUL!")
print(f"MT5 Version: {mt5.version()}")

# 2. Get Account Information
acc = mt5.account_info()
if acc is not None:
    print("\n--- ACCOUNT DETAILS ---")
    print(f"Broker/Company : {acc.company}")
    print(f"Server Name    : {acc.server}")
    print(f"Account Number : {acc.login}")
    print(f"Balance        : {acc.balance:.2f}")
    print(f"Equity         : {acc.equity:.2f}")
    print(f"Margin         : {acc.margin:.2f}")
    print(f"Free Margin    : {acc.margin_free:.2f}")
    print(f"Margin Level   : {acc.margin_level:.2f}%")
    print(f"Trade Allowed  : {acc.trade_allowed} (Account level trade permission)")
else:
    print("\n❌ Failed to retrieve account info.")

# 3. Check Terminal Info
term = mt5.terminal_info()
if term is not None:
    print("\n--- TERMINAL STATE ---")
    print(f"Algo Trading Enabled: {term.trade_allowed} (Must be TRUE for bot to trade!)")
    print(f"Connected to Server : {term.connected}")
else:
    print("\n❌ Failed to retrieve terminal info.")

# 4. Check Symbol Details
sym_info = mt5.symbol_info(symbol)
if sym_info is not None:
    print(f"\n--- SYMBOL PARAMETERS: {symbol} ---")
    print(f"Trade Contract Size  : {sym_info.trade_contract_size}")
    print(f"Volume Min           : {sym_info.volume_min}")
    print(f"Volume Max           : {sym_info.volume_max}")
    print(f"Volume Step          : {sym_info.volume_step}")
    print(f"Spread               : {sym_info.spread}")
    print(f"Digits               : {sym_info.digits}")
    print(f"Trade Mode           : {sym_info.trade_mode} (If 0=disabled, 4=full access)")
    
    # Enable symbol in Market Watch if not enabled
    if not sym_info.visible:
        print(f"Symbol '{symbol}' was not visible in Market Watch. Attempting to select...")
        mt5.symbol_select(symbol, True)
else:
    print(f"\n❌ Symbol '{symbol}' NOT FOUND in MT5. Printing first 10 symbols containing 'XAU' or 'GOLD'...")
    all_syms = mt5.symbols_get()
    matches = [s.name for s in all_syms if "XAU" in s.name.upper() or "GOLD" in s.name.upper()]
    print(f"Matches found: {matches[:10]}")

# 5. Perform order_check for 22.84 Lots (Simulation)
if sym_info is not None and acc is not None:
    tick = mt5.symbol_info_tick(symbol)
    if tick is not None:
        price = tick.bid # SELL test
        sl = price + 12.0
        tp = price - 24.0
        volume = 22.84
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 20,
            "magic": 99999,
            "comment": "Simulation Diagnostic Check",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        print(f"\n--- ORDER_CHECK SIMULATION (Volume: {volume} Lots, Price: {price:.2f}) ---")
        check_result = mt5.order_check(request)
        if check_result is None:
            print(f"Order check failed entirely. Error code: {mt5.last_error()}")
        else:
            print(f"Check Retcode: {check_result.retcode}")
            print(f"Check Comment: {check_result.comment}")
            print(f"Check Margin Needed: {check_result.margin:.2f}")
            print(f"Check Balance Left : {check_result.balance:.2f}")
            if check_result.retcode == 0:
                print("🟢 Result: Order is completely VALID! Broker will accept this order!")
            else:
                print(f"🔴 Result: REJECTED by Broker! Reason code: {check_result.retcode}")
                # Try ORDER_FILLING_FOK
                print("\nRetrying simulation with ORDER_FILLING_FOK filling mode...")
                request["type_filling"] = mt5.ORDER_FILLING_FOK
                check_result_fok = mt5.order_check(request)
                if check_result_fok:
                    print(f"FOK Check Retcode: {check_result_fok.retcode}")
                    print(f"FOK Check Comment: {check_result_fok.comment}")
                    if check_result_fok.retcode == 0:
                        print("🟢 Result with FOK: Order is VALID!")
    else:
        print("\n❌ Failed to retrieve current price ticks for simulation.")

mt5.shutdown()
print("\nMT5 connection closed.")
