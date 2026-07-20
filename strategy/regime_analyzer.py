"""
strategy/regime_analyzer.py

Computes the market regime (BULL_TREND, BEAR_TREND, RANGING) using Technical Analysis
on Alpaca Historical Data.
Uses ADX for Trend Strength, and EMA 20/50 for Trend Direction.
"""
import os
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY, logger

class MarketRegimeAnalyzer:
    def __init__(self):
        self.crypto_client = CryptoHistoricalDataClient(APCA_API_KEY_ID, APCA_API_SECRET_KEY)
        self.stock_client = StockHistoricalDataClient(APCA_API_KEY_ID, APCA_API_SECRET_KEY)

    def _calc_ema(self, series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(period).mean()
        return atr

    def _calc_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        up_move = df['high'] - df['high'].shift(1)
        down_move = df['low'].shift(1) - df['low']
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        plus_dm_series = pd.Series(plus_dm, index=df.index)
        minus_dm_series = pd.Series(minus_dm, index=df.index)
        
        atr = self._calc_atr(df, period)
        
        # Calculate +DI and -DI (smoothed)
        plus_di = 100 * (plus_dm_series.ewm(alpha=1/period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm_series.ewm(alpha=1/period, adjust=False).mean() / atr)
        
        # Calculate ADX
        dx = (np.abs(plus_di - minus_di) / np.abs(plus_di + minus_di)) * 100
        adx = dx.ewm(alpha=1/period, adjust=False).mean()
        return adx

    def analyze_asset(self, symbol: str, is_crypto: bool = True) -> dict:
        """
        Fetches the last 100 1-Hour bars and calculates the market regime.
        Returns a dict: {"regime": "BULL_TREND", "adx": 30.5, "ema20_over_ema50": True}
        """
        try:
            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=7) # Enough days to get 100 hourly bars
            
            if is_crypto:
                fetch_symbol = symbol[:3] + "/" + symbol[3:] if ("USD" in symbol and "/" not in symbol) else symbol
                req = CryptoBarsRequest(
                    symbol_or_symbols=[fetch_symbol],
                    timeframe=TimeFrame.Hour,
                    start=start_dt,
                    end=end_dt
                )
                bars = self.crypto_client.get_crypto_bars(req)
                # Ensure the symbol index is consistent with what we requested
                symbol_key = fetch_symbol
            else:
                req = StockBarsRequest(
                    symbol_or_symbols=[symbol],
                    timeframe=TimeFrame.Hour,
                    start=start_dt,
                    end=end_dt,
                    feed=DataFeed.IEX # Using IEX for free tier
                )
                bars = self.stock_client.get_stock_bars(req)
                symbol_key = symbol
                
            if bars.df.empty:
                return {"regime": "UNKNOWN", "adx": 0.0, "reason": "No data"}
            
            # Alpaca bars dataframe has a MultiIndex (symbol, timestamp)
            # Let's extract the dataframe for this symbol
            if isinstance(bars.df.index, pd.MultiIndex):
                df = bars.df.loc[symbol_key].copy()
            else:
                df = bars.df.copy()
                
            if len(df) < 50:
                 return {"regime": "UNKNOWN", "adx": 0.0, "reason": "Not enough data for EMAs"}
            
            # Sort chronologically just in case
            df = df.sort_index()
            
            # Indicators
            df['ema20'] = self._calc_ema(df['close'], 20)
            df['ema50'] = self._calc_ema(df['close'], 50)
            df['adx'] = self._calc_adx(df, 14)
            
            last_bar = df.iloc[-1]
            adx_val = float(last_bar['adx'])
            ema20 = float(last_bar['ema20'])
            ema50 = float(last_bar['ema50'])
            
            if pd.isna(adx_val) or pd.isna(ema20) or pd.isna(ema50):
                 return {"regime": "UNKNOWN", "adx": 0.0, "reason": "NaN indicators"}
                 
            # Regime Classification Rules
            # ADX > 25 indicates a strong trend. ADX < 25 is ranging.
            if adx_val > 25.0:
                if ema20 > ema50:
                    regime = "BULL_TREND"
                else:
                    regime = "BEAR_TREND"
            else:
                regime = "RANGING"
                
            logger.info(f"[Regime] {symbol} => {regime} (ADX: {adx_val:.1f}, EMA20: {ema20:.1f}, EMA50: {ema50:.1f})")
            return {
                "regime": regime,
                "adx": round(adx_val, 2),
                "ema20": round(ema20, 2),
                "ema50": round(ema50, 2),
                "updated_at": end_dt.isoformat()
            }
            
        except Exception as e:
            logger.error(f"[RegimeAnalyzer] Error analyzing {symbol}: {e}")
            return {"regime": "UNKNOWN", "adx": 0.0, "reason": str(e)}

    def save_regimes(self, regimes: dict):
        """Saves the regime analysis to market_regime.json"""
        out_path = os.path.join("data", "state", "market_regime.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(regimes, f, indent=4)
            logger.info(f"[RegimeAnalyzer] Saved regimes to {out_path}")
        except Exception as e:
            logger.error(f"[RegimeAnalyzer] Failed to save regimes: {e}")
