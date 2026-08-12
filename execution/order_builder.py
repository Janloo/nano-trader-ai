"""
execution/order_builder.py

Contains the logic for calculating Order parameters (qty, limit price, stop loss, time in force)
and building the Alpaca LimitOrderRequest or MarketOrderRequest objects.
"""
from typing import Optional, Union
from alpaca.trading.requests import LimitOrderRequest, StopLossRequest, MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from config.config_manager import RiskSettings


class OrderBuilder:
    """Builds Alpaca order requests for given constraints."""

    @staticmethod
    def build_order(symbol: str, price: float, size_usd: float,
                    is_crypto: bool, is_short: bool, atr: float,
                    sma_sl: Optional[float], config: RiskSettings,
                    regime: str) -> Union[LimitOrderRequest, MarketOrderRequest]:
        """
        Builds the Alpaca order request.
        """
        # If price <= 0, treat as a hedge and use a simple MarketOrder
        if price <= 0:
            return MarketOrderRequest(
                symbol=symbol,
                notional=round(size_usd, 2),
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC
            )

        atr_tp_mult = getattr(config, "atr_take_profit_multiplier", 3.0)
        atr_sl_mult = getattr(config, "atr_stop_loss_multiplier", 2.0)

        if is_crypto:
            if is_short:
                sl_price = round(sma_sl, 2) if sma_sl else round(price * 1.05, 2)
                side = OrderSide.SELL
            else:
                sl_price = round(sma_sl, 2) if sma_sl else round(price * 0.95, 2)
                side = OrderSide.BUY
        else:
            if regime == "BULL_TREND" and not is_short:
                atr_tp_mult = max(atr_tp_mult, 3.5)
            elif regime == "RANGING":
                atr_tp_mult = min(atr_tp_mult, 1.5)

            if atr > 0:
                if is_short:
                    sl_price = round(price + (atr_sl_mult * atr), 2)
                    side = OrderSide.SELL
                else:
                    sl_price = round(price - (atr_sl_mult * atr), 2)
                    side = OrderSide.BUY
            else:
                if is_short:
                    sl_price = round(price * 1.015, 2)
                    side = OrderSide.SELL
                else:
                    sl_price = round(price * 0.985, 2)
                    side = OrderSide.BUY

        qty = size_usd / price
        qty = round(qty, 4) if is_crypto else round(qty, 2)

        limit_price = round(price * 0.9995, 2) if side == OrderSide.BUY else round(price * 1.0005, 2)
        tif = TimeInForce.GTC if is_crypto else TimeInForce.DAY

        return LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=tif,
            limit_price=limit_price,
            stop_loss=StopLossRequest(stop_price=sl_price)
        )
