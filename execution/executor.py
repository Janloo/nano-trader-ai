import json
import os
from datetime import datetime, timezone
from typing import List, Optional
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.models import Position

from client.alpaca_client import AlpacaClientWrapper
from config.settings import TRADE_AMOUNT_USD, logger

class OrderExecutor:
    def __init__(self, client: AlpacaClientWrapper):
        self.client = client

        self.trades_path = os.path.join("data", "archives", "trades.jsonl")
        self.portfolio_path = os.path.join("data", "archives", "portfolio_history.jsonl")

    def _append_jsonl(self, path: str, record: dict):
        """Appends a dictionary as a JSON Line to the specified file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Error appending to {path}: {e}")

    def log_portfolio_status(self, equity: float, buying_power: float, unrealized_pnl: float):
        """Appends portfolio snapshot status to historical logs."""
        self._append_jsonl(self.portfolio_path, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "equity": equity,
            "buying_power": buying_power,
            "unrealized_pnl": unrealized_pnl
        })

    def log_trade(self, symbol: str, side: str, qty: float, notional: float, price: float, order_id: str):
        """Appends transaction trade details to historical logs."""
        self._append_jsonl(self.trades_path, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "notional": notional,
            "price": price
        })

    def get_position_for_symbol(self, symbol: str, positions: List[Position]) -> Optional[Position]:
        """Finds the open position for a given symbol from a list of open positions (slash-insensitive)."""
        if not positions:
            return None
        clean_sym = symbol.replace("/", "").upper()
        for pos in positions:
            pos_sym = pos.symbol.replace("/", "").upper()
            if pos_sym == clean_sym:
                return pos
        return None

    def execute_trade(self, symbol: str, signal: float, positions: List[Position], current_price: float) -> Optional[str]:
        """
        Executes a trade based on the strategy signal and existing positions.
        Returns the order ID if an order was submitted, else None.
        """
        position = self.get_position_for_symbol(symbol, positions)
        order_symbol = symbol.replace("BTCUSD", "BTC/USD")
        
        # BUY condition: Signal is >= 0.3
        if signal >= 0.3:
            if position is not None:
                # We already hold a position. Avoid compounding to manage risk.
                logger.info(
                    f"[{symbol} Execution] Signal is BUY ({signal:.2f}) but position already exists "
                    f"(Qty: {position.qty}, Market Value: {getattr(position, 'market_value', 'N/A')}). No action taken."
                )
                return None
                
            logger.info(
                f"[{symbol} Execution] Signal is BUY ({signal:.2f}) and no position exists. "
                f"Submitting BUY order for notional amount: ${TRADE_AMOUNT_USD:.2f}"
            )
            try:
                # Submit market order with notional
                order_id = "mock-buy-id"
                order = None
                
                # Check if we have an active API client
                if self.client is not None:
                    order_data = MarketOrderRequest(
                        symbol=order_symbol,
                        notional=TRADE_AMOUNT_USD,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY
                    )
                    order = self.client.submit_order(order_data)
                    order_id = str(order.id)
                
                # Deduce execution price and quantity
                price = current_price
                qty = TRADE_AMOUNT_USD / current_price
                if order and getattr(order, "filled_avg_price", None) is not None:
                    try:
                        price = float(order.filled_avg_price)
                        qty = float(order.filled_qty) if getattr(order, "filled_qty", None) else qty
                    except (ValueError, TypeError):
                        pass
                
                logger.info(f"[{symbol} Execution] BUY order submitted. Order ID: {order_id}")
                self.log_trade(symbol, "BUY", qty, TRADE_AMOUNT_USD, price, order_id)
                return order_id
            except Exception as e:
                logger.error(f"[{symbol} Execution] Failed to submit BUY order for {symbol}: {e}")
                return None

        # SELL condition: Signal is <= -0.3
        elif signal <= -0.3:
            if position is None:
                logger.info(f"[{symbol} Execution] Signal is SELL ({signal:.2f}) but no position exists. No action taken.")
                return None

            try:
                qty = float(position.qty)
            except (ValueError, TypeError):
                logger.error(f"[{symbol} Execution] Could not parse position quantity: {position.qty}")
                return None

            logger.info(
                f"[{symbol} Execution] Signal is SELL ({signal:.2f}) and position exists (Qty: {qty}). "
                f"Submitting SELL order to liquidate position."
            )
            try:
                order_id = "mock-sell-id"
                order = None
                
                if self.client is not None:
                    order_data = MarketOrderRequest(
                        symbol=order_symbol,
                        qty=qty,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.DAY
                    )
                    order = self.client.submit_order(order_data)
                    order_id = str(order.id)
                
                price = current_price
                if order and getattr(order, "filled_avg_price", None) is not None:
                    try:
                        price = float(order.filled_avg_price)
                    except (ValueError, TypeError):
                        pass
                notional = qty * price
                
                logger.info(f"[{symbol} Execution] SELL order submitted. Order ID: {order_id}")
                self.log_trade(symbol, "SELL", qty, notional, price, order_id)
                return order_id
            except Exception as e:
                logger.error(f"[{symbol} Execution] Failed to submit SELL order for {symbol}: {e}")
                return None

        else:
            logger.info(f"[{symbol} Execution] Signal is neutral ({signal:.2f}). Holding position.")
            return None
