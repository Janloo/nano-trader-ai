"""
execution/position_sizer.py

Unifies and centralizes all position sizing logic for both swing and HFT execution.
Ensures hard constraints (buying power, global caps) are never exceeded, even
during Martingale/DCA expansions.
"""
import logging
from typing import List, Optional

from config.config_manager import RiskSettings

logger = logging.getLogger("nano-trader-ai")


class PositionSizer:

    @staticmethod
    def calc_base_size(config: RiskSettings, total_equity: float, buying_power: float) -> float:
        """
        Calculates the base size based on HFT budget.
        """
        if total_equity <= 0 or buying_power <= 0:
            return 0.0

        hft_equity = total_equity * getattr(config, "hft_budget_pct", 0.20)
        # Fraction is 1% of the HFT budget
        size = hft_equity * 0.01

        # Check against absolute minimum
        if size < 11.0:
            size = 11.0
            
        # If we can't even afford the minimum, return 0
        if size > hft_equity:
            return 0.0

        # Cannot exceed buying power
        if size > buying_power:
            return 0.0

        return size

    @staticmethod
    def apply_global_caps(size_usd: float, is_crypto: bool, is_short: bool,
                          positions: List[any], config: RiskSettings,
                          total_equity: float, buying_power: float) -> Optional[float]:
        """
        Enforces global portfolio limits for crypto/stocks and cash reserve.
        Returns clamped size_usd, or None if completely blocked.
        """
        if not is_short:
            # Cash Reserve Check
            min_cash_usd = total_equity * getattr(config, "global_min_cash_pct", 0.05)
            available_cash_for_trading = buying_power - min_cash_usd
            if available_cash_for_trading <= 0:
                return None
            if size_usd > available_cash_for_trading:
                size_usd = available_cash_for_trading

            # Asset Class Allocation Check
            current_crypto_value = sum(float(p.market_value) for p in positions if getattr(p, "asset_class", "") == "crypto")
            current_stocks_value = sum(float(p.market_value) for p in positions if getattr(p, "asset_class", "") != "crypto")

            if is_crypto:
                max_crypto_usd = total_equity * getattr(config, "global_max_crypto_pct", 0.50)
                available_crypto = max_crypto_usd - current_crypto_value
                if available_crypto <= 0:
                    return None
                if size_usd > available_crypto:
                    size_usd = available_crypto
            else:
                max_stocks_usd = total_equity * getattr(config, "global_max_stocks_pct", 1.0)
                available_stocks = max_stocks_usd - current_stocks_value
                if available_stocks <= 0:
                    return None
                if size_usd > available_stocks:
                    size_usd = available_stocks

        return size_usd

    @staticmethod
    def apply_martingale(base_size_usd: float, multiplier: float, layer: int,
                         buying_power: float, max_crypto_usd: float,
                         current_crypto_value: float) -> float:
        """
        Calculates DCA Martingale size safely, firmly clamping to available capital.
        This prevents the 'runaway size' bug.
        """
        size_usd = base_size_usd * (multiplier ** layer)

        # Hard clamps
        max_allowed = buying_power * 0.95
        available_crypto = max_crypto_usd - current_crypto_value
        max_allowed = min(max_allowed, available_crypto)

        if size_usd > max_allowed:
            size_usd = max_allowed

        return size_usd

    @staticmethod
    def apply_preflight(size_usd: float, buying_power: float, is_short: bool) -> Optional[float]:
        """
        Final safety clamp: leave 5% BP buffer, check Alpaca $10 minimum.
        """
        if not is_short:
            if size_usd >= buying_power * 0.98:
                size_usd = buying_power * 0.95

            if size_usd < 10.0:
                return None

        return size_usd

    # ──────────────────────────────────────────────────────────────────────────
    # Backward compatibility for existing HFT / Swing code (until fully migrated)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def calculate_micro_size(cls, symbol: str, config: RiskSettings, total_equity: float, buying_power: float, risk_fraction: float = 0.01) -> float:
        """Legacy entrypoint used by current realtime_executor."""
        hft_equity = total_equity * getattr(config, "hft_budget_pct", 0.20)
        effective_buying_power = min(buying_power, hft_equity)
        size = hft_equity * risk_fraction
        if size < 11.0:
            size = 11.0
            
        if size > effective_buying_power:
            return 0.0
        return size

    @classmethod
    def calculate_kelly_size(cls, symbol: str, price: float, sentiment_score: float,
                             atr: float, config: RiskSettings,
                             total_equity: float, buying_power: float) -> float:
        """Legacy entrypoint used by Swing Bot (execution/trader.py)."""
        # Re-implementing the old kelly size logic just enough to keep tests passing
        # and old callers happy.
        try:
            if total_equity <= 0 or buying_power <= 0:
                return 0.0
                
            win_rate = getattr(config, "historical_win_rate", 0.55)
            reward_risk = getattr(config, "historical_reward_risk", 1.5)

            if atr > 0 and price > 0:
                sl_distance_pct = (atr * getattr(config, "atr_stop_loss_multiplier", 2.0)) / price
            else:
                sl_distance_pct = 0.015
                
            risk_amount_usd = total_equity * getattr(config, "max_risk_per_trade_pct", 0.02)
            position_size_usd = risk_amount_usd / sl_distance_pct if sl_distance_pct > 0 else 0
            
            max_capital_usd = total_equity * getattr(config, "max_capital_per_trade_pct", 0.05)
            allocation = min(position_size_usd, max_capital_usd)
            
            if getattr(config, "use_kelly_criterion", True):
                if reward_risk <= 0:
                    return 0.0
                f_star = win_rate - ((1.0 - win_rate) / reward_risk)
                if f_star <= 0:
                    return 0.0
                kelly_fraction = f_star * getattr(config, "kelly_fraction_multiplier", 1.0)
                kelly_fraction = min(max(kelly_fraction, 0.0), 1.0)
                allocation = allocation * kelly_fraction
            
            score_abs = min(max(abs(sentiment_score), 0.75), 1.0)
            modulation = 0.5 + 0.5 * ((score_abs - 0.75) / 0.25)
            final_allocation = allocation * modulation
            
            final_allocation = min(final_allocation, buying_power)
            if final_allocation < 10.50:
                return 0.0
            return final_allocation
        except Exception:
            return 0.0
