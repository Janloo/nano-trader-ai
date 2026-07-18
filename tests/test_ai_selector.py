"""
tests/test_ai_selector.py

Unit tests for the Dynamic Asset Selection (DAS) engine.
"""
import json
import os
import pytest
from unittest.mock import MagicMock, patch

from strategy.ai_selector import GeminiAssetSelector, load_universe


# ────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────

SAMPLE_UNIVERSE = [
    {"symbol": "BTCUSD", "type": "crypto",  "name": "Bitcoin / USD"},
    {"symbol": "ETHUSD", "type": "crypto",  "name": "Ethereum / USD"},
    {"symbol": "SPY",    "type": "equity",  "name": "S&P 500 ETF"},
    {"symbol": "NVDA",   "type": "equity",  "name": "NVIDIA Corp."},
]

SAMPLE_NEWS = (
    "1. [Global Economy] Fed holds rates steady amid inflation concerns.\n"
    "2. [Crypto Market] Bitcoin surges past $70k on ETF inflows.\n"
    "3. [Tech Stocks] NVIDIA reports record quarterly earnings.\n"
)


# ────────────────────────────────────────────────
# load_universe tests
# ────────────────────────────────────────────────

def test_load_universe_returns_defaults_when_missing(tmp_path, monkeypatch):
    """load_universe returns safe defaults when the JSON file is missing."""
    monkeypatch.chdir(tmp_path)
    config = load_universe()
    assert "assets" in config
    assert len(config["assets"]) >= 1
    # At least one crypto asset is always in defaults
    types = {a["type"] for a in config["assets"]}
    assert "crypto" in types


def test_load_universe_loads_real_file():
    """load_universe correctly parses config/market_universe.json."""
    config = load_universe()
    assert "assets" in config
    assert "max_selections" in config
    assert "sentiment_threshold" in config
    symbols = [a["symbol"] for a in config["assets"]]
    assert "BTCUSD" in symbols
    assert "SPY" in symbols


# ────────────────────────────────────────────────
# GeminiAssetSelector — MOCK mode tests
# ────────────────────────────────────────────────

def test_mock_select_returns_valid_selections():
    """In mock mode, selector returns a non-empty list of valid asset dicts."""
    with patch("strategy.ai_selector.GEMINI_API_KEY", ""):
        selector = GeminiAssetSelector()

    result = selector.select_assets(SAMPLE_UNIVERSE, SAMPLE_NEWS)
    assert isinstance(result, list)
    assert len(result) >= 1
    assert len(result) <= 2  # max_selections from universe config

    for item in result:
        assert "symbol" in item
        assert "type" in item
        assert "sentiment_score" in item
        assert "reasoning" in item
        assert "selected_at" in item
        assert item["symbol"] in {a["symbol"] for a in SAMPLE_UNIVERSE}


def test_mock_select_prefers_crypto():
    """In mock mode, first selected asset should be a crypto asset."""
    with patch("strategy.ai_selector.GEMINI_API_KEY", ""):
        selector = GeminiAssetSelector()

    result = selector.select_assets(SAMPLE_UNIVERSE, SAMPLE_NEWS)
    assert result[0]["type"] == "crypto"


def test_mock_select_sentiment_within_bounds():
    """Mock sentiment scores should be within [-1.0, 1.0] range."""
    with patch("strategy.ai_selector.GEMINI_API_KEY", ""):
        selector = GeminiAssetSelector()

    result = selector.select_assets(SAMPLE_UNIVERSE, SAMPLE_NEWS)
    for item in result:
        assert -1.0 <= item["sentiment_score"] <= 1.0


# ────────────────────────────────────────────────
# GeminiAssetSelector — Fallback logic tests
# ────────────────────────────────────────────────

def test_fallback_selection_returns_crypto_only():
    """_fallback_selection should prefer crypto assets for 24/7 trading."""
    with patch("strategy.ai_selector.GEMINI_API_KEY", ""):
        selector = GeminiAssetSelector()

    fallback = selector._fallback_selection(SAMPLE_UNIVERSE, max_sel=2)
    assert len(fallback) > 0
    for item in fallback:
        assert item["type"] == "crypto"


def test_fallback_selection_caps_at_max_sel():
    """_fallback_selection never returns more than max_sel items."""
    with patch("strategy.ai_selector.GEMINI_API_KEY", ""):
        selector = GeminiAssetSelector()

    fallback = selector._fallback_selection(SAMPLE_UNIVERSE, max_sel=1)
    assert len(fallback) <= 1


# ────────────────────────────────────────────────
# GeminiAssetSelector — Live API (mocked) tests
# ────────────────────────────────────────────────

def test_live_select_parses_valid_json():
    """Live mode: selector correctly parses valid Gemini JSON response."""
    mock_response_json = json.dumps({
        "selected_assets": [
            {"symbol": "BTCUSD", "sentiment_score": 0.88, "reasoning": "Strong institutional demand."},
            {"symbol": "NVDA",   "sentiment_score": 0.91, "reasoning": "Record AI chip earnings."}
        ]
    })
    mock_response = MagicMock()
    mock_response.text = mock_response_json

    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response

    with patch("strategy.ai_selector.GEMINI_API_KEY", "fake-key-123"):
        selector = GeminiAssetSelector()
        selector.model = mock_model

    result = selector.select_assets(SAMPLE_UNIVERSE, SAMPLE_NEWS)

    assert len(result) == 2
    symbols = [r["symbol"] for r in result]
    assert "BTCUSD" in symbols
    assert "NVDA" in symbols
    assert result[0]["type"] in {"crypto", "equity"}


def test_live_select_filters_invalid_symbols():
    """Live mode: symbols not in universe are silently filtered out."""
    mock_response_json = json.dumps({
        "selected_assets": [
            {"symbol": "INVALID_SYM", "sentiment_score": 0.99, "reasoning": "Fake asset."},
            {"symbol": "BTCUSD",      "sentiment_score": 0.80, "reasoning": "Valid crypto."}
        ]
    })
    mock_response = MagicMock()
    mock_response.text = mock_response_json

    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response

    with patch("strategy.ai_selector.GEMINI_API_KEY", "fake-key-123"):
        selector = GeminiAssetSelector()
        selector.model = mock_model

    result = selector.select_assets(SAMPLE_UNIVERSE, SAMPLE_NEWS)

    assert all(r["symbol"] != "INVALID_SYM" for r in result)
    assert any(r["symbol"] == "BTCUSD" for r in result)


def test_live_select_falls_back_on_quota_error():
    """Live mode: 429 quota error triggers fallback to crypto selection."""
    mock_model = MagicMock()
    mock_model.generate_content.side_effect = Exception("429 quota exceeded")

    with patch("strategy.ai_selector.GEMINI_API_KEY", "fake-key-123"):
        with patch("strategy.ai_selector.time.sleep"):  # skip backoff waits in tests
            selector = GeminiAssetSelector()
            selector.model = mock_model
            result = selector.select_assets(SAMPLE_UNIVERSE, SAMPLE_NEWS)

    # Fallback returns crypto assets
    assert isinstance(result, list)
    for item in result:
        assert item["type"] == "crypto"
