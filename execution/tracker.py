import os
import json
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional
from alpaca.data.timeframe import TimeFrame
from config.settings import logger
from client.alpaca_client import AlpacaClientWrapper

def fetch_price_at_time(client: AlpacaClientWrapper, symbol: str, target_time: datetime) -> Optional[float]:
    """Queries Alpaca historical client for a minute bar close to target_time."""
    try:
        # Map crypto symbols for historical API (e.g. BTCUSD -> BTC/USD)
        query_symbol = symbol
        if symbol.endswith("USD") and symbol != "USD":
            query_symbol = symbol[:-3] + "/USD"
            
        # Search window of 10 minutes around the target time
        start = target_time - timedelta(minutes=5)
        end = target_time + timedelta(minutes=5)
        
        bars_df = client.get_historical_bars([query_symbol], TimeFrame.Minute, start, end)
        if not bars_df.empty:
            if isinstance(bars_df.index, pd.MultiIndex):
                if query_symbol in bars_df.index.levels[0]:
                    df = bars_df.xs(query_symbol, level=0).copy()
                else:
                    df = bars_df.copy()
            else:
                df = bars_df.copy()
                
            # Find the closest timestamp to the target_time
            times = df.index
            time_diffs = []
            for t in times:
                t_val = t[1] if isinstance(t, tuple) else t
                t_utc = t_val.tz_convert(timezone.utc) if getattr(t_val, 'tzinfo', None) else t_val.replace(tzinfo=timezone.utc)
                time_diffs.append(abs(t_utc - target_time))
                
            df['diff'] = time_diffs
            df = df.sort_values(by='diff')
            return float(df['close'].iloc[0])
    except Exception as e:
        logger.warning(f"Failed to fetch feedback price at {target_time} for {symbol}: {e}")
    return None

def update_feedback_loop_metrics(client: Optional[AlpacaClientWrapper]):
    """
    Scans sqlite db and updates metrics for entries older than +1h or +4h.
    """
    if client is None:
        return

    from data.db import get_ai_analytics_pending_feedback, update_ai_analytics_feedback
    logs = get_ai_analytics_pending_feedback()

    now = datetime.now(timezone.utc)

    for entry in logs:
        analytics_id = entry["id"]
        timestamp_str = entry["timestamp"]
        try:
            trade_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        symbol = entry["asset"]
        exec_price = float(entry["price"]) if entry["price"] else 0.0
        
        # If execution price is 0 (e.g. from macro bias analysis without immediate trade),
        # fetch the historical price at the time of the analysis to serve as the baseline!
        if exec_price <= 0:
            fetched_base_price = fetch_price_at_time(client, symbol, trade_time)
            if fetched_base_price is None:
                continue
            exec_price = fetched_base_price
            
        ret_1h = entry["return_1h"]
        ret_4h = entry["return_4h"]
        updated = False

        # Calculate +1 Hour close price
        if ret_1h is None:
            target_1h = trade_time + timedelta(hours=1)
            if now >= target_1h:
                price_1h = fetch_price_at_time(client, symbol, target_1h)
                if price_1h is not None:
                    ret_1h = ((price_1h - exec_price) / exec_price) * 100.0
                    updated = True
                    logger.info(f"[Feedback Loop] Updated +1h price for {symbol} to ${price_1h:.2f} (Return: {ret_1h:.2f}%)")

        # Calculate +4 Hour close price
        if ret_4h is None:
            target_4h = trade_time + timedelta(hours=4)
            if now >= target_4h:
                price_4h = fetch_price_at_time(client, symbol, target_4h)
                if price_4h is not None:
                    ret_4h = ((price_4h - exec_price) / exec_price) * 100.0
                    updated = True
                    logger.info(f"[Feedback Loop] Updated +4h price for {symbol} to ${price_4h:.2f} (Return: {ret_4h:.2f}%)")

        if updated:
            update_ai_analytics_feedback(analytics_id, ret_1h, ret_4h)
