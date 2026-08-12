"""
execution/guard_checks.py

Manages cooldowns, panic states, and global API safety guards.
Extracted from realtime_executor.py for single responsibility.
"""
import time
import logging
from typing import Dict
from datetime import datetime, timezone

logger = logging.getLogger("nano-trader-ai")


class GuardManager:
    """
    Centralized safety checks and cooldown management.
    """
    def __init__(self):
        self._last_order_time: Dict[str, datetime] = {}
        self._panic_cooldown_until: float = 0.0
        self._global_error_cooldown_until: float = 0.0

    def is_symbol_in_cooldown(self, symbol: str, cooldown_seconds: float = 60.0) -> bool:
        """Returns True if the symbol has been traded within the cooldown period."""
        last_trade = self._last_order_time.get(symbol)
        if not last_trade:
            return False

        now = datetime.now(timezone.utc)
        age_seconds = (now - last_trade).total_seconds()
        return age_seconds < cooldown_seconds

    def register_trade(self, symbol: str) -> None:
        """Records the time a trade occurred for a symbol."""
        self._last_order_time[symbol] = datetime.now(timezone.utc)

    def is_panic_active(self) -> bool:
        """Returns True if the market is currently in a panic state."""
        return time.time() < self._panic_cooldown_until

    def check_and_update_panic_state(self, trailing_states: Dict[str, dict],
                                     threshold_pct: float = -1.20,
                                     required_count: int = 3,
                                     cooldown_min: int = 3) -> bool:
        """
        Evaluates current asset drops. If enough assets drop below the threshold,
        activates the panic cooldown.
        Returns True if panic is active.
        """
        if self.is_panic_active():
            return True

        panic_count = 0
        dipping_assets = []

        for sym, state in trailing_states.items():
            if sym.endswith("USD") and state.get("imm_dip_pct", 0) <= threshold_pct:
                panic_count += 1
                dipping_assets.append(sym)

        if panic_count >= required_count:
            logger.error(f"[GUARDIAN] Market Panic Detected! Assets dipping: {', '.join(dipping_assets)} below {threshold_pct}%. Suspending BUYs for {cooldown_min} minutes.")
            self._panic_cooldown_until = time.time() + (cooldown_min * 60)
            return True

        return False

    def is_global_error_cooldown_active(self) -> bool:
        """Returns True if trading is paused globally due to severe API errors (e.g. Insufficient Balance)."""
        return time.time() < self._global_error_cooldown_until

    def trigger_global_error_cooldown(self, minutes: int = 60) -> None:
        """Activates a global trading pause for the specified minutes."""
        self._global_error_cooldown_until = time.time() + (minutes * 60)
