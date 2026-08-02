import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd

from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide
from alpaca.trading.models import Position, Order

from client.alpaca_client import AlpacaClientWrapper
from backtesting.data_loader import BacktestDataLoader

logger = logging.getLogger(__name__)

class VirtualAccount:
    def __init__(self, initial_cash: float):
        self.equity = str(initial_cash)
        self.buying_power = str(initial_cash)
        self.cash = initial_cash

class VirtualPosition:
    def __init__(self, symbol: str, qty: float, market_value: float, avg_entry_price: float):
        self.symbol = symbol
        self.qty = str(qty)
        self.market_value = str(market_value)
        self.avg_entry_price = str(avg_entry_price)

class VirtualOrder:
    def __init__(self, order_id: str, symbol: str, qty: float, filled_avg_price: float, side: OrderSide):
        self.id = order_id
        self.symbol = symbol
        self.qty = str(qty)
        self.filled_avg_price = str(filled_avg_price)
        self.side = side

class SimulatedAlpacaClient(AlpacaClientWrapper):
    def __init__(self, initial_cash: float = 100000.0):
        # Do NOT call super().__init__() because we don't want to initialize real Alpaca clients
        self.cash = initial_cash
        self.positions: Dict[str, Dict[str, float]] = {}  # symbol -> {'qty': float, 'avg_price': float}
        self.data_loader = BacktestDataLoader()
        self.current_time: Optional[datetime] = None
        
        # We need a way to get the "current price" of an asset at the simulated time.
        # This will be injected by the engine or fetched via data_loader.
        self.latest_prices: Dict[str, float] = {}

    def set_simulated_time(self, current_time: datetime):
        self.current_time = current_time

    def set_latest_price(self, symbol: str, price: float):
        self.latest_prices[symbol] = price

    def get_account_info(self) -> VirtualAccount:
        # Calculate total equity
        equity = self.cash
        for sym, pos in self.positions.items():
            current_price = self.latest_prices.get(sym, pos['avg_price'])
            equity += pos['qty'] * current_price
        
        account = VirtualAccount(self.cash)
        account.equity = str(equity)
        account.buying_power = str(self.cash)
        return account

    def get_positions(self) -> List[VirtualPosition]:
        result = []
        for sym, pos in self.positions.items():
            if pos['qty'] > 0:
                current_price = self.latest_prices.get(sym, pos['avg_price'])
                market_value = pos['qty'] * current_price
                result.append(VirtualPosition(sym, pos['qty'], market_value, pos['avg_price']))
        return result

    def get_historical_bars(self, symbols: List[str], timeframe, start: datetime, end: datetime = None) -> pd.DataFrame:
        if end is None:
            end = self.current_time
        return self.data_loader.get_historical_bars(symbols, timeframe, start, end)

    def get_news_articles(self, symbols: List[str], start: datetime, end: datetime = None, limit: int = 50) -> pd.DataFrame:
        if end is None:
            end = self.current_time
        return self.data_loader.get_news_articles(symbols, start, end, limit)

    def submit_order(self, order_request: Any) -> VirtualOrder:
        symbol = order_request.symbol
        side = order_request.side
        
        # Extract qty or notional
        qty = getattr(order_request, "qty", None)
        notional = getattr(order_request, "notional", None)
        
        price = self.latest_prices.get(symbol)
        if not price:
            raise ValueError(f"[Backtest] No latest price available for {symbol} to execute order.")

        # Resolve exact qty
        if qty is None and notional is not None:
            qty = float(notional) / price
        elif qty is not None:
            qty = float(qty)
        else:
            raise ValueError("Order must specify qty or notional")

        # Basic minimum order check (Alpaca rules)
        trade_value = qty * price
        if trade_value < 10.50 and side == OrderSide.BUY:
            # We raise the exact exception string so the wrapper logic (if we were using the real wrapper)
            # or the backtest itself mimics the real broker
            raise Exception(f"40010000: order notional {trade_value} is less than the minimal amount of order 10.5")

        # Execute
        import uuid
        order_id = str(uuid.uuid4())
        
        if side == OrderSide.BUY:
            cost = qty * price
            if cost > self.cash:
                raise Exception("insufficient balance")
            self.cash -= cost
            
            if symbol not in self.positions:
                self.positions[symbol] = {'qty': 0.0, 'avg_price': 0.0}
            
            old_qty = self.positions[symbol]['qty']
            old_cost = old_qty * self.positions[symbol]['avg_price']
            new_qty = old_qty + qty
            new_avg_price = (old_cost + cost) / new_qty
            
            self.positions[symbol]['qty'] = new_qty
            self.positions[symbol]['avg_price'] = new_avg_price
            
        elif side == OrderSide.SELL:
            if symbol not in self.positions or self.positions[symbol]['qty'] < qty:
                # Allow shorting? For now, no.
                # Or just close whatever is there.
                available = self.positions.get(symbol, {}).get('qty', 0.0)
                if available < qty:
                    # In real Alpaca, it might fail. In backtest, we just cap it or fail.
                    raise Exception("insufficient position for sell")
            
            proceeds = qty * price
            self.cash += proceeds
            self.positions[symbol]['qty'] -= qty
            
            if self.positions[symbol]['qty'] <= 1e-8:
                del self.positions[symbol]
                
        logger.info(f"[Backtest] Executed {side} {qty:.4f} {symbol} @ ${price:.2f}")
        return VirtualOrder(order_id, symbol, qty, price, side)
