"""
strategy/bollinger_squeeze.py

Bollinger Band Squeeze Breakout Strategy — Detects periods of compressed
volatility (squeeze) and generates signals when the price breaks out.

A Bollinger Squeeze occurs when the bandwidth (upper - lower) / middle
contracts below a threshold, indicating the market is coiling for a big move.
When the squeeze releases and price breaks a band, a directional signal fires.
"""
import logging
import math
from collections import deque
from typing import Dict, Optional

logger = logging.getLogger("nano-trader-ai")


class BollingerSqueezeDetector:
    """
    Detects Bollinger Band squeeze and breakout patterns.

    Squeeze: bandwidth < squeeze_threshold (e.g. < 0.5% for crypto)
    Breakout UP:   Price closes above upper band after squeeze → BUY
    Breakout DOWN: Price closes below lower band after squeeze → SHORT signal
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0,
                 squeeze_threshold_pct: float = 0.5, min_squeeze_bars: int = 3):
        """
        :param period: SMA period for Bollinger Bands
        :param std_dev: Standard deviation multiplier
        :param squeeze_threshold_pct: Bandwidth % below which squeeze is active
        :param min_squeeze_bars: Minimum consecutive bars in squeeze before breakout is valid
        """
        self.period = period
        self.std_dev = std_dev
        self.squeeze_threshold_pct = squeeze_threshold_pct / 100.0
        self.min_squeeze_bars = min_squeeze_bars
        self._prices: Dict[str, deque] = {}
        self._squeeze_count: Dict[str, int] = {}
        self._was_in_squeeze: Dict[str, bool] = {}

    def update(self, symbol: str, close: float):
        """Records a new close price."""
        if symbol not in self._prices:
            self._prices[symbol] = deque(maxlen=self.period + 10)
            self._squeeze_count[symbol] = 0
            self._was_in_squeeze[symbol] = False
        self._prices[symbol].append(close)

    def _calc_bands(self, symbol: str) -> Optional[dict]:
        """Calculates Bollinger Bands (SMA, Upper, Lower, Bandwidth)."""
        prices = self._prices.get(symbol)
        if prices is None or len(prices) < self.period:
            return None

        # Use last 'period' prices
        data = list(prices)[-self.period:]
        sma = sum(data) / len(data)

        if sma <= 0:
            return None

        # Standard deviation
        variance = sum((x - sma) ** 2 for x in data) / len(data)
        std = math.sqrt(variance)

        upper = sma + (self.std_dev * std)
        lower = sma - (self.std_dev * std)
        bandwidth = (upper - lower) / sma  # Normalized bandwidth

        return {
            "sma": sma,
            "upper": upper,
            "lower": lower,
            "bandwidth": bandwidth,
            "std": std,
        }

    def check_signal(self, symbol: str, current_price: float) -> Optional[str]:
        """
        Checks for squeeze breakout signals.

        Returns:
        - "SQUEEZE_BUY": Price broke above upper band after squeeze → momentum buy
        - "SQUEEZE_SHORT": Price broke below lower band after squeeze → short signal
        - None: No signal (still in squeeze or no pattern)
        """
        bands = self._calc_bands(symbol)
        if bands is None:
            return None

        bandwidth = bands["bandwidth"]
        upper = bands["upper"]
        lower = bands["lower"]
        sma = bands["sma"]

        # Check if currently in squeeze
        is_squeezed = bandwidth < self.squeeze_threshold_pct

        if is_squeezed:
            self._squeeze_count[symbol] = self._squeeze_count.get(symbol, 0) + 1
            self._was_in_squeeze[symbol] = True
            return None  # Still in squeeze, no signal yet

        # Check for breakout AFTER squeeze
        was_squeezed = self._was_in_squeeze.get(symbol, False)
        squeeze_bars = self._squeeze_count.get(symbol, 0)

        if was_squeezed and squeeze_bars >= self.min_squeeze_bars:
            # Squeeze just released — check direction
            self._was_in_squeeze[symbol] = False
            self._squeeze_count[symbol] = 0

            if current_price > upper:
                logger.info(
                    f"[BOLLINGER] {symbol} SQUEEZE BREAKOUT UP! "
                    f"Price: ${current_price:.2f} > Upper: ${upper:.2f} "
                    f"(Squeeze lasted {squeeze_bars} bars, BW: {bandwidth*100:.3f}%)"
                )
                return "SQUEEZE_BUY"

            elif current_price < lower:
                logger.info(
                    f"[BOLLINGER] {symbol} SQUEEZE BREAKOUT DOWN! "
                    f"Price: ${current_price:.2f} < Lower: ${lower:.2f} "
                    f"(Squeeze lasted {squeeze_bars} bars, BW: {bandwidth*100:.3f}%)"
                )
                return "SQUEEZE_SHORT"

        # Reset squeeze counter if not in squeeze and no breakout
        if not is_squeezed:
            self._squeeze_count[symbol] = 0
            self._was_in_squeeze[symbol] = False

        return None

    def get_bandwidth(self, symbol: str) -> Optional[float]:
        """Returns current bandwidth percentage, or None if insufficient data."""
        bands = self._calc_bands(symbol)
        if bands is None:
            return None
        return bands["bandwidth"] * 100.0
