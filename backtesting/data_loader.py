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
        Fetches historical bars, attempting to load from cache first.
        (Note: For simplicity, caching is done per exact date range requested)
        """
        # Ensure UTC timezone for consistency
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
            
        start_str = start.isoformat()
        end_str = end.isoformat()
        tf_str = str(timeframe)
        symbols_key = ",".join(sorted(symbols))
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT bars_json FROM bars_cache WHERE symbol=? AND timeframe=? AND start_date=? AND end_date=?",
                           (symbols_key, tf_str, start_str, end_str))
            row = cursor.fetchone()
            
            if row:
                logger.info(f"Loaded historical bars from cache for {symbols_key} ({tf_str})")
                df = pd.read_json(row[0])
                if not df.empty and 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
                return df
                
        logger.info(f"Fetching historical bars from Alpaca for {symbols_key} ({tf_str})...")
        df = self.client.get_historical_bars(symbols, timeframe, start, end)
        
        if not df.empty:
            # We must reset index to turn multi-index into columns before JSON serialization
            reset_df = df.reset_index()
            # Store in cache
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO bars_cache (symbol, timeframe, start_date, end_date, bars_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (symbols_key, tf_str, start_str, end_str, reset_df.to_json(date_format='iso')))
                conn.commit()
                
        return df

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
