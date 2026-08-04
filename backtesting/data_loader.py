import sqlite3
import os
import json
import logging
import pandas as pd
from datetime import datetime, timezone
from typing import List, Optional, Dict
from client.alpaca_client import AlpacaClientWrapper
from alpaca.data.timeframe import TimeFrame

logger = logging.getLogger(__name__)

class BacktestDataLoader:
    def __init__(self, db_path: str = "data/backtest_cache.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.client = AlpacaClientWrapper()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # AI responses cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_cache (
                    symbol TEXT,
                    date_str TEXT,
                    response_json TEXT,
                    PRIMARY KEY (symbol, date_str)
                )
            """)
            # Historical bars cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bars_cache (
                    symbol TEXT,
                    timeframe TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    bars_json TEXT,
                    PRIMARY KEY (symbol, timeframe, start_date, end_date)
                )
            """)
            conn.commit()

    def get_historical_bars(self, symbols: List[str], timeframe: TimeFrame, start: datetime, end: datetime) -> pd.DataFrame:
        """
        Fetches historical bars, caching data in monthly chunks to avoid API timeouts
        on very large historical queries (e.g. 6 months of 1-minute bars).
        """
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
            
        tf_str = str(timeframe)
        symbols_key = ",".join(sorted(symbols))
        all_bars = []
        
        # Helper to generate monthly chunks
        from dateutil.relativedelta import relativedelta
        current_start = start
        
        while current_start < end:
            # End of the month or 'end' if it's closer
            next_month = (current_start + relativedelta(months=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            current_end = min(next_month - pd.Timedelta(seconds=1), end)
            
            start_str = current_start.isoformat()
            end_str = current_end.isoformat()
            
            chunk_df = None
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT bars_json FROM bars_cache WHERE symbol=? AND timeframe=? AND start_date=? AND end_date=?",
                               (symbols_key, tf_str, start_str, end_str))
                row = cursor.fetchone()
                if row:
                    logger.info(f"Loaded chunk from cache: {symbols_key} {start_str} to {end_str}")
                    import io
                    chunk_df = pd.read_json(io.StringIO(row[0]))
                    if not chunk_df.empty and 'timestamp' in chunk_df.columns:
                        chunk_df['timestamp'] = pd.to_datetime(chunk_df['timestamp'], utc=True)
                        
            if chunk_df is None:
                logger.info(f"Fetching chunk from Alpaca: {symbols_key} {start_str} to {end_str}")
                chunk_df = self.client.get_historical_bars(symbols, timeframe, current_start, current_end)
                
                if not chunk_df.empty:
                    reset_df = chunk_df.reset_index()
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT OR REPLACE INTO bars_cache (symbol, timeframe, start_date, end_date, bars_json)
                            VALUES (?, ?, ?, ?, ?)
                        """, (symbols_key, tf_str, start_str, end_str, reset_df.to_json(date_format='iso')))
                        conn.commit()
            
            if chunk_df is not None and not chunk_df.empty:
                # If it was fetched from Alpaca, it has a multi-index (symbol, timestamp)
                # If from cache, it's flat. Let's make sure it's flat for concatenation.
                if 'timestamp' not in chunk_df.columns and not isinstance(chunk_df.index, pd.RangeIndex):
                     chunk_df = chunk_df.reset_index()
                all_bars.append(chunk_df)
                
            current_start = next_month

        if not all_bars:
            return pd.DataFrame()
            
        combined_df = pd.concat(all_bars, ignore_index=True)
        # Restore multi-index expected by downstream
        if 'symbol' in combined_df.columns and 'timestamp' in combined_df.columns:
            combined_df = combined_df.set_index(['symbol', 'timestamp'])
        return combined_df

    def get_cached_ai_response(self, symbol: str, date_str: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT response_json FROM ai_cache WHERE symbol=? AND date_str=?", (symbol, date_str))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
        return None

    def cache_ai_response(self, symbol: str, date_str: str, response: Dict):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO ai_cache (symbol, date_str, response_json)
                VALUES (?, ?, ?)
            """, (symbol, date_str, json.dumps(response)))
            conn.commit()

    def get_news_articles(self, symbols: List[str], start: datetime, end: datetime, limit: int = 50) -> pd.DataFrame:
        """
        Fetches historical news articles for backtesting.
        Does not heavily cache news in this version, but delegates to AlpacaClient.
        """
        return self.client.get_news_articles(symbols, start, end, limit)
