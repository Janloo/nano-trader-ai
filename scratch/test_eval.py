import time
import pandas as pd
from alpaca.data.timeframe import TimeFrame
from realtime_executor import RealtimeExecutor
from datetime import datetime, timezone, timedelta
import logging

logging.basicConfig(level=logging.WARNING)

print("Creating dummy data...")
start_time = datetime.now(timezone.utc)
flat_bars = []
for i in range(1000):
    flat_bars.append({
        'timestamp': start_time + timedelta(minutes=i),
        'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.5,
        'volume': 10, 'trade_count': 5, 'vwap': 100.5,
        'symbol': 'BTCUSD'
    })

executor = RealtimeExecutor(["BTCUSD"])

# Mock disk I/O
def mock_update_price_history(sym, price):
    pass
executor._update_price_history = mock_update_price_history

# Mock broker
class MockBroker:
    def get_open_position(self, sym): raise Exception("No pos")
    def get_account_info(self):
        class Acc:
            equity="10000"
            buying_power="10000"
        return Acc()
    def get_all_positions(self): return []
executor._trading_client = MockBroker()

print("Testing 1000 bars...")
s = time.time()
count = 0
for row in flat_bars:
    class MockBar:
        def __init__(self, symbol, close, timestamp):
            self.symbol = symbol
            self.close = close
            self.timestamp = timestamp
    bar = MockBar(row['symbol'], row['close'], row['timestamp'])
    executor.on_bar(bar)
    count += 1
    if count == 1000:
        break

print(f"Time for 1000 bars: {time.time() - s} seconds")
