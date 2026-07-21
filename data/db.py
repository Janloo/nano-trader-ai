import sqlite3
import os
import threading
import json
from contextlib import contextmanager

DB_PATH = os.path.join("data", "trading_bot.db")
db_lock = threading.Lock()

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                action TEXT,
                qty REAL,
                price REAL,
                notional REAL,
                sentiment_score REAL,
                reasoning TEXT,
                execution_type TEXT,
                order_id TEXT
            )
        ''')
        
        # AI Analytics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                asset TEXT,
                price REAL,
                action TEXT,
                confidence REAL,
                sentiment_score REAL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                reasoning TEXT,
                return_1h REAL,
                return_4h REAL,
                analysis_id TEXT
            )
        ''')
        
        # Portfolio History table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                equity REAL,
                buying_power REAL,
                unrealized_pnl REAL,
                average_sentiment REAL DEFAULT 0.0
            )
        ''')
        
        conn.commit()

@contextmanager
def get_db():
    with db_lock:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

def insert_trade(timestamp, symbol, action, qty, price, notional, sentiment_score, reasoning, execution_type, order_id=""):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (timestamp, symbol, action, qty, price, notional, sentiment_score, reasoning, execution_type, order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (timestamp, symbol, action, qty, price, notional, sentiment_score, reasoning, execution_type, order_id))
        conn.commit()

def insert_ai_analytics(timestamp, asset, price, action, confidence, sentiment_score, prompt_tokens, completion_tokens, reasoning, return_1h, return_4h, analysis_id=""):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ai_analytics (timestamp, asset, price, action, confidence, sentiment_score, prompt_tokens, completion_tokens, reasoning, return_1h, return_4h, analysis_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (timestamp, asset, price, action, confidence, sentiment_score, prompt_tokens, completion_tokens, reasoning, return_1h, return_4h, analysis_id))
        conn.commit()
        return cursor.lastrowid

def insert_portfolio_snap(timestamp, equity, buying_power, unrealized_pnl, average_sentiment=0.0):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO portfolio_history (timestamp, equity, buying_power, unrealized_pnl, average_sentiment)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, equity, buying_power, unrealized_pnl, average_sentiment))
        conn.commit()

def update_ai_analytics_feedback(analytics_id, return_1h, return_4h):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE ai_analytics
            SET return_1h = COALESCE(?, return_1h),
                return_4h = COALESCE(?, return_4h)
            WHERE id = ?
        ''', (return_1h, return_4h, analytics_id))
        conn.commit()

def get_trades(limit=50):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_new_trades(last_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE id > ? ORDER BY id ASC", (last_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_portfolio_history(limit=100):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM portfolio_history ORDER BY timestamp ASC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_ai_analytics(limit=50):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_analytics ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_ai_analytics_pending_feedback():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_analytics WHERE return_4h IS NULL ORDER BY timestamp ASC")
        return [dict(row) for row in cursor.fetchall()]

def get_ai_analytics_completed_feedback():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_analytics WHERE return_1h IS NOT NULL OR return_4h IS NOT NULL ORDER BY timestamp ASC")
        return [dict(row) for row in cursor.fetchall()]

# Initialize db on module load
init_db()
