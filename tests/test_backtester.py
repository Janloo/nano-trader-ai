import pytest
import pandas as pd
from datetime import datetime, timezone
from backtesting.simulated_broker import SimulatedAlpacaClient, VirtualAccount, VirtualPosition, VirtualOrder
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

def test_simulated_broker_buy_and_sell():
    broker = SimulatedAlpacaClient(initial_cash=10000.0)
    
    # Setup simulated environment
    dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    broker.set_simulated_time(dt)
    broker.set_latest_price("BTCUSD", 50000.0)
    
    # 1. Buy 0.1 BTC ($5000)
    req_buy = MarketOrderRequest(
        symbol="BTCUSD",
        qty=0.1,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.GTC
    )
    
    order = broker.submit_order(req_buy)
    assert order.side == OrderSide.BUY
    assert order.qty == "0.1"
    
    # Verify account
    account = broker.get_account_info()
    assert float(account.cash) == 5000.0
    assert float(account.equity) == 10000.0
    
    # Verify positions
    positions = broker.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "BTCUSD"
    assert positions[0].qty == "0.1"
    
    # 2. Price increases to $60000
    broker.set_latest_price("BTCUSD", 60000.0)
    
    account_up = broker.get_account_info()
    assert float(account_up.equity) == 11000.0  # $5000 cash + (0.1 * 60000) = $11000
    
    # 3. Sell 0.1 BTC
    req_sell = MarketOrderRequest(
        symbol="BTCUSD",
        qty=0.1,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.GTC
    )
    order_sell = broker.submit_order(req_sell)
    assert order_sell.side == OrderSide.SELL
    
    # Verify final account
    account_final = broker.get_account_info()
    assert float(account_final.cash) == 11000.0
    assert float(account_final.equity) == 11000.0
    assert len(broker.get_positions()) == 0

def test_simulated_broker_insufficient_funds():
    broker = SimulatedAlpacaClient(initial_cash=1000.0)
    broker.set_latest_price("BTCUSD", 50000.0)
    
    # Try to buy 1 BTC ($50000), should fail
    req_buy = MarketOrderRequest(
        symbol="BTCUSD",
        qty=1.0,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.GTC
    )
    
    with pytest.raises(Exception, match="insufficient balance"):
        broker.submit_order(req_buy)

def test_simulated_broker_minimal_amount():
    broker = SimulatedAlpacaClient(initial_cash=10000.0)
    broker.set_latest_price("BTCUSD", 50000.0)
    
    # Try to buy $5 worth of BTC (minimum is 10.50)
    req_buy = MarketOrderRequest(
        symbol="BTCUSD",
        notional=5.0,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.GTC
    )
    
    with pytest.raises(Exception, match=r"40010000: order notional 5.0 is less than the minimal amount of order 10.5"):
        broker.submit_order(req_buy)
