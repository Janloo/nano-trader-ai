import pandas as pd
import numpy as np
from strategy.base import BaseStrategy
from config.settings import logger

class TechnicalStrategy(BaseStrategy):
    def __init__(self, fast_period: int = 50, slow_period: int = 200, rsi_period: int = 14):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.rsi_period = rsi_period

    def calculate_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """Calculates Relative Strength Index (RSI)."""
        if len(series) < period + 1:
            return pd.Series(index=series.index, data=np.nan)
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-9)  # Add epsilon to prevent division by zero
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def analyze(self, symbol: str, bars_df: pd.DataFrame, news_df: pd.DataFrame) -> float:
        """Analyzes historical bars and returns a technical indicator signal."""
        if bars_df is None or bars_df.empty:
            logger.warning(f"No price data available for {symbol}")
            return 0.0

        try:
            # Check if MultiIndex is used (symbol, timestamp) which is standard in alpaca-py
            if isinstance(bars_df.index, pd.MultiIndex):
                if symbol in bars_df.index.levels[0]:
                    df = bars_df.xs(symbol, level=0).copy()
                else:
                    df = bars_df.copy()
            else:
                df = bars_df.copy()
        except Exception as e:
            logger.error(f"Error index-slicing bars DataFrame for {symbol}: {e}")
            df = bars_df.copy()

        if len(df) < self.rsi_period + 1:
            logger.warning(
                f"Insufficient price history for {symbol} to calculate indicators. "
                f"Required: >{self.rsi_period}, Available: {len(df)}"
            )
            return 0.0

        # Sort chronologically to calculate indicators correctly
        df = df.sort_index()
        close_prices = df['close']

        # Adjust windows if there is less data than configured periods
        fast_window = min(self.fast_period, len(df))
        slow_window = min(self.slow_period, len(df))

        sma_fast = close_prices.rolling(window=fast_window).mean().iloc[-1]
        sma_slow = close_prices.rolling(window=slow_window).mean().iloc[-1]

        rsi_series = self.calculate_rsi(close_prices, self.rsi_period)
        rsi = rsi_series.iloc[-1]

        # Calculate signals
        sma_signal = 0.0
        if fast_window >= 5 and slow_window >= 10:
            if sma_fast > sma_slow:
                sma_signal = 0.5   # Bullish crossover
            elif sma_fast < sma_slow:
                sma_signal = -0.5  # Bearish crossover

        rsi_signal = 0.0
        if not np.isnan(rsi):
            if rsi < 30:
                rsi_signal = 0.5   # Oversold (BUY)
            elif rsi > 70:
                rsi_signal = -0.5  # Overbought (SELL)

        total_signal = sma_signal + rsi_signal
        logger.info(
            f"[{symbol} Tech] Close: {close_prices.iloc[-1]:.2f} | "
            f"SMA({fast_window}): {sma_fast:.2f} | SMA({slow_window}): {sma_slow:.2f} | "
            f"RSI: {rsi:.2f} -> Signal: {total_signal:.2f}"
        )
        return float(total_signal)
