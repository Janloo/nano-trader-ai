#!/usr/bin/env python3
"""
realtime_executor.py — Hybrid Async Architecture: Micro (Fast) Process

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

from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY, logger

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
DIP_THRESHOLD_PCT = -0.5      # Minimum % drop to trigger a DIP signal
DIP_WINDOW_SECONDS = 300      # 5-minute rolling window
ORDER_COOLDOWN_SECONDS = 300  # 5 minutes between orders on same asset
BIAS_EXPIRY_HOURS = 2         # Bias older than this = NEUTRAL (stale)
NOTIONAL_USD = 5.00           # Order size per trigger

BIAS_FILE = os.path.join("data", "state", "market_bias.json")
TRADES_FILE_JSONL = os.path.join("data", "archives", "trades.jsonl")
WS_LOG_FILE = os.path.join("data", "state", "ws_triggers.json")
LOGBOOK_FILE = os.path.join("data", "archives", "human_logbook.txt")


# ─────────────────────────────────────────────
# BiasReader — Safe concurrent file reader
# ─────────────────────────────────────────────
class BiasReader:
    """Reads market_bias.json safely, handling concurrent writes and expiry."""

    @staticmethod
    def read() -> Dict:
        """Returns the current bias dict, or empty/NEUTRAL if stale or missing."""
        try:
            if not os.path.exists(BIAS_FILE):
                return {"target_assets": [], "expired": True}

            with open(BIAS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Check expiry
            expires_at_str = data.get("expires_at", "")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > expires_at:
                    logger.warning("[WS] Market bias is EXPIRED (>2h old). Treating as NEUTRAL.")
                    data["expired"] = True
                    return data

            data["expired"] = False
            return data

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[WS] Failed to parse market_bias.json (concurrent write?): {e}")
            return {"target_assets": [], "expired": True}
        except Exception as e:
            logger.error(f"[WS] Error reading market_bias.json: {e}")
            return {"target_assets": [], "expired": True}

    @staticmethod
    def get_bias_for_symbol(symbol: str) -> Dict:
        """Returns bias info for a specific symbol, or NEUTRAL defaults."""
        data = BiasReader.read()
        if data.get("expired", True):
            return {"bias": "NEUTRAL", "sentiment_score": 0.0, "reasoning": "Bias expired or unavailable."}

        for asset in data.get("target_assets", []):
            if asset.get("symbol") == symbol:
                return asset

        return {"bias": "NEUTRAL", "sentiment_score": 0.0, "reasoning": f"{symbol} not in current AI selection."}


# ─────────────────────────────────────────────
# DipDetector — Rolling window micro-fluctuation detector
# ─────────────────────────────────────────────
class DipDetector:
    """Tracks prices over a rolling window and detects DIP events."""

    def __init__(self, window_seconds: int = DIP_WINDOW_SECONDS,
                 dip_threshold_pct: float = DIP_THRESHOLD_PCT):
        self.window_seconds = window_seconds
        self.dip_threshold_pct = dip_threshold_pct
        # {symbol: deque of (timestamp_utc, price)}
        self._prices: Dict[str, deque] = {}

    def update(self, symbol: str, price: float, timestamp: datetime) -> Optional[float]:
        """
        Records a new price point. Returns the % change from the window high
        if a DIP is detected, otherwise None.
        """
        if symbol not in self._prices:
            self._prices[symbol] = deque()

        window = self._prices[symbol]
        window.append((timestamp, price))

        # Prune entries older than the window
        cutoff = timestamp - timedelta(seconds=self.window_seconds)
        while window and window[0][0] < cutoff:
            window.popleft()

        if len(window) < 2:
            return None

        # Calculate % change from window high
        window_high = max(p for _, p in window)
        if window_high <= 0:
            return None

        pct_change = ((price - window_high) / window_high) * 100.0

        if pct_change <= self.dip_threshold_pct:
            return pct_change

        return None


# ─────────────────────────────────────────────
# Trade Logger — Writes to trades.json and ws_triggers.json
# ─────────────────────────────────────────────
class WSTradeLogger:
    """Logs WebSocket-triggered trades to the shared trades.json and ws_triggers.json."""

    @staticmethod
    def log_trigger(symbol: str, price: float, dip_pct: float,
                    bias: str, sentiment_score: float, reasoning: str,
                    order_id: str, executed: bool):
        """Logs a DIP trigger event to ws_triggers.json."""
        os.makedirs(os.path.dirname(WS_LOG_FILE), exist_ok=True)
        try:
            triggers = []
            if os.path.exists(WS_LOG_FILE):
                with open(WS_LOG_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        triggers = json.loads(content)

            triggers.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "price": price,
                "dip_pct": round(dip_pct, 4),
                "bias": bias,
                "sentiment_score": sentiment_score,
                "reasoning": reasoning,
                "order_id": order_id,
                "executed": executed
            })

            # Keep only last 200 entries
            triggers = triggers[-200:]
            with open(WS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(triggers, f, indent=4)
        except Exception as e:
            logger.error(f"[WS] Failed to log trigger: {e}")

    @staticmethod
    def log_trade(symbol: str, price: float, qty: float, order_id: str,
                  sentiment_score: float, reasoning: str, dip_pct: float):
        """Appends a WebSocket-triggered trade to trades.jsonl."""
        os.makedirs(os.path.dirname(TRADES_FILE_JSONL), exist_ok=True)
        try:
            trade_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "order_id": order_id,
                "symbol": symbol,
                "side": "BUY",
                "qty": qty,
                "notional": NOTIONAL_USD,
                "price": price,
                "sentiment_score": sentiment_score,
                "reasoning": reasoning,
                "execution_type": "hybrid_websocket_trigger",
                "dip_pct": round(dip_pct, 4),
                "das_selected": True,
                "das_reasoning": reasoning
            }

            with open(TRADES_FILE_JSONL, "a", encoding="utf-8") as f:
                f.write(json.dumps(trade_data) + "\n")
        except Exception as e:
            logger.error(f"[WS] Failed to log trade: {e}")

    @staticmethod
    def write_logbook(msg: str):
        """Writes to human_logbook.txt."""
        os.makedirs(os.path.dirname(LOGBOOK_FILE), exist_ok=True)
        try:
            with open(LOGBOOK_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except Exception:
            pass

    @staticmethod
    def log_price(symbol: str, price: float, timestamp: datetime):
        """Logs a price point to data/realtime_price_history.json, keeping the last 200 points."""
        history_file = os.path.join("data", "state", "realtime_price_history.json")
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        try:
            history = {}
            if os.path.exists(history_file):
                with open(history_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        history = json.loads(content)
            
            if symbol not in history:
                history[symbol] = []
                
            history[symbol].append({
                "timestamp": timestamp.isoformat(),
                "price": price
            })
            
            # Keep last 200 points
            history[symbol] = history[symbol][-200:]
            
            # Write atomically
            tmp_path = history_file + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
            os.replace(tmp_path, history_file)
        except Exception as e:
            logger.error(f"[WS] Failed to log price history: {e}")


# ─────────────────────────────────────────────
# WebSocket Executor — Main process
# ─────────────────────────────────────────────
class RealtimeExecutor:
    """
    Connects to Alpaca CryptoDataStream, monitors prices, and executes
    DIP-based trades when the macro AI bias is BULLISH.
    """

    def __init__(self, symbols: List[str], dry_run: bool = False):
        self.symbols = symbols
        self.dry_run = dry_run
        self.dip_detector = DipDetector()
        self._last_order_time: Dict[str, datetime] = {}
        self._trading_client = None

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

    def _is_on_cooldown(self, symbol: str) -> bool:
        """Returns True if the symbol is in cooldown (order placed recently)."""
        last = self._last_order_time.get(symbol)
        if last is None:
            return False
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed < ORDER_COOLDOWN_SECONDS

    def _execute_order(self, symbol: str, price: float, dip_pct: float,
                       bias_info: Dict) -> Optional[str]:
        """Places a $5 fractional market buy order."""
        sentiment_score = bias_info.get("sentiment_score", 0.0)
        reasoning = bias_info.get("reasoning", "")

        if self.dry_run:
            order_id = f"dry-ws-{int(time.time())}"
            logger.info(
                f"[WS DRY-RUN] Would BUY ${NOTIONAL_USD} of {symbol} at ${price:.2f} "
                f"(DIP: {dip_pct:.2f}%, Bias: BULLISH, Score: {sentiment_score:.2f})"
            )
        else:
            try:
                self._init_trading_client()
                from alpaca.trading.requests import MarketOrderRequest
                from alpaca.trading.enums import OrderSide, TimeInForce

                order_symbol = symbol.replace("BTCUSD", "BTC/USD").replace("ETHUSD", "ETH/USD")
                order_data = MarketOrderRequest(
                    symbol=order_symbol,
                    notional=NOTIONAL_USD,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )
                order = self._trading_client.submit_order(order_data)
                order_id = str(order.id)

                # Update price from fill if available
                if getattr(order, "filled_avg_price", None):
                    try:
                        price = float(order.filled_avg_price)
                    except (ValueError, TypeError):
                        pass

                logger.info(
                    f"[WS TRIGGER] BUY ${NOTIONAL_USD} of {symbol} EXECUTED! "
                    f"Price: ${price:.2f} | DIP: {dip_pct:.2f}% | Order: {order_id}"
                )
            except Exception as e:
                logger.error(f"[WS] Order execution failed for {symbol}: {e}")
                WSTradeLogger.write_logbook(
                    f"[WS ERROR] Ordine fallito su {symbol}: {e}"
                )
                WSTradeLogger.log_trigger(
                    symbol, price, dip_pct, "BULLISH", sentiment_score,
                    reasoning, "FAILED", False
                )
                return None

        # Log the trade
        qty = NOTIONAL_USD / price if price > 0 else 0.0
        WSTradeLogger.log_trade(symbol, price, qty, order_id, sentiment_score, reasoning, dip_pct)
        WSTradeLogger.log_trigger(symbol, price, dip_pct, "BULLISH", sentiment_score, reasoning, order_id, True)
        WSTradeLogger.write_logbook(
            f"[WS TRIGGER] BUY ${NOTIONAL_USD} di {symbol} a ${price:.2f} (DIP: {dip_pct:.2f}%, AI Bias: BULLISH)"
        )

        # Send Telegram notification
        try:
            from notifications.telegram_notifier import notify_trade_executed
            notify_trade_executed(
                symbol=symbol, action="BUY", notional=NOTIONAL_USD,
                price=price, sentiment_score=sentiment_score,
                reasoning=f"WebSocket DIP Trigger ({dip_pct:.2f}%): {reasoning}",
                order_id=order_id
            )
        except Exception:
            pass

        # Set cooldown
        self._last_order_time[symbol] = datetime.now(timezone.utc)
        return order_id

    def on_bar(self, bar):
        """
        Called on each incoming 1-minute bar from the WebSocket stream.
        Evaluates DIP + Bias conditions and triggers orders.
        """
        symbol_raw = bar.symbol  # e.g. "BTC/USD"
        # Normalize symbol back to our format
        symbol = symbol_raw.replace("/", "")  # "BTCUSD"
        price = float(bar.close)
        bar_time = bar.timestamp if hasattr(bar, "timestamp") else datetime.now(timezone.utc)

        # Ensure timezone-aware
        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)

        # Log streaming price for the real-time dashboard chart
        WSTradeLogger.log_price(symbol, price, bar_time)

        # Update DIP detector
        dip_pct = self.dip_detector.update(symbol, price, bar_time)

        if dip_pct is not None:
            logger.info(
                f"[WS DIP] {symbol} dropped {dip_pct:.2f}% in {DIP_WINDOW_SECONDS}s "
                f"window. Price: ${price:.2f}"
            )

            # Check cooldown
            if self._is_on_cooldown(symbol):
                logger.info(f"[WS] {symbol} is on cooldown — skipping trigger.")
                WSTradeLogger.log_trigger(
                    symbol, price, dip_pct, "COOLDOWN", 0.0, "Cooldown active", "", False
                )
                return

            # Read AI bias
            bias_info = BiasReader.get_bias_for_symbol(symbol)
            bias = bias_info.get("bias", "NEUTRAL")
            sentiment_score = bias_info.get("sentiment_score", 0.0)

            logger.info(f"[WS] {symbol} bias check: {bias} (score: {sentiment_score:.2f})")

            if bias == "BULLISH" and sentiment_score >= 0.75:
                # TRIGGER! DIP + BULLISH = BUY
                logger.info(f"[WS TRIGGER] DIP + BULLISH confirmed for {symbol}! Executing order...")
                self._execute_order(symbol, price, dip_pct, bias_info)
            else:
                logger.info(f"[WS] {symbol} DIP detected but bias is {bias} — ignoring.")
                WSTradeLogger.log_trigger(
                    symbol, price, dip_pct, bias, sentiment_score,
                    bias_info.get("reasoning", ""), "", False
                )

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
                for symbol in self.symbols:
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
                        from reporting.generator import generate_dashboard
                        generate_dashboard()
                    except Exception as ex:
                        logger.error(f"[WS SIMULATION] Error running bar handler: {ex}")
                        
                await asyncio.sleep(2)

        try:
            loop.run_until_complete(sim_loop())
        except KeyboardInterrupt:
            logger.info("[WS SIMULATION] Shutting down simulation gracefully.")

    def run(self, simulate: bool = False):
        """Starts the WebSocket stream or simulation loop and blocks indefinitely."""
        logger.info("=" * 60)
        logger.info("[WS] Starting Real-Time WebSocket Executor")
        logger.info(f"[WS] Mode: {'DRY-RUN' if self.dry_run else 'LIVE'} {'(SIMULATED)' if simulate else ''}")
        logger.info(f"[WS] Symbols: {self.symbols}")
        logger.info(f"[WS] DIP Threshold: {DIP_THRESHOLD_PCT}% over {DIP_WINDOW_SECONDS}s")
        logger.info(f"[WS] Order Cooldown: {ORDER_COOLDOWN_SECONDS}s")
        logger.info("=" * 60)

        if simulate:
            self._run_simulation()
            return

        from alpaca.data.live.crypto import CryptoDataStream

        # Map symbols to Alpaca format
        ws_symbols = [s.replace("BTCUSD", "BTC/USD").replace("ETHUSD", "ETH/USD") for s in self.symbols]

        stream = CryptoDataStream(APCA_API_KEY_ID, APCA_API_SECRET_KEY)

        async def bar_handler(bar):
            self.on_bar(bar)

        stream.subscribe_bars(bar_handler, *ws_symbols)

        logger.info(f"[WS] Connecting to Alpaca CryptoDataStream for {ws_symbols}...")
        try:
            stream.run()
        except KeyboardInterrupt:
            logger.info("[WS] Shutting down WebSocket executor gracefully.")
        except Exception as e:
            # Fall back to simulation if auth failed
            if "auth failed" in str(e).lower() or "authentication" in str(e).lower():
                logger.warning("[WS] Authentication failed! Falling back to --simulate mode automatically.")
                self._run_simulation()
            else:
                logger.error(f"[WS] WebSocket stream error: {e}")
                WSTradeLogger.write_logbook(f"[WS ERROR] Stream disconnected: {e}")
                raise


def main():
    parser = argparse.ArgumentParser(
        description="nano-trader-ai Hybrid Real-Time WebSocket Executor"
    )
    parser.add_argument("--dry-run", action="store_true", help="Log only, no orders.")
    parser.add_argument("--simulate", action="store_true", help="Simulate incoming price feeds.")
    parser.add_argument(
        "--symbols", nargs="+", default=["BTCUSD", "ETHUSD"],
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
