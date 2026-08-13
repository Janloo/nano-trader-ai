#!/usr/bin/env python3
"""
realtime_executor.py â€” Hybrid Async Architecture: Micro (Fast) Process

Connects to Alpaca's CryptoDataStream WebSocket and monitors real-time
1-minute bars for DIP opportunities. When a DIP is detected and the
macro AI bias (from data/market_bias.json) is BULLISH, it executes
a fractional $5 market buy order instantly.

Usage:
    python realtime_executor.py                        # Live mode
    python realtime_executor.py --dry-run              # Log only, no orders
    python realtime_executor.py --symbols BTCUSD       # Override symbols
"""
import argparse
import json
import os
import sys
import time
import asyncio
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
import threading
import logging

from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY, logger
from strategy.bollinger_squeeze import BollingerSqueezeDetector

# Suppress noisy asyncio/websockets tracebacks during reconnections
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("websockets").setLevel(logging.CRITICAL)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Configuration
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DIP_THRESHOLD_PCT = -0.20      # Minimum % drop to trigger a DIP signal
SPIKE_THRESHOLD_PCT = 0.20     # Minimum % rise to trigger a SPIKE signal
DIP_WINDOW_SECONDS = 300      # 5-minute rolling window
ORDER_COOLDOWN_SECONDS = 60   # 1 minute between orders on same asset
BIAS_EXPIRY_HOURS = 72        # Temporarily extended for the weekend
NOTIONAL_USD = 10.00          # Fallback static order size

BIAS_FILE = os.path.join("data", "state", "market_bias.json")
TRADES_FILE_JSONL = os.path.join("data", "archives", "trades.jsonl")
WS_LOG_FILE = os.path.join("data", "state", "ws_triggers.json")
LOGBOOK_FILE = os.path.join("data", "archives", "human_logbook.txt")


from data.bias_reader import BiasReader



from config.config_manager import RiskConfigReader, RegimeConfigReader

from strategy.volatility_detector import VolatilityDetector
from strategy.indicator_manager import IndicatorManager
from data.trade_logger import WSTradeLogger
from execution.guard_checks import GuardManager
from execution.order_builder import OrderBuilder
from execution.order_executor import OrderExecutor
from execution.emergency import EmergencyLiquidator
from hft.bar_processor import BarProcessor

