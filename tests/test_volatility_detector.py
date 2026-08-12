"""
tests/test_volatility_detector.py

Unit tests for strategy/volatility_detector.py — TDD: written BEFORE the implementation.
"""
import pytest
from datetime import datetime, timezone, timedelta


def _make_ts(offset_seconds: int = 0) -> datetime:
    """Helper: UTC timestamp offset by N seconds."""
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


class TestVolatilityDetectorBasic:
    """Basic update/window behavior."""

    def test_returns_none_tuple_on_single_price_point(self):
        from strategy.volatility_detector import VolatilityDetector
        vd = VolatilityDetector(window_seconds=300, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        imm, trail, spike = vd.update("BTCUSD", 65000.0, _make_ts())
        assert imm is None
        assert trail is None
        assert spike is None

    def test_returns_none_tuple_on_two_stable_prices(self):
        from strategy.volatility_detector import VolatilityDetector
        vd = VolatilityDetector(window_seconds=300, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        vd.update("BTCUSD", 65000.0, _make_ts(0))
        imm, trail, spike = vd.update("BTCUSD", 65000.0, _make_ts(30))
        assert imm is None
        assert trail is None
        assert spike is None

    def test_prunes_entries_outside_window(self):
        from strategy.volatility_detector import VolatilityDetector
        vd = VolatilityDetector(window_seconds=60, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        # Add a price far in the past (well outside 60s window)
        old_ts = _make_ts(-200)
        vd.update("BTCUSD", 70000.0, old_ts)
        # Add a recent price — the window should only contain this one
        new_ts = _make_ts(0)
        imm, trail, spike = vd.update("BTCUSD", 65000.0, new_ts)
        # Only one point in the window: should not trigger
        assert imm is None


class TestVolatilityDetectorDip:
    """DIP detection (immediate and trailing)."""

    def test_immediate_dip_detected_below_threshold(self):
        from strategy.volatility_detector import VolatilityDetector
        vd = VolatilityDetector(window_seconds=300, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        # Establish a high price
        vd.update("BTCUSD", 65000.0, _make_ts(0))
        # Drop by 0.3% (below -0.20% threshold)
        new_price = 65000.0 * (1.0 - 0.003)
        imm, trail, spike = vd.update("BTCUSD", new_price, _make_ts(30))
        assert imm is not None
        assert imm < -0.20

    def test_no_immediate_dip_above_threshold(self):
        from strategy.volatility_detector import VolatilityDetector
        vd = VolatilityDetector(window_seconds=300, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        vd.update("BTCUSD", 65000.0, _make_ts(0))
        # Drop by only 0.1% (above -0.20% threshold)
        new_price = 65000.0 * (1.0 - 0.001)
        imm, trail, spike = vd.update("BTCUSD", new_price, _make_ts(30))
        assert imm is None

    def test_trailing_buy_fires_on_rebound_from_bottom(self):
        from strategy.volatility_detector import VolatilityDetector
        vd = VolatilityDetector(window_seconds=300, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        # Step 1: establish high
        vd.update("BTCUSD", 65000.0, _make_ts(0))
        # Step 2: drop below threshold (trailing activates)
        bottom = 65000.0 * (1.0 - 0.005)  # -0.5%
        vd.update("BTCUSD", bottom, _make_ts(30))
        # Step 3: price rebounds +0.06% from bottom (above 0.05% rebound threshold)
        rebound = bottom * 1.0006
        imm, trail, spike = vd.update("BTCUSD", rebound, _make_ts(60))
        assert trail is not None
        assert trail < 0  # Should be a negative dip pct

    def test_trailing_state_reset_after_firing(self):
        from strategy.volatility_detector import VolatilityDetector
        vd = VolatilityDetector(window_seconds=300, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        vd.update("BTCUSD", 65000.0, _make_ts(0))
        bottom = 65000.0 * (1.0 - 0.005)
        vd.update("BTCUSD", bottom, _make_ts(30))
        rebound = bottom * 1.0006
        imm, trail, spike = vd.update("BTCUSD", rebound, _make_ts(60))
        assert trail is not None
        # After firing, state should be reset
        assert vd._trailing_state["BTCUSD"]["active"] is False
        assert vd._trailing_state["BTCUSD"]["lowest"] == float('inf')

    def test_dynamic_dip_threshold_overrides_default(self):
        from strategy.volatility_detector import VolatilityDetector
        # Default threshold: -0.20%
        vd = VolatilityDetector(window_seconds=300, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        vd.update("BTCUSD", 65000.0, _make_ts(0))
        # Drop by -0.25% (would trigger with default, but we pass a tighter -0.50% override)
        new_price = 65000.0 * (1.0 - 0.0025)
        imm, trail, spike = vd.update("BTCUSD", new_price, _make_ts(30), dynamic_dip_pct=-0.50)
        # With -0.50% threshold, a -0.25% drop should NOT be an immediate dip
        assert imm is None


class TestVolatilityDetectorSpike:
    """SPIKE detection."""

    def test_spike_detected_above_threshold(self):
        from strategy.volatility_detector import VolatilityDetector
        vd = VolatilityDetector(window_seconds=300, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        # Establish a low price
        vd.update("BTCUSD", 65000.0, _make_ts(0))
        # Spike up by 0.3%
        spike_price = 65000.0 * (1.0 + 0.003)
        imm, trail, spike = vd.update("BTCUSD", spike_price, _make_ts(30))
        assert spike is not None
        assert spike > 0.20

    def test_no_spike_below_threshold(self):
        from strategy.volatility_detector import VolatilityDetector
        vd = VolatilityDetector(window_seconds=300, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        vd.update("BTCUSD", 65000.0, _make_ts(0))
        # Rise by only 0.1%
        spike_price = 65000.0 * (1.0 + 0.001)
        imm, trail, spike = vd.update("BTCUSD", spike_price, _make_ts(30))
        assert spike is None

    def test_independent_tracking_per_symbol(self):
        from strategy.volatility_detector import VolatilityDetector
        vd = VolatilityDetector(window_seconds=300, dip_threshold_pct=-0.20, spike_threshold_pct=0.20)
        # BTC goes up
        vd.update("BTCUSD", 65000.0, _make_ts(0))
        vd.update("ETHUSD", 3000.0, _make_ts(0))
        imm_btc, _, spike_btc = vd.update("BTCUSD", 65000.0 * 1.003, _make_ts(30))
        imm_eth, _, spike_eth = vd.update("ETHUSD", 3000.0, _make_ts(30))
        assert spike_btc is not None
        assert spike_eth is None
