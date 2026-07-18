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
        # Search window of 10 minutes around the target time
        start = target_time - timedelta(minutes=5)
        end = target_time + timedelta(minutes=5)
        
        bars_df = client.get_historical_bars([symbol], TimeFrame.Minute, start, end)
        if not bars_df.empty:
            if isinstance(bars_df.index, pd.MultiIndex):
                # Map symbol name for indexing
                mapped_symbol = "BTC/USD" if symbol == "BTCUSD" else symbol
                if mapped_symbol in bars_df.index.levels[0]:
                    df = bars_df.xs(mapped_symbol, level=0).copy()
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
    Scans data/ai_analytics_logs.json and updates metrics for entries older than +1h or +4h.
    """
    file_path = os.path.join("data", "archives", "ai_analytics_logs.jsonl")
    if not os.path.exists(file_path) or client is None:
        return

    logs = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
    except Exception as e:
        logger.error(f"Failed to read ai_analytics_logs.jsonl for feedback update: {e}")
        return

    updated = False
    now = datetime.now(timezone.utc)

    for entry in logs:
        timestamp_str = entry.get("timestamp")
        if not timestamp_str:
            continue

        try:
            trade_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        symbol = entry.get("asset")
        exec_price = float(entry.get("price", 0.0))
        if exec_price <= 0:
            continue
            
        feedback = entry.setdefault("feedback_loop_metric", {})

        # Calculate +1 Hour close price
        if feedback.get("price_at_1h") is None:
            target_1h = trade_time + timedelta(hours=1)
            if now >= target_1h:
                price_1h = fetch_price_at_time(client, symbol, target_1h)
                if price_1h is not None:
                    feedback["price_at_1h"] = price_1h
                    feedback["return_1h"] = ((price_1h - exec_price) / exec_price) * 100.0
                    updated = True
                    logger.info(f"[Feedback Loop] Updated +1h price for {symbol} to ${price_1h:.2f} (Return: {feedback['return_1h']:.2f}%)")

        # Calculate +4 Hour close price
        if feedback.get("price_at_4h") is None:
            target_4h = trade_time + timedelta(hours=4)
            if now >= target_4h:
                price_4h = fetch_price_at_time(client, symbol, target_4h)
                if price_4h is not None:
                    feedback["price_at_4h"] = price_4h
                    feedback["return_4h"] = ((price_4h - exec_price) / exec_price) * 100.0
                    updated = True
                    logger.info(f"[Feedback Loop] Updated +4h price for {symbol} to ${price_4h:.2f} (Return: {feedback['return_4h']:.2f}%)")

    if updated:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save feedback update logs: {e}")
