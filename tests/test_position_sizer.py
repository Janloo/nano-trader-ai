"""
tests/test_position_sizer.py

Unit tests for execution/position_sizer.py — TDD rewrite.
Covers ALL sizing paths: base size, global caps, Martingale.
The golden test (test_martingale_is_always_clamped_by_buying_power) would have
caught the bug that caused ~$800 paper trading loss.
"""
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_config(**overrides):
    """Returns a minimal RiskSettings-like object."""
    from config.config_manager import RiskSettings
    defaults = {
        "hft_budget_pct": 0.20,
        "global_max_crypto_pct": 0.50,
        "global_max_stocks_pct": 1.0,
        "global_min_cash_pct": 0.05,
        "crypto_max_grid_layers": 3,
        "max_open_positions_per_asset": 1,
    }
    defaults.update(overrides)
    return RiskSettings(**{k: v for k, v in defaults.items() if hasattr(RiskSettings, k)})


def _make_account(equity: float = 10_000.0, buying_power: float = 10_000.0):
    acc = MagicMock()
    acc.equity = str(equity)
    acc.buying_power = str(buying_power)
    return acc


def _make_position(market_value: float, avg_entry: float, qty: float, asset_class: str = "crypto"):
    p = MagicMock()
    p.market_value = str(market_value)
    p.avg_entry_price = str(avg_entry)
    p.qty = str(qty)
    p.asset_class = asset_class
    return p


# ──────────────────────────────────────────────────────────────────────────────
# calc_base_size
# ──────────────────────────────────────────────────────────────────────────────

class TestCalcBaseSize:
    def test_base_size_is_fraction_of_hft_budget(self):
        from execution.position_sizer import PositionSizer
        config = _make_config(hft_budget_pct=0.20)
        # equity=10000, hft_budget=2000
        size = PositionSizer.calc_base_size(config, total_equity=10_000.0, buying_power=10_000.0)
        assert size == pytest.approx(10_000.0 * 0.20 * 0.01, rel=0.01)  # 1% of HFT budget

    def test_base_size_never_exceeds_buying_power(self):
        from execution.position_sizer import PositionSizer
        config = _make_config(hft_budget_pct=0.20)
        # Buying power is very low
        size = PositionSizer.calc_base_size(config, total_equity=10_000.0, buying_power=5.0)
        assert size == 0.0  # Below $10 minimum → returns 0

    def test_base_size_returns_zero_when_budget_below_10(self):
        from execution.position_sizer import PositionSizer
        # Very small account: equity=100, hft_budget=20, 1%=0.2 → below $10
        config = _make_config(hft_budget_pct=0.20)
        size = PositionSizer.calc_base_size(config, total_equity=100.0, buying_power=100.0)
        assert size == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# apply_global_caps
# ──────────────────────────────────────────────────────────────────────────────

class TestApplyGlobalCaps:
    def test_crypto_cap_blocks_when_limit_reached(self):
        from execution.position_sizer import PositionSizer
        config = _make_config(global_max_crypto_pct=0.50, global_min_cash_pct=0.0)
        # equity=10000 → max_crypto=5000
        # Current crypto value already at cap
        positions = [_make_position(market_value=5000.0, avg_entry=50000.0, qty=0.1, asset_class="crypto")]
        result = PositionSizer.apply_global_caps(
            size_usd=200.0, is_crypto=True, is_short=False,
            positions=positions, config=config,
            total_equity=10_000.0, buying_power=10_000.0
        )
        assert result is None  # Should be blocked

    def test_crypto_cap_clamps_size_when_partially_full(self):
        from execution.position_sizer import PositionSizer
        config = _make_config(global_max_crypto_pct=0.50, global_min_cash_pct=0.0)
        # equity=10000 → max_crypto=5000, current=4900 → available=100
        positions = [_make_position(market_value=4900.0, avg_entry=50000.0, qty=0.1, asset_class="crypto")]
        result = PositionSizer.apply_global_caps(
            size_usd=500.0, is_crypto=True, is_short=False,
            positions=positions, config=config,
            total_equity=10_000.0, buying_power=10_000.0
        )
        assert result == pytest.approx(100.0, abs=1.0)  # Clamped to available

    def test_cash_reserve_blocks_when_buying_power_below_min(self):
        from execution.position_sizer import PositionSizer
        config = _make_config(global_min_cash_pct=0.10, global_max_crypto_pct=1.0)
        # equity=10000, buying_power=500 (< 1000 min cash) → blocked
        result = PositionSizer.apply_global_caps(
            size_usd=200.0, is_crypto=True, is_short=False,
            positions=[], config=config,
            total_equity=10_000.0, buying_power=500.0
        )
        assert result is None

    def test_short_order_bypasses_cash_reserve_check(self):
        from execution.position_sizer import PositionSizer
        config = _make_config(global_min_cash_pct=0.10, global_max_crypto_pct=1.0)
        # Same as above but is_short=True: should NOT block
        result = PositionSizer.apply_global_caps(
            size_usd=200.0, is_crypto=True, is_short=True,
            positions=[], config=config,
            total_equity=10_000.0, buying_power=500.0
        )
        assert result is not None


# ──────────────────────────────────────────────────────────────────────────────
# apply_martingale  ← THE GOLDEN TEST
# ──────────────────────────────────────────────────────────────────────────────

