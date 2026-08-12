"""
data/trade_logger.py

Handles persistence of WebSocket trade events: trigger log, price history, human logbook.
Extracted from realtime_executor.py as a standalone module with single responsibility.
"""
import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("nano-trader-ai")

WS_LOG_FILE = os.path.join("data", "state", "ws_triggers.json")
LOGBOOK_FILE = os.path.join("data", "archives", "human_logbook.txt")
PRICE_HISTORY_FILE = os.path.join("data", "state", "realtime_price_history.json")


class WSTradeLogger:
    """Logs WebSocket-triggered trades to ws_triggers.json, price history, and the human logbook."""

    @staticmethod
    def log_trigger(symbol: str, price: float, dip_pct: float,
                    bias: str, sentiment_score: float, reasoning: str,
                    order_id: str, executed: bool):
        """Logs a DIP/SPIKE trigger event to ws_triggers.json (max 200 entries)."""
        os.makedirs(os.path.dirname(WS_LOG_FILE), exist_ok=True)
        try:
            triggers = []
            if os.path.exists(WS_LOG_FILE):
                with open(WS_LOG_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        triggers = json.loads(content)

            triggers.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "price": price,
                "dip_pct": round(dip_pct, 4),
                "bias": bias,
                "sentiment_score": sentiment_score,
                "reasoning": reasoning,
                "order_id": order_id,
                "executed": executed
            })

            # Keep only last 200 entries
            triggers = triggers[-200:]
            with open(WS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(triggers, f, indent=4)
        except Exception as e:
            logger.error(f"[WSTradeLogger] Failed to log trigger: {e}")

    @staticmethod
    def log_trade(symbol: str, price: float, qty: float, order_id: str,
                  sentiment_score: float, reasoning: str, dip_pct: float):
        """Appends a WebSocket-triggered trade to SQLite DB."""
        try:
            from data.db import insert_trade
            timestamp = datetime.now(timezone.utc).isoformat()
            insert_trade(
                timestamp=timestamp,
                symbol=symbol,
                action="BUY",
                qty=qty,
                price=price,
                notional=qty * price,
                sentiment_score=sentiment_score,
                reasoning=f"{reasoning} (DIP: {dip_pct:.4f}%)",
                execution_type="hybrid_websocket_trigger",
                order_id=order_id
            )
        except Exception as e:
            logger.error(f"[WSTradeLogger] Failed to log trade to DB: {e}")

    @staticmethod
    def write_logbook(msg: str):
        """Appends a timestamped message to the human-readable logbook file."""
        os.makedirs(os.path.dirname(LOGBOOK_FILE), exist_ok=True)
        try:
            with open(LOGBOOK_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except Exception:
            pass

    @staticmethod
    def log_price(symbol: str, price: float, timestamp: datetime):
        """Logs a price point to realtime_price_history.json (max 200 points per symbol). Atomic write."""
        os.makedirs(os.path.dirname(PRICE_HISTORY_FILE), exist_ok=True)
        try:
            history = {}
            if os.path.exists(PRICE_HISTORY_FILE):
                with open(PRICE_HISTORY_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        try:
                            decoder = json.JSONDecoder()
                            history, _ = decoder.raw_decode(content)
                        except json.JSONDecodeError:
                            logger.warning("[WSTradeLogger] realtime_price_history.json was corrupted. Resetting.")
                            history = {}

            if symbol not in history:
                history[symbol] = []

            history[symbol].append({
                "timestamp": timestamp.isoformat(),
                "price": price
            })

            # Keep last 200 points
            history[symbol] = history[symbol][-200:]

            # Write atomically
            tmp_path = PRICE_HISTORY_FILE + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
            os.replace(tmp_path, PRICE_HISTORY_FILE)
        except Exception as e:
            logger.error(f"[WSTradeLogger] Failed to log price history: {e}")
