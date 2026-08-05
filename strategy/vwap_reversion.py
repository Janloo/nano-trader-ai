"""
strategy/vwap_reversion.py

VWAP Reversion Strategy — Generates BUY signals when price drops below
the Volume Weighted Average Price (VWAP) by a configurable ATR-scaled threshold.

VWAP is the benchmark price that institutional traders use. When price is below
VWAP, the asset is trading at a "discount" relative to the average price paid
by the market. This strategy buys the discount and exits when price reverts
back above VWAP.
"""
import logging
from collections import deque
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger("nano-trader-ai")


class VWAPReversionStrategy:
    """
    Calculates a rolling VWAP from incoming price/volume data and generates
    mean-reversion signals.

    Entry: price < VWAP - (entry_atr_mult * ATR) AND RSI < rsi_threshold
    Exit:  price > VWAP + (exit_atr_mult * ATR)
    """

    def __init__(self, max_bars: int = 200, entry_atr_mult: float = 0.5,
                 exit_atr_mult: float = 0.3, rsi_threshold: float = 45.0):
        """
        :param max_bars: Maximum number of bars to keep for VWAP calculation
        :param entry_atr_mult: ATR multiplier for entry threshold below VWAP
        :param exit_atr_mult: ATR multiplier for exit threshold above VWAP
        :param rsi_threshold: RSI must be below this for a BUY signal
        """
        self.max_bars = max_bars
        self.entry_atr_mult = entry_atr_mult
        self.exit_atr_mult = exit_atr_mult
        self.rsi_threshold = rsi_threshold
        # {symbol: deque of (price, volume)}
        self._data: Dict[str, deque] = {}
        # Track if we have an active VWAP position signal
        self._active_signals: Dict[str, bool] = {}

    def update(self, symbol: str, price: float, volume: float):
        """Records a new price/volume data point."""
        if symbol not in self._data:
            self._data[symbol] = deque(maxlen=self.max_bars)
        self._data[symbol].append((price, volume))

    def get_vwap(self, symbol: str) -> Optional[float]:
        """Returns the current VWAP for the symbol, or None if insufficient data."""
        data = self._data.get(symbol)
        if data is None or len(data) < 5:
            return None

        total_pv = sum(p * v for p, v in data)
        total_v = sum(v for _, v in data)

        if total_v <= 0:
            # Fallback to Simple Moving Average if volume is exactly 0
            return sum(p for p, _ in data) / len(data)

        return total_pv / total_v

    def check_signal(self, symbol: str, current_price: float,
                     atr: Optional[float] = None,
                     rsi: Optional[float] = None) -> Optional[str]:
        """
        Checks for VWAP reversion signals.

        Returns:
        - "VWAP_BUY": Price is significantly below VWAP → mean reversion entry
        - "VWAP_EXIT": Price has reverted above VWAP → take profit
        - None: No signal
        """
        vwap = self.get_vwap(symbol)
        if vwap is None or vwap <= 0:
            return None

        # Calculate distance from VWAP
        vwap_distance_pct = (current_price - vwap) / vwap

        # Use ATR for dynamic threshold, or fallback to fixed 0.3%
        if atr is not None and atr > 0 and current_price > 0:
            atr_pct = atr / current_price
            entry_threshold = -(self.entry_atr_mult * atr_pct)
            exit_threshold = self.exit_atr_mult * atr_pct
        else:
            entry_threshold = -0.003  # -0.3% below VWAP
            exit_threshold = 0.002    # +0.2% above VWAP

        is_active = self._active_signals.get(symbol, False)

        # EXIT: Price reverted above VWAP + threshold
        if is_active and vwap_distance_pct >= exit_threshold:
            logger.info(
                f"[VWAP] {symbol} EXIT signal — Price: ${current_price:.2f}, "
                f"VWAP: ${vwap:.2f}, Distance: {vwap_distance_pct*100:.3f}% "
                f"(Exit threshold: {exit_threshold*100:.3f}%)"
            )
            self._active_signals[symbol] = False
            return "VWAP_EXIT"

        # ENTRY: Price below VWAP - threshold
        if not is_active and vwap_distance_pct <= entry_threshold:
            # RSI confirmation if available
            if rsi is not None and rsi >= self.rsi_threshold:
                logger.info(
                    f"[VWAP] {symbol} BUY blocked — RSI {rsi:.1f} >= {self.rsi_threshold} (not oversold enough)"
                )
                return None

            logger.info(
                f"[VWAP] {symbol} BUY signal — Price: ${current_price:.2f}, "
                f"VWAP: ${vwap:.2f}, Distance: {vwap_distance_pct*100:.3f}% "
                f"(Entry threshold: {entry_threshold*100:.3f}%)"
            )
            self._active_signals[symbol] = True
            return "VWAP_BUY"

        return None

    def is_below_vwap(self, symbol: str, current_price: float) -> bool:
        """Simple check: is the current price below the VWAP?"""
        vwap = self.get_vwap(symbol)
        if vwap is None:
            return False
        return current_price < vwap
