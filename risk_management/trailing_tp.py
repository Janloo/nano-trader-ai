import logging
from typing import Dict, List, Optional
from risk_management.performance_tracker import record_win, record_loss

logger = logging.getLogger("nano-trader-ai")


# Default escalator levels: each level defines activation_pct and close_fraction
# Example: At 0.5% profit, close 25% of position; at 1.0%, close another 25%; etc.
DEFAULT_ESCALATOR_LEVELS = [
    {"activation_pct": 0.005, "close_fraction": 0.25, "label": "L1-LockIn"},
    {"activation_pct": 0.010, "close_fraction": 0.25, "label": "L2-ScaleOut"},
    {"activation_pct": 0.015, "close_fraction": 0.50, "label": "L3-MoonBag"},  # Close remaining 50%
]


class TrailingTakeProfitManager:
    """
    Smart Multi-Level Profit Target Escalator with Trailing Take-Profit.

    Instead of a binary Scale-Out / Close-All, this manager uses configurable
    profit levels that progressively lock in gains:
    - Level 1 (0.5% profit): Close 25% of position (lock in base gains)
    - Level 2 (1.0% profit): Close another 25%
    - Level 3 (1.5%+ profit): Close remaining 50% (moon bag exit)

    All levels are dynamically adjusted based on ATR and market regime.
    """

    def __init__(self, activation_pct: float = 0.005, trailing_pct: float = 0.002,
                 escalator_levels: List[dict] = None):
        self.activation_pct = activation_pct
        self.trailing_pct = trailing_pct
        self.escalator_levels = escalator_levels or DEFAULT_ESCALATOR_LEVELS
        self.peaks: Dict[str, float] = {}
        # Track which escalator level each symbol has reached (0 = none triggered yet)
        self._level_state: Dict[str, int] = {}
        # Legacy compat
        self.scaled_out_symbols: set = set()

    def _get_regime_multiplier(self, symbol: str) -> float:
        """
        Returns a TP widening multiplier based on market regime.
        BULL_TREND: 1.5x (let profits run longer)
        RANGING: 0.7x (take profits earlier)
        BEAR_TREND / UNKNOWN: 1.0x (default)
        """
        try:
            import os, json
            regime_path = os.path.join("data", "state", "market_regime.json")
            if os.path.exists(regime_path):
                with open(regime_path, "r", encoding="utf-8") as f:
                    regimes = json.load(f)
                regime = regimes.get(symbol, {}).get("regime", "UNKNOWN")
                if regime == "BULL_TREND":
                    return 1.5
                elif regime == "RANGING":
                    return 0.7
        except Exception:
            pass
        return 1.0

    def _compute_dynamic_levels(self, symbol: str, atr_pct: float = None) -> List[dict]:
        """
        Computes dynamic escalator levels adjusted by ATR and regime.
        """
        regime_mult = self._get_regime_multiplier(symbol)

        levels = []
        for base_level in self.escalator_levels:
            act_pct = base_level["activation_pct"]

            # ATR adjustment: widen levels based on volatility
            if atr_pct is not None and atr_pct > 0:
                # Each level should be at least (level_index + 1) * ATR
                act_pct = max(act_pct, atr_pct * (len(levels) + 1))

            # Regime adjustment
            act_pct *= regime_mult

            levels.append({
                "activation_pct": act_pct,
                "close_fraction": base_level["close_fraction"],
                "label": base_level.get("label", f"L{len(levels)+1}"),
            })

        return levels

    def update_and_check(self, symbol: str, current_price: float,
                         avg_entry_price: float, is_short: bool = False,
                         atr_pct: float = None) -> Optional[str]:
        """
        Returns "SCALE_OUT", "CLOSE_ALL", or None.

        Multi-level escalator logic:
        - Each level triggers a partial close (SCALE_OUT) with its configured fraction
        - The final level triggers CLOSE_ALL for the remaining position
        - Between levels, standard trailing logic protects gains
        """
        if avg_entry_price <= 0:
            return None

        profit_pct = (current_price - avg_entry_price) / avg_entry_price
        if is_short:
            profit_pct = -profit_pct

        # Compute dynamic levels for this symbol
        levels = self._compute_dynamic_levels(symbol, atr_pct)
        current_level = self._level_state.get(symbol, 0)
        total_levels = len(levels)

        # Check if we've hit the next escalator level
        if current_level < total_levels:
            next_level = levels[current_level]
            target_activation = next_level["activation_pct"]

            if profit_pct >= target_activation:
                is_final_level = (current_level == total_levels - 1)
                close_frac = next_level["close_fraction"]
                label = next_level["label"]

                # Record performance
                if profit_pct > 0:
                    record_win(profit_pct)
                else:
                    record_loss(abs(profit_pct))

                if is_final_level:
                    # Final level: close everything remaining
                    logger.info(
                        f"[TRAILING TP] {symbol} hit {label}! "
                        f"Profit: {profit_pct*100:.2f}% (Target: {target_activation*100:.2f}%). "
                        f"CLOSING ALL remaining position."
                    )
                    # Reset state
                    self._level_state.pop(symbol, None)
                    self.peaks.pop(symbol, None)
                    self.scaled_out_symbols.discard(symbol)
                    return "CLOSE_ALL"
                else:
                    # Intermediate level: partial scale-out
                    logger.info(
                        f"[TRAILING TP] {symbol} hit {label}! "
                        f"Profit: {profit_pct*100:.2f}% (Target: {target_activation*100:.2f}%). "
                        f"Scaling out {close_frac*100:.0f}%."
                    )
                    self._level_state[symbol] = current_level + 1
                    self.scaled_out_symbols.add(symbol)
                    # Update peak for trailing between levels
                    self.peaks[symbol] = current_price
                    return "SCALE_OUT"

        # === Trailing protection between levels ===
        # Once at least Level 1 has triggered, we activate trailing protection
        # to prevent giving back all gains between levels
        if current_level > 0 and current_level < total_levels:
            # Compute trailing threshold
            current_trailing = self.trailing_pct
            if atr_pct is not None and atr_pct > 0:
                current_trailing = max(self.trailing_pct, atr_pct * 0.5)

            # Track peak
            if symbol not in self.peaks:
                self.peaks[symbol] = current_price
            else:
                if not is_short and current_price > self.peaks[symbol]:
                    self.peaks[symbol] = current_price
                elif is_short and current_price < self.peaks[symbol]:
                    self.peaks[symbol] = current_price

            # Check drawdown from peak
            peak = self.peaks[symbol]
            drawdown = (peak - current_price) / peak if not is_short else (current_price - peak) / peak

            if drawdown >= current_trailing:
                # Trailing stop hit between levels — close remaining
                actual_profit_pct = profit_pct - drawdown
                if actual_profit_pct > 0:
                    record_win(actual_profit_pct)
                else:
                    record_loss(abs(actual_profit_pct))

                logger.info(
                    f"[TRAILING TP] {symbol} trailing protection hit between levels! "
                    f"Peak: {peak:.2f}, Drawdown: {drawdown*100:.2f}%. "
                    f"Closing remaining position to protect gains."
                )
                # Reset state
                self._level_state.pop(symbol, None)
                self.peaks.pop(symbol, None)
                self.scaled_out_symbols.discard(symbol)
                return "CLOSE_ALL"

        # === Pre-Level-1 trailing (legacy behavior) ===
        # Before any level triggers, use standard activation/trailing logic
        if current_level == 0:
            current_activation = self.activation_pct
            current_trailing = self.trailing_pct
            if atr_pct is not None and atr_pct > 0:
                current_activation = max(self.activation_pct, atr_pct * 1.5)
                current_trailing = max(self.trailing_pct, atr_pct * 0.5)

            if profit_pct >= current_activation:
                if symbol not in self.peaks:
                    logger.info(
                        f"[TRAILING TP] {symbol} pre-escalator trailing activated! "
                        f"Profit: {profit_pct*100:.2f}%"
                    )
                    self.peaks[symbol] = current_price
                else:
                    if not is_short and current_price > self.peaks[symbol]:
                        self.peaks[symbol] = current_price
                    elif is_short and current_price < self.peaks[symbol]:
                        self.peaks[symbol] = current_price

            elif profit_pct < current_activation and symbol in self.peaks:
                del self.peaks[symbol]

        return None

    def reset_symbol(self, symbol: str):
        """Fully resets all tracking state for a symbol (call after position is fully closed)."""
        self._level_state.pop(symbol, None)
        self.peaks.pop(symbol, None)
        self.scaled_out_symbols.discard(symbol)
