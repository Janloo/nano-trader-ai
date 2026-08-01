"""
tests/test_realtime_executor.py

Unit tests for realtime_executor.py (Micro execution layer).
"""
import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from realtime_executor import BiasReader, RealtimeExecutor, WSTradeLogger

SAMPLE_UNIVERSE_BIAS = {
    "target_assets": [
        {
            "symbol": "BTCUSD",
            "bias": "BULLISH",
            "sentiment_score": 0.85,
            "reasoning": "Strong crypto market.",
            "asset_type": "crypto"
        },
        {
            "symbol": "ETHUSD",
            "bias": "NEUTRAL",
            "sentiment_score": 0.20,
            "reasoning": "Consolidation.",
            "asset_type": "crypto"
        }
    ],
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    "macro_articles_analyzed": 10
}


@pytest.fixture
def mock_bias_file(tmp_path):
    """Sets up a temporary market_bias.json file."""
    bias_path = tmp_path / "market_bias.json"
    with patch("realtime_executor.BIAS_FILE", str(bias_path)):
        yield bias_path


# ────────────────────────────────────────────────
# BiasReader Tests
# ────────────────────────────────────────────────

def test_bias_reader_file_missing(mock_bias_file):
    """If file is missing, read() should return expired/stale bias dict."""
    if os.path.exists(mock_bias_file):
        os.remove(mock_bias_file)
    data = BiasReader.read()
    assert data.get("expired") is True
    assert len(data.get("target_assets", [])) == 0


def test_bias_reader_reads_valid_bias(mock_bias_file):
    """Correctly reads active bias from file."""
    with open(mock_bias_file, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_UNIVERSE_BIAS, f)

    data = BiasReader.read()
    assert data.get("expired") is False
    assert len(data.get("target_assets")) == 2
    
    btc_bias = BiasReader.get_bias_for_symbol("BTCUSD")
    assert btc_bias["bias"] == "BULLISH"
    assert btc_bias["sentiment_score"] == 0.85


def test_bias_reader_handles_expired_bias(mock_bias_file):
    """Stale bias (> 2 hours old) is treated as NEUTRAL/expired."""
    expired_bias = SAMPLE_UNIVERSE_BIAS.copy()
    expired_bias["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    
    with open(mock_bias_file, "w", encoding="utf-8") as f:
        json.dump(expired_bias, f)

    data = BiasReader.read()
    assert data.get("expired") is True
    
    btc_bias = BiasReader.get_bias_for_symbol("BTCUSD")
    assert btc_bias["bias"] == "NEUTRAL"
    assert btc_bias["sentiment_score"] == 0.0


# ────────────────────────────────────────────────
# DipDetector Tests
# ────────────────────────────────────────────────


# ────────────────────────────────────────────────
# RealtimeExecutor Logic Tests
# ────────────────────────────────────────────────

def test_cooldown_logic():
    """Verify cooldown prevents immediate repeat orders on same symbol."""
    executor = RealtimeExecutor(symbols=["BTCUSD"], dry_run=True)
    
    assert executor._is_on_cooldown("BTCUSD") is False
    
    # Set last order time to now
    executor._last_order_time["BTCUSD"] = datetime.now(timezone.utc)
    assert executor._is_on_cooldown("BTCUSD") is True
    
    # Set last order time to 6 minutes ago (cooldown is 5 mins)
    executor._last_order_time["BTCUSD"] = datetime.now(timezone.utc) - timedelta(minutes=6)
    assert executor._is_on_cooldown("BTCUSD") is False
