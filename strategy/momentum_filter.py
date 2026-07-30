"""
strategy/momentum_filter.py

Momentum Acceleration Filter — Measures the Rate of Change (ROC) of price
to determine whether a DIP is decelerating (good entry) or accelerating (wait).

This acts as a pre-filter before order execution: only buy when the selling
pressure is visibly exhausting.
"""
import logging
from collections import deque
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger("nano-trader-ai")


class MomentumAccelerationFilter:
    """
    Analyzes the Rate of Change (ROC) of prices to determine momentum state.

    ROC = (price - price_N_periods_ago) / price_N_periods_ago * 100

    States:
    - DECELERATING: Negative momentum is weakening (selling pressure exhausting) → Good to BUY
    - ACCELERATING: Negative momentum is intensifying (crash deepening) → WAIT
    - NEUTRAL: No significant momentum pattern
    """

    def __init__(self, fast_period: int = 5, slow_period: int = 10, max_buffer: int = 30):
        """
        :param fast_period: Short ROC lookback (5 bars = 5 minutes)
        :param slow_period: Long ROC lookback (10 bars = 10 minutes)
        :param max_buffer: Maximum number of prices to keep in buffer
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.max_buffer = max_buffer
        self._prices: Dict[str, deque] = {}

    def update(self, symbol: str, price: float):
        """Records a new price point for the symbol."""
        if symbol not in self._prices:
            self._prices[symbol] = deque(maxlen=self.max_buffer)
        self._prices[symbol].append(price)

    def _calc_roc(self, prices: deque, period: int) -> Optional[float]:
        """Calculates Rate of Change over the given period."""
        if len(prices) < period + 1:
            return None
        old_price = prices[-(period + 1)]
        current_price = prices[-1]
        if old_price <= 0:
            return None
        return ((current_price - old_price) / old_price) * 100.0

    def check(self, symbol: str) -> str:
        """
        Analyzes momentum state for a symbol.

        Returns:
        - "DECELERATING": Selling pressure is weakening → good entry
        - "ACCELERATING": Selling pressure is intensifying → wait
        - "NEUTRAL": Insufficient data or no clear pattern
        """
        prices = self._prices.get(symbol)
        if prices is None or len(prices) < self.slow_period + 2:
            return "NEUTRAL"

        # Calculate current and previous ROC for both timeframes
        fast_roc = self._calc_roc(prices, self.fast_period)
        slow_roc = self._calc_roc(prices, self.slow_period)

        if fast_roc is None or slow_roc is None:
            return "NEUTRAL"

        # Calculate ROC of ROC (acceleration) by comparing to 1 bar ago
        # Build a 1-bar-shifted version
        prev_prices = deque(list(prices)[:-1], maxlen=self.max_buffer)
        prev_fast_roc = self._calc_roc(prev_prices, self.fast_period)

        if prev_fast_roc is None:
            return "NEUTRAL"

        # Acceleration = change in ROC
        acceleration = fast_roc - prev_fast_roc

        # Both ROCs are negative (we're in a dip)
        if fast_roc < 0 and slow_roc < 0:
            if acceleration > 0:
                # Negative momentum is weakening (ROC becoming less negative)
                logger.info(
                    f"[MOMENTUM] {symbol} DECELERATING — "
                    f"FastROC: {fast_roc:.3f}%, SlowROC: {slow_roc:.3f}%, "
                    f"Accel: +{acceleration:.3f}%"
                )
                return "DECELERATING"
            elif acceleration < -0.02:
                # Negative momentum is intensifying
                logger.info(
                    f"[MOMENTUM] {symbol} ACCELERATING DOWN — "
                    f"FastROC: {fast_roc:.3f}%, SlowROC: {slow_roc:.3f}%, "
                    f"Accel: {acceleration:.3f}%"
                )
                return "ACCELERATING"

        return "NEUTRAL"

    def should_allow_buy(self, symbol: str) -> bool:
        """
        Convenience method: returns True if a BUY should be allowed.
        Returns True for DECELERATING or NEUTRAL (permissive).
        Returns False only for ACCELERATING (active block).
        """
        state = self.check(symbol)
        if state == "ACCELERATING":
            logger.info(f"[MOMENTUM FILTER] Blocking BUY on {symbol}: momentum still accelerating downward.")
            return False
        return True
