import logging
from config.config_manager import RiskSettings

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
    def calculate_kelly_size(cls, symbol: str, price: float, sentiment_score: float, 
                             atr: float, config: RiskSettings, 
                             total_equity: float, buying_power: float) -> float:
        """
        Calculates the optimal USD position size using Volatility (ATR) and Kelly Criterion for Swing Bot.
        """
        try:
            if total_equity <= 0 or buying_power <= 0:
                return 0.0
                
            win_rate = config.historical_win_rate
            reward_risk = config.historical_reward_risk

            if config.use_kelly_criterion:
                try:
                    from risk_management.performance_tracker import get_live_stats
                    live = get_live_stats()
                    if live.get("sufficient_data"):
                        win_rate = live["win_rate"]
                        reward_risk = live["reward_risk_ratio"]
                except Exception:
                    pass
            
            # 1. Volatility Scaling: Calculate stop loss distance based on ATR
            if atr > 0 and price > 0:
                sl_distance_pct = (atr * config.atr_stop_loss_multiplier) / price
            else:
                sl_distance_pct = 0.015 # fallback 1.5% stop loss
                
            # 2. Risk Amount ($)
            risk_amount_usd = total_equity * config.max_risk_per_trade_pct
            
            # 3. Position Size ($) based on Risk and Volatility
            position_size_usd = risk_amount_usd / sl_distance_pct if sl_distance_pct > 0 else 0
            
            # 4. Apply maximum capital cap (based on actual equity)
            max_capital_usd = total_equity * config.max_capital_per_trade_pct
            allocation = min(position_size_usd, max_capital_usd)
            
            # 5. Apply Kelly Criterion Modulation (if enabled)
            if config.use_kelly_criterion:
                kelly_fraction = cls.calculate_kelly_fraction(win_rate, reward_risk, multiplier=config.kelly_fraction_multiplier)
                if kelly_fraction <= 0:
                    logger.info(f"[RISK CALC] Kelly fraction is 0 (No edge). Rejecting trade for {symbol}.")
                    return 0.0
                allocation = allocation * kelly_fraction
            
            # 6. Modulate by sentiment score (0.75 -> 50% of allocation, 1.0 -> 100% of allocation)
            score_abs = min(max(abs(sentiment_score), 0.75), 1.0)
            modulation = 0.5 + 0.5 * ((score_abs - 0.75) / 0.25)
            final_allocation = allocation * modulation
            
            # Ensure it fits buying power and is at least Alpaca minimum
            final_allocation = min(final_allocation, buying_power)
            if final_allocation < 10.50:
                return 0.0 # Cannot afford minimum trade
            return final_allocation
            
        except Exception as e:
            logger.error(f"[RISK CALC] Error calculating dynamic size: {e}")
            return 0.0

    @classmethod
    def calculate_micro_size(cls, symbol: str, config: RiskSettings, total_equity: float, buying_power: float, risk_fraction: float = 0.01) -> float:
        """
        Calculates a dynamic micro-size for the HFT Scalper Bot, strictly enforcing the Chinese Wall budget.
        """
        hft_equity = total_equity * config.hft_budget_pct
        effective_buying_power = min(buying_power, hft_equity)
        
        # Calculate size based on a fraction of the HFT budget
        size = hft_equity * risk_fraction
        
        if size > effective_buying_power or size < 10.0: # 10.0 is Alpaca's crypto minimum roughly
            return 0.0
            
        return size
