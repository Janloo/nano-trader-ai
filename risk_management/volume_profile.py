import math
from typing import Dict, List, Optional
from collections import defaultdict

class VolumeProfileManager:
    """
    Tracks trading volume at different price buckets to construct a Volume Profile.
    This allows us to identify the Point of Control (POC) and High Volume Nodes (HVN).
    """

    def __init__(self, bucket_size: float = 50.0):
        self.bucket_size = bucket_size
        # Map: symbol -> {bucket_price: volume}
        self._profiles: Dict[str, Dict[float, float]] = defaultdict(lambda: defaultdict(float))

    def _get_bucket(self, price: float) -> float:
        """
        Rounds the price down to the nearest bucket size.
        E.g. price 60049 with bucket 50 becomes 60000.
        price 60050 with bucket 50 becomes 60050.
        """
        return math.floor(price / self.bucket_size) * self.bucket_size

    def add_volume(self, symbol: str, price: float, volume: float):
        """
        Add volume to the corresponding price bucket for a symbol.
        """
        bucket = self._get_bucket(price)
        self._profiles[symbol][bucket] += volume

    def get_poc(self, symbol: str) -> Optional[float]:
        """
        Returns the Point of Control (bucket with the highest volume) for a symbol.
        """
        if symbol not in self._profiles or not self._profiles[symbol]:
            return None
            
        profile = self._profiles[symbol]
        return max(profile, key=profile.get)

    def get_hvn(self, symbol: str, threshold_pct: float = 0.8) -> List[float]:
        """
        Returns a list of High Volume Nodes (HVN) for a symbol.
        An HVN is any bucket whose volume is >= threshold_pct of the POC's volume.
        """
        poc = self.get_poc(symbol)
        if poc is None:
            return []
            
        profile = self._profiles[symbol]
        max_vol = profile[poc]
        
        if max_vol == 0:
            return []
            
        hvns = []
        for bucket, vol in profile.items():
            if vol >= max_vol * threshold_pct:
                hvns.append(bucket)
                
        return sorted(hvns)
