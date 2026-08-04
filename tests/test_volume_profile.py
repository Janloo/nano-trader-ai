import unittest
from typing import Dict, List
from collections import defaultdict

# We haven't implemented this yet, it will fail (TDD)
try:
    from risk_management.volume_profile import VolumeProfileManager
except ImportError:
    # Dummy class so the test runs and fails on logic instead of import error if we want
    class VolumeProfileManager:
        def __init__(self, bucket_size=50.0):
            pass
        def add_volume(self, symbol: str, price: float, volume: float):
            pass
        def get_poc(self, symbol: str) -> float:
            return 0.0
        def get_hvn(self, symbol: str, threshold_pct: float = 0.8) -> List[float]:
            return []

class TestVolumeProfileManager(unittest.TestCase):

    def test_add_volume_and_poc(self):
        vpm = VolumeProfileManager(bucket_size=50.0)
        
        # Add volume at different prices
        # Bucket 60000: ranges from 60000 to 60050
        vpm.add_volume("BTCUSD", 60010.5, 2.0)
        vpm.add_volume("BTCUSD", 60049.9, 3.0) # Total 5.0 in 60000 bucket
        
        # Bucket 60050
        vpm.add_volume("BTCUSD", 60050.0, 10.0) # Total 10.0 in 60050 bucket
        
        # Bucket 60100
        vpm.add_volume("BTCUSD", 60120.0, 1.0) # Total 1.0 in 60100 bucket
        
        # The Point of Control (POC) should be the bucket with the most volume (60050)
        poc = vpm.get_poc("BTCUSD")
        self.assertEqual(poc, 60050.0)

    def test_hvn_detection(self):
        vpm = VolumeProfileManager(bucket_size=50.0)
        
        vpm.add_volume("BTCUSD", 60000, 100.0) # HVN
        vpm.add_volume("BTCUSD", 60050, 10.0)  # LVN
        vpm.add_volume("BTCUSD", 60100, 85.0)  # HVN
        vpm.add_volume("BTCUSD", 60150, 5.0)   # LVN
        
        # If max volume is 100, and threshold is 0.8 (80% of max),
        # HVNs should be 60000 (100) and 60100 (85)
        hvns = vpm.get_hvn("BTCUSD", threshold_pct=0.8)
        self.assertEqual(len(hvns), 2)
        self.assertIn(60000.0, hvns)
        self.assertIn(60100.0, hvns)

    def test_empty_profile(self):
        vpm = VolumeProfileManager(bucket_size=50.0)
        self.assertIsNone(vpm.get_poc("ETHUSD"))
        self.assertEqual(vpm.get_hvn("ETHUSD"), [])

if __name__ == "__main__":
    unittest.main()
