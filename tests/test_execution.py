import pytest
from unittest.mock import MagicMock
from execution.executor import OrderExecutor
from alpaca.trading.enums import OrderSide, TimeInForce

def test_get_position_for_symbol():
    """Verify finding specific positions from the portfolio list."""
    mock_client = MagicMock()
    executor = OrderExecutor(mock_client)
    
    pos1 = MagicMock(symbol="AAPL")
    pos2 = MagicMock(symbol="MSFT")
    positions = [pos1, pos2]
    
    assert executor.get_position_for_symbol("AAPL", positions) == pos1
    assert executor.get_position_for_symbol("NVDA", positions) is None
    assert executor.get_position_for_symbol("AAPL", []) is None

def test_execute_trade_buy_no_position():
    """Verify buying a new position using notional dollar amount when signal is BUY."""
    from config.settings import TRADE_AMOUNT_USD
    mock_client = MagicMock()
    mock_order = MagicMock(id="order-123", filled_avg_price=None, filled_qty=None)
    mock_client.submit_order.return_value = mock_order
    
    executor = OrderExecutor(mock_client)
    executor.log_trade = MagicMock()  # Mock to prevent file writing
    
    # Signal = 0.4 (>= 0.3) -> BUY order should be triggered
    order_id = executor.execute_trade("AAPL", 0.4, [], 150.00)
    
    assert order_id == "order-123"
    mock_client.submit_order.assert_called_once()
    args, kwargs = mock_client.submit_order.call_args
    req = args[0]
    assert req.symbol == "AAPL"
    assert req.notional == TRADE_AMOUNT_USD
    assert req.side == OrderSide.BUY
    assert req.time_in_force == TimeInForce.DAY
    executor.log_trade.assert_called_once_with("AAPL", "BUY", TRADE_AMOUNT_USD / 150.00, TRADE_AMOUNT_USD, 150.00, "order-123")

def test_execute_trade_buy_already_holding():
    """Verify holding when a position is already owned to prevent compound risk."""
    mock_client = MagicMock()
    executor = OrderExecutor(mock_client)
    executor.log_trade = MagicMock()
    
    pos = MagicMock(symbol="AAPL", qty="1.5", market_value="150.00")
    order_id = executor.execute_trade("AAPL", 0.4, [pos], 150.00)
    
    assert order_id is None
    mock_client.submit_order.assert_not_called()
    executor.log_trade.assert_not_called()

def test_execute_trade_sell_holding():
    """Verify liquidating (selling quantity) when signal is SELL."""
    mock_client = MagicMock()
    mock_order = MagicMock(id="order-456", filled_avg_price=None)
    mock_client.submit_order.return_value = mock_order
    
    executor = OrderExecutor(mock_client)
    executor.log_trade = MagicMock()
    
    pos = MagicMock(symbol="AAPL", qty="1.5", market_value="150.00")
    # Signal = -0.5 (<= -0.3) -> SELL order should be triggered
    order_id = executor.execute_trade("AAPL", -0.5, [pos], 150.00)
    
    assert order_id == "order-456"
    mock_client.submit_order.assert_called_once()
    args, kwargs = mock_client.submit_order.call_args
    req = args[0]
    assert req.symbol == "AAPL"
    assert req.qty == 1.5
    assert req.side == OrderSide.SELL
    assert req.time_in_force == TimeInForce.DAY
    executor.log_trade.assert_called_once_with("AAPL", "SELL", 1.5, 1.5 * 150.00, 150.00, "order-456")

def test_execute_trade_sell_not_holding():
    """Verify doing nothing when signal is SELL but no position is held."""
    mock_client = MagicMock()
    executor = OrderExecutor(mock_client)
    executor.log_trade = MagicMock()
    
    order_id = executor.execute_trade("AAPL", -0.5, [], 150.00)
    
    assert order_id is None
    mock_client.submit_order.assert_not_called()
    executor.log_trade.assert_not_called()

def test_execute_trade_neutral():
    """Verify holding when signal is inside the neutral boundary (-0.3, 0.3)."""
    mock_client = MagicMock()
    executor = OrderExecutor(mock_client)
    executor.log_trade = MagicMock()
    
    # Signal = 0.1 (neutral) -> no action
    order_id = executor.execute_trade("AAPL", 0.1, [], 150.00)
    assert order_id is None
    mock_client.submit_order.assert_not_called()
    executor.log_trade.assert_not_called()
