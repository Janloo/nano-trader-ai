import pytest
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime, timezone, timedelta
import pandas as pd
import json
import os
from execution.tracker import update_feedback_loop_metrics, fetch_price_at_time

def test_fetch_price_at_time():
    """Verify that fetch_price_at_time correctly returns the closest bar's close price."""
    mock_client = MagicMock()
    target_time = datetime(2026, 7, 17, 15, 30, tzinfo=timezone.utc)
    
    # Mock return DataFrame
    mock_df = pd.DataFrame({
        "close": [150.00]
    }, index=[target_time])
    mock_client.get_historical_bars.return_value = mock_df
    
    price = fetch_price_at_time(mock_client, "SPY", target_time)
    assert price == 150.00
    mock_client.get_historical_bars.assert_called_once()

def test_update_feedback_loop_metrics():
    """Verify that update_feedback_loop_metrics calculates correct returns for +1h and +4h times."""
    mock_client = MagicMock()
    
    # Target prices
    price_1h = 105.00  # +5% return
    price_4h = 90.00   # -10% return
    
    def mock_fetch(symbols, timeframe, start, end):
        # Return different mock dfs depending on time
        if start.hour == 16:  # +1h target time (15:30 + 1h = 16:30)
            return pd.DataFrame({"close": [price_1h]}, index=[start + timedelta(minutes=5)])
        else:  # +4h target time (19:30)
            return pd.DataFrame({"close": [price_4h]}, index=[start + timedelta(minutes=5)])
            
    mock_client.get_historical_bars.side_effect = mock_fetch
    
    # Mock data logs path
    test_logs = [
        {
            "id": 1,
            "timestamp": "2026-07-17T15:30:00.000000+00:00",
            "asset": "SPY",
            "price": 100.00,
            "raw_news_titles": '["Test"]',
            "ai_raw_output": "{}",
            "execution_success": 1,
            "error_details": "",
            "return_1h": None,
            "return_4h": None
        }
    ]

    with patch("data.db.get_ai_analytics_pending_feedback", return_value=test_logs), \
         patch("data.db.update_ai_analytics_feedback") as mock_update:

         # Force datetime now to be in the future (older than 4 hours from trade time)
         with patch("execution.tracker.datetime") as mock_dt:
             mock_dt.now.return_value = datetime(2026, 7, 17, 21, 0, tzinfo=timezone.utc)
             mock_dt.fromisoformat = datetime.fromisoformat

             update_feedback_loop_metrics(mock_client)
             
             assert mock_update.called
             args, _ = mock_update.call_args
             # args = (analytics_id, ret_1h, ret_4h)
             assert args[0] == 1
             assert args[1] == pytest.approx(5.0)
             assert args[2] == pytest.approx(-10.0)
