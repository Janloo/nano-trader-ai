"""
strategy/volatility_detector.py

Rolling-window DIP and SPIKE detector.
Extracted from realtime_executor.py as a standalone module with single responsibility.

Detects two types of events:
- Immediate DIP: current price dropped >= dip_threshold_pct% from window high
- Trailing DIP: price dipped below threshold, then rebounded >= 0.05% from the bottom
- SPIKE: current price rose >= spike_threshold_pct% from window low
"""
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

logger = logging.getLogger("nano-trader-ai")

# Defaults — can be overridden per-instance or per-update call
_DEFAULT_WINDOW_SECONDS = 300
_DEFAULT_DIP_THRESHOLD_PCT = -0.20
_DEFAULT_SPIKE_THRESHOLD_PCT = 0.20


class VolatilityDetector:
    """
    Tracks prices over a rolling window and detects DIP and SPIKE events.

    Returns (immediate_dip_pct, trailing_dip_pct, spike_pct) from update().
    Each value is None if the corresponding event was not detected.
    """

    def __init__(self,
                 window_seconds: int = _DEFAULT_WINDOW_SECONDS,
                 dip_threshold_pct: float = _DEFAULT_DIP_THRESHOLD_PCT,
                 spike_threshold_pct: float = _DEFAULT_SPIKE_THRESHOLD_PCT):
        self.window_seconds = window_seconds
        self.dip_threshold_pct = dip_threshold_pct
        self.spike_threshold_pct = spike_threshold_pct
        # {symbol: deque of (timestamp_utc, price)}
        self._prices: Dict[str, deque] = {}
        # {symbol: trailing state dict}
        self._trailing_state: Dict[str, dict] = {}

    def _ensure_symbol(self, symbol: str) -> None:
        """Initialises per-symbol state on first use."""
        if symbol not in self._prices:
            self._prices[symbol] = deque()
        if symbol not in self._trailing_state:
            self._trailing_state[symbol] = {
                "active": False,
                "lowest": float('inf'),
                "dip_pct": 0.0,
                "window_high": 0.0,
                "imm_dip_pct": 0.0,
            }

    def _prune_window(self, symbol: str, timestamp: datetime) -> None:
        """Removes entries older than window_seconds."""
        window = self._prices[symbol]
        cutoff = timestamp - timedelta(seconds=self.window_seconds)
        while window and window[0][0] < cutoff:
            window.popleft()

    def _check_immediate_dip(self, price: float, window_high: float,
                             active_dip_threshold: float) -> Optional[float]:
        """Returns the percentage drop from window high if below threshold, else None."""
        if window_high <= 0:
            return None
        pct_change = ((price - window_high) / window_high) * 100.0
        return pct_change if pct_change <= active_dip_threshold else None

    def _update_trailing_state(self, symbol: str, price: float,
                                pct_change_high: float,
                                active_dip_threshold: float) -> Optional[float]:
        """
        Manages the trailing DIP state machine.
        Returns the recorded dip_pct when a trailing buy fires, else None.
        """
        t_state = self._trailing_state[symbol]

        if pct_change_high <= active_dip_threshold:
            if not t_state["active"]:
                t_state["active"] = True
                t_state["lowest"] = price
                t_state["dip_pct"] = pct_change_high
            else:
                if price < t_state["lowest"]:
                    t_state["lowest"] = price
                    t_state["dip_pct"] = pct_change_high

        if t_state["active"]:
            # Abort if price has fully recovered above threshold
            if pct_change_high > active_dip_threshold and price > (t_state["lowest"] * 1.002):
                t_state["active"] = False
                return None

            # Fire on rebound >= 0.05% from the absolute bottom
            rebound_price = t_state["lowest"] * (1.0 + (0.05 / 100.0))
            if price >= rebound_price and price > t_state["lowest"]:
                fired_dip = t_state["dip_pct"]
                t_state["active"] = False
                t_state["lowest"] = float('inf')
                return fired_dip

        return None

    def _check_spike(self, price: float, window_low: float,
                     active_spike_threshold: float) -> Optional[float]:
        """Returns the percentage rise from window low if above threshold, else None."""
        if window_low <= 0:
            return None
        pct_change = ((price - window_low) / window_low) * 100.0
        return pct_change if pct_change >= active_spike_threshold else None

    def update(self, symbol: str, price: float, timestamp: datetime,
               dynamic_dip_pct: float = None,
               dynamic_spike_pct: float = None) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Records a new price point and evaluates DIP/SPIKE conditions.

        Args:
            symbol: Asset symbol (e.g. 'BTCUSD')
            price: Current closing price
            timestamp: UTC timestamp of this bar
            dynamic_dip_pct: Override dip threshold for this call (optional)
            dynamic_spike_pct: Override spike threshold for this call (optional)

        Returns:
            (immediate_dip_pct, trailing_dip_pct, spike_pct)
            Each is None if the corresponding event was not detected.
        """
        active_dip_threshold = dynamic_dip_pct if dynamic_dip_pct is not None else self.dip_threshold_pct
        active_spike_threshold = dynamic_spike_pct if dynamic_spike_pct is not None else self.spike_threshold_pct

        self._ensure_symbol(symbol)
        window = self._prices[symbol]
        window.append((timestamp, price))
        self._prune_window(symbol, timestamp)

        if len(window) < 2:
            return None, None, None

        window_high = max(p for _, p in window)
        window_low = min(p for _, p in window)
        t_state = self._trailing_state[symbol]

        # Track immediate tick-to-tick change
        t_state["imm_dip_pct"] = ((price - window[-2][1]) / window[-2][1]) * 100.0

        # Compute pct change from window high
        pct_change_high = ((price - window_high) / window_high) * 100.0

        immediate_dip_pct = self._check_immediate_dip(price, window_high, active_dip_threshold)
        trailing_dip_pct = self._update_trailing_state(symbol, price, pct_change_high, active_dip_threshold)
        spike_pct = self._check_spike(price, window_low, active_spike_threshold)

        return immediate_dip_pct, trailing_dip_pct, spike_pct
