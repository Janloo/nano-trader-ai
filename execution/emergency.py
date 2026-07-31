import os
from config.settings import logger
from client.alpaca_client import AlpacaClientWrapper

LOCK_FILE = os.path.join("data", "state", "EMERGENCY_LOCKDOWN.txt")

class EmergencyLiquidator:
    @staticmethod
    def trigger_lockdown(reason: str):
        """Creates the lock file to prevent new trades."""
        os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(reason)
        logger.critical(f"🚨 [EMERGENCY LOCKDOWN INITIATED] Reason: {reason}")
        
    @staticmethod
    def is_locked() -> bool:
        """Checks if the system is in lockdown mode."""
        return os.path.exists(LOCK_FILE)

    @staticmethod
    def clear_lockdown():
        """Clears the lockdown state."""
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("🟢 [EMERGENCY LOCKDOWN] Cleared. Trading resumed.")

    @staticmethod
    def liquidate_all_positions():
        """Connects to Alpaca and forcefully closes all positions and pending orders."""
        logger.critical("🚨 [EMERGENCY LIQUIDATOR] Liquidating ALL open positions and cancelling pending orders!")
        try:
            client = AlpacaClientWrapper()
            # Cancel all pending orders and close all positions at market price
            responses = client.trading_client.close_all_positions(cancel_orders=True)
            
            logger.critical(f"🚨 [EMERGENCY LIQUIDATOR] Liquidation requests submitted. Responses: {len(responses)}")
            for resp in responses:
                logger.info(f"Liquidation response: {resp}")
                
        except Exception as e:
            logger.error(f"❌ [EMERGENCY LIQUIDATOR] Failed to liquidate positions: {e}")
            # Even if it fails, we keep the lockdown on so the bot doesn't open new positions.
