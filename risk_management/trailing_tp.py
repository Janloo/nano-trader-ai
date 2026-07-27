import logging
from typing import Dict

logger = logging.getLogger("nano-trader-ai")

class TrailingTakeProfitManager:
    """
    Manages custom dynamic Trailing Take-Profit.
    Activates when profit exceeds a certain threshold, then trails the peak price.
    """
    def __init__(self, activation_pct: float = 0.005, trailing_pct: float = 0.002):
        self.activation_pct = activation_pct
        self.trailing_pct = trailing_pct
        self.peaks: Dict[str, float] = {}

    def update_and_check(self, symbol: str, current_price: float, avg_entry_price: float, is_short: bool = False, atr_pct: float = None) -> bool:
        """
        Returns True if the trailing stop has been hit and the position should be closed.
        If atr_pct is provided, dynamically widens the activation and trailing thresholds based on volatility.
        """
        if avg_entry_price <= 0:
            return False
            
        profit_pct = (current_price - avg_entry_price) / avg_entry_price
        if is_short:
            profit_pct = -profit_pct
            
        # Calculate dynamic thresholds if ATR is provided
        current_activation = self.activation_pct
        current_trailing = self.trailing_pct
        if atr_pct is not None and atr_pct > 0:
            # Scale activation to at least 1.5x ATR, and trailing to 0.5x ATR
            current_activation = max(self.activation_pct, atr_pct * 1.5)
            current_trailing = max(self.trailing_pct, atr_pct * 0.5)

        # Is the position profitable enough to activate trailing?
        if profit_pct >= current_activation:
            if symbol not in self.peaks:
                logger.info(f"[TRAILING TP] {symbol} trailing activated! Profit: {profit_pct*100:.2f}% (Price: {current_price:.2f}, Dynamic Activation: {current_activation*100:.2f}%)")
                self.peaks[symbol] = current_price
            else:
                if not is_short and current_price > self.peaks[symbol]:
                    self.peaks[symbol] = current_price
                elif is_short and current_price < self.peaks[symbol]:
                    self.peaks[symbol] = current_price
                    
            # Check if it dropped from peak by trailing_pct
            peak = self.peaks[symbol]
            drawdown = (peak - current_price) / peak if not is_short else (current_price - peak) / peak
            
            if drawdown >= current_trailing:
                logger.info(f"[TRAILING TP] {symbol} hit trail trigger! Peak: {peak:.2f}, Drop: {drawdown*100:.2f}% (Dynamic Trailing: {current_trailing*100:.2f}%). Executing close.")
                del self.peaks[symbol]
                return True
                
        # Reset peak if it falls below activation (shouldn't happen often if we exit, but just in case)
        elif profit_pct < current_activation and symbol in self.peaks:
             del self.peaks[symbol]
             
        return False
