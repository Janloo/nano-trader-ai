import logging
from typing import Dict

logger = logging.getLogger("nano-trader-ai")

class PositionSizer:
    """
    Advanced Position Sizing Engine supporting Volatility Scaling (ATR) 
    and Kelly Criterion.
    """

    @staticmethod
    def calculate_kelly_fraction(win_rate: float, reward_risk_ratio: float, multiplier: float = 1.0) -> float:
        """
        Calculates the Kelly Criterion fraction.
        f* = W - ((1 - W) / R)
        """
        if reward_risk_ratio <= 0:
            return 0.0
            
        f_star = win_rate - ((1.0 - win_rate) / reward_risk_ratio)
        
        # Edge case: If mathematical advantage is negative, do not trade.
        if f_star <= 0:
            return 0.0
            
        # Apply fractional Kelly multiplier (e.g. 0.5 for Half-Kelly)
        fraction = f_star * multiplier
        
        # Cap absolute max at 100% of allocatable capital
        return min(max(fraction, 0.0), 1.0)

    @classmethod
    def calculate_position_size(cls, symbol: str, price: float, sentiment_score: float, 
                                atr: float, risk_config: Dict, 
                                total_equity: float, buying_power: float, 
                                fallback_notional: float) -> float:
        """
        Calculates the optimal USD position size using Volatility (ATR) and Kelly Criterion.
        """
        try:
            max_capital_pct = risk_config.get("max_capital_per_trade_pct", 0.05)
            max_risk_pct = risk_config.get("max_risk_per_trade_pct", 0.01)
            atr_sl_mult = risk_config.get("atr_stop_loss_multiplier", 2.0)
            
            # Kelly configs
            use_kelly = risk_config.get("use_kelly_criterion", False)
            kelly_mult = risk_config.get("kelly_fraction_multiplier", 0.5)
            win_rate = risk_config.get("historical_win_rate", 0.55)
            reward_risk = risk_config.get("historical_reward_risk", 1.5)
            
            # 1. Volatility Scaling: Calculate stop loss distance based on ATR
            if atr > 0 and price > 0:
                sl_distance_pct = (atr * atr_sl_mult) / price
            else:
                sl_distance_pct = 0.015 # fallback 1.5% stop loss
                
            # 2. Risk Amount ($)
            risk_amount_usd = total_equity * max_risk_pct
            
            # 3. Position Size ($) based on Risk and Volatility
            position_size_usd = risk_amount_usd / sl_distance_pct if sl_distance_pct > 0 else 0
            
            # 4. Apply maximum capital cap
            max_capital_usd = buying_power * max_capital_pct
            allocation = min(position_size_usd, max_capital_usd)
            
            # 5. Apply Kelly Criterion Modulation (if enabled)
            if use_kelly:
                kelly_fraction = cls.calculate_kelly_fraction(win_rate, reward_risk, multiplier=kelly_mult)
                if kelly_fraction <= 0:
                    logger.info(f"[RISK CALC] Kelly fraction is 0 (No edge). Rejecting trade for {symbol}.")
                    return 0.0
                # Scale the allocation by the Kelly Fraction
                allocation = allocation * kelly_fraction
            
            # 6. Modulate by sentiment score (0.75 -> 50% of allocation, 1.0 -> 100% of allocation)
            score_abs = min(max(abs(sentiment_score), 0.75), 1.0)
            modulation = 0.5 + 0.5 * ((score_abs - 0.75) / 0.25)
            
            final_allocation = allocation * modulation
            
            logger.info(f"[RISK CALC] {symbol} | Eq: ${total_equity:.2f} | SL: {sl_distance_pct*100:.2f}% | " 
                        f"Base: ${position_size_usd:.2f} | Final: ${final_allocation:.2f}")
            
            return max(final_allocation, 10.50) # Alpaca minimum is $10 for crypto
            
        except Exception as e:
            logger.error(f"[RISK CALC] Error calculating dynamic size: {e}")
            return fallback_notional
