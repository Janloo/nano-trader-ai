import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import pandas as pd
from client.alpaca_client import AlpacaClientWrapper
from alpaca.data.timeframe import TimeFrame

@patch("client.alpaca_client.TradingClient")
@patch("client.alpaca_client.StockHistoricalDataClient")
@patch("client.alpaca_client.NewsClient")
def test_alpaca_client_wrapper_init(mock_news, mock_historical, mock_trading):
    """Verify that clients are properly instantiated within the wrapper."""
    wrapper = AlpacaClientWrapper()
    assert wrapper.trading_client is not None
    assert wrapper.data_client is not None
    assert wrapper.news_client is not None

@patch("client.alpaca_client.TradingClient")
@patch("client.alpaca_client.StockHistoricalDataClient")
@patch("client.alpaca_client.NewsClient")
def test_alpaca_client_wrapper_methods(mock_news, mock_historical, mock_trading):
    """Verify wrapper delegates calls to the respective Alpaca clients with correct formatting."""
    instance_trading = mock_trading.return_value
    instance_historical = mock_historical.return_value
    instance_news = mock_news.return_value
    
    wrapper = AlpacaClientWrapper()
    
    # 1. get_account_info
    instance_trading.get_account.return_value = "mock_account"
    assert wrapper.get_account_info() == "mock_account"
    instance_trading.get_account.assert_called_once()
    
    # 2. get_historical_bars
    mock_bars = MagicMock()
    mock_bars.df = pd.DataFrame([{"close": 100.0}])
    instance_historical.get_stock_bars.return_value = mock_bars
    
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    res = wrapper.get_historical_bars(["AAPL"], TimeFrame.Day, start)
    assert not res.empty
    instance_historical.get_stock_bars.assert_called_once()
    
    # 3. get_news_articles
    mock_news_resp = MagicMock()
    mock_news_resp.df = pd.DataFrame([{"headline": "Good news!"}])
    instance_news.get_news.return_value = mock_news_resp
    
    res_news = wrapper.get_news_articles(["AAPL"], start)
    assert not res_news.empty
    instance_news.get_news.assert_called_once()
    
    # 4. get_positions
    instance_trading.get_all_positions.return_value = ["mock_position"]
    assert wrapper.get_positions() == ["mock_position"]
    instance_trading.get_all_positions.assert_called_once()
    
    # 5. submit_order
    instance_trading.submit_order.return_value = "mock_order"
    assert wrapper.submit_order("order_req") == "mock_order"
    instance_trading.submit_order.assert_called_once_with("order_req")