class TestApplyMartingale:
    """
    The golden tests: Martingale sizing MUST be bounded by buying_power.
    These tests would have caught the bug that caused the $800 paper trading loss.
    """

    def test_martingale_is_always_clamped_by_buying_power(self):
        """
        THE GOLDEN TEST.
        If martingale grows size_usd beyond buying_power, the result
        must still be <= buying_power * 0.95, never the full expanded value.
        """
        from execution.position_sizer import PositionSizer
        config = _make_config(global_max_crypto_pct=0.50, crypto_max_grid_layers=5)

        # Scenario: Layer 3 with 1.5x multiplier → base 300 * 1.5^2 = 675
        # But buying_power is only 400 → should be clamped to 400*0.95=380
        open_pos = _make_position(market_value=600.0, avg_entry=65000.0, qty=0.01)
        result_size = PositionSizer.apply_martingale(
            base_size_usd=300.0,
            multiplier=1.5,
            layer=2,  # layer index 2 → 1.5^2 = 2.25x → 675
            buying_power=400.0,
            max_crypto_usd=10_000.0,
            current_crypto_value=600.0,
        )
        # Must not exceed buying_power * 0.95
        assert result_size <= 400.0 * 0.95
        assert result_size > 0  # Should still trade something

    def test_martingale_is_clamped_by_max_crypto_cap(self):
        """Martingale must also respect the global crypto allocation cap."""
        from execution.position_sizer import PositionSizer
        # max_crypto_usd=5000, current=4800 → available=200
        # base_size=200, multiplier=2.0, layer=2 → 200*4=800 > 200
        result_size = PositionSizer.apply_martingale(
            base_size_usd=200.0,
            multiplier=2.0,
            layer=2,
            buying_power=10_000.0,
            max_crypto_usd=5_000.0,
            current_crypto_value=4_800.0,
        )
        assert result_size <= 200.0  # Capped at available crypto headroom

    def test_martingale_no_open_position_returns_base_size(self):
        """With no existing position, Martingale returns base size unchanged."""
        from execution.position_sizer import PositionSizer
        result = PositionSizer.apply_martingale(
            base_size_usd=200.0,
            multiplier=1.5,
            layer=0,  # layer 0 → 1.5^0 = 1.0 → no multiplication
            buying_power=10_000.0,
            max_crypto_usd=5_000.0,
            current_crypto_value=0.0,
        )
        assert result == pytest.approx(200.0, rel=0.01)


# ──────────────────────────────────────────────────────────────────────────────
# apply_preflight
# ──────────────────────────────────────────────────────────────────────────────

class TestApplyPreflight:
    def test_preflight_clamps_to_95pct_buying_power(self):
        from execution.position_sizer import PositionSizer
        # size_usd >= 98% of buying_power → should be clamped to 95%
        result = PositionSizer.apply_preflight(
            size_usd=9900.0, buying_power=10_000.0, is_short=False
        )
        assert result == pytest.approx(10_000.0 * 0.95, abs=1.0)

    def test_preflight_returns_none_below_10usd(self):
        from execution.position_sizer import PositionSizer
        result = PositionSizer.apply_preflight(
            size_usd=5.0, buying_power=10_000.0, is_short=False
        )
        assert result is None

    def test_preflight_does_not_clamp_short_orders(self):
        """Short orders do not consume buying power the same way — no clamping."""
        from execution.position_sizer import PositionSizer
        result = PositionSizer.apply_preflight(
            size_usd=9900.0, buying_power=10_000.0, is_short=True
        )
        # For shorts, we don't apply the buying power clamp
        assert result == pytest.approx(9900.0, rel=0.01)

    def test_preflight_passes_through_valid_size(self):
        from execution.position_sizer import PositionSizer
        result = PositionSizer.apply_preflight(
            size_usd=300.0, buying_power=10_000.0, is_short=False
        )
        assert result == pytest.approx(300.0)


# ──────────────────────────────────────────────────────────────────────────────
# Backward compat: calculate_micro_size (used by existing callers)
# ──────────────────────────────────────────────────────────────────────────────

class TestCalculateMicroSize:
    def test_micro_size_within_hft_budget(self):
        from execution.position_sizer import PositionSizer
        from config.config_manager import RiskSettings
        config = RiskSettings(hft_budget_pct=0.20)
        size = PositionSizer.calculate_micro_size(
            "BTCUSD", config, total_equity=10_000.0, buying_power=10_000.0
        )
        # hft_budget = 10000*0.20 = 2000, size = 2000*0.01 = 20
        assert size == pytest.approx(20.0, rel=0.01)

    def test_micro_size_zero_when_below_minimum(self):
        from execution.position_sizer import PositionSizer
        from config.config_manager import RiskSettings
        config = RiskSettings(hft_budget_pct=0.001)  # tiny budget
        size = PositionSizer.calculate_micro_size(
            "BTCUSD", config, total_equity=100.0, buying_power=100.0
        )
        assert size == 0.0

    def test_micro_size_bounded_by_effective_buying_power(self):
        from execution.position_sizer import PositionSizer
        from config.config_manager import RiskSettings
        # Buying power very low compared to hft budget
        config = RiskSettings(hft_budget_pct=0.50)
        # hft_budget would be 10000*0.5=5000, but buying_power only 100
        # effective_buying_power = min(100, 5000) = 100
        # size = 5000 * 0.01 = 50 > effective_buying_power=100 → actually 50 < 100 → OK
        # Let's make buying_power = 30: size=50 > 30 → returns 0
        size = PositionSizer.calculate_micro_size(
            "BTCUSD", config, total_equity=10_000.0, buying_power=30.0
        )
        assert size == 0.0
