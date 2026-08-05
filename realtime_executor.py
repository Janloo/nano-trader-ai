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
from strategy.bollinger_squeeze import BollingerSqueezeDetector

# Suppress noisy asyncio/websockets tracebacks during reconnections
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("websockets").setLevel(logging.CRITICAL)

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
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
from config.config_manager import config_manager, RiskSettings
import dataclasses

class RiskConfigReader:
    @staticmethod
    def read() -> Dict:
        try:
            settings = config_manager.load_risk_settings()
            return dataclasses.asdict(settings)
        except Exception as e:
            logger.error(f"[CONFIG] Error reading risk config: {e}")
            return dataclasses.asdict(RiskSettings())

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
        # {symbol: dict for trailing state}
        self._trailing_state: Dict[str, dict] = {}

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
            return None, None, None

        if symbol not in self._trailing_state:
            self._trailing_state[symbol] = {"active": False, "lowest": float('inf'), "dip_pct": 0.0, "window_high": 0.0}
        t_state = self._trailing_state[symbol]

        # Calculate % change from window high (DIP)
        window_high = max(p for _, p in window)
        dip_pct = None
        
        immediate_dip_pct = None
        if window_high > 0:
            pct_change_high = ((price - window_high) / window_high) * 100.0
            
            # Immediate trigger
            if pct_change_high <= active_dip_threshold:
                immediate_dip_pct = pct_change_high
            
            # 1. Activate trailing if we hit threshold
            if pct_change_high <= active_dip_threshold:
                if not t_state["active"]:
                    t_state["active"] = True
                    t_state["lowest"] = price
                    t_state["dip_pct"] = pct_change_high
                    t_state["window_high"] = window_high
                else:
                    # Update lowest price if it keeps dropping
                    if price < t_state["lowest"]:
                        t_state["lowest"] = price
                        t_state["dip_pct"] = pct_change_high

            # 2. Check for rebound if active
            if t_state["active"]:
                # If price recovered back above the threshold level entirely, abort trailing
                if pct_change_high > active_dip_threshold and price > (t_state["lowest"] * 1.002):
                    t_state["active"] = False
                
                # Rebound check (e.g. +0.05% from the absolute bottom)
                rebound_price = t_state["lowest"] * (1.0 + (0.05 / 100.0))
                if price >= rebound_price and price > t_state["lowest"]:
                    # Trailing buy confirmed!
                    dip_pct = t_state["dip_pct"]  # Return the deepest dip recorded
                    # Reset state
                    t_state["active"] = False
                    t_state["lowest"] = float('inf')

        # Calculate % change from window low (SPIKE)
        window_low = min(p for _, p in window)
        spike_pct = None
        if window_low > 0:
            pct_change_low = ((price - window_low) / window_low) * 100.0
            if pct_change_low >= active_spike_threshold:
                spike_pct = pct_change_low

        return immediate_dip_pct, dip_pct, spike_pct

