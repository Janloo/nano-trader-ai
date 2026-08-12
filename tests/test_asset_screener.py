"""
tests/test_asset_screener.py

TDD tests for the DynamicAssetScreener component.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

class TestDynamicAssetScreener:
    
    @patch("data.asset_screener.TradingClient")
    @patch("data.asset_screener.CryptoHistoricalDataClient")
    def test_get_top_volatile_assets(self, mock_hist_client_class, mock_trading_client_class):
        from data.asset_screener import DynamicAssetScreener
        
        # 1. Mock TradingClient to return active, tradable crypto assets
        mock_trading_client = MagicMock()
        mock_asset_1 = MagicMock(symbol="BTC/USD", tradable=True, fractionable=True, status="active")
        mock_asset_2 = MagicMock(symbol="ETH/USD", tradable=True, fractionable=True, status="active")
        mock_asset_3 = MagicMock(symbol="SHIB/USD", tradable=True, fractionable=True, status="active")
        mock_asset_4 = MagicMock(symbol="DOGE/USD", tradable=True, fractionable=True, status="active")
        # Inactive asset
        mock_asset_5 = MagicMock(symbol="XRP/USD", tradable=False, fractionable=True, status="inactive")
        
        mock_trading_client.get_all_assets.return_value = [mock_asset_1, mock_asset_2, mock_asset_3, mock_asset_4, mock_asset_5]
        mock_trading_client_class.return_value = mock_trading_client
        
        # 2. Mock Historical Client to return snapshot data
        mock_hist_client = MagicMock()
        mock_snapshots = {
            "BTC/USD": MagicMock(daily_bar=MagicMock(volume=1000, high=65000, low=63000)), # vol: 64M, range: 3.1%
            "ETH/USD": MagicMock(daily_bar=MagicMock(volume=20000, high=3500, low=3200)), # vol: 67M, range: 9.3%
            "SHIB/USD": MagicMock(daily_bar=MagicMock(volume=100000000000, high=0.00002, low=0.000018)), # vol: 2M USD, range: 11.1%
            "DOGE/USD": MagicMock(daily_bar=MagicMock(volume=50000000, high=0.15, low=0.14)) # vol: 7.5M USD, range: 7.1%
        }
        mock_hist_client.get_crypto_snapshots.return_value = mock_snapshots
        mock_hist_client_class.return_value = mock_hist_client
        
        # 3. Test the Screener
        screener = DynamicAssetScreener(api_key="TEST", api_secret="TEST")
        top_assets = screener.get_top_volatile_assets(limit=2)
        
        # Expected:
        # SHIB has 11.1% range
        # ETH has 9.3% range
        # DOGE has 7.1%
        # BTC has 3.1%
        # XRP is inactive and should be ignored
        
        assert len(top_assets) == 2
        assert top_assets[0] == "SHIBUSD"
        assert top_assets[1] == "ETHUSD"
