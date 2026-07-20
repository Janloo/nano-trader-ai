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
import threading
import logging

from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY, logger

# Suppress noisy asyncio/websockets tracebacks during reconnections
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("websockets").setLevel(logging.CRITICAL)

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
DIP_THRESHOLD_PCT = -0.50      # Minimum % drop to trigger a DIP signal
SPIKE_THRESHOLD_PCT = 0.50     # Minimum % rise to trigger a SPIKE signal
DIP_WINDOW_SECONDS = 300      # 5-minute rolling window
ORDER_COOLDOWN_SECONDS = 300  # 5 minutes between orders on same asset
BIAS_EXPIRY_HOURS = 72        # Temporarily extended for the weekend
NOTIONAL_USD = 10.00          # Fallback static order size

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
# RiskConfigReader
# ─────────────────────────────────────────────
class RiskConfigReader:
    @staticmethod
    def read() -> Dict:
        try:
            path = os.path.join("config", "risk_settings.json")
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[WS] Error reading risk_settings.json: {e}")
            return {}

class RegimeConfigReader:
    @staticmethod
    def read() -> Dict:
        try:
            path = os.path.join("data", "state", "market_regime.json")
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {}

# ─────────────────────────────────────────────
# VolatilityDetector — Rolling window micro-fluctuation detector
# ─────────────────────────────────────────────
class VolatilityDetector:
    """Tracks prices over a rolling window and detects DIP and SPIKE events."""

    def __init__(self, window_seconds: int = DIP_WINDOW_SECONDS,
                 dip_threshold_pct: float = DIP_THRESHOLD_PCT,
                 spike_threshold_pct: float = SPIKE_THRESHOLD_PCT):
        self.window_seconds = window_seconds
        self.dip_threshold_pct = dip_threshold_pct
        self.spike_threshold_pct = spike_threshold_pct
        # {symbol: deque of (timestamp_utc, price)}
        self._prices: Dict[str, deque] = {}

    def update(self, symbol: str, price: float, timestamp: datetime,
               dynamic_dip_pct: float = None, dynamic_spike_pct: float = None):
        """
        Records a new price point. Returns (dip_pct, spike_pct).
        dip_pct is the % change from window high if <= dip_threshold_pct.
        spike_pct is the % change from window low if >= spike_threshold_pct.
        """
        active_dip_threshold = dynamic_dip_pct if dynamic_dip_pct is not None else self.dip_threshold_pct
        active_spike_threshold = dynamic_spike_pct if dynamic_spike_pct is not None else self.spike_threshold_pct
        if symbol not in self._prices:
            self._prices[symbol] = deque()

        window = self._prices[symbol]
        window.append((timestamp, price))

        # Prune entries older than the window
        cutoff = timestamp - timedelta(seconds=self.window_seconds)
        while window and window[0][0] < cutoff:
            window.popleft()

        if len(window) < 2:
            return None, None

        # Calculate % change from window high (DIP)
        window_high = max(p for _, p in window)
        dip_pct = None
        if window_high > 0:
            pct_change_high = ((price - window_high) / window_high) * 100.0
            if pct_change_high <= active_dip_threshold:
                dip_pct = pct_change_high

        # Calculate % change from window low (SPIKE)
        window_low = min(p for _, p in window)
        spike_pct = None
        if window_low > 0:
            pct_change_low = ((price - window_low) / window_low) * 100.0
            if pct_change_low >= active_spike_threshold:
                spike_pct = pct_change_low

        return dip_pct, spike_pct

