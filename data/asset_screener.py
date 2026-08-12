"""
data/asset_screener.py

Component for dynamic asset screening on Alpaca.
Finds the most volatile tradable crypto assets.
"""
import os
import logging
from typing import List
from alpaca.trading.client import TradingClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoSnapshotRequest

logger = logging.getLogger("nano-trader-ai")

class DynamicAssetScreener:
    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY")
        self.api_secret = api_secret or os.environ.get("ALPACA_SECRET_KEY")
        
        self.trading_client = TradingClient(self.api_key, self.api_secret, paper=True)
        self.hist_client = CryptoHistoricalDataClient(self.api_key, self.api_secret)
        
    def get_top_volatile_assets(self, limit: int = 3, min_volume_usd: float = 100000.0) -> List[str]:
        """
        Queries Alpaca for active, fractionable crypto assets and sorts them by
        daily volatility (high-low range).
        Returns a list of symbols in the format 'BTCUSD' (without slash).
        """
        logger.info("Scanning for most volatile crypto assets...")
        
        try:
            # 1. Get all active and tradable crypto assets
            assets = self.trading_client.get_all_assets()
            valid_symbols = []
            
            for asset in assets:
                # We want active, tradable crypto assets
                # Some are classed as 'crypto'
                if asset.status == "active" and asset.tradable and asset.fractionable:
                    # In Alpaca, crypto pairs have a '/' like 'BTC/USD'
                    if asset.symbol.endswith("/USD"):
                        valid_symbols.append(asset.symbol)
            
            if not valid_symbols:
                logger.warning("No valid crypto assets found in Alpaca.")
                return []
                
            # 2. Get snapshots for all valid symbols to calculate daily range
            request = CryptoSnapshotRequest(symbol_or_symbols=valid_symbols)
            snapshots = self.hist_client.get_crypto_snapshots(request)
            
            scored_assets = []
            for symbol, snapshot in snapshots.items():
                if snapshot.daily_bar:
                    high = snapshot.daily_bar.high
                    low = snapshot.daily_bar.low
                    volume = snapshot.daily_bar.volume
                    
                    if high and low and high > low:
                        # Range percentage
                        range_pct = (high - low) / low * 100.0
                        
                        # Estimate USD volume roughly (using high as proxy for price)
                        est_vol_usd = volume * high
                        
                        if est_vol_usd >= min_volume_usd:
                            scored_assets.append({
                                "symbol": symbol.replace("/", ""), # Convert 'BTC/USD' to 'BTCUSD'
                                "range": range_pct,
                                "vol_usd": est_vol_usd
                            })
                            
            # 3. Sort by range (volatility) descending
            scored_assets.sort(key=lambda x: x["range"], reverse=True)
            
            top_symbols = [a["symbol"] for a in scored_assets[:limit]]
            logger.info(f"Top volatile assets selected: {top_symbols}")
            return top_symbols
            
        except Exception as e:
            logger.error(f"Error during asset screening: {e}")
            return []
