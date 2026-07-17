import pandas as pd
from strategy.base import BaseStrategy
from config.settings import logger

class AISentimentStrategy(BaseStrategy):
    def __init__(self):
        # Bullish and bearish lexicon lists
        self.positive_keywords = {
            "buy", "bullish", "growth", "profit", "surged", "upbeat", "upgrade", 
            "beats", "higher", "record", "gain", "positive", "expansion", "rally", 
            "outperform", "success", "optimistic", "strong", "advancing", "surge",
            "bull", "win", "improved", "beat"
        }
        self.negative_keywords = {
            "sell", "bearish", "loss", "decline", "downbeat", "downgrade", "misses", 
            "lower", "drop", "fall", "negative", "contraction", "slump", "plunge", 
            "underperform", "failure", "pessimistic", "weak", "declining", "crash",
            "bear", "lose", "worsened", "miss"
        }

    def _score_text(self, text: str) -> float:
        """Helper to calculate word-frequency sentiment score for a string of text."""
        if not text or not isinstance(text, str):
            return 0.0
        # Clean text and split to words
        clean_text = text.lower().replace(".", "").replace(",", "").replace("!", "").replace("?", "")
        words = clean_text.split()
        
        pos_count = sum(1 for word in words if word in self.positive_keywords)
        neg_count = sum(1 for word in words if word in self.negative_keywords)
        
        total = pos_count + neg_count
        if total == 0:
            return 0.0
        return (pos_count - neg_count) / total

    def analyze(self, symbol: str, bars_df: pd.DataFrame, news_df: pd.DataFrame) -> float:
        """Scans the headlines and summaries of the news dataframe and returns average sentiment."""
        if news_df is None or news_df.empty:
            logger.info(f"[{symbol} Sentiment] No news data available -> Neutral (0.0)")
            return 0.0

        scores = []
        for _, row in news_df.iterrows():
            headline = getattr(row, "headline", "")
            summary = getattr(row, "summary", "")
            
            # Weighted scoring: headline carries 2x the weight of summary
            headline_score = self._score_text(headline)
            summary_score = self._score_text(summary)
            
            if headline_score != 0.0 or summary_score != 0.0:
                combined = (headline_score * 2.0 + summary_score) / 3.0
                scores.append(combined)

        if not scores:
            logger.info(f"[{symbol} Sentiment] News processed but no keywords matched -> Neutral (0.0)")
            return 0.0

        avg_score = sum(scores) / len(scores)
        logger.info(f"[{symbol} Sentiment] Analyzed {len(scores)} articles -> Average Score: {avg_score:.2f}")
        return float(avg_score)
