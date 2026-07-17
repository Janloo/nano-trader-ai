from datetime import datetime
from typing import List, Optional
import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.models import TradeAccount, Position, Order
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import StockBarsRequest, NewsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY, APCA_API_BASE_URL, logger

class AlpacaClientWrapper:
    def __init__(self):
        is_paper = "paper" in APCA_API_BASE_URL.lower()
        logger.info(f"Initializing Alpaca Clients. Base URL: {APCA_API_BASE_URL} (Paper: {is_paper})")
        
        self.trading_client = TradingClient(
            api_key=APCA_API_KEY_ID,
            secret_key=APCA_API_SECRET_KEY,
            paper=is_paper,
            url_override=APCA_API_BASE_URL
        )
        
        self.data_client = StockHistoricalDataClient(
            api_key=APCA_API_KEY_ID,
            secret_key=APCA_API_SECRET_KEY
        )
        
        self.crypto_client = CryptoHistoricalDataClient(
            api_key=APCA_API_KEY_ID,
            secret_key=APCA_API_SECRET_KEY
        )
        
        self.news_client = NewsClient(
            api_key=APCA_API_KEY_ID,
            secret_key=APCA_API_SECRET_KEY
        )

    def get_account_info(self) -> TradeAccount:
        """Retrieves user account info."""
        return self.trading_client.get_account()

    def get_historical_bars(self, symbols: List[str], timeframe: TimeFrame, start: datetime, end: Optional[datetime] = None) -> pd.DataFrame:
        """Fetches historical bars for given symbols (stocks or crypto) and returns a pandas DataFrame."""
        symbol = symbols[0]
        # Route to crypto if ticker contains BTC/ETH/SOL/DOGE or contains a slash
        is_crypto = any(c in symbol.upper() for c in ["BTC", "ETH", "SOL", "DOGE"]) or "/" in symbol
        
        if is_crypto:
            mapped_symbols = [s.replace("BTCUSD", "BTC/USD") for s in symbols]
            request_params = CryptoBarsRequest(
                symbol_or_symbols=mapped_symbols,
                timeframe=timeframe,
                start=start,
                end=end
            )
            bars = self.crypto_client.get_crypto_bars(request_params)
            df = bars.df.copy()
            if isinstance(df.index, pd.MultiIndex):
                # Map the index value back from "BTC/USD" to "BTCUSD" if it was originally requested as "BTCUSD"
                df = df.rename(index={"BTC/USD": "BTCUSD"}, level=0)
            return df
        else:
            request_params = StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=timeframe,
                start=start,
                end=end,
                feed=DataFeed.IEX
            )
            bars = self.data_client.get_stock_bars(request_params)
            return bars.df

    def get_news_articles(self, symbols: List[str], start: datetime, end: Optional[datetime] = None, limit: int = 20) -> pd.DataFrame:
        """Fetches recent news articles for given symbols and returns a pandas DataFrame."""
        # Convert list of symbols to a comma-separated string if it is a list
        symbols_str = ",".join(symbols) if isinstance(symbols, list) else symbols
        request_params = NewsRequest(
            symbols=symbols_str,
            start=start,
            end=end,
            limit=limit,
            include_content=False
        )
        news = self.news_client.get_news(request_params)
        return news.df

    def get_positions(self) -> List[Position]:
        """Gets all current open positions."""
        return self.trading_client.get_all_positions()

    def submit_order(self, order_request: MarketOrderRequest) -> Order:
        """Submits an order to Alpaca."""
        return self.trading_client.submit_order(order_request)
