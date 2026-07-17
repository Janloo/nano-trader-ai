import pandas as pd
from strategy.base import BaseStrategy
from config.settings import logger

class ConditionalDcaStrategy(BaseStrategy):
    def __init__(self, period: int = 20):
        self.period = period

    def analyze(self, symbol: str, bars_df: pd.DataFrame, news_df: pd.DataFrame) -> float:
        """
        Analyzes close prices of the last 20 days.
        Returns 1.0 (BUY signal) if current price is BELOW the 20-day SMA, otherwise 0.0.
        """
        if bars_df is None or bars_df.empty:
            logger.warning(f"No price data available for {symbol}")
            return 0.0

        try:
            # Check if MultiIndex is used (symbol, timestamp)
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

        # Sort chronologically to make sure we calculate SMA over historical order
        df = df.sort_index()

        if len(df) < self.period:
            logger.warning(
                f"Insufficient price history for {symbol} to calculate SMA-{self.period}. "
                f"Required: {self.period}, Available: {len(df)}"
            )
            return 0.0

        close_prices = df['close']
        
        # Calculate Simple Moving Average (SMA)
        sma_20 = close_prices.rolling(window=self.period).mean().iloc[-1]
        current_price = close_prices.iloc[-1]
        
        logger.info(f"[{symbol} DCA Analysis] Current Price: ${current_price:,.2f} | SMA-20: ${sma_20:,.2f}")
        
        if current_price < sma_20:
            logger.info(f"[{symbol} DCA Analysis] Price is BELOW SMA-20 (Discounted). Signal: BUY (1.0)")
            return 1.0
        else:
            logger.info(f"[{symbol} DCA Analysis] Price is ABOVE or EQUAL to SMA-20. Signal: HOLD (0.0)")
            return 0.0
