import unittest
from strategy.bollinger_squeeze import BollingerSqueezeDetector

class TestBollingerSqueezeDetector(unittest.TestCase):
    
    def test_no_signal_initially(self):
        detector = BollingerSqueezeDetector(period=5, std_dev=2.0, squeeze_threshold_pct=1.0, min_squeeze_bars=2)
        # Not enough data for period=5
        for price in [100, 101, 99, 100]:
            detector.update("SOLUSD", price)
            self.assertIsNone(detector.check_signal("SOLUSD", price))

    def test_squeeze_and_breakout_up(self):
        detector = BollingerSqueezeDetector(period=20, std_dev=2.0, squeeze_threshold_pct=2.0, min_squeeze_bars=2)
        
        # 1. Feed tightly compressed prices to trigger a squeeze
        prices = [100.0, 100.1, 99.9, 100.0] * 6  # 24 values
        
        for p in prices:
            detector.update("SOLUSD", p)
            # The signal should be None because we are in squeeze
            signal = detector.check_signal("SOLUSD", p)
            self.assertIsNone(signal)
            
        self.assertTrue(detector._was_in_squeeze.get("SOLUSD", False))
        
        # 2. Breakout UP
        # We need a price that is way above the upper band.
        # Current SMA is ~100. std is ~0.1. Upper band is ~100.2
        breakout_price = 110.0
        detector.update("SOLUSD", breakout_price)
        bands = detector._calc_bands("SOLUSD")
        print("UPPER BANDS:", bands)
        signal = detector.check_signal("SOLUSD", breakout_price)
        
        self.assertEqual(signal, "SQUEEZE_BUY")

    def test_squeeze_and_breakout_down(self):
        detector = BollingerSqueezeDetector(period=20, std_dev=2.0, squeeze_threshold_pct=2.0, min_squeeze_bars=2)
        
        # Feed tightly compressed prices
        prices = [50.0, 50.1, 49.9, 50.0] * 6 # 24 values
        for p in prices:
            detector.update("SOLUSD", p)
            detector.check_signal("SOLUSD", p)
            
        self.assertTrue(detector._was_in_squeeze.get("SOLUSD", False))
        
        # Breakout DOWN
        breakout_price = 30.0
        detector.update("SOLUSD", breakout_price)
        signal = detector.check_signal("SOLUSD", breakout_price)
        
        self.assertEqual(signal, "SQUEEZE_SHORT")

if __name__ == '__main__':
    unittest.main()
