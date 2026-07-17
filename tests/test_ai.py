import pytest
from strategy.ai_analyzer import GeminiSentimentStrategy
from unittest.mock import patch

def test_gemini_mock_analysis():
    """Verify Gemini strategy fallback mock returns expected schema and parses keywords correctly."""
    with patch("strategy.ai_analyzer.GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE"):
        strategy = GeminiSentimentStrategy()
        assert strategy.is_mocked is True
    
    # 1. Bullish scenario
    res_bullish = strategy.analyze_news_text("SPY", "Market surged with record profits and bullish growth.")
    assert res_bullish["action"] == "BUY"
    assert res_bullish["sentiment_score"] > 0.5
    assert res_bullish["confidence"] > 75
    
    # 2. Bearish scenario
    res_bearish = strategy.analyze_news_text("SPY", "Stocks drop following losses and bearish forecasts.")
    assert res_bearish["action"] == "SELL"
    assert res_bearish["sentiment_score"] < 0.0
    
    # 3. Neutral scenario
    res_neutral = strategy.analyze_news_text("SPY", "Standard trading continues with calm market indexes.")
    assert res_neutral["action"] == "HOLD"
    assert res_neutral["sentiment_score"] == pytest.approx(0.15)