# ─────────────────────────────────────────────
# IndicatorManager — ATR & RSI Calculation
# ─────────────────────────────────────────────
class IndicatorManager:
    """Calculates ATR and RSI from incoming OHLC bars."""
    def __init__(self, period=14):
        self.period = period
        self._bars: Dict[str, deque] = {}

    def update(self, symbol: str, high: float, low: float, close: float):
        if symbol not in self._bars:
            self._bars[symbol] = deque(maxlen=self.period + 1)
        self._bars[symbol].append({"high": high, "low": low, "close": close})

    def get_last_price(self, symbol: str) -> Optional[float]:
        if symbol in self._bars and len(self._bars[symbol]) > 0:
            return self._bars[symbol][-1]["close"]
        return None

    def get_atr(self, symbol: str) -> Optional[float]:
        bars = self._bars.get(symbol, [])
        if len(bars) < self.period + 1:
            return None
        
        trs = []
        for i in range(1, len(bars)):
            prev_close = bars[i-1]["close"]
            h = bars[i]["high"]
            l = bars[i]["low"]
            tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
            trs.append(tr)
        return sum(trs[-self.period:]) / self.period

    def get_rsi(self, symbol: str) -> Optional[float]:
        bars = self._bars.get(symbol, [])
        if len(bars) < self.period + 1:
            return None

        gains = []
        losses = []
        for i in range(1, len(bars)):
            change = bars[i]["close"] - bars[i-1]["close"]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
                
        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period
        
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

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

    def _calculate_position_size(self, symbol: str, price: float, sentiment_score: float, atr: float = 0.0, risk_config: Dict = None) -> float:
        """Calculates the position size dynamically based on risk configuration and AI confidence."""
        fallback = NOTIONAL_USD
        if self.dry_run:
            return fallback

        if not risk_config:
            risk_config = {}

        try:
            self._init_trading_client()
            account = self._trading_client.get_account()
            bp = float(account.buying_power)
            total_equity = float(account.equity)
            
            max_capital_pct = risk_config.get("max_capital_per_trade_pct", 0.05)
            max_risk_pct = risk_config.get("max_risk_per_trade_pct", 0.01)
            atr_sl_mult = risk_config.get("atr_stop_loss_multiplier", 2.0)
            
            # 1. Calculate the stop loss distance
            if atr > 0 and price > 0:
                sl_distance_pct = (atr * atr_sl_mult) / price
            else:
                sl_distance_pct = 0.015 # fallback 1.5% stop loss
                
            # 2. Risk Amount ($)
            risk_amount_usd = total_equity * max_risk_pct
            
            # 3. Position Size ($) based on risk
            position_size_usd = risk_amount_usd / sl_distance_pct if sl_distance_pct > 0 else 0
            
            # 4. Apply maximum capital cap
            max_capital_usd = bp * max_capital_pct
            allocation = min(position_size_usd, max_capital_usd)
            
            # 5. Modulate by sentiment score (0.75 -> 50% of allocation, 1.0 -> 100% of allocation)
            score_abs = min(max(abs(sentiment_score), 0.75), 1.0)
            modulation = 0.5 + 0.5 * ((score_abs - 0.75) / 0.25)
            
            final_allocation = allocation * modulation
            
            logger.info(f"[RISK CALC] Equity: {total_equity}, Risk Amt: {risk_amount_usd}, SL Dist: {sl_distance_pct:.4f}, Calc Pos: {position_size_usd:.2f}, Final Alloc: {final_allocation:.2f}")
            return max(final_allocation, 5.0)
        except Exception as e:
            logger.warning(f"[WS] Failed to calculate dynamic size: {e}. Using fallback ${fallback}")
            return fallback

    def _execute_order(self, symbol: str, price: float, change_pct: float,
                       bias_info: Dict, is_short: bool = False, atr: float = 0.0) -> Optional[str]:
        """Places a Bracket Order with dynamic TP/SL."""
        sentiment_score = bias_info.get("sentiment_score", 0.0)
        reasoning = bias_info.get("reasoning", "")
        bias_type = "BEARISH" if is_short else "BULLISH"
        
        # Determine asset class
        is_crypto = symbol.endswith("USD")
        
        if is_short and is_crypto:
            logger.warning(f"[WS] Cannot short Crypto {symbol} on Alpaca. Skipping execution.")
            WSTradeLogger.write_logbook(f"[WS INFO] Salto lo Short su Crypto {symbol} (non supportato).")
            return None

        risk_config = RiskConfigReader.read()
        
        # Check max open positions (anti-spam)
        try:
            self._init_trading_client()
            max_open = risk_config.get("max_open_positions_per_asset", 1)
            
            check_symbol = symbol.replace("USD", "/USD") if (is_crypto and "USD" in symbol) else symbol
            
            try:
                open_pos = self._trading_client.get_open_position(check_symbol)
                if float(open_pos.qty) != 0 and max_open <= 1:
                    logger.warning(f"[WS] Already have an open position for {check_symbol}. Skipping order.")
                    return None
            except Exception as e:
                pass # Usually implies no open position
        except Exception as e:
            logger.warning(f"[WS] Error checking open positions: {e}")

        size_usd = self._calculate_position_size(symbol, price, sentiment_score, atr, risk_config)

        if self.dry_run:
            order_id = f"dry-ws-{int(time.time())}"
            side_str = "SHORT" if is_short else "BUY"
            logger.info(
                f"[WS DRY-RUN] Would {side_str} ${size_usd:.2f} of {symbol} at ${price:.2f} "
                f"(Change: {change_pct:.2f}%, Bias: {bias_type}, Score: {sentiment_score:.2f}, ATR: {atr:.4f})"
            )
        else:
            try:
                self._init_trading_client()
                from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
                from alpaca.trading.enums import OrderSide, TimeInForce
                
                atr_tp_mult = risk_config.get("atr_take_profit_multiplier", 3.0)
                atr_sl_mult = risk_config.get("atr_stop_loss_multiplier", 2.0)

                # Determine dynamic TP multiplier from regime if passed
                regimes = RegimeConfigReader.read()
                symbol_regime = regimes.get(symbol, {}).get("regime", "UNKNOWN")
                if symbol_regime == "BULL_TREND" and not is_short:
                    atr_tp_mult = max(atr_tp_mult, 3.5) # Wider TP in strong uptrend
                elif symbol_regime == "RANGING":
                    atr_tp_mult = min(atr_tp_mult, 1.5) # Scalp TP in ranging market
                    
                # Dynamic TP/SL using ATR if available, else fallback
                if atr > 0:
                    if is_short:
                        tp_price = round(price - (atr_tp_mult * atr), 2)
                        sl_price = round(price + (atr_sl_mult * atr), 2)
                        side = OrderSide.SELL
                    else:
                        tp_price = round(price + (atr_tp_mult * atr), 2)
                        sl_price = round(price - (atr_sl_mult * atr), 2)
                        side = OrderSide.BUY
                else:
                    if is_short:
                        tp_price = round(price * 0.975, 2)
                        sl_price = round(price * 1.015, 2)
                        side = OrderSide.SELL
                    else:
                        tp_price = round(price * 1.025, 2)
                        sl_price = round(price * 0.985, 2)
                        side = OrderSide.BUY

                if is_crypto and "USD" in symbol and "/" not in symbol:
                    order_symbol = symbol.replace("USD", "/USD")
                else:
                    order_symbol = symbol
                
                qty = size_usd / price if price > 0 else 0.0
                qty = round(qty, 4) if is_crypto else round(qty, 2)

                order_data = MarketOrderRequest(
                    symbol=order_symbol,
                    qty=qty,
                    side=side,
                    time_in_force=TimeInForce.GTC,
                    take_profit=TakeProfitRequest(limit_price=tp_price),
                    stop_loss=StopLossRequest(stop_price=sl_price)
                )
                order = self._trading_client.submit_order(order_data)
                order_id = str(order.id)

                # Update price from fill if available
                if getattr(order, "filled_avg_price", None):
                    try:
                        price = float(order.filled_avg_price)
                    except (ValueError, TypeError):
                        pass

                side_str = "SHORT" if is_short else "BUY"
                logger.info(
                    f"[WS TRIGGER] {side_str} ${size_usd:.2f} of {symbol} EXECUTED! "
                    f"Price: ${price:.2f} | Change: {change_pct:.2f}% | Order: {order_id}"
                )
            except Exception as e:
                logger.error(f"[WS] Order execution failed for {symbol}: {e}")
                WSTradeLogger.write_logbook(f"[WS ERROR] Ordine fallito su {symbol}: {e}")
                WSTradeLogger.log_trigger(symbol, price, change_pct, bias_type, sentiment_score, reasoning, "FAILED", False)
                return None

        # Log the trade
        qty = size_usd / price if price > 0 else 0.0
        side_str = "SELL" if is_short else "BUY"
        WSTradeLogger.log_trade(symbol, price, qty, order_id, sentiment_score, reasoning, change_pct)
        WSTradeLogger.log_trigger(symbol, price, change_pct, bias_type, sentiment_score, reasoning, order_id, True)
        WSTradeLogger.write_logbook(
            f"[WS TRIGGER] {side_str} ${size_usd:.2f} di {symbol} a ${price:.2f} (Change: {change_pct:.2f}%, AI Bias: {bias_type})"
        )

        # Send Telegram notification
        try:
            from notifications.telegram_notifier import notify_trade_executed
            notify_trade_executed(
                symbol=symbol, action=side_str, notional=size_usd,
                price=price, sentiment_score=sentiment_score,
                reasoning=f"WebSocket Trigger ({change_pct:.2f}%): {reasoning}",
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
        Evaluates DIP/SPIKE + Bias conditions and triggers orders.
        """
        symbol_raw = bar.symbol  # e.g. "BTC/USD"
        # Normalize symbol back to our format
        symbol = symbol_raw.replace("/", "")  # "BTCUSD"
        price = float(bar.close)
        bar_time = bar.timestamp if hasattr(bar, "timestamp") else datetime.now(timezone.utc)

        # Ensure timezone-aware
        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)

        # Update Indicator Manager with OHLC
        high = float(bar.high) if hasattr(bar, "high") else price
        low = float(bar.low) if hasattr(bar, "low") else price
        self.indicator_mgr.update(symbol, high, low, price)

        # Check Warm-up
        atr = self.indicator_mgr.get_atr(symbol)
        rsi = self.indicator_mgr.get_rsi(symbol)
        
        if atr is None or rsi is None:
            # Silent return during 14-min warmup
            return

        # Log streaming price for the real-time dashboard chart
        WSTradeLogger.log_price(symbol, price, bar_time)

        # Read Regime and adjust DIP threshold dynamically
        regimes = RegimeConfigReader.read()
        regime_data = regimes.get(symbol, {})
        regime = regime_data.get("regime", "UNKNOWN")
        
        dynamic_dip = DIP_THRESHOLD_PCT # default -0.5
        if regime == "BULL_TREND":
            dynamic_dip = -0.25 # Catch shallow dips
        elif regime == "RANGING":
            dynamic_dip = -0.60 # Wait for deeper dips
        elif regime == "BEAR_TREND":
            dynamic_dip = -1.20 # Extreme capitulation only
            
        # Update Volatility detector with dynamic threshold
        dip_pct, spike_pct = self.vol_detector.update(symbol, price, bar_time, dynamic_dip_pct=dynamic_dip)

        if dip_pct is not None or spike_pct is not None:
            if dip_pct is not None:
                logger.info(f"[WS DIP] {symbol} dropped {dip_pct:.2f}% in {DIP_WINDOW_SECONDS}s. Price: ${price:.2f}")
            if spike_pct is not None:
                logger.info(f"[WS SPIKE] {symbol} jumped {spike_pct:.2f}% in {DIP_WINDOW_SECONDS}s. Price: ${price:.2f}")

            # Check cooldown
            if self._is_on_cooldown(symbol):
                logger.info(f"[WS] {symbol} is on cooldown — skipping trigger.")
                # Pass 0.0 for change_pct just to log
                WSTradeLogger.log_trigger(symbol, price, dip_pct or spike_pct or 0.0, "COOLDOWN", 0.0, "Cooldown active", "", False)
                return

            # Read AI bias
            bias_info = BiasReader.get_bias_for_symbol(symbol)
            bias = bias_info.get("bias", "NEUTRAL")
            sentiment_score = bias_info.get("sentiment_score", 0.0)

            logger.info(f"[WS] {symbol} bias check: {bias} (score: {sentiment_score:.2f})")

            # Logic 1: DIP + BULLISH = BUY
            if dip_pct is not None and bias == "BULLISH" and sentiment_score >= 0.75:
                if rsi > 70:
                    logger.info(f"[WS FILTER] {symbol} RSI is {rsi:.2f} (>70). Skipping BUY to avoid overbought entry.")
                    return
                logger.info(f"[WS TRIGGER] DIP + BULLISH confirmed for {symbol}! Executing BUY order...")
                self._execute_order(symbol, price, dip_pct, bias_info, is_short=False, atr=atr)
            
            # Logic 2: SPIKE + BEARISH = SHORT
            elif spike_pct is not None and bias == "BEARISH" and sentiment_score <= -0.75:
                logger.info(f"[WS TRIGGER] SPIKE + BEARISH confirmed for {symbol}! Executing SHORT order...")
                self._execute_order(symbol, price, spike_pct, bias_info, is_short=True, atr=atr)
            
            else:
                change = dip_pct if dip_pct is not None else spike_pct
                logger.info(f"[WS] {symbol} fluctuation detected but bias is {bias} — ignoring.")
                WSTradeLogger.log_trigger(
                    symbol, price, change, bias, sentiment_score,
                    bias_info.get("reasoning", ""), "", False
                )

    def on_stock_bar(self, bar):
        """
        Called on each incoming bar for stocks (QQQ).
        Detects +0.25% spikes and triggers crypto LEAD-LAG buying.
        """
        symbol = bar.symbol
        price = float(bar.close)
        bar_time = bar.timestamp if hasattr(bar, "timestamp") else datetime.now(timezone.utc)

        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)

        # Update Indicator Manager with OHLC
        high = float(bar.high) if hasattr(bar, "high") else price
        low = float(bar.low) if hasattr(bar, "low") else price
        self.indicator_mgr.update(symbol, high, low, price)

        dip_pct, spike_pct = self.vol_detector.update(symbol, price, bar_time)

        # QQQ Lead-Lag Trigger threshold is +0.25%
        if spike_pct is not None and spike_pct >= 0.25:
            logger.info(f"[WS LEAD-LAG] {symbol} jumped {spike_pct:.2f}% in {DIP_WINDOW_SECONDS}s. Price: ${price:.2f}")

            # Cross-Asset Check: if QQQ spikes, look for BULLISH targets
            for target_sym in self.target_symbols:
                if self._is_on_cooldown(target_sym):
                    continue
                
                # Check warm-up status of the target asset
                atr = self.indicator_mgr.get_atr(target_sym)
                rsi = self.indicator_mgr.get_rsi(target_sym)
                target_price = self.indicator_mgr.get_last_price(target_sym)
                
                if atr is None or rsi is None or target_price is None:
                    continue

                bias_info = BiasReader.get_bias_for_symbol(target_sym)
                bias = bias_info.get("bias", "NEUTRAL")
                sentiment_score = bias_info.get("sentiment_score", 0.0)

                if bias == "BULLISH" and sentiment_score >= 0.75:
                    if rsi > 70:
                        logger.info(f"[WS FILTER] {target_sym} RSI is {rsi:.2f} (>70). Skipping Lead-Lag BUY.")
                        continue
                        
                    logger.info(f"[WS LEAD-LAG TRIGGER] QQQ Spike + BULLISH {target_sym} confirmed! Executing anticipatory BUY order...")
                    
                    # Execute on the target symbol
                    self._execute_order(target_sym, target_price, spike_pct, bias_info, is_short=False, atr=atr)
                    
                    # Prevent multiple executions immediately
                    self._last_order_time[target_sym] = datetime.now(timezone.utc)

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
        
        bias_data = BiasReader.read()
        target_assets = bias_data.get("target_assets", [])
        
        if not target_assets:
            logger.warning("[WS] No targets found in AI bias. Falling back to default crypto targets.")
            self.target_symbols = [s.upper() for s in self.symbols]
        else:
            self.target_symbols = [asset["symbol"].upper() for asset in target_assets]

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
            self.on_bar(bar)
            
        async def stock_handler(bar):
            if bar.symbol == "QQQ":
                self.on_stock_bar(bar)
            if bar.symbol in self.target_symbols:
                self.on_bar(bar)

        if "QQQ" not in equity_symbols_ws:
            equity_symbols_ws.append("QQQ")
            
        def run_crypto():
            if not crypto_symbols_ws:
                return
            while True:
                try:
                    logger.info(f"[WS] Connecting to Alpaca CryptoDataStream for {crypto_symbols_ws}...")
                    crypto_stream = CryptoDataStream(APCA_API_KEY_ID, APCA_API_SECRET_KEY)
                    crypto_stream.subscribe_bars(crypto_handler, *crypto_symbols_ws)
                    crypto_stream.run()
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

        t_crypto = threading.Thread(target=run_crypto, daemon=True)
        t_stock = threading.Thread(target=run_stock, daemon=True)

        try:
            t_crypto.start()
            t_stock.start()
            
            # Keep main thread alive while streams run in background
            while t_crypto.is_alive() or t_stock.is_alive():
                time.sleep(1)
                
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
