import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from risk_management.orderbook_analyzer import OrderBookAnalyzer

class TestOrderBookAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = OrderBookAnalyzer(imbalance_threshold=3.0)

    def test_neutral_imbalance(self):
        bids = [{'p': 100, 's': 10}, {'p': 99, 's': 10}]
        asks = [{'p': 101, 's': 10}, {'p': 102, 's': 10}]
        
        self.analyzer.update("AAPL", bids, asks)
        result = self.analyzer.check_imbalance("AAPL")
        self.assertEqual(result, "NEUTRAL")

    def test_bearish_wall(self):
        bids = [{'p': 100, 's': 5}, {'p': 99, 's': 5}] # total 10
        asks = [{'p': 101, 's': 20}, {'p': 102, 's': 20}] # total 40
        
        self.analyzer.update("AAPL", bids, asks)
        result = self.analyzer.check_imbalance("AAPL")
        # 40 / 10 = 4.0 >= 3.0 threshold -> BEARISH_WALL
        self.assertEqual(result, "BEARISH_WALL")

    def test_bullish_wall(self):
        # Testing with object-like structure just to be sure (if passed as mock)
        class MockLevel:
            def __init__(self, s):
                self.s = s
                
        bids = [MockLevel(30), MockLevel(20)] # total 50
        asks = [MockLevel(5), MockLevel(5)] # total 10
        
        self.analyzer.update("BTCUSD", bids, asks)
        result = self.analyzer.check_imbalance("BTCUSD")
        # 50 / 10 = 5.0 >= 3.0 threshold -> BULLISH_WALL
        self.assertEqual(result, "BULLISH_WALL")
        
    def test_missing_data(self):
        result = self.analyzer.check_imbalance("UNKNOWN")
        self.assertEqual(result, "NEUTRAL")

if __name__ == '__main__':
    unittest.main()
