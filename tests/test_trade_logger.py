"""
tests/test_trade_logger.py

Unit tests for data/trade_logger.py — TDD: written BEFORE the implementation.
"""
import json
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


class TestWSTradeLoggerLogTrigger:
    """Tests for WSTradeLogger.log_trigger()"""

    def test_creates_json_file_on_first_trigger(self, tmp_path):
        from data.trade_logger import WSTradeLogger
        ws_log = tmp_path / "ws_triggers.json"
        with patch("data.trade_logger.WS_LOG_FILE", str(ws_log)):
            WSTradeLogger.log_trigger("BTCUSD", 65000.0, -0.3, "BULLISH", 0.85, "test reasoning", "order-1", True)
        assert ws_log.exists()
        data = json.loads(ws_log.read_text())
        assert len(data) == 1
        assert data[0]["symbol"] == "BTCUSD"
        assert data[0]["executed"] is True

    def test_appends_to_existing_triggers(self, tmp_path):
        from data.trade_logger import WSTradeLogger
        ws_log = tmp_path / "ws_triggers.json"
        existing = [{"symbol": "ETHUSD", "price": 3000.0}]
        ws_log.write_text(json.dumps(existing))
        with patch("data.trade_logger.WS_LOG_FILE", str(ws_log)):
            WSTradeLogger.log_trigger("SOLUSD", 80.0, -0.5, "BULLISH", 0.9, "reason", "order-2", True)
        data = json.loads(ws_log.read_text())
        assert len(data) == 2
        assert data[1]["symbol"] == "SOLUSD"

    def test_keeps_max_200_entries(self, tmp_path):
        from data.trade_logger import WSTradeLogger
        ws_log = tmp_path / "ws_triggers.json"
        # Write 200 existing entries
        existing = [{"symbol": f"SYM{i}", "price": float(i)} for i in range(200)]
        ws_log.write_text(json.dumps(existing))
        with patch("data.trade_logger.WS_LOG_FILE", str(ws_log)):
            WSTradeLogger.log_trigger("NEWUSD", 1.0, 0.1, "NEUTRAL", 0.0, "r", "o", False)
        data = json.loads(ws_log.read_text())
        assert len(data) == 200
        # Last entry should be the new one
        assert data[-1]["symbol"] == "NEWUSD"


class TestWSTradeLoggerLogPrice:
    """Tests for WSTradeLogger.log_price()"""

    def test_creates_price_history_for_new_symbol(self, tmp_path):
        from data.trade_logger import WSTradeLogger
        history_file = tmp_path / "realtime_price_history.json"
        with patch("data.trade_logger.PRICE_HISTORY_FILE", str(history_file)):
            WSTradeLogger.log_price("BTCUSD", 65000.0, datetime.now(timezone.utc))
        data = json.loads(history_file.read_text())
        assert "BTCUSD" in data
        assert len(data["BTCUSD"]) == 1
        assert data["BTCUSD"][0]["price"] == 65000.0

    def test_appends_price_to_existing_symbol(self, tmp_path):
        from data.trade_logger import WSTradeLogger
        history_file = tmp_path / "realtime_price_history.json"
        initial = {"BTCUSD": [{"timestamp": "2020-01-01T00:00:00+00:00", "price": 60000.0}]}
        history_file.write_text(json.dumps(initial))
        with patch("data.trade_logger.PRICE_HISTORY_FILE", str(history_file)):
            WSTradeLogger.log_price("BTCUSD", 65000.0, datetime.now(timezone.utc))
        data = json.loads(history_file.read_text())
        assert len(data["BTCUSD"]) == 2

    def test_keeps_max_200_price_points(self, tmp_path):
        from data.trade_logger import WSTradeLogger
        history_file = tmp_path / "realtime_price_history.json"
        initial = {"BTCUSD": [{"timestamp": f"2020-01-01T{i:02d}:00:00+00:00", "price": float(i)} for i in range(200)]}
        history_file.write_text(json.dumps(initial))
        with patch("data.trade_logger.PRICE_HISTORY_FILE", str(history_file)):
            WSTradeLogger.log_price("BTCUSD", 99999.0, datetime.now(timezone.utc))
        data = json.loads(history_file.read_text())
        assert len(data["BTCUSD"]) == 200
        assert data["BTCUSD"][-1]["price"] == 99999.0


class TestWSTradeLoggerWriteLogbook:
    """Tests for WSTradeLogger.write_logbook()"""

    def test_appends_message_to_logbook(self, tmp_path):
        from data.trade_logger import WSTradeLogger
        logbook = tmp_path / "human_logbook.txt"
        with patch("data.trade_logger.LOGBOOK_FILE", str(logbook)):
            WSTradeLogger.write_logbook("Test message")
        content = logbook.read_text()
        assert "Test message" in content

    def test_multiple_writes_append_new_lines(self, tmp_path):
        from data.trade_logger import WSTradeLogger
        logbook = tmp_path / "human_logbook.txt"
        with patch("data.trade_logger.LOGBOOK_FILE", str(logbook)):
            WSTradeLogger.write_logbook("Message 1")
            WSTradeLogger.write_logbook("Message 2")
        lines = logbook.read_text().strip().split("\n")
        assert len(lines) == 2
        assert "Message 1" in lines[0]
        assert "Message 2" in lines[1]
