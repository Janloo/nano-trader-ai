import unittest
from realtime_executor import IndicatorManager

class TestIndicatorManagerVolume(unittest.TestCase):
    def test_volume_sma(self):
        mgr = IndicatorManager(period=20)
        
        # Feed 20 bars with volume 100
        for i in range(20):
            mgr.update("SOLUSD", 10.0, 9.0, 9.5, volume=100.0)
            
        sma = mgr.get_volume_sma("SOLUSD")
        self.assertEqual(sma, 100.0)
        
        # Feed one bar with volume 300
        mgr.update("SOLUSD", 10.0, 9.0, 9.5, volume=300.0)
        sma2 = mgr.get_volume_sma("SOLUSD")
        
        # The oldest 100 is replaced by 300.
        # sum = 19 * 100 + 300 = 2200. Average = 2200 / 20 = 110.0
        self.assertAlmostEqual(sma2, 110.0)

    def test_volume_spike(self):
        mgr = IndicatorManager(period=20)
        
        # Feed 20 bars with volume 100
        for i in range(20):
            mgr.update("SOLUSD", 10.0, 9.0, 9.5, volume=100.0)
            
        # Is current volume (100) a spike > 2x ? No.
        self.assertFalse(mgr.is_volume_spike("SOLUSD", current_volume=100.0, threshold=2.0))
        
        # Is current volume 250 a spike > 2x ? Yes. (250 > 2 * 100)
        self.assertTrue(mgr.is_volume_spike("SOLUSD", current_volume=250.0, threshold=2.0))
        
        # Is current volume 150 a spike > 2x ? No.
        self.assertFalse(mgr.is_volume_spike("SOLUSD", current_volume=150.0, threshold=2.0))

if __name__ == '__main__':
    unittest.main()
