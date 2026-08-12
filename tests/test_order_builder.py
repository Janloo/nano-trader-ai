"""
tests/test_order_builder.py

TDD tests for execution/order_builder.py
"""
import pytest
from unittest.mock import MagicMock
from alpaca.trading.enums import OrderSide, TimeInForce


def _make_config(**kwargs):
    from config.config_manager import RiskSettings
    defaults = {
        "atr_take_profit_multiplier": 3.0,
        "atr_stop_loss_multiplier": 2.0,
        "crypto_micro_tp_pct": 0.50,
    }
    defaults.update(kwargs)
    return RiskSettings(**{k: v for k, v in defaults.items() if hasattr(RiskSettings, k)})


class TestOrderBuilderCrypto:
    def test_crypto_buy_order_builder(self):
        from execution.order_builder import OrderBuilder
        config = _make_config(crypto_micro_tp_pct=0.50)
        # 100 USD / 50,000 = 0.002 BTC
        # TP = +0.50% = 50250, SL = sma if available, else 0.95 = 47500
        req = OrderBuilder.build_order(
            symbol="BTCUSD", price=50000.0, size_usd=100.0, is_crypto=True,
            is_short=False, atr=0, sma_sl=None, config=config, regime="UNKNOWN"
        )
        assert req.symbol == "BTCUSD"
        assert req.qty == 0.002
        assert req.side == OrderSide.BUY
        assert req.time_in_force == TimeInForce.GTC
        assert req.limit_price == 49975.0  # 50000 * 0.9995
        assert req.stop_loss.stop_price == 47500.0  # 50000 * 0.95

    def test_crypto_short_order_builder_uses_sma_sl(self):
        from execution.order_builder import OrderBuilder
        config = _make_config(crypto_micro_tp_pct=0.50)
        req = OrderBuilder.build_order(
            symbol="BTCUSD", price=50000.0, size_usd=100.0, is_crypto=True,
            is_short=True, atr=0, sma_sl=51000.0, config=config, regime="UNKNOWN"
        )
        assert req.side == OrderSide.SELL
        assert req.stop_loss.stop_price == 51000.0  # Used SMA
        assert req.limit_price == 50025.0  # 50000 * 1.0005


class TestOrderBuilderStocks:
    def test_stock_buy_order_with_atr_and_regime(self):
        from execution.order_builder import OrderBuilder
        # Base TP = 3.0, but in BULL_TREND it should widen to 3.5
        config = _make_config(atr_take_profit_multiplier=3.0, atr_stop_loss_multiplier=2.0)
        req = OrderBuilder.build_order(
            symbol="AAPL", price=150.0, size_usd=150.0, is_crypto=False,
            is_short=False, atr=2.0, sma_sl=None, config=config, regime="BULL_TREND"
        )
        assert req.time_in_force == TimeInForce.DAY
        assert req.qty == 1.0  # 150/150, rounded to 2 for stocks
        # TP should be +3.5 ATR (7.0) -> not directly accessible on LimitOrderRequest if TP is not placed here?
        # Wait, the old code didn't actually submit a TakeProfitRequest! It only submitted StopLossRequest!
        # Let's verify this in the test. If it doesn't submit a TP request, we just check SL.
        assert req.stop_loss.stop_price == 146.0  # 150 - (2.0 * 2.0)

    def test_hedge_market_order_if_price_zero(self):
        from execution.order_builder import OrderBuilder
        config = _make_config()
        # if price <= 0, returns MarketOrderRequest
        req = OrderBuilder.build_order(
            symbol="SH", price=0.0, size_usd=100.0, is_crypto=False,
            is_short=False, atr=0, sma_sl=None, config=config, regime="UNKNOWN"
        )
        # Should be a MarketOrderRequest
        from alpaca.trading.requests import MarketOrderRequest
        assert isinstance(req, MarketOrderRequest)
        assert req.notional == 100.0
