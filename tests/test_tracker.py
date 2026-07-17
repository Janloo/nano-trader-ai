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
            "timestamp": "2026-07-17T15:30:00.000000+00:00",
            "asset": "SPY",
            "price": 100.00,
            "raw_news_titles": ["Test"],
            "ai_raw_output": {},
            "execution_success": True,
            "error_details": "",
            "feedback_loop_metric": {
                "price_at_1h": None,
                "price_at_4h": None,
                "return_1h": None,
                "return_4h": None
            }
        }
    ]
    
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(test_logs))) as mock_file, \
         patch("json.dump") as mock_dump:
         
         # Force datetime now to be in the future (older than 4 hours from trade time)
         with patch("execution.tracker.datetime") as mock_dt:
             mock_dt.now.return_value = datetime(2026, 7, 17, 21, 0, tzinfo=timezone.utc)
             mock_dt.fromisoformat = datetime.fromisoformat
             
             update_feedback_loop_metrics(mock_client)
             
             # Check that json dump was called to update values
             assert mock_dump.called
             args, kwargs = mock_dump.call_args
             written_data = args[0]
             
             feedback = written_data[0]["feedback_loop_metric"]
             assert feedback["price_at_1h"] == 105.00
             assert feedback["return_1h"] == pytest.approx(5.0)
             assert feedback["price_at_4h"] == 90.00
             assert feedback["return_4h"] == pytest.approx(-10.0)
