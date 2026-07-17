from strategy.base import BaseStrategy
from strategy.technical import TechnicalStrategy
from strategy.ai_sentiment import AISentimentStrategy
import pandas as pd
from config.settings import logger

class CombinedStrategy(BaseStrategy):
    def __init__(self, technical_weight: float = 0.7, sentiment_weight: float = 0.3):
        self.tech_strategy = TechnicalStrategy()
        self.sentiment_strategy = AISentimentStrategy()
        self.technical_weight = technical_weight
        self.sentiment_weight = sentiment_weight

    def analyze(self, symbol: str, bars_df: pd.DataFrame, news_df: pd.DataFrame) -> float:
        """Combines Technical and AI Sentiment signals into a single score."""
        tech_signal = self.tech_strategy.analyze(symbol, bars_df, news_df)
        
        if news_df is None or news_df.empty:
            logger.info(f"[{symbol} Combined] No news available; using 100% technical signal: {tech_signal:.2f}")
            return tech_signal
            
        sentiment_signal = self.sentiment_strategy.analyze(symbol, bars_df, news_df)
        
        # Combined weighted signal
        combined_signal = (tech_signal * self.technical_weight) + (sentiment_signal * self.sentiment_weight)
        logger.info(
            f"[{symbol} Combined] Tech Signal: {tech_signal:.2f} (weight: {self.technical_weight}) | "
            f"Sentiment Signal: {sentiment_signal:.2f} (weight: {self.sentiment_weight}) -> "
            f"Final Combined Signal: {combined_signal:.2f}"
        )
        return float(combined_signal)
