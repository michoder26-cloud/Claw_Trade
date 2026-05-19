import sys
import os
import MetaTrader5 as mt5

sys.path.insert(0, 'src')
from mt5_connector import MT5Connector

conn = MT5Connector()
if not conn.connect():
    print("❌ Failed to connect to MT5")
    sys.exit(1)

ticket = 1784418694

print(f"Querying deals for position ticket: {ticket}...")
deals = mt5.history_deals_get(position=ticket)
if deals is None:
    print(f"❌ No deals found or error: {mt5.last_error()}")
else:
    print(f"Found {len(deals)} deals:")
    for deal in deals:
        print("--- Deal ---")
        print(f"Ticket/Order: {deal.order}")
        print(f"Position ID: {deal.position_id}")
        print(f"Type (0=Buy, 1=Sell): {deal.type}")
        print(f"Entry (0=In, 1=Out, 2=InOut): {deal.entry}")
        print(f"Volume: {deal.volume}")
        print(f"Price: {deal.price}")
        print(f"Profit: {deal.profit} {deal.comment}")
        print(f"Symbol: {deal.symbol}")
        print(f"Comment: {deal.comment}")
        print(f"Reason: {deal.reason}")
        # Reason mapping: 0=client, 3=SL, 4=TP, etc.
        # mt5.DEAL_REASON_CLIENT = 0
        # mt5.DEAL_REASON_SL = 3
        # mt5.DEAL_REASON_TP = 4
        # mt5.DEAL_REASON_SO = 5 (Stop Out)

conn.shutdown()
