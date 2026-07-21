import logging
from typing import Dict

logger = logging.getLogger("nano-trader-ai")

class OrderBookAnalyzer:
    """
    Analyzes Level 2 Order Book data to detect severe imbalances
    and predict incoming market drops or pumps.
    """
    
    def __init__(self, imbalance_threshold: float = 3.0):
        """
        :param imbalance_threshold: The ratio required to trigger a wall alert.
        Default is 3.0 (e.g. 3x more sell volume than buy volume).
        """
        self.imbalance_threshold = imbalance_threshold
        # Store the latest book per symbol
        self.books: Dict[str, dict] = {}
        
    def update(self, symbol: str, bids: list, asks: list):
        """
        Update the local order book snapshot.
        bids and asks are expected to be lists of objects or dicts with 'p' (price) and 's' (size).
        Alpaca Orderbook data typically comes as arrays of OrderbookQuote objects.
        """
        self.books[symbol] = {
            "bids": bids,
            "asks": asks
        }

    def check_imbalance(self, symbol: str, top_n: int = 10) -> str:
        """
        Returns 'BEARISH_WALL' if ask volume is overwhelmingly higher than bid volume.
        Returns 'BULLISH_WALL' if bid volume is overwhelmingly higher than ask volume.
        Returns 'NEUTRAL' otherwise.
        """
        if symbol not in self.books:
            return "NEUTRAL"
            
        book = self.books[symbol]
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        
        if not bids or not asks:
            return "NEUTRAL"
            
        # Helper to extract size whether it's an object attribute or dict key
        def get_size(level):
            if hasattr(level, 's'):
                return float(level.s)
            elif isinstance(level, dict) and 's' in level:
                return float(level['s'])
            elif hasattr(level, 'size'):
                return float(level.size)
            elif isinstance(level, dict) and 'size' in level:
                return float(level['size'])
            return 0.0
            
        bid_vol = sum(get_size(b) for b in bids[:top_n])
        ask_vol = sum(get_size(a) for a in asks[:top_n])
        
        if bid_vol == 0 and ask_vol > 0:
            return "BEARISH_WALL"
        if ask_vol == 0 and bid_vol > 0:
            return "BULLISH_WALL"
        if bid_vol == 0 and ask_vol == 0:
            return "NEUTRAL"
            
        ask_to_bid_ratio = ask_vol / bid_vol
        bid_to_ask_ratio = bid_vol / ask_vol
        
        if ask_to_bid_ratio >= self.imbalance_threshold:
            logger.info(f"[L2 ORDERBOOK] {symbol} SELL WALL DETECTED! AskVol: {ask_vol:.2f} vs BidVol: {bid_vol:.2f} (Ratio: {ask_to_bid_ratio:.1f})")
            return "BEARISH_WALL"
            
        if bid_to_ask_ratio >= self.imbalance_threshold:
            logger.info(f"[L2 ORDERBOOK] {symbol} BUY WALL DETECTED! BidVol: {bid_vol:.2f} vs AskVol: {ask_vol:.2f} (Ratio: {bid_to_ask_ratio:.1f})")
            return "BULLISH_WALL"
            
        return "NEUTRAL"
