"""
tests/test_order_executor.py

TDD tests for execution/order_executor.py
"""
import pytest
from unittest.mock import patch, MagicMock
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


class TestOrderExecutor:
    def test_execute_order_success(self):
        from execution.order_executor import OrderExecutor
        from execution.guard_checks import GuardManager
        
        guard_mgr = GuardManager()
        mock_client = MagicMock()
        mock_order = MagicMock()
        mock_order.id = "order123"
        mock_order.filled_avg_price = "150.5"
        mock_client.submit_order.return_value = mock_order
        
        req = MarketOrderRequest(symbol="AAPL", notional=100.0, side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
        
        with patch("data.trade_logger.WSTradeLogger.log_trade") as mock_log_trade, \
             patch("data.trade_logger.WSTradeLogger.log_trigger") as mock_log_trigger, \
             patch("data.trade_logger.WSTradeLogger.write_logbook") as mock_logbook, \
             patch("notifications.telegram_notifier.notify_trade_executed") as mock_notify:
             
            executor = OrderExecutor(mock_client, guard_mgr)
            order_id = executor.execute_order(
                order_request=req,
                price=150.0,
                size_usd=100.0,
                change_pct=1.5,
                bias_type="BULLISH",
                sentiment_score=0.8,
                reasoning="Test",
                is_short=False
            )
            
            assert order_id == "order123"
            mock_client.submit_order.assert_called_once_with(req)
            mock_log_trade.assert_called_once()
            mock_log_trigger.assert_called_once()
            mock_notify.assert_called_once()
            assert guard_mgr.is_symbol_in_cooldown("AAPL", cooldown_seconds=60) is True

    def test_execute_order_insufficient_balance_triggers_guard(self):
        from execution.order_executor import OrderExecutor
        from execution.guard_checks import GuardManager
        
        guard_mgr = GuardManager()
        mock_client = MagicMock()
        mock_client.submit_order.side_effect = Exception("insufficient balance")
        
        req = MarketOrderRequest(symbol="AAPL", notional=100.0, side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
        
        with patch("data.trade_logger.WSTradeLogger.log_trigger") as mock_log_trigger:
            executor = OrderExecutor(mock_client, guard_mgr)
            order_id = executor.execute_order(
                order_request=req, price=150.0, size_usd=100.0,
                change_pct=1.5, bias_type="BULLISH", sentiment_score=0.8,
                reasoning="Test", is_short=False
            )
            
            assert order_id is None
            assert guard_mgr.is_global_error_cooldown_active() is True
            # Failed log trigger
            mock_log_trigger.assert_called_once()
            args, kwargs = mock_log_trigger.call_args
            assert args[6] == "FAILED"  # order_id argument in log_trigger