class RealtimeExecutor:
    """
    Connects to Alpaca CryptoDataStream, monitors prices, and executes
    DIP-based trades when the macro AI bias is BULLISH, or SPIKE-based
    trades when the macro AI bias is BEARISH.
    """

    def __init__(self, symbols: List[str], dry_run: bool = False):
        self.symbols = symbols
        self.target_symbols = []
        self.dry_run = dry_run
        self.vol_detector = VolatilityDetector()
        self.indicator_mgr = IndicatorManager(period=14)
        self._last_order_time: Dict[str, datetime] = {}
        self._trading_client = None
        
        from risk_management.orderbook_analyzer import OrderBookAnalyzer
        from risk_management.trailing_tp import TrailingTakeProfitManager
        from strategy.fast_guardian import FastGuardian
        from strategy.momentum_filter import MomentumAccelerationFilter
        from strategy.vwap_reversion import VWAPReversionStrategy
        from strategy.bollinger_squeeze import BollingerSqueezeDetector
        from strategy.correlation_engine import CrossAssetCorrelationEngine
        from risk_management.volume_profile import VolumeProfileManager
        self.orderbook_analyzer = OrderBookAnalyzer(imbalance_threshold=3.0)
        self.trailing_mgr = TrailingTakeProfitManager(activation_pct=0.005, trailing_pct=0.002)
        self.volume_profile_mgr = VolumeProfileManager(bucket_size=50.0)
        self.fast_guardian = FastGuardian()
        # New strategies
        self.momentum_filter = MomentumAccelerationFilter(fast_period=5, slow_period=10)
        self.vwap_strategy = VWAPReversionStrategy(max_bars=200, entry_atr_mult=0.5, exit_atr_mult=0.3)
        risk_config = RiskConfigReader.read()
        squeeze_threshold = risk_config.get("squeeze_threshold_pct", 0.005)
        self.bollinger_detector = BollingerSqueezeDetector(period=20, std_dev=2.0, squeeze_threshold_pct=squeeze_threshold)
        self.correlation_engine = CrossAssetCorrelationEngine(window=30, min_correlation=0.65)
        self.alert_states: Dict[str, dict] = {}
        
        self.bar_processor = BarProcessor(
            vol_detector=self.vol_detector,
            indicator_mgr=self.indicator_mgr,
            guard_mgr=GuardManager(),
            momentum_filter=self.momentum_filter,
            vwap_strategy=self.vwap_strategy,
            bollinger_detector=self.bollinger_detector,
            correlation_engine=self.correlation_engine,
            volume_profile_mgr=self.volume_profile_mgr
        )
        
        self._last_trailing_check = datetime.now(timezone.utc)
        self._shadow_last_order_time: Dict[str, datetime] = {}
        # MTF Confluence Cache: {symbol: {"trend": "UP"/"DOWN"/"NEUTRAL", "fetched_at": datetime}}
        self._mtf_trend_cache: Dict[str, dict] = {}
        self._mtf_cache_ttl_seconds: int = 3600  # Refresh every hour
        self.guard_mgr = GuardManager()
        self.order_executor = None
        self._reversal_wait_states: Dict[str, dict] = {}
        self._last_ws_msg_time: float = time.time()

    def _check_mtf_trend(self, symbol: str) -> str:
        """
        Checks the macro trend for a given symbol by computing EMA50 on 1H bars.
        Returns 'UP', 'DOWN', or 'NEUTRAL'.
        Uses a 1-hour cache to avoid hammering the API.
        """
        now = datetime.now(timezone.utc)
        cached = self._mtf_trend_cache.get(symbol)
        if cached:
            age = (now - cached["fetched_at"]).total_seconds()
            if age < self._mtf_cache_ttl_seconds:
                return cached["trend"]

        try:
            from alpaca.data.historical import CryptoHistoricalDataClient
            from alpaca.data.requests import CryptoBarsRequest
            from alpaca.data.timeframe import TimeFrame
            from dateutil.relativedelta import relativedelta

            client = CryptoHistoricalDataClient(APCA_API_KEY_ID, APCA_API_SECRET_KEY)
            # Fetch last 60 1H bars (enough for EMA50 + a few extras)
            start = now - relativedelta(hours=62)
            alpaca_symbol = symbol.replace("USD", "/USD") if "USD" in symbol else symbol
            req = CryptoBarsRequest(symbol_or_symbols=alpaca_symbol, timeframe=TimeFrame.Hour, start=start, end=now)
            bars = client.get_crypto_bars(req)
            df = bars.df if hasattr(bars, "df") else None
            
            if df is not None and len(df) >= 50:
                # Flatten multi-index if needed
                if hasattr(df.index, "levels"):
                    df = df.xs(alpaca_symbol, level=0) if alpaca_symbol in df.index.get_level_values(0) else df
                closes = df["close"].values[-50:]
                ema50 = closes[-1]
                k = 2.0 / (50 + 1)
                for c in closes:
                    ema50 = c * k + ema50 * (1 - k)

                last_close = closes[-1]
                if last_close > ema50 * 1.001:
                    trend = "UP"
                elif last_close < ema50 * 0.999:
                    trend = "DOWN"
                else:
                    trend = "NEUTRAL"

                logger.info(f"[MTF] {symbol} â€” EMA50(1H): {ema50:.4f}, Last: {last_close:.4f} â†’ Trend: {trend}")
            else:
                trend = "NEUTRAL"

        except Exception as e:
            logger.warning(f"[MTF] Could not fetch 1H data for {symbol}: {e}")
            trend = "NEUTRAL"

        self._mtf_trend_cache[symbol] = {"trend": trend, "fetched_at": now}
        return trend

    def _init_trading_client(self):
        """Lazily initializes the Alpaca trading client."""
        if self._trading_client is None and not self.dry_run:
            from alpaca.trading.client import TradingClient
            is_paper = True  # Always paper for safety
            self._trading_client = TradingClient(
                api_key=APCA_API_KEY_ID,
                secret_key=APCA_API_SECRET_KEY,
                paper=is_paper
            )
            self.order_executor = OrderExecutor(self._trading_client, self.guard_mgr)

    def _manage_trailing_stops(self, current_price: float, symbol: str):
        """Checks open positions for trailing take profit triggers."""
        if self.dry_run:
            return
            
        now = datetime.now(timezone.utc)
        if (now - self._last_trailing_check).total_seconds() < 2.0:
            return # throttle API calls
        self._last_trailing_check = now
        
        try:
            self._init_trading_client()
            check_symbol = symbol
            try:
                pos = self._trading_client.get_open_position(check_symbol)
                qty = float(pos.qty)
                avg_entry = float(pos.avg_entry_price)
                is_short = qty < 0
                
                # Fetch ATR to pass to trailing manager
                atr_val = self.indicator_mgr.get_atr(symbol)
                atr_pct = (atr_val / current_price) if atr_val and current_price > 0 else 0.0
                
                action = self.trailing_mgr.update_and_check(symbol, current_price, avg_entry, is_short, atr_pct)
                
                # Check if position is large enough to scale out (min Alpaca order is $10.5, so we need $21+)
                pos_value = abs(qty) * current_price
                if action == "SCALE_OUT" and pos_value < 22.0:
                    action = "CLOSE_ALL"
                    
                if action == "SCALE_OUT":
                    logger.info(f"[WS] Trailing TP triggered for {symbol}! Scaling out 50%.")
                    from alpaca.trading.requests import MarketOrderRequest
                    from alpaca.trading.enums import OrderSide, TimeInForce
                    
                    close_side = OrderSide.BUY if is_short else OrderSide.SELL
                    scale_qty = round(abs(qty) / 2.0, 5) # Assuming crypto precision
                    req = MarketOrderRequest(
                        symbol=check_symbol,
                        qty=scale_qty,
                        side=close_side,
                        time_in_force=TimeInForce.GTC
                    )
                    self._trading_client.submit_order(req)
                    WSTradeLogger.write_logbook(f"[TRAILING TP] Scale-out 50% in profitto su {symbol} (Moonbag attivata).")
                elif action == "CLOSE_ALL":
                    logger.info(f"[WS] Trailing TP triggered for {symbol}! Closing remaining position.")
                    from alpaca.trading.requests import MarketOrderRequest
                    from alpaca.trading.enums import OrderSide, TimeInForce
                    
                    close_side = OrderSide.BUY if is_short else OrderSide.SELL
                    req = MarketOrderRequest(
                        symbol=check_symbol,
                        qty=abs(qty),
                        side=close_side,
                        time_in_force=TimeInForce.GTC
                    )
                    self._trading_client.submit_order(req)
                    WSTradeLogger.write_logbook(f"[TRAILING TP] Chiusura totale in profitto su {symbol} (Trail Hit).")
            except Exception:
                pass # No position
        except Exception as e:
            logger.error(f"[WS] Error in trailing stop manager: {e}")

    def _execute_order(self, symbol: str, price: float, change_pct: float,
                       bias_info: dict, is_short: bool = False, atr: float = 0.0) -> str:
        """
        Places a Bracket Order with dynamic TP/SL using the new execution components.
        """
        from config.config_manager import RiskConfigReader, RegimeConfigReader
        from execution.position_sizer import PositionSizer
        
        risk_config = RiskConfigReader.read()
        sentiment_score = bias_info.get("sentiment_score", 0.0)
        reasoning = bias_info.get("reasoning", "")
        bias_type = "BEARISH" if is_short else "BULLISH"
        
        is_crypto = symbol.endswith("USD")
        
        # L2 Wall Check
        imbalance = self.orderbook_analyzer.check_imbalance(symbol)
        if not is_short and imbalance == "BEARISH_WALL":
            logger.warning(f"[L2 FILTER] {symbol} has a huge BEARISH WALL. Skipping LONG execution.")
            return None
        if is_short and imbalance == "BULLISH_WALL":
            logger.warning(f"[L2 FILTER] {symbol} has a huge BULLISH WALL. Skipping SHORT execution.")
            return None

        # Crypto short block
        if is_short and is_crypto:
            logger.warning(f"[WS] Cannot short Crypto {symbol} on Alpaca. Skipping execution.")
            return None

        try:
            self._init_trading_client()
            account = self._trading_client.get_account()
            total_equity = float(account.equity)
            buying_power = float(account.buying_power)
        except Exception as e:
            logger.warning(f"[WS] Failed to get account info: {e}")
            total_equity = 10000.0
            buying_power = 10000.0

        size_usd = PositionSizer.calculate_micro_size(
            symbol, risk_config, total_equity, buying_power
        )

        if self.dry_run:
            logger.info(
                f"[WS DRY-RUN] Would {bias_type} ${size_usd:.2f} of {symbol} at ${price:.2f} "
                f"(Change: {change_pct:.2f}%, Bias: {bias_type}, Score: {sentiment_score:.2f}, ATR: {atr:.4f})"
            )
            return f"dry-ws-{int(time.time())}"

        try:
            self._init_trading_client()
            bands = self.bollinger_detector._calc_bands(symbol)
            sma_sl = bands["sma"] if bands else None
            
            regimes = RegimeConfigReader.read()
            symbol_regime = regimes.get(symbol, {}).get("regime", "UNKNOWN")
            
            order_data = OrderBuilder.build_order(
                symbol=symbol, price=price, size_usd=size_usd,
                is_crypto=is_crypto, is_short=is_short, atr=atr,
                sma_sl=sma_sl, config=risk_config, regime=symbol_regime
            )
            
            if self.order_executor is None:
                self.order_executor = OrderExecutor(self._trading_client, self.guard_mgr)
                
            order_id = self.order_executor.execute_order(
                order_request=order_data,
                price=price,
                size_usd=size_usd,
                change_pct=change_pct,
                bias_type=bias_type,
                sentiment_score=sentiment_score,
                reasoning=reasoning,
                is_short=is_short
            )
            return order_id
        except Exception as e:
            logger.error(f"[WS] Order execution setup failed for {symbol}: {e}")
            return None

    def on_bar(self, bar):
        """
        Called on each incoming 1-minute bar from the WebSocket stream.
        Delegates to BarProcessor and executes the returned actions.
        """
        symbol_raw = bar.symbol  # e.g. "BTC/USD"
        symbol = symbol_raw.replace("/", "")  # "BTCUSD"
        price = float(bar.close)
        bar_time = bar.timestamp if hasattr(bar, "timestamp") else datetime.now(timezone.utc)

        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)
            
        self.current_time = bar_time
        high = float(bar.high) if hasattr(bar, "high") else price
        low = float(bar.low) if hasattr(bar, "low") else price
        volume = float(bar.volume) if hasattr(bar, "volume") else 0.0
        
        WSTradeLogger.log_price(symbol, price, bar_time)
        self._manage_trailing_stops(price, symbol)

        actions = self.bar_processor.process_crypto_bar(
            symbol=symbol, price=price, bar_time=bar_time,
            high=high, low=low, volume=volume,
            alert_states=self.alert_states
        )
        
        for action in actions:
            if action["action"] == "CLOSE_ALL":
                try:
                    self._init_trading_client()
                    self._trading_client.close_position(action["symbol"])
                    WSTradeLogger.write_logbook(f"[EMERGENCY] Chiusura d'emergenza su {action['symbol']} completata.")
                    # Remove alert
                    if action["symbol"] in self.alert_states:
                        del self.alert_states[action["symbol"]]
                except Exception:
                    pass
            elif action["action"] == "EXECUTE":
                if EmergencyLiquidator.is_locked():
                    status = EmergencyLiquidator.get_status()
                    logger.warning(f"[EMERGENCY] Skipping EXECUTE on {action['symbol']} due to lockdown: {status}")
                    continue
                self._execute_order(
                    symbol=action["symbol"],
                    price=price,
                    change_pct=action.get("dip_pct", 0.0),
                    bias_info=action["bias_info"],
                    is_short=action["is_short"],
                    atr=action["atr"]
                )

    def on_stock_bar(self, bar):
        """
        Called on each incoming bar for stocks (QQQ).
        Delegates to BarProcessor and executes returned actions.
        """
        symbol = bar.symbol
        price = float(bar.close)
        bar_time = bar.timestamp if hasattr(bar, "timestamp") else datetime.now(timezone.utc)

        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)

        high = float(bar.high) if hasattr(bar, "high") else price
        low = float(bar.low) if hasattr(bar, "low") else price

        actions = self.bar_processor.process_stock_bar(
            symbol=symbol, price=price, bar_time=bar_time,
            high=high, low=low, target_symbols=self.target_symbols
        )
        
        for action in actions:
            if action["action"] == "EXECUTE":
                if EmergencyLiquidator.is_locked():
                    status = EmergencyLiquidator.get_status()
                    logger.warning(f"[EMERGENCY] Skipping EXECUTE on {action['symbol']} due to lockdown: {status}")
                    continue
                # We can't really execute short on QQQ here anyway, but it's passed as False
                self._execute_order(
                    symbol=action["symbol"],
                    price=action["price"],
                    change_pct=action.get("dip_pct", 0.0),
                    bias_info=action["bias_info"],
                    is_short=action["is_short"],
                    atr=action["atr"]
                )
                self._last_order_time[action["symbol"]] = datetime.now(timezone.utc)

    def _run_simulation(self):
        """Simulates incoming bars for testing, dry-runs, and credential-free modes."""
        logger.info("[WS SIMULATION] Starting real-time simulation loop (2s updates)...")
        
        prices = {"BTCUSD": 64000.00, "ETHUSD": 3200.00}
        
        class MockBar:
            def __init__(self, symbol, close, timestamp):
                self.symbol = symbol
                self.close = close
                self.timestamp = timestamp

            @property
            def symbol_normalized(self):
                return self.symbol.replace("/", "")

        import random
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def sim_loop():
            step = 0
            while True:
                step += 1
                for symbol in self.target_symbols:
                    current = prices.get(symbol, 100.0)
                    
                    # Every 12 steps (approx 24s), simulate a -0.65% DIP
                    if step % 12 == 0:
                        change = -0.0068
                        logger.info(f"[WS SIMULATION] Forcing DIP on {symbol}...")
                    else:
                        change = random.uniform(-0.0015, 0.0015)
                        
                    new_price = current * (1.0 + change)
                    prices[symbol] = new_price
                    
                    ws_sym = symbol.replace("BTCUSD", "BTC/USD").replace("ETHUSD", "ETH/USD")
                    bar = MockBar(ws_sym, new_price, datetime.now(timezone.utc))
                    
                    try:
                        self.on_bar(bar)
                        # Regenerate dashboard to show visual changes
                        pass
                    except Exception as ex:
                        logger.error(f"[WS SIMULATION] Error running bar handler: {ex}")
                        
                await asyncio.sleep(2)

        try:
            loop.run_until_complete(sim_loop())
        except KeyboardInterrupt:
            logger.info("[WS SIMULATION] Shutting down simulation gracefully.")

    def run(self, simulate: bool = False):
        """Starts the WebSocket stream or simulation loop and blocks indefinitely."""
        
        # Force use of CLI symbols to override AI macro bias
        self.target_symbols = [s.upper() for s in self.symbols]

        logger.info("=" * 60)
        logger.info("[WS] Starting Real-Time WebSocket Executor")
        logger.info(f"[WS] Mode: {'DRY-RUN' if self.dry_run else 'LIVE'} {'(SIMULATED)' if simulate else ''}")
        logger.info(f"[WS] Target Symbols: {self.target_symbols}")
        logger.info(f"[WS] DIP Threshold: {DIP_THRESHOLD_PCT}% over {DIP_WINDOW_SECONDS}s")
        logger.info(f"[WS] Order Cooldown: {ORDER_COOLDOWN_SECONDS}s")
        logger.info("=" * 60)

        if simulate:
            self._run_simulation()
            return

        from alpaca.data.live.crypto import CryptoDataStream
        from alpaca.data.live.stock import StockDataStream
        from alpaca.data.enums import DataFeed

        crypto_symbols_ws = []
        equity_symbols_ws = []
        
        for sym in self.target_symbols:
            if sym.endswith("USD"):
                crypto_symbols_ws.append(sym.replace("USD", "/USD"))
            else:
                equity_symbols_ws.append(sym)

        async def crypto_handler(bar):
            try:
                self._last_ws_msg_time = time.time()
                self.on_bar(bar)
            except Exception as e:
                from utils.error_handler import log_system_error
                log_system_error("WebSocket Crypto", e, f"Processing bar for {bar.symbol}")
            
            
        async def stock_handler(bar):
            try:
                if bar.symbol == "QQQ":
                    self.on_stock_bar(bar)
                if bar.symbol in self.target_symbols:
                    self.on_bar(bar)
            except Exception as e:
                from utils.error_handler import log_system_error
                log_system_error("WebSocket Stock", e, f"Processing bar for {bar.symbol}")

        if "QQQ" not in equity_symbols_ws:
            equity_symbols_ws.append("QQQ")
            
        def run_crypto():
            if not crypto_symbols_ws:
                return
            while True:
                try:
                    logger.info(f"[WS] Connecting to Alpaca CryptoDataStream for {crypto_symbols_ws}...")
                    self.crypto_stream = CryptoDataStream(APCA_API_KEY_ID, APCA_API_SECRET_KEY)
                    self.crypto_stream.subscribe_bars(crypto_handler, *crypto_symbols_ws)
                    
                    async def orderbook_handler(orderbook):
                        self._last_ws_msg_time = time.time()
                        self.orderbook_analyzer.update(orderbook.symbol, orderbook.bids, orderbook.asks)
                        
                    self.crypto_stream.subscribe_orderbooks(orderbook_handler, *crypto_symbols_ws)
                    
                    def watchdog_loop():
                        import os
                        while True:
                            time.sleep(10)
                            if time.time() - self._last_ws_msg_time > 600:
                                logger.warning("[WATCHDOG] No WS messages for 600 seconds. Connection might be silent.")
                                
                    threading.Thread(target=watchdog_loop, daemon=True).start()
                    
                    self.crypto_stream.run()
                except Exception as e:
                    logger.error(f"[WS] Crypto stream error: {e}")
                
                logger.info("[WS] Crypto stream closed. Reconnecting in 5 secondi...")
                time.sleep(5)

        def run_stock():
            if not equity_symbols_ws:
                return
            while True:
                try:
                    logger.info(f"[WS] Connecting to Alpaca StockDataStream for {equity_symbols_ws}...")
                    stock_stream = StockDataStream(APCA_API_KEY_ID, APCA_API_SECRET_KEY, feed=DataFeed.IEX)
                    stock_stream.subscribe_bars(stock_handler, *equity_symbols_ws)
                    stock_stream.run()
                except Exception as e:
                    logger.error(f"[WS] Stock stream error: {e}")
                
                logger.info("[WS] Stock stream closed. Reconnecting in 5 secondi...")
                time.sleep(5)

        def run_news():
            if not self.target_symbols:
                return
            while True:
                try:
                    logger.info("[WS] Connecting to Alpaca NewsDataStream...")
                    from alpaca.data.live.news import NewsDataStream
                    news_stream = NewsDataStream(APCA_API_KEY_ID, APCA_API_SECRET_KEY)
                    
                    async def news_handler(news):
                        try:
                            # Alpaca sends news.symbols like ['BTCUSD', 'ETHUSD', 'AAPL']
                            # Match them against our target symbols
                            symbols_in_news = [s for s in news.symbols if s.replace("/", "") in self.target_symbols or s in self.target_symbols]
                            if not symbols_in_news:
                                return
                                
                            logger.info(f"[NEWS INCOMING] {news.headline}")
                            eval_result = self.fast_guardian.evaluate_headline(news.headline)
                            
                            if eval_result != "IGNORE":
                                logger.critical(f"[GUARDIAN ALERT] {eval_result} detected for {symbols_in_news}!")
                                WSTradeLogger.write_logbook(f"ðŸš¨ [GUARDIAN ALERT] {eval_result}: {news.headline} ({symbols_in_news})")
                                now = datetime.now(timezone.utc)
                                for sym in symbols_in_news:
                                    self.alert_states[sym] = {"type": eval_result, "timestamp": now}
                        except Exception as e:
                            from utils.error_handler import log_system_error
                            log_system_error("WebSocket News", e, "Processing incoming news headline")
                    
                    # Subscribe to news for all target symbols
                    news_stream.subscribe_news(news_handler, *[s.replace("USD", "") for s in self.target_symbols] + self.target_symbols)
                    news_stream.run()
                except Exception as e:
                    logger.error(f"[WS] News stream error: {e}")
                time.sleep(5)
                
        def run_screener():
            # Only run screener if configured to do so
            risk_config = RiskConfigReader.read()
            if not risk_config.get("dynamic_asset_screener_enabled", True):
                return
                
            from data.asset_screener import DynamicAssetScreener
            screener = DynamicAssetScreener()
            
            while True:
                time.sleep(10) # Initial wait to let WS connect
                try:
                    new_symbols = screener.get_top_volatile_assets(limit=3)
                    if new_symbols:
                        old_crypto = [s for s in self.target_symbols if s.endswith("USD")]
                        new_crypto = [s for s in new_symbols if s.endswith("USD")]
                        
                        if set(old_crypto) != set(new_crypto):
                            logger.info(f"[SCREENER] Updating target crypto assets from {old_crypto} to {new_crypto}")
                            
                            # Update target_symbols
                            self.target_symbols = [s for s in self.target_symbols if not s.endswith("USD")] + new_crypto
                            
                            to_unsub = [s.replace("USD", "/USD") for s in old_crypto if s not in new_crypto]
                            to_sub = [s.replace("USD", "/USD") for s in new_crypto if s not in old_crypto]
                            
                            # Update crypto_symbols_ws so reconnects use new symbols
                            crypto_symbols_ws.clear()
                            crypto_symbols_ws.extend([s.replace("USD", "/USD") for s in new_crypto])
                            
                            # Update live stream if it exists
                            if hasattr(self, 'crypto_stream') and self.crypto_stream:
                                if to_unsub:
                                    self.crypto_stream.unsubscribe_bars(*to_unsub)
                                    self.crypto_stream.unsubscribe_orderbooks(*to_unsub)
                                if to_sub:
                                    self.crypto_stream.subscribe_bars(crypto_handler, *to_sub)
                                    self.crypto_stream.subscribe_orderbooks(orderbook_handler, *to_sub)
                except Exception as e:
                    logger.error(f"[SCREENER] Error: {e}")
                
                time.sleep(3600) # Re-screen every hour

        t_crypto = threading.Thread(target=run_crypto, daemon=True)
        t_stock = threading.Thread(target=run_stock, daemon=True)
        t_news = threading.Thread(target=run_news, daemon=True)
        t_screener = threading.Thread(target=run_screener, daemon=True)

        try:
            t_crypto.start()
            t_stock.start()
            t_news.start()
            t_screener.start()
            
            last_snap_time = time.time()
            while t_crypto.is_alive() or t_stock.is_alive() or t_news.is_alive():
                time.sleep(1)
                now_ts = time.time()
                if now_ts - last_snap_time > 60:
                    try:
                        from client.alpaca_client import AlpacaClientWrapper
                        from data.db import insert_portfolio_snap
                        
                        _temp_client = AlpacaClientWrapper()
                        _acc = _temp_client.get_account_info()
                        if _acc:
                            pos = _temp_client.get_positions()
                            crypto_eq = sum(float(p.market_value) for p in pos if getattr(p, "asset_class", "") == "crypto")
                            stock_eq = sum(float(p.market_value) for p in pos if getattr(p, "asset_class", "") != "crypto")
                            insert_portfolio_snap(datetime.now(timezone.utc).isoformat(), float(_acc.equity), float(_acc.buying_power), 0.0, 0.0, crypto_eq, stock_eq)
                        last_snap_time = now_ts
                    except Exception as e:
                        logger.debug(f"[WS] Failed to save periodic portfolio snap: {e}")
                
        except KeyboardInterrupt:
            logger.info("[WS] Shutting down WebSocket executor gracefully.")
        except Exception as e:
            logger.error(f"[WS] WebSocket thread manager error: {e}")
            WSTradeLogger.write_logbook(f"[WS ERROR] Thread manager disconnected: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(
        description="nano-trader-ai Hybrid Real-Time WebSocket Executor"
    )
    parser.add_argument("--dry-run", action="store_true", help="Log only, no orders.")
    parser.add_argument("--simulate", action="store_true", help="Simulate incoming price feeds.")
    parser.add_argument(
        "--symbols", nargs="+", default=["SOLUSD"],
        help="Symbols to monitor (default: BTCUSD ETHUSD)"
    )
    args = parser.parse_args()

    # Determine if we should simulate based on key placeholders
    is_placeholder = not APCA_API_KEY_ID or not APCA_API_SECRET_KEY or "YOUR_" in APCA_API_KEY_ID
    simulate_mode = args.simulate or is_placeholder

    if not args.dry_run and not simulate_mode:
        if not APCA_API_KEY_ID or not APCA_API_SECRET_KEY:
            logger.error("Alpaca credentials missing. Run with --dry-run or set env vars.")
            sys.exit(1)

    executor = RealtimeExecutor(
        symbols=[s.upper() for s in args.symbols],
        dry_run=args.dry_run
    )
    executor.run(simulate=simulate_mode)


if __name__ == "__main__":
    main()


