"""
tests/test_realtime_executor.py

Unit tests for realtime_executor.py (Micro execution layer).
"""
import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from realtime_executor import BiasReader, DipDetector, RealtimeExecutor, WSTradeLogger

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

def test_dip_detector_tracks_rolling_window():
    """Prunes old price points outside the rolling window and finds DIPs correctly."""
    detector = DipDetector(window_seconds=10, dip_threshold_pct=-1.0)
    now = datetime.now(timezone.utc)
    
    # 1. First price point
    dip = detector.update("BTCUSD", 100.0, now)
    assert dip is None
    
    # 2. Price climbs, no dip
    dip = detector.update("BTCUSD", 105.0, now + timedelta(seconds=2))
    assert dip is None
    
    # 3. Price drops but not enough (-0.5%)
    dip = detector.update("BTCUSD", 104.5, now + timedelta(seconds=4))
    assert dip is None
    
    # 4. Price drops past threshold (-1.9% from high of 105.0)
    dip = detector.update("BTCUSD", 103.0, now + timedelta(seconds=6))
    assert dip is not None
    assert dip == pytest.approx(-1.90476, abs=1e-3)
    
    # 5. Point older than window is pruned
    # Update with timestamp past 10 seconds. High (105.0 at +2s) will be pruned if we update at +15s
    # The new window will only contain the point at +15s (102.0)
    dip = detector.update("BTCUSD", 102.0, now + timedelta(seconds=15))
    assert dip is None


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


@patch("realtime_executor.WSTradeLogger.log_trade")
@patch("realtime_executor.WSTradeLogger.log_trigger")
def test_on_bar_triggers_order_on_valid_conditions(mock_log_trigger, mock_log_trade, mock_bias_file):
    """on_bar executes order when DIP and BULLISH bias conditions are met."""
    with open(mock_bias_file, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_UNIVERSE_BIAS, f)

    executor = RealtimeExecutor(symbols=["BTCUSD"], dry_run=True)
    
    # Create mock bar indicating a DIP
    # High: 100.0, Close: 99.0 (-1.0% drop)
    now = datetime.now(timezone.utc)
    bar1 = MagicMock(symbol="BTC/USD", close=100.0, timestamp=now)
    bar2 = MagicMock(symbol="BTC/USD", close=99.0, timestamp=now + timedelta(seconds=5))
    
    executor.on_bar(bar1)
    
    with patch.object(executor, "_execute_order", return_value="mock-order-id") as mock_exec:
        executor.on_bar(bar2)
        mock_exec.assert_called_once()
        # Verify symbol and dip_pct arguments
        args, kwargs = mock_exec.call_args
        assert args[0] == "BTCUSD"
        assert args[1] == 99.0
        assert args[2] == pytest.approx(-1.0)
        assert args[3]["bias"] == "BULLISH"
