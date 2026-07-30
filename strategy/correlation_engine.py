"""
strategy/correlation_engine.py

Cross-Asset Correlation Engine — Computes rolling correlations between all
monitored assets and generates anticipatory lead-lag signals.

When a "leader" asset moves first, correlated "follower" assets are expected
to follow with a delay of 1-5 minutes. This engine detects the leader's move
and fires signals on the followers before they move.
"""
import logging
import math
from collections import deque
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger("nano-trader-ai")


class CrossAssetCorrelationEngine:
    """
    Maintains a rolling price buffer for all assets, computes a correlation
    matrix, and generates lead-lag signals.

    Usage:
        engine = CrossAssetCorrelationEngine()
        # On each bar:
        engine.update(symbol, price)
        # When a significant move is detected on a symbol:
        signals = engine.get_lead_lag_signals("BTCUSD", -0.30)
        # Returns: [{"symbol": "LTCUSD", "correlation": 0.87, "direction": "BUY", "confidence": 0.87}]
    """

    def __init__(self, window: int = 30, min_correlation: float = 0.65,
                 min_move_pct: float = 0.15, cooldown_bars: int = 5):
        """
        :param window: Rolling window size for correlation (30 = 30 bars)
        :param min_correlation: Minimum correlation to consider lead-lag valid
        :param min_move_pct: Minimum % move on leader to trigger follower signal
        :param cooldown_bars: Minimum bars between signals on same follower
        """
        self.window = window
        self.min_correlation = min_correlation
        self.min_move_pct = min_move_pct
        self.cooldown_bars = cooldown_bars
        self._prices: Dict[str, deque] = {}
        self._correlation_cache: Dict[Tuple[str, str], float] = {}
        self._cache_update_counter: int = 0
        self._cache_refresh_interval: int = 5  # Refresh every 5 updates
        self._last_signal_bar: Dict[str, int] = {}
        self._bar_counter: int = 0

    def update(self, symbol: str, price: float):
        """Records a new price for the symbol."""
        if symbol not in self._prices:
            self._prices[symbol] = deque(maxlen=self.window + 5)
        self._prices[symbol].append(price)
        self._bar_counter += 1

        # Periodically refresh correlation cache
        self._cache_update_counter += 1
        if self._cache_update_counter >= self._cache_refresh_interval:
            self._refresh_correlations()
            self._cache_update_counter = 0

    def _calc_returns(self, prices: deque) -> List[float]:
        """Converts prices to percentage returns."""
        data = list(prices)
        if len(data) < 2:
            return []
        returns = []
        for i in range(1, len(data)):
            if data[i - 1] > 0:
                returns.append((data[i] - data[i - 1]) / data[i - 1])
            else:
                returns.append(0.0)
        return returns

    def _pearson_correlation(self, x: List[float], y: List[float]) -> Optional[float]:
        """Calculates Pearson correlation coefficient between two return series."""
        n = min(len(x), len(y))
        if n < 10:  # Need at least 10 data points for meaningful correlation
            return None

        x = x[-n:]
        y = y[-n:]

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        var_x = sum((xi - mean_x) ** 2 for xi in x)
        var_y = sum((yi - mean_y) ** 2 for yi in y)

        denom = math.sqrt(var_x * var_y)
        if denom < 1e-10:
            return None

        return cov / denom

    def _refresh_correlations(self):
        """Recalculates the correlation matrix for all symbol pairs."""
        symbols = list(self._prices.keys())
        returns_cache = {}

        for sym in symbols:
            returns_cache[sym] = self._calc_returns(self._prices[sym])

        for i, sym_a in enumerate(symbols):
            for sym_b in symbols[i + 1:]:
                ret_a = returns_cache.get(sym_a, [])
                ret_b = returns_cache.get(sym_b, [])
                corr = self._pearson_correlation(ret_a, ret_b)
                if corr is not None:
                    self._correlation_cache[(sym_a, sym_b)] = corr
                    self._correlation_cache[(sym_b, sym_a)] = corr

    def get_correlation(self, sym_a: str, sym_b: str) -> Optional[float]:
        """Returns the rolling correlation between two symbols."""
        return self._correlation_cache.get((sym_a, sym_b))

    def get_correlation_matrix(self) -> Dict[Tuple[str, str], float]:
        """Returns the full correlation matrix."""
        return dict(self._correlation_cache)

    def get_lead_lag_signals(self, leader_symbol: str,
                             move_pct: float) -> List[dict]:
        """
        When a significant move is detected on the leader symbol,
        check for correlated followers that should follow.

        :param leader_symbol: The symbol that moved first
        :param move_pct: The percentage move (negative for dip, positive for spike)
        :returns: List of signal dicts: [{symbol, correlation, direction, confidence}]
        """
        if abs(move_pct) < self.min_move_pct:
            return []

        signals = []
        all_symbols = list(self._prices.keys())

        for follower in all_symbols:
            if follower == leader_symbol:
                continue

            corr = self.get_correlation(leader_symbol, follower)
            if corr is None:
                continue

            abs_corr = abs(corr)
            if abs_corr < self.min_correlation:
                continue

            # Check cooldown
            last_bar = self._last_signal_bar.get(follower, 0)
            if self._bar_counter - last_bar < self.cooldown_bars:
                continue

            # Determine direction based on correlation sign
            if corr > 0:
                # Positive correlation: follower should move in same direction
                if move_pct < 0:
                    direction = "BUY"  # Leader dipped → follower will dip → buy anticipatory
                else:
                    direction = "SELL"  # Leader spiked → follower will spike
            else:
                # Negative/inverse correlation: follower should move opposite
                if move_pct < 0:
                    direction = "SELL"  # Leader dipped → follower should rise
                else:
                    direction = "BUY"  # Leader spiked → follower should dip

            confidence = abs_corr  # Use correlation as confidence

            signals.append({
                "symbol": follower,
                "correlation": round(corr, 3),
                "direction": direction,
                "confidence": round(confidence, 3),
                "leader": leader_symbol,
                "leader_move_pct": round(move_pct, 3),
            })

            # Set cooldown
            self._last_signal_bar[follower] = self._bar_counter

            logger.info(
                f"[CORRELATION] Lead-Lag signal: {leader_symbol} moved {move_pct:.2f}% "
                f"→ {follower} ({direction}) | Corr: {corr:.3f}, Conf: {confidence:.3f}"
            )

        return signals
