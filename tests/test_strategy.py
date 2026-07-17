import pytest
import pandas as pd
import numpy as np
from strategy.technical import TechnicalStrategy
from strategy.ai_sentiment import AISentimentStrategy
from strategy.combined import CombinedStrategy

def test_rsi_calculation():
    """Verify that RSI is correctly calculated on flat and increasing sequences."""
    strategy = TechnicalStrategy(rsi_period=14)
    
    # 1. Flat prices -> RSI should be either 0.0 or NaN
    series = pd.Series([10.0] * 20)
    rsi = strategy.calculate_rsi(series, period=14)
    assert rsi.iloc[-1] == 0.0 or np.isnan(rsi.iloc[-1])

    # 2. Monotonically increasing price -> RSI should hit 100
    series_asc = pd.Series(range(1, 25), dtype=float)
    rsi_asc = strategy.calculate_rsi(series_asc, period=14)
    assert rsi_asc.iloc[-1] == pytest.approx(100.0)

def test_technical_strategy_signals():
    """Verify combined SMA crossover and RSI bounds logic."""
    strategy = TechnicalStrategy(fast_period=5, slow_period=10, rsi_period=4)
    
    dates = pd.date_range(end="2026-01-01", periods=15)
    # Monotonically increasing close prices
    bars_df = pd.DataFrame({
        "close": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24],
        "open": [10.0]*15, "high": [10.0]*15, "low": [10.0]*15, "volume": [1000]*15
    }, index=dates)

    # SMA: fast_sma (last 5, avg=22) > slow_sma (last 10, avg=19.5) -> bullish crossover (+0.5)
    # RSI: close is constantly rising -> RSI = 100 -> overbought (-0.5)
    # Total technical signal: 0.5 + (-0.5) = 0.0
    signal = strategy.analyze("TEST", bars_df, None)
    assert signal == 0.0

def test_sentiment_strategy():
    """Verify sentiment lexicon matches positive/negative words and weights headline/summary."""
    strategy = AISentimentStrategy()
    
    # 1. Empty news -> neutral score
    assert strategy.analyze("TEST", None, None) == 0.0
    assert strategy.analyze("TEST", None, pd.DataFrame()) == 0.0
    
    # 2. Bullish keyword occurrence
    news_bullish = pd.DataFrame([
        {"headline": "Company reports profit growth", "summary": "Stock surged after upbeat earnings report."}
    ])
    score_bullish = strategy.analyze("TEST", None, news_bullish)
    assert score_bullish > 0.0
    
    # 3. Bearish keyword occurrence
    news_bearish = pd.DataFrame([
        {"headline": "Company facing downgrade and loss", "summary": "Shares drop due to weak demand and failure."}
    ])
    score_bearish = strategy.analyze("TEST", None, news_bearish)
    assert score_bearish < 0.0

def test_combined_strategy():
    """Verify weighted combination logic and single-signal fallback."""
    strategy = CombinedStrategy(technical_weight=0.6, sentiment_weight=0.4)
    
    # If news is empty, fallback to 100% technical signal
    strategy.tech_strategy.analyze = lambda symbol, bars, news: 0.5
    assert strategy.analyze("TEST", pd.DataFrame(), None) == 0.5
    assert strategy.analyze("TEST", pd.DataFrame(), pd.DataFrame()) == 0.5
    
    # Combine tech signal (0.5) and sentiment signal (-0.2)
    # Result: (0.5 * 0.6) + (-0.2 * 0.4) = 0.30 - 0.08 = 0.22
    strategy.sentiment_strategy.analyze = lambda symbol, bars, news: -0.2
    combined = strategy.analyze("TEST", pd.DataFrame(), pd.DataFrame([{"dummy": 1}]))
    assert pytest.approx(combined) == 0.22

def test_conditional_dca_strategy():
    """Verify ConditionalDcaStrategy buy signal triggers only when close is below SMA."""
    from strategy.conditional_dca import ConditionalDcaStrategy
    strategy = ConditionalDcaStrategy(period=5)
    
    # 1. Price is BELOW SMA-5 (Average = 9.8, last price = 9.0) -> BUY (1.0)
    bars_buy = pd.DataFrame({
        "close": [10.0, 10.0, 10.0, 10.0, 9.0]
    })
    assert strategy.analyze("TEST", bars_buy, None) == 1.0
    
    # 2. Price is ABOVE SMA-5 (Average = 10.2, last price = 11.0) -> HOLD (0.0)
    bars_hold = pd.DataFrame({
        "close": [10.0, 10.0, 10.0, 10.0, 11.0]
    })
    assert strategy.analyze("TEST", bars_hold, None) == 0.0
