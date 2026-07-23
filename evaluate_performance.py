import sys
import os
from datetime import datetime, timezone, timedelta
import sqlite3
import time

from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY, logger

def get_db():
    return sqlite3.connect('data/trading_bot.db')

def update_returns():
    crypto_client = CryptoHistoricalDataClient(api_key=APCA_API_KEY_ID, secret_key=APCA_API_SECRET_KEY)
    stock_client = StockHistoricalDataClient(api_key=APCA_API_KEY_ID, secret_key=APCA_API_SECRET_KEY)

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get pending rows that are older than 1 hour
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)
        cursor.execute("SELECT * FROM ai_analytics WHERE return_1h IS NULL AND timestamp < ?", (cutoff_time.isoformat(),))
        pending_trades = cursor.fetchall()

        if not pending_trades:
            print("No pending trades ready for 1-hour evaluation.")
            return

        print(f"Found {len(pending_trades)} trades to evaluate.")

        for trade in pending_trades:
            trade_id = trade['id']
            symbol = trade['asset']
            action = trade['action']
            exec_price = float(trade['price'])
            
            trade_dt = datetime.fromisoformat(trade['timestamp'])
            eval_dt = trade_dt + timedelta(hours=1)
            is_crypto = "USD" in symbol or "BTC" in symbol or "ETH" in symbol

            try:
                if is_crypto:
                    req_start = CryptoBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame.Minute, start=trade_dt - timedelta(minutes=5), end=trade_dt + timedelta(minutes=5))
                    req_end = CryptoBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame.Minute, start=eval_dt - timedelta(minutes=5), end=eval_dt + timedelta(minutes=5))
                    bars_start = crypto_client.get_crypto_bars(req_start)
                    bars_end = crypto_client.get_crypto_bars(req_end)
                else:
                    req_start = StockBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame.Minute, start=trade_dt - timedelta(minutes=5), end=trade_dt + timedelta(minutes=5))
                    req_end = StockBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame.Minute, start=eval_dt - timedelta(minutes=5), end=eval_dt + timedelta(minutes=5))
                    bars_start = stock_client.get_stock_bars(req_start)
                    bars_end = stock_client.get_stock_bars(req_end)
                
                if bars_start.df.empty or bars_end.df.empty:
                    print(f"No bars found for {symbol}")
                    continue
                
                # Get P1
                df_start = bars_start.df.reset_index()
                df_start['diff'] = abs((df_start['timestamp'] - trade_dt).dt.total_seconds())
                p1 = df_start.sort_values('diff').iloc[0]['close']

                # Get P2
                df_end = bars_end.df.reset_index()
                df_end['diff'] = abs((df_end['timestamp'] - eval_dt).dt.total_seconds())
                p2 = df_end.sort_values('diff').iloc[0]['close']
                
                # Calculate return
                if "BUY" in action or "HOLD" in action:
                    ret_1h = ((p2 - p1) / p1) * 100.0
                elif "SELL" in action or "HEDGE" in action:
                    ret_1h = ((p1 - p2) / p1) * 100.0
                else:
                    ret_1h = 0.0

                print(f"Evaluated {symbol} {action}: P1={p1} P2={p2} (1h return: {ret_1h:.2f}%)")

                # Update database
                cursor.execute("UPDATE ai_analytics SET return_1h = ?, price = ? WHERE id = ?", (ret_1h, p1, trade_id))
                conn.commit()

            except Exception as e:
                print(f"Error evaluating {symbol}: {e}")

if __name__ == "__main__":
    update_returns()
