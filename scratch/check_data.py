import sys
from datetime import datetime, timedelta, timezone
from backtesting.data_loader import BacktestDataLoader
from alpaca.data.timeframe import TimeFrame

loader = BacktestDataLoader()
end = datetime.now(timezone.utc)
start = end - timedelta(days=180)
symbols = ['BTC/USD', 'ETH/USD', 'SOL/USD']

bars = loader.get_historical_bars(symbols, TimeFrame.Minute, start, end)
print("Total bars:", len(bars))
if not bars.empty:
    if 'timestamp' in bars.columns:
        ts = bars['timestamp']
    else:
        ts = bars.index.get_level_values('timestamp')
    print("Min ts:", ts.min())
    print("Max ts:", ts.max())
    print("Symbols:", bars.index.get_level_values('symbol').unique() if not 'symbol' in bars.columns else bars['symbol'].unique())
