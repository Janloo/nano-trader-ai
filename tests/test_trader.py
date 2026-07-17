import pytest
from unittest.mock import MagicMock
from execution.trader import AITrader
from alpaca.trading.enums import OrderSide, TimeInForce

def test_execute_ai_decision_buy():
    """Verify executing fractional BUY orders when AI action is BUY and confidence is high."""
    mock_client = MagicMock()
    mock_order = MagicMock(id="order-ai-123", filled_avg_price=None, filled_qty=None)
    mock_client.submit_order.return_value = mock_order
    
    trader = AITrader(mock_client)
    trader._read_data = MagicMock(return_value={"portfolio_history": [], "trades": []})
    trader._write_data = MagicMock()
    
    decision = {
        "action": "BUY",
        "confidence": 85,
        "sentiment_score": 0.8,
        "reasoning": "Macro indicators are strong."
    }
    
    order_id = trader.execute_ai_decision("SPY", decision, 740.00, [], ["News Headline 1"])
    assert order_id == "order-ai-123"
    mock_client.submit_order.assert_called_once()
    trader._write_data.assert_called_once()
    
    # Verify order structure
    args, kwargs = mock_client.submit_order.call_args
    req = args[0]
    assert req.symbol == "SPY"
    assert req.notional == 5.00
    assert req.side == OrderSide.BUY

def test_execute_ai_decision_hold():
    """Verify doing nothing when AI action is HOLD or confidence is low."""
    mock_client = MagicMock()
    trader = AITrader(mock_client)
    trader._read_data = MagicMock(return_value={"portfolio_history": [], "trades": []})
    trader._write_data = MagicMock()
    
    decision = {
        "action": "HOLD",
        "confidence": 60,
        "sentiment_score": 0.1,
        "reasoning": "Standard trading indexes."
    }
    
    order_id = trader.execute_ai_decision("SPY", decision, 740.00, [], ["News Headline 1"])
    assert order_id is None
    mock_client.submit_order.assert_not_called()
    trader._write_data.assert_not_called()
