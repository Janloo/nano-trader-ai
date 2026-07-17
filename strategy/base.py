from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    @abstractmethod
    def analyze(self, symbol: str, bars_df: pd.DataFrame, news_df: pd.DataFrame) -> float:
        """
        Analyzes the market data and news for a specific symbol.
        
        Parameters:
        - symbol (str): The ticker symbol to analyze.
        - bars_df (pd.DataFrame): Historical price bars.
        - news_df (pd.DataFrame): Recent news articles.
        
        Returns:
        - float: A score between -1.0 (strong sell) and 1.0 (strong buy).
                 0.0 represents a neutral/hold position.
        """
        pass
