"""
tests/test_bias_reader.py

Unit tests for data/bias_reader.py — TDD: written BEFORE the implementation.
"""
import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, mock_open


class TestBiasReaderRead:
    """Tests for BiasReader.read()"""

    def test_read_returns_expired_flag_when_file_missing(self, tmp_path):
        from data.bias_reader import BiasReader
        with patch("data.bias_reader.BIAS_FILE", str(tmp_path / "nonexistent.json")):
            result = BiasReader.read()
        assert result.get("expired") is True
        assert result.get("target_assets") == []

    def test_read_returns_expired_flag_when_bias_is_stale(self, tmp_path):
        from data.bias_reader import BiasReader
        bias_file = tmp_path / "market_bias.json"
        stale_payload = {
            "target_assets": [{"symbol": "BTCUSD", "bias": "BULLISH", "sentiment_score": 0.8}],
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
            "expires_at": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
        }
        bias_file.write_text(json.dumps(stale_payload))
        with patch("data.bias_reader.BIAS_FILE", str(bias_file)):
            result = BiasReader.read()
        assert result.get("expired") is True

    def test_read_returns_non_expired_when_fresh(self, tmp_path):
        from data.bias_reader import BiasReader
        bias_file = tmp_path / "market_bias.json"
        fresh_payload = {
            "target_assets": [{"symbol": "SOLUSD", "bias": "BULLISH", "sentiment_score": 0.9}],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        }
        bias_file.write_text(json.dumps(fresh_payload))
        with patch("data.bias_reader.BIAS_FILE", str(bias_file)):
            result = BiasReader.read()
        assert result.get("expired") is False
        assert len(result.get("target_assets", [])) == 1

    def test_read_returns_expired_flag_on_json_decode_error(self, tmp_path):
        from data.bias_reader import BiasReader
        bias_file = tmp_path / "market_bias.json"
        bias_file.write_text("{ this is: not valid json }")
        with patch("data.bias_reader.BIAS_FILE", str(bias_file)):
            result = BiasReader.read()
        assert result.get("expired") is True
        assert result.get("target_assets") == []


class TestBiasReaderGetBiasForSymbol:
    """Tests for BiasReader.get_bias_for_symbol()"""

    def test_returns_correct_entry_for_known_symbol(self, tmp_path):
        from data.bias_reader import BiasReader
        bias_file = tmp_path / "market_bias.json"
        fresh_payload = {
            "target_assets": [
                {"symbol": "BTCUSD", "bias": "BULLISH", "sentiment_score": 0.85},
                {"symbol": "SOLUSD", "bias": "BEARISH", "sentiment_score": -0.70},
            ],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        }
        bias_file.write_text(json.dumps(fresh_payload))
        with patch("data.bias_reader.BIAS_FILE", str(bias_file)):
            result = BiasReader.get_bias_for_symbol("SOLUSD")
        assert result["bias"] == "BEARISH"
        assert result["sentiment_score"] == pytest.approx(-0.70)

    def test_returns_neutral_for_unknown_symbol(self, tmp_path):
        from data.bias_reader import BiasReader
        bias_file = tmp_path / "market_bias.json"
        fresh_payload = {
            "target_assets": [{"symbol": "BTCUSD", "bias": "BULLISH", "sentiment_score": 0.85}],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        }
        bias_file.write_text(json.dumps(fresh_payload))
        with patch("data.bias_reader.BIAS_FILE", str(bias_file)):
            result = BiasReader.get_bias_for_symbol("XYZUSD")
        assert result["bias"] == "NEUTRAL"
        assert result["sentiment_score"] == 0.0

    def test_returns_neutral_when_bias_is_expired(self, tmp_path):
        from data.bias_reader import BiasReader
        bias_file = tmp_path / "market_bias.json"
        stale_payload = {
            "target_assets": [{"symbol": "BTCUSD", "bias": "BULLISH", "sentiment_score": 0.85}],
            "expires_at": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
        }
        bias_file.write_text(json.dumps(stale_payload))
        with patch("data.bias_reader.BIAS_FILE", str(bias_file)):
            result = BiasReader.get_bias_for_symbol("BTCUSD")
        assert result["bias"] == "NEUTRAL"

    def test_returns_neutral_when_file_missing(self, tmp_path):
        from data.bias_reader import BiasReader
        with patch("data.bias_reader.BIAS_FILE", str(tmp_path / "nonexistent.json")):
            result = BiasReader.get_bias_for_symbol("BTCUSD")
        assert result["bias"] == "NEUTRAL"
        assert result["sentiment_score"] == 0.0