# ─────────────────────────────────────────────
# IndicatorManager — ATR & RSI Calculation
# ─────────────────────────────────────────────
class IndicatorManager:
    """Calculates ATR, RSI, and Multi-Timeframe RSI Confluence from incoming OHLC bars."""
    def __init__(self, period=14):
        self.period = period
        self._bars: Dict[str, deque] = {}
        self._rsi_history: Dict[str, deque] = {}
        # Multi-TF RSI: aggregate 1min bars into 5min and 15min
        self._mtf_bar_counter: Dict[str, int] = {}
        self._mtf_5m_closes: Dict[str, deque] = {}
        self._mtf_15m_closes: Dict[str, deque] = {}
        self._mtf_5m_buffer: Dict[str, list] = {}  # accumulate 5 x 1min closes
        self._mtf_15m_buffer: Dict[str, list] = {}  # accumulate 15 x 1min closes
        self._ema_9: Dict[str, float] = {}
        self._ema_21: Dict[str, float] = {}
        self._volumes: Dict[str, deque] = {}

    def update(self, symbol: str, high: float, low: float, close: float, volume: float = 0.0):
        if symbol not in self._bars:
            self._bars[symbol] = deque(maxlen=self.period + 1)
            self._volumes[symbol] = deque(maxlen=self.period)
            self._rsi_history[symbol] = deque(maxlen=60)
            self._mtf_bar_counter[symbol] = 0
            self._mtf_5m_closes[symbol] = deque(maxlen=self.period + 1)
            self._mtf_15m_closes[symbol] = deque(maxlen=self.period + 1)
            self._mtf_5m_buffer[symbol] = []
            self._mtf_15m_buffer[symbol] = []
            self._ema_9[symbol] = close
            self._ema_21[symbol] = close
        self._bars[symbol].append({"high": high, "low": low, "close": close, "volume": volume})
        self._volumes[symbol].append(volume)
        
        # Calculate EMA iteratively
        self._ema_9[symbol] = (close - self._ema_9[symbol]) * (2 / (9 + 1)) + self._ema_9[symbol]
        self._ema_21[symbol] = (close - self._ema_21[symbol]) * (2 / (21 + 1)) + self._ema_21[symbol]
        
        # Calculate and store RSI for history if we have enough bars
        rsi_val = self.get_rsi(symbol)
        if rsi_val is not None:
            self._rsi_history[symbol].append({"close": close, "rsi": rsi_val})

        # Multi-TF aggregation
        self._mtf_bar_counter[symbol] = self._mtf_bar_counter.get(symbol, 0) + 1
        self._mtf_5m_buffer[symbol].append(close)
        self._mtf_15m_buffer[symbol].append(close)
        # Every 5 bars, aggregate to 5min close
        if len(self._mtf_5m_buffer[symbol]) >= 5:
            avg_close = sum(self._mtf_5m_buffer[symbol]) / len(self._mtf_5m_buffer[symbol])
            self._mtf_5m_closes[symbol].append(avg_close)
            self._mtf_5m_buffer[symbol] = []
        # Every 15 bars, aggregate to 15min close
        if len(self._mtf_15m_buffer[symbol]) >= 15:
            avg_close = sum(self._mtf_15m_buffer[symbol]) / len(self._mtf_15m_buffer[symbol])
            self._mtf_15m_closes[symbol].append(avg_close)
            self._mtf_15m_buffer[symbol] = []

    def get_ema(self, symbol: str, period: int) -> Optional[float]:
        if period == 9:
            return self._ema_9.get(symbol)
        elif period == 21:
            return self._ema_21.get(symbol, None)

    def get_volume_sma(self, symbol: str) -> Optional[float]:
        if symbol not in self._volumes or len(self._volumes[symbol]) == 0:
            return None
        return sum(self._volumes[symbol]) / len(self._volumes[symbol])

    def is_volume_spike(self, symbol: str, current_volume: float, threshold: float = 2.0) -> bool:
        sma = self.get_volume_sma(symbol)
        if sma is None or sma == 0:
            return False
        return current_volume > (sma * threshold)

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

    def detect_bullish_divergence(self, symbol: str) -> bool:
        """
        Detects Bullish RSI Divergence: Price makes a Lower Low, but RSI makes a Higher Low.
        We look over the last 15 periods in the rsi_history.
        """
        history = self._rsi_history.get(symbol, [])
        if len(history) < 15:
            return False
        
        # Get the last point
        curr = history[-1]
        
        # Find the minimum price in the older history (e.g., from index -15 to -2)
        older_history = list(history)[-15:-1]
        
        min_older_idx = 0
        min_older_price = older_history[0]["close"]
        for i, pt in enumerate(older_history):
            if pt["close"] < min_older_price:
                min_older_price = pt["close"]
                min_older_idx = i
                
        older_min_pt = older_history[min_older_idx]
        
        # Check if current price is a new low (Lower Low)
        if curr["close"] < older_min_pt["close"]:
            # Check if current RSI is HIGHER than the RSI at the previous price low (Higher Low)
            if curr["rsi"] > older_min_pt["rsi"]:
                return True
                
        return False

    def _calc_rsi_from_closes(self, closes: deque) -> Optional[float]:
        """Calculates RSI from a deque of close prices."""
        if len(closes) < self.period + 1:
            return None
        data = list(closes)
        gains = []
        losses = []
        for i in range(1, len(data)):
            change = data[i] - data[i-1]
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

    def get_rsi_5m(self, symbol: str) -> Optional[float]:
        """Returns RSI calculated on aggregated 5-minute closes."""
        closes = self._mtf_5m_closes.get(symbol)
        if closes is None:
            return None
        return self._calc_rsi_from_closes(closes)

    def get_rsi_15m(self, symbol: str) -> Optional[float]:
        """Returns RSI calculated on aggregated 15-minute closes."""
        closes = self._mtf_15m_closes.get(symbol)
        if closes is None:
            return None
        return self._calc_rsi_from_closes(closes)

    def get_mtf_rsi_confluence(self, symbol: str) -> tuple:
        """
        Returns (score, description) for multi-timeframe RSI confluence.
        score: 0 = no confluence, 1 = double (1m+5m), 2 = triple (1m+5m+15m)
        Only counts when RSI < 30 (oversold).
        """
        rsi_1m = self.get_rsi(symbol)
        rsi_5m = self.get_rsi_5m(symbol)
        rsi_15m = self.get_rsi_15m(symbol)

        oversold_threshold = 30.0
        count = 0
        parts = []

        if rsi_1m is not None and rsi_1m < oversold_threshold:
            count += 1
            parts.append(f"1m:{rsi_1m:.1f}")
        if rsi_5m is not None and rsi_5m < oversold_threshold:
            count += 1
            parts.append(f"5m:{rsi_5m:.1f}")
        if rsi_15m is not None and rsi_15m < oversold_threshold:
            count += 1
            parts.append(f"15m:{rsi_15m:.1f}")

        if count >= 3:
            return (2, f"Triple RSI Confluence ({', '.join(parts)})")
        elif count >= 2:
            return (1, f"Double RSI Confluence ({', '.join(parts)})")
        return (0, "No MTF RSI Confluence")

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
        """Appends a WebSocket-triggered trade to SQLite DB."""
        try:
            from data.db import insert_trade
            from datetime import datetime, timezone
            timestamp = datetime.now(timezone.utc).isoformat()
            insert_trade(
                timestamp=timestamp,
                symbol=symbol,
                action="BUY",
                qty=qty,
                price=price,
                notional=qty * price,
                sentiment_score=sentiment_score,
                reasoning=f"{reasoning} (DIP: {dip_pct:.4f}%)",
                execution_type="hybrid_websocket_trigger",
                order_id=order_id
            )
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
                        try:
                            decoder = json.JSONDecoder()
                            history, _ = decoder.raw_decode(content)
                        except json.JSONDecodeError:
                            logger.warning("[WS] realtime_price_history.json was corrupted. Resetting.")
                            history = {}
            
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
        self._last_trailing_check = datetime.now(timezone.utc)
        self._shadow_last_order_time: Dict[str, datetime] = {}
        # MTF Confluence Cache: {symbol: {"trend": "UP"/"DOWN"/"NEUTRAL", "fetched_at": datetime}}
        self._mtf_trend_cache: Dict[str, dict] = {}
        self._mtf_cache_ttl_seconds: int = 3600  # Refresh every hour
        self.panic_cooldown_until: float = 0.0
        self._reversal_wait_states: Dict[str, dict] = {}

    def _check_market_panic(self) -> bool:
        """
        Checks if >= guardian_panic_asset_count crypto assets are dipping below guardian_panic_threshold_pct.
        If so, activates panic mode for guardian_panic_cooldown_min minutes.
        Returns True if panic is active, False otherwise.
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        if now_ts < self.panic_cooldown_until:
            return True

        risk_config = RiskConfigReader.read()
        threshold_pct = risk_config.get("guardian_panic_threshold_pct", -0.30)
        required_count = risk_config.get("guardian_panic_asset_count", 3)
        cooldown_min = risk_config.get("guardian_panic_cooldown_min", 5)

        panic_count = 0
        dipping_assets = []
        for sym, state in self.vol_detector._trailing_state.items():
            if sym.endswith("USD") and state.get("dip_pct", 0) <= threshold_pct:
                panic_count += 1
                dipping_assets.append(sym)

        if panic_count >= required_count:
            logger.error(f"[GUARDIAN] Market Panic Detected! Assets dipping: {', '.join(dipping_assets)} below {threshold_pct}%. Suspending BUYs for {cooldown_min} minutes.")
            self.panic_cooldown_until = now_ts + (cooldown_min * 60)
            return True

        return False

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

                logger.info(f"[MTF] {symbol} — EMA50(1H): {ema50:.4f}, Last: {last_close:.4f} → Trend: {trend}")
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

    def _is_on_cooldown(self, symbol: str) -> bool:
        """Returns True if the symbol is in cooldown (order placed recently)."""
        last = self._last_order_time.get(symbol)
        if last is None:
            return False
        
        now_time = getattr(self, 'current_time', datetime.now(timezone.utc))
        elapsed = (now_time - last).total_seconds()
        is_crypto = symbol.endswith("USD")
        cooldown_target = 15 if is_crypto else ORDER_COOLDOWN_SECONDS
        return elapsed < cooldown_target
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
        """Places a Bracket Order with dynamic TP/SL."""
        risk_config = RiskConfigReader.read()

        sentiment_score = bias_info.get("sentiment_score", 0.0)
        reasoning = bias_info.get("reasoning", "")
        bias_type = "BEARISH" if is_short else "BULLISH"
        mtf_size_multiplier = bias_info.get("_mtf_size_multiplier", 1.0)  # MTF Confluence filter
        
        # Determine asset class
        is_crypto = symbol.endswith("USD")
        
        # Level 2 Orderbook Check
        imbalance = self.orderbook_analyzer.check_imbalance(symbol)
        if not is_short and imbalance == "BEARISH_WALL":
            logger.warning(f"[L2 FILTER] {symbol} has a huge BEARISH WALL. Skipping LONG execution.")
            WSTradeLogger.write_logbook(f"[L2 INFO] Salto il Long su {symbol} causa Muro di Vendita (Bearish Wall).")
            return None
        if is_short and imbalance == "BULLISH_WALL":
            logger.warning(f"[L2 FILTER] {symbol} has a huge BULLISH WALL. Skipping SHORT execution.")
            WSTradeLogger.write_logbook(f"[L2 INFO] Salto lo Short su {symbol} causa Muro di Acquisto (Bullish Wall).")
            return None

        if is_short and is_crypto:
            if "BTC" in symbol:
                alpha_inverse_hedge = risk_config.get("alpha_inverse_hedge", False)
                if not alpha_inverse_hedge:
                    logger.warning(f"[WS ALPHA] Alpha Hedge logged for {symbol} (Alpha feature disabled).")
                    from data.db import insert_ai_analytics
                    insert_ai_analytics(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        asset="BITI",
                        price=0.0, # ETF price unknown locally
                        action="SHADOW_HEDGE",
                        confidence=0.9,
                        sentiment_score=sentiment_score,
                        prompt_tokens=0, completion_tokens=0,
                        reasoning=f"Alpha Hedge triggered from Bearish {symbol}",
                        return_1h=None, return_4h=None
                    )
                    return None
                else:
                    logger.warning(f"[WS ALPHA] Alpha Classic Short logged for {symbol} (Alpha feature active).")
                    from data.db import insert_ai_analytics
                    insert_ai_analytics(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        asset=symbol,
                        price=price,
                        action="SHADOW_SELL",
                        confidence=0.9,
                        sentiment_score=sentiment_score,
                        prompt_tokens=0, completion_tokens=0,
                        reasoning=f"Alpha Classic Short triggered (Alpha is hedging on BITI)",
                        return_1h=None, return_4h=None
                    )
                    
                logger.warning(f"[WS HEDGE] Converting Crypto SHORT on {symbol} to LONG on ETF BITI")
                WSTradeLogger.write_logbook(f"[HEDGE] Sostituito Short {symbol} con Acquisto ETF Inverso (BITI).")
                symbol = "BITI"
                is_short = False
                is_crypto = False
                price = 0.0  # Unknown price, will trigger a simple Market Order without Bracket
            else:
                logger.warning(f"[WS] Cannot short Crypto {symbol} on Alpaca. Skipping execution.")
                WSTradeLogger.write_logbook(f"[WS INFO] Salto lo Short su Crypto {symbol} (non supportato).")
                return None

        # Fetch account data for position sizing
        try:
            self._init_trading_client()
            account = self._trading_client.get_account()
            total_equity = float(account.equity)
            buying_power = float(account.buying_power)
            
            # Budget logic moved to position_sizer.py

        except Exception as e:
            logger.warning(f"[WS] Failed to get account info: {e}")
            total_equity = 10000.0 # fallback
            buying_power = 10000.0 # fallback
            
        from risk_management.position_sizer import PositionSizer
        from config.config_manager import config_manager
        
        # Load typed config for position sizer
        typed_config = config_manager.load_risk_settings()
        
        if is_crypto:
            # --- NEW STRATEGY: Fixed Risk Sizing (5% of Equity) ---
            risk_pct = 0.05
            risk_usd = total_equity * risk_pct
            
            bands = self.bollinger_detector._calc_bands(symbol)
            if bands:
                sma = bands["sma"]
                # Stop loss is placed at SMA
                distance = abs(price - sma)
                dist_pct = distance / price if price > 0 else 0.01
                
                # Minimum distance clamp to avoid infinite size (e.g. 0.5%)
                if dist_pct < 0.005:
                    dist_pct = 0.005
                    
                size_usd = risk_usd / dist_pct
                logger.info(f"[RISK MANAGER] Risk {risk_pct*100:.1f}% (${risk_usd:.2f}) with SL distance {dist_pct*100:.2f}%. Required Size: ${size_usd:.2f}")
            else:
                # Fallback
                size_usd = PositionSizer.calculate_micro_size(
                    symbol, typed_config, total_equity, buying_power
                )
        else:
            size_usd = PositionSizer.calculate_micro_size(
                symbol, typed_config, total_equity, buying_power
            )

        # Apply MTF Confluence multiplier (0.5 if macro trend is DOWN, else 1.0)
        if mtf_size_multiplier != 1.0:
            size_usd = size_usd * mtf_size_multiplier
            logger.info(f"[MTF] Applied size multiplier {mtf_size_multiplier:.1f}x to {symbol}: ${size_usd:.2f}")

        # --- NEW: Global Allocation & Cash Reserve Checks ---
        try:
            self._init_trading_client()
            
            global_min_cash_pct = risk_config.get("global_min_cash_pct", 0.10)
            global_max_crypto_pct = risk_config.get("global_max_crypto_pct", 0.50)
            global_max_stocks_pct = risk_config.get("global_max_stocks_pct", 0.50)
            
            min_cash_usd = total_equity * global_min_cash_pct
            max_crypto_usd = total_equity * global_max_crypto_pct
            max_stocks_usd = total_equity * global_max_stocks_pct
            
            open_positions = self._trading_client.get_all_positions()
            current_crypto_value = 0.0
            current_stocks_value = 0.0
            
            for p in open_positions:
                val = float(p.market_value)
                if p.asset_class == 'crypto':
                    current_crypto_value += val
                else:
                    current_stocks_value += val
                    
            if not is_short:
                # 1. Cash Reserve Check
                available_cash_for_trading = buying_power - min_cash_usd
                if available_cash_for_trading <= 0:
                    logger.warning(f"[WS] Cash Reserve limit reached (Available: ${buying_power:.2f}, Min Req: ${min_cash_usd:.2f})")
                    return None
                    
                if size_usd > available_cash_for_trading:
                    size_usd = available_cash_for_trading
                    
                # 2. Asset Class Allocation Check
                if is_crypto:
                    available_crypto = max_crypto_usd - current_crypto_value
                    if available_crypto <= 0:
                        logger.warning(f"[WS] Global Crypto limit reached (Current: ${current_crypto_value:.2f}, Max: ${max_crypto_usd:.2f})")
                        return None
                    if size_usd > available_crypto:
                        size_usd = available_crypto
                else:
                    available_stocks = max_stocks_usd - current_stocks_value
                    if available_stocks <= 0:
                        logger.warning(f"[WS] Global Stocks limit reached (Current: ${current_stocks_value:.2f}, Max: ${max_stocks_usd:.2f})")
                        return None
                    if size_usd > available_stocks:
                        size_usd = available_stocks

        except Exception as e:
            logger.error(f"[WS] Error checking global allocations: {e}")

        # Pre-flight Balance Check
        if not is_short:
            if size_usd > buying_power:
                size_usd = buying_power * 0.95  # Leave 5% buffer
            if size_usd < 10.0:
                logger.warning(f"[WS] Insufficient balance for {symbol} (Requires > $10, Available: ${buying_power:.2f})")
                return None

        # Check max open positions (anti-spam) and apply Martingale scaling
        try:
            self._init_trading_client()
            if is_crypto:
                max_open = risk_config.get("crypto_max_grid_layers", 3)
            else:
                max_open = risk_config.get("max_open_positions_per_asset", 1)
            
            check_symbol = symbol
            base_size_usd = size_usd
            
            try:
                open_pos = self._trading_client.get_open_position(check_symbol)
                current_qty = abs(float(open_pos.qty))
                if current_qty > 0:
                    # Estimate current layers based on original base size
                    current_layers = float(open_pos.market_value) / base_size_usd if base_size_usd > 0 else 0
                    if current_layers >= (max_open - 0.5):
                        logger.warning(f"[WS] Max grid layers reached for {check_symbol} (Current: ~{current_layers:.1f}, Max: {max_open}). Skipping order.")
                        return None
                        
                    # Smart Asymmetric DCA (Martingale)
                    layer_int = int(current_layers)
                    
                    # ATR Spacing Filter
                    if atr > 0:
                        avg_entry = float(open_pos.avg_entry_price)
                        if not is_short and price > (avg_entry - atr):
                            logger.info(f"[WS FILTER] Skipping DCA Layer {layer_int+1} per {check_symbol}: Price ${price:.2f} troppo vicino a Avg Entry ${avg_entry:.2f} (Richiesto > 1 ATR spacing: ${atr:.2f})")
                            return None
                        elif is_short and price < (avg_entry + atr):
                            logger.info(f"[WS FILTER] Skipping DCA Layer {layer_int+1} per {check_symbol}: Price ${price:.2f} troppo vicino a Avg Entry ${avg_entry:.2f} (Richiesto > 1 ATR spacing: ${atr:.2f})")
                            return None

                    # L2 Smart DCA Multiplier
                    imbalance = self.orderbook_analyzer.check_imbalance(check_symbol)
                    multiplier = 1.5
                    if not is_short:
                        if imbalance == "BULLISH_WALL":
                            multiplier = 2.0
                            logger.info(f"[WS L2] Bullish Wall detected on {check_symbol}! Using aggressive DCA multiplier (2.0x)")
                        elif imbalance == "BEARISH_WALL":
                            multiplier = 1.2
                            logger.info(f"[WS L2] Bearish Wall detected on {check_symbol}! Using conservative DCA multiplier (1.2x)")
                    else:
                        if imbalance == "BEARISH_WALL":
                            multiplier = 2.0
                            logger.info(f"[WS L2] Bearish Wall detected on {check_symbol}! Using aggressive DCA multiplier (2.0x)")
                        elif imbalance == "BULLISH_WALL":
                            multiplier = 1.2
                            logger.info(f"[WS L2] Bullish Wall detected on {check_symbol}! Using conservative DCA multiplier (1.2x)")

                    size_usd = base_size_usd * (multiplier ** layer_int)
                    logger.info(f"[WS] Smart DCA active for {check_symbol}: Layer {layer_int+1}, Base Size: ${base_size_usd:.2f} -> Scaled Size: ${size_usd:.2f}")
            except Exception as e:
                pass # Usually implies no open position
        except Exception as e:
            logger.warning(f"[WS] Error checking open positions: {e}")

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
                from alpaca.trading.requests import LimitOrderRequest, StopLossRequest, MarketOrderRequest
                from alpaca.trading.enums import OrderSide, TimeInForce
                
                # If price is 0.0 (e.g. ETF Hedge), we place a simple market order without brackets
                if price <= 0:
                    req = MarketOrderRequest(
                        symbol=symbol,
                        notional=round(size_usd, 2),
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY
                    )
                    res = self._trading_client.submit_order(req)
                    order_id = str(res.id)
                    logger.info(f"[WS] Executed HEDGE Market Order for {symbol}, Notional: ${size_usd:.2f}")
                else:
                    atr_tp_mult = risk_config.get("atr_take_profit_multiplier", 3.0)
                    atr_sl_mult = risk_config.get("atr_stop_loss_multiplier", 2.0)

                    if is_crypto:
                        base_tp = risk_config.get("crypto_micro_tp_pct", 0.50)
                        micro_tp_pct = getattr(self, 'crypto_micro_tp_pct', base_tp) / 100.0
                        
                        # Fetch SMA for Stop Loss
                        bands = self.bollinger_detector._calc_bands(symbol)
                        sma_sl = bands["sma"] if bands else None
                        
                        if is_short:
                            tp_price = round(price * (1.0 - micro_tp_pct), 2)
                            sl_price = round(sma_sl, 2) if sma_sl else round(price * 1.05, 2)
                            side = OrderSide.SELL
                        else:
                            tp_price = round(price * (1.0 + micro_tp_pct), 2)
                            sl_price = round(sma_sl, 2) if sma_sl else round(price * 0.95, 2)
                            side = OrderSide.BUY
                    else:
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

                order_symbol = symbol
                
                qty = size_usd / price if price > 0 else 0.0
                qty = round(qty, 4) if is_crypto else round(qty, 2)

                # Maker Limit Price
                limit_price = round(price * 0.9995, 2) if side == OrderSide.BUY else round(price * 1.0005, 2)

                # Fractional stock orders require DAY; crypto supports GTC
                tif = TimeInForce.GTC if is_crypto else TimeInForce.DAY

                order_data = LimitOrderRequest(
                    symbol=order_symbol,
                    qty=qty,
                    side=side,
                    time_in_force=tif,
                    limit_price=limit_price,
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
                error_msg = str(e).lower()
                if "insufficient balance" in error_msg:
                    logger.error(f"[WS] Insufficient balance error caught for {symbol}.")
                    self._global_buy_cooldown_until = time.time() + 3600
                    WSTradeLogger.write_logbook("[API WARNING] Liquidità esaurita (da API)! Acquisti in pausa per 1 ora.")
                else:
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
        self._last_order_time[symbol] = getattr(self, 'current_time', datetime.now(timezone.utc))
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
            
        self.current_time = bar_time

        # Confirmation Filter for High Alerts
        alert = self.alert_states.get(symbol)
        if alert:
            age = (datetime.now(timezone.utc) - alert["timestamp"]).total_seconds()
            if age > 300: # 5 minutes expiry
                logger.info(f"[GUARDIAN] Alert expired for {symbol}.")
                del self.alert_states[symbol]
            else:
                if alert["type"] == "CATACLYSM":
                    # Instant kill switch on a minor dip
                    imm_dip, dip, _ = self.vol_detector.update(symbol, price, bar_time, dynamic_dip_pct=-0.15)
                    if dip is not None:
                        logger.error(f"[GUARDIAN KILL SWITCH] CATACLYSM CONFIRMED for {symbol}! Liquidating!")
                        try:
                            self._init_trading_client()
                            self._trading_client.close_position(symbol)
                            WSTradeLogger.write_logbook(f"[EMERGENCY] Chiusura d'emergenza su {symbol} completata.")
                        except Exception:
                            pass
                        del self.alert_states[symbol]
                        return
                    return # Block standard execution while in CATACLYSM alert!
                elif alert["type"] == "MOONSHOT":
                    pass

        # Update Indicator Manager with OHLC
        high = float(bar.high) if hasattr(bar, "high") else price
        low = float(bar.low) if hasattr(bar, "low") else price
        volume = float(bar.volume) if hasattr(bar, "volume") else 0.0
        self.indicator_mgr.update(symbol, high, low, price, volume=volume)
        if volume > 0:
            self.volume_profile_mgr.add_volume(symbol, price, volume)

        # Update new strategy modules
        self.momentum_filter.update(symbol, price)
        self.vwap_strategy.update(symbol, price, volume)
        self.bollinger_detector.update(symbol, price)
        self.correlation_engine.update(symbol, price)

        # Check Warm-up
        atr = self.indicator_mgr.get_atr(symbol)
        rsi = self.indicator_mgr.get_rsi(symbol)
        
        if atr is None or rsi is None:
            # Silent return during 14-min warmup
            return

        # Correlated Asset Panic Filter
        if self._check_market_panic():
            # Only block BUY signals. We still want to trail stops and update indicators.
            # We will just skip the rest of the execution block that might trigger a buy.
            # But let's make sure we still log prices and manage trailing stops.
            WSTradeLogger.log_price(symbol, price, bar_time)
            self._manage_trailing_stops(price, symbol)
            return

        # Log streaming price for the real-time dashboard chart
        WSTradeLogger.log_price(symbol, price, bar_time)

        # Update Trailing Stop logic
        self._manage_trailing_stops(price, symbol)

        # Read Regime and adjust DIP threshold dynamically
        risk_config = RiskConfigReader.read()
        
        # Volatility-Adjusted DIP Threshold
        base_dip = abs(risk_config.get("crypto_micro_dip_pct", 0.15))
        alpha_dynamic_dip = risk_config.get("alpha_dynamic_dip", False)
        if alpha_dynamic_dip and atr is not None and atr > 0 and price > 0:
            atr_pct = (atr / price) * 100.0
            mult = risk_config.get("atr_dynamic_dip_multiplier", 1.0)
            dynamic_dip = -abs(base_dip * (1 + (atr_pct * mult)))
        else:
            dynamic_dip = -abs(base_dip)
            
        immediate_dip, trailing_dip, spike_pct = self.vol_detector.update(symbol, price, bar_time, dynamic_dip_pct=dynamic_dip)
        
        alpha_smart_trailing = risk_config.get("alpha_smart_trailing", False)
        
        # Alpha logging for trailing buy — cooldown checked via DB so it survives restarts
        shadow_cooldown = 1800  # 30 minutes
        dip_condition = (not alpha_smart_trailing and trailing_dip is not None) or \
                        (alpha_smart_trailing and immediate_dip is not None)
        
        if dip_condition:
            from data.db import get_db
            with get_db() as _conn:
                last_shadow_row = _conn.execute(
                    "SELECT timestamp FROM ai_analytics WHERE action LIKE 'SHADOW_%' AND asset = ? ORDER BY timestamp DESC LIMIT 1",
                    (symbol,)
                ).fetchone()
            can_shadow = True
            if last_shadow_row:
                try:
                    last_ts = datetime.fromisoformat(last_shadow_row[0].replace("Z", "+00:00"))
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                    can_shadow = (datetime.now(timezone.utc) - last_ts).total_seconds() >= shadow_cooldown
                except Exception:
                    can_shadow = True
            
            if can_shadow:
                from data.db import insert_ai_analytics
                if not alpha_smart_trailing and trailing_dip is not None:
                    insert_ai_analytics(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        asset=symbol, price=price, action="SHADOW_BUY",
                        confidence=0.9, sentiment_score=0.0,
                        prompt_tokens=0, completion_tokens=0,
                        reasoning=f"Alpha Trailing Buy hit at {trailing_dip:.2f}%",
                        return_1h=None, return_4h=None
                    )
                elif alpha_smart_trailing and immediate_dip is not None:
                    insert_ai_analytics(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        asset=symbol, price=price, action="SHADOW_BUY",
                        confidence=0.9, sentiment_score=0.0,
                        prompt_tokens=0, completion_tokens=0,
                        reasoning=f"Alpha Classic Buy (No Trailing) hit at {immediate_dip:.2f}%",
                        return_1h=None, return_4h=None
                    )
            
        dip_pct = trailing_dip if alpha_smart_trailing else immediate_dip

        # --- NEW STRATEGY: ALTCOIN MOMENTUM BREAKOUT (SOLUSD) ---
        is_crypto = symbol.endswith("USD")
        if is_crypto:
            # We focus on Momentum Breakouts for Crypto
            
            # Check cooldown
            if self._is_on_cooldown(symbol):
                return

            bias_info = BiasReader.get_bias_for_symbol(symbol)
            bias = bias_info.get("bias", "NEUTRAL")
            
            # 1. Update Bollinger Squeeze Detector and ask if we just broke out
            self.bollinger_detector.update(symbol, price)
            signal = self.bollinger_detector.check_signal(symbol, price)
            
            if signal == "SQUEEZE_BUY":
                # 2. Check for Volume Spike Confirmation
                vol_thresh = getattr(self, 'volume_spike_multiplier', 2.0)
                if self.indicator_mgr.is_volume_spike(symbol, volume, threshold=vol_thresh):
                    logger.info(f"[WS TRIGGER] CONFIRMED SQUEEZE BREAKOUT UP with Volume Spike for {symbol}! Triggering BUY.")
                    WSTradeLogger.write_logbook(f"[MOMENTUM] Esplosione rialzista su {symbol} con Spike di Volumi. Esecuzione BUY (Leva).")
                    
                    # We pass the signal as 'dip_pct' argument just for logging signature compatibility
                    self._execute_order(symbol, price, 0.0, bias_info, is_short=False, atr=atr)
                else:
                    logger.info(f"[WS FILTER] {symbol} broke out UP but volume ({volume}) was too low. Ignoring.")
            
            elif signal == "SQUEEZE_SHORT":
                vol_thresh = getattr(self, 'volume_spike_multiplier', 2.0)
                if self.indicator_mgr.is_volume_spike(symbol, volume, threshold=vol_thresh):
                    logger.info(f"[WS TRIGGER] CONFIRMED SQUEEZE BREAKOUT DOWN with Volume Spike for {symbol}! Triggering SHORT.")
                    WSTradeLogger.write_logbook(f"[MOMENTUM] Crollo ribassista su {symbol} con Spike di Volumi. Esecuzione SHORT (Leva).")
                    
                    self._execute_order(symbol, price, 0.0, bias_info, is_short=True, atr=atr)
                else:
                    logger.info(f"[WS FILTER] {symbol} broke out DOWN but volume ({volume}) was too low. Ignoring.")
                    
        else:
            # Legacy Stock Logic (DIP)
            if dip_pct is not None:
                if self._is_on_cooldown(symbol):
                    return
                bias_info = BiasReader.get_bias_for_symbol(symbol)
                bias = bias_info.get("bias", "NEUTRAL")
                sentiment_score = bias_info.get("sentiment_score", 0.0)
                
                stock_buy_condition = bias == "BULLISH" and sentiment_score >= 0.75
                if stock_buy_condition:
                    if rsi > 70:
                        return
                    logger.info(f"[WS TRIGGER] DIP confirmed for {symbol}! Executing BUY order...")
                    self._execute_order(symbol, price, dip_pct, bias_info, is_short=False, atr=atr)

        # === VWAP Reversion Strategy (independent signal source) ===
        if risk_config.get("strategy_vwap_enabled", True):
            vwap_signal = self.vwap_strategy.check_signal(symbol, price, atr=atr, rsi=rsi)
            if vwap_signal == "VWAP_BUY" and not self._is_on_cooldown(symbol):
                momentum_ok = True
                if risk_config.get("strategy_momentum_filter_enabled", True) and not True:
                    momentum_ok = self.momentum_filter.should_allow_buy(symbol)
                
                if momentum_ok:
                    bias_info = BiasReader.get_bias_for_symbol(symbol)
                    logger.info(f"[VWAP TRIGGER] Mean-reversion BUY on {symbol} at ${price:.2f}")
                    self._execute_order(symbol, price, 0.0, bias_info, is_short=False, atr=atr)
                    self._last_order_time[symbol] = getattr(self, 'current_time', datetime.now(timezone.utc))

        # === Bollinger Squeeze Breakout (independent signal source) ===
        if risk_config.get("strategy_bollinger_enabled", True):
            self.bollinger_detector.squeeze_threshold_pct = risk_config.get("squeeze_threshold_pct", 0.005)
            bb_signal = self.bollinger_detector.check_signal(symbol, price)
            if bb_signal == "SQUEEZE_BUY" and not self._is_on_cooldown(symbol):
                momentum_ok = True
                if risk_config.get("strategy_momentum_filter_enabled", True):
                    momentum_ok = self.momentum_filter.should_allow_buy(symbol)
                    
                if momentum_ok:
                    bias_info = BiasReader.get_bias_for_symbol(symbol)
                    logger.info(f"[BOLLINGER TRIGGER] Squeeze breakout BUY on {symbol} at ${price:.2f}")
                    self._execute_order(symbol, price, 0.0, bias_info, is_short=False, atr=atr)
                    self._last_order_time[symbol] = getattr(self, 'current_time', datetime.now(timezone.utc))
            elif bb_signal == "SQUEEZE_SHORT":
                bias_info = BiasReader.get_bias_for_symbol(symbol)
                bias = bias_info.get("bias", "NEUTRAL")
                if bias == "BEARISH" and not self._is_on_cooldown(symbol):
                    logger.info(f"[BOLLINGER TRIGGER] Squeeze breakout SHORT on {symbol} at ${price:.2f}")
                    self._execute_order(symbol, price, 0.0, bias_info, is_short=True, atr=atr)
                    self._last_order_time[symbol] = getattr(self, 'current_time', datetime.now(timezone.utc))

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

        immediate_dip, trailing_dip, spike_pct = self.vol_detector.update(symbol, price, bar_time)

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
                    crypto_stream = CryptoDataStream(APCA_API_KEY_ID, APCA_API_SECRET_KEY)
                    crypto_stream.subscribe_bars(crypto_handler, *crypto_symbols_ws)
                    
                    async def orderbook_handler(orderbook):
                        self.orderbook_analyzer.update(orderbook.symbol, orderbook.bids, orderbook.asks)
                        
                    crypto_stream.subscribe_orderbooks(orderbook_handler, *crypto_symbols_ws)
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
                                WSTradeLogger.write_logbook(f"🚨 [GUARDIAN ALERT] {eval_result}: {news.headline} ({symbols_in_news})")
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

        t_crypto = threading.Thread(target=run_crypto, daemon=True)
        t_stock = threading.Thread(target=run_stock, daemon=True)
        t_news = threading.Thread(target=run_news, daemon=True)

        try:
            t_crypto.start()
            t_stock.start()
            t_news.start()
            
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
