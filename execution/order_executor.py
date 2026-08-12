"""
execution/order_executor.py

Submits the order to Alpaca, handles API exceptions (like insufficient balance),
logs the trade, and sends Telegram notifications.
Extracted from realtime_executor.py.
"""
import logging
from typing import Optional, Union
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from execution.guard_checks import GuardManager
from data.trade_logger import WSTradeLogger

logger = logging.getLogger("nano-trader-ai")


class OrderExecutor:
    """Executes Alpaca orders and handles post-execution logic (logging, notifications)."""

    def __init__(self, trading_client, guard_mgr: GuardManager):
        self._trading_client = trading_client
        self.guard_mgr = guard_mgr

    def execute_order(self, order_request: Union[LimitOrderRequest, MarketOrderRequest],
                      price: float, size_usd: float, change_pct: float,
                      bias_type: str, sentiment_score: float, reasoning: str,
                      is_short: bool) -> Optional[str]:
        """
        Submits the order and runs all post-execution logic.
        Returns the Order ID on success, None on failure.
        """
        symbol = order_request.symbol
        side_str = "SHORT" if is_short else "BUY"

        try:
            order = self._trading_client.submit_order(order_request)
            order_id = str(order.id)

            # Update price from fill if available
            if getattr(order, "filled_avg_price", None):
                try:
                    price = float(order.filled_avg_price)
                except (ValueError, TypeError):
                    pass

            logger.info(
                f"[WS TRIGGER] {side_str} ${size_usd:.2f} of {symbol} EXECUTED! "
                f"Price: ${price:.2f} | Change: {change_pct:.2f}% | Order: {order_id}"
            )
        except Exception as e:
            error_msg = str(e).lower()
            if "insufficient balance" in error_msg:
                logger.error(f"[WS] Insufficient balance error caught for {symbol}. Reason: {e}")
                self.guard_mgr.trigger_global_error_cooldown(60)
                WSTradeLogger.write_logbook("[API WARNING] Liquidità esaurita (da API)! Acquisti in pausa per 1 ora.")
            else:
                logger.error(f"[WS] Order execution failed for {symbol}: {e}")
                WSTradeLogger.write_logbook(f"[WS ERROR] Ordine fallito su {symbol}: {e}")
            
            WSTradeLogger.log_trigger(symbol, price, change_pct, bias_type, sentiment_score, reasoning, "FAILED", False)
            return None

        # Log the trade
        qty = size_usd / price if price > 0 else 0.0
        side_display = "SELL" if is_short else "BUY"
        
        WSTradeLogger.log_trade(symbol, price, qty, order_id, sentiment_score, reasoning, change_pct)
        WSTradeLogger.log_trigger(symbol, price, change_pct, bias_type, sentiment_score, reasoning, order_id, True)
        WSTradeLogger.write_logbook(
            f"[WS TRIGGER] {side_display} ${size_usd:.2f} di {symbol} a ${price:.2f} (Change: {change_pct:.2f}%, AI Bias: {bias_type})"
        )

        # Send Telegram notification
        try:
            from notifications.telegram_notifier import notify_trade_executed
            notify_trade_executed(
                symbol=symbol, action=side_display, notional=size_usd,
                price=price, sentiment_score=sentiment_score,
                reasoning=f"WebSocket Trigger ({change_pct:.2f}%): {reasoning}",
                order_id=order_id
            )
        except Exception:
            pass

        # Set cooldown
        self.guard_mgr.register_trade(symbol)
        
        return order_id
