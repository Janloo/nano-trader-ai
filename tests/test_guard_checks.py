"""
tests/test_guard_checks.py

Unit tests for execution/guard_checks.py — TDD.
Covers cooldowns, panic states, and global API error states.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock


def _make_ts(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


class TestGuardChecksSymbolCooldown:
    def test_symbol_not_in_cooldown_if_never_traded(self):
        from execution.guard_checks import GuardManager
        guard = GuardManager()
        assert guard.is_symbol_in_cooldown("BTCUSD", cooldown_seconds=300) is False

    def test_symbol_in_cooldown_just_after_trade(self):
        from execution.guard_checks import GuardManager
        guard = GuardManager()
        guard.register_trade("BTCUSD")
        assert guard.is_symbol_in_cooldown("BTCUSD", cooldown_seconds=300) is True

    def test_symbol_not_in_cooldown_after_time_passes(self):
        from execution.guard_checks import GuardManager
        guard = GuardManager()
        # Mock time from 6 minutes ago
        guard._last_order_time["BTCUSD"] = _make_ts(-360)
        assert guard.is_symbol_in_cooldown("BTCUSD", cooldown_seconds=300) is False


class TestGuardChecksGlobalPanic:
    def test_no_panic_initially(self):
        from execution.guard_checks import GuardManager
        guard = GuardManager()
        assert guard.is_panic_active() is False

    def test_panic_activates_if_enough_assets_dip(self):
        from execution.guard_checks import GuardManager
        guard = GuardManager()
        # Mock trailing states: 3 assets dipping below -1.2%
        states = {
            "BTCUSD": {"imm_dip_pct": -1.5},
            "ETHUSD": {"imm_dip_pct": -1.3},
            "SOLUSD": {"imm_dip_pct": -2.0},
            "ADAUSD": {"imm_dip_pct": -0.5},
        }
        
        is_panic = guard.check_and_update_panic_state(
            trailing_states=states,
            threshold_pct=-1.20,
            required_count=3,
            cooldown_min=5
        )
        assert is_panic is True
        assert guard.is_panic_active() is True

    def test_panic_does_not_activate_if_not_enough_assets_dip(self):
        from execution.guard_checks import GuardManager
        guard = GuardManager()
        states = {
            "BTCUSD": {"imm_dip_pct": -1.5},
            "ETHUSD": {"imm_dip_pct": -1.3},
            "SOLUSD": {"imm_dip_pct": -0.5},  # Only 2 below -1.2%
        }
        is_panic = guard.check_and_update_panic_state(
            trailing_states=states,
            threshold_pct=-1.20,
            required_count=3,
            cooldown_min=5
        )
        assert is_panic is False
        assert guard.is_panic_active() is False

    def test_panic_expires_after_cooldown(self):
        from execution.guard_checks import GuardManager
        import time
        guard = GuardManager()
        # Manually set panic expiration in the past
        guard._panic_cooldown_until = time.time() - 10
        assert guard.is_panic_active() is False


class TestGuardChecksGlobalErrorCooldown:
    def test_no_error_cooldown_initially(self):
        from execution.guard_checks import GuardManager
        guard = GuardManager()
        assert guard.is_global_error_cooldown_active() is False

    def test_error_cooldown_activates_and_expires(self):
        from execution.guard_checks import GuardManager
        import time
        guard = GuardManager()
        guard.trigger_global_error_cooldown(minutes=60)
        assert guard.is_global_error_cooldown_active() is True
        
        # Expire it
        guard._global_error_cooldown_until = time.time() - 10
        assert guard.is_global_error_cooldown_active() is False
