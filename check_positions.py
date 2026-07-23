from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY, APCA_API_BASE_URL
from alpaca.trading.client import TradingClient
client = TradingClient(APCA_API_KEY_ID, APCA_API_SECRET_KEY, paper=True)
positions = client.get_all_positions()
account = client.get_account()
bp = float(account.buying_power)
eq = float(account.equity)
print(f"Cash (buying power): {bp:,.2f}")
print(f"Equity total:        {eq:,.2f}")
print()
print("--- POSIZIONI APERTE ---")
total_invested = 0
for p in positions:
    val = float(p.market_value)
    total_invested += val
    upnl = float(p.unrealized_pl)
    pct = (val / eq * 100) if eq > 0 else 0
    print(f"  {p.symbol}: {val:,.2f} ({pct:.1f}% portfolio) | PnL: {upnl:+.2f}")
print(f"Totale investito: {total_invested:,.2f}")
print(f"Cash pct: {(bp / eq * 100):.1f}%")
