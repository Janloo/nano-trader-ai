"""
tests/test_integration_execute_order.py

Integration test for the new execution pipeline: BarProcessor -> OrderBuilder -> OrderExecutor.
Ensures that realtime_executor.py integrates them correctly.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import alpaca.trading.requests
import alpaca.trading.enums

def test_integration_crypto_buy_pipeline():
    from realtime_executor import RealtimeExecutor
    
    executor = RealtimeExecutor(symbols=["BTCUSD"], dry_run=False)
    
    # Mock trading client and responses
    mock_client = MagicMock()
    mock_order = MagicMock(id="int-order-123", filled_avg_price="50000.0")
    mock_client.submit_order.return_value = mock_order
    mock_client.get_account.return_value = MagicMock(equity="10000.0", buying_power="10000.0")
    
    # Mock open positions for DCA check
    mock_client.get_open_position.side_effect = Exception("No position")
    mock_client.get_all_positions.return_value = []
    
    executor._trading_client = mock_client
    
    # Mock guard checks (no cooldown, no panic)
    executor.guard_mgr = MagicMock()
    executor.guard_mgr.is_symbol_in_cooldown.return_value = False
    executor.guard_mgr.check_and_update_panic_state.return_value = False
    
    # We want BarProcessor to emit a BUY signal
    # We can either feed an actual bar and mock the strategies to emit it, 
    # or just test _execute_order directly since it calls OrderBuilder + OrderExecutor.
    
    with patch("data.trade_logger.WSTradeLogger.log_trade"), \
         patch("data.trade_logger.WSTradeLogger.log_trigger"), \
         patch("data.trade_logger.WSTradeLogger.write_logbook"), \
         patch("notifications.telegram_notifier.notify_trade_executed"):
         
        bias_info = {"bias": "BULLISH", "sentiment_score": 0.85, "reasoning": "Integration Test"}
        
        order_id = executor._execute_order(
            symbol="BTCUSD",
            price=50000.0,
            change_pct=-1.5,
            bias_info=bias_info,
            is_short=False,
            atr=500.0
        )
        
        assert order_id == "int-order-123"
        mock_client.submit_order.assert_called_once()
        
        args, kwargs = mock_client.submit_order.call_args
        req = args[0]
        
        # Check that OrderBuilder correctly constructed the order
        assert req.symbol == "BTCUSD"
        assert req.side == alpaca.trading.enums.OrderSide.BUY
        assert req.time_in_force == alpaca.trading.enums.TimeInForce.GTC
        assert isinstance(req, alpaca.trading.requests.LimitOrderRequest)
