"""
strategy/indicator_manager.py

Calculates ATR, RSI, EMA-9/21, volume SMA, and Multi-Timeframe RSI Confluence
from incoming real-time OHLC bars.

Extracted from realtime_executor.py as a standalone module with single responsibility.
Each method has a clear, narrow contract; no I/O, no API calls.
"""
import logging
from collections import deque
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("nano-trader-ai")


class IndicatorManager:
    """
    Stateful per-symbol indicator calculator.

    Maintains rolling OHLC bars and computes:
    - ATR (Average True Range)
    - RSI (Relative Strength Index) on 1m, 5m and 15m timeframes
    - EMA-9 and EMA-21 (exponential moving averages)
    - Volume SMA and spike detection
    - Bullish RSI Divergence
    """

    def __init__(self, period: int = 14):
        self.period = period
        self._bars: Dict[str, deque] = {}
        self._rsi_history: Dict[str, deque] = {}
        self._mtf_bar_counter: Dict[str, int] = {}
        self._mtf_5m_closes: Dict[str, deque] = {}
        self._mtf_15m_closes: Dict[str, deque] = {}
        self._mtf_5m_buffer: Dict[str, List[float]] = {}
        self._mtf_15m_buffer: Dict[str, List[float]] = {}
        self._ema_9: Dict[str, float] = {}
        self._ema_21: Dict[str, float] = {}
        self._volumes: Dict[str, deque] = {}

    # ──────────────────────────────────────────────
    # Initialisation helpers
    # ──────────────────────────────────────────────

    def _init_symbol(self, symbol: str, close: float) -> None:
        """Lazily initialises per-symbol state on the first bar."""
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

    # ──────────────────────────────────────────────
    # Update
    # ──────────────────────────────────────────────

    def update(self, symbol: str, high: float, low: float, close: float, volume: float = 0.0) -> None:
        """Ingest one OHLC bar and update all indicators."""
        if symbol not in self._bars:
            self._init_symbol(symbol, close)

        self._bars[symbol].append({"high": high, "low": low, "close": close})
        self._volumes[symbol].append(volume)

        # Update EMAs iteratively
        k9 = 2.0 / (9 + 1)
        k21 = 2.0 / (21 + 1)
        self._ema_9[symbol] = close * k9 + self._ema_9[symbol] * (1.0 - k9)
        self._ema_21[symbol] = close * k21 + self._ema_21[symbol] * (1.0 - k21)

        # Store RSI history once we have enough bars
        rsi_val = self.get_rsi(symbol)
        if rsi_val is not None:
            self._rsi_history[symbol].append({"close": close, "rsi": rsi_val})

        # Multi-TF aggregation
        self._mtf_bar_counter[symbol] = self._mtf_bar_counter.get(symbol, 0) + 1
        self._mtf_5m_buffer[symbol].append(close)
        self._mtf_15m_buffer[symbol].append(close)

        if len(self._mtf_5m_buffer[symbol]) >= 5:
            avg = sum(self._mtf_5m_buffer[symbol]) / len(self._mtf_5m_buffer[symbol])
            self._mtf_5m_closes[symbol].append(avg)
            self._mtf_5m_buffer[symbol] = []

        if len(self._mtf_15m_buffer[symbol]) >= 15:
            avg = sum(self._mtf_15m_buffer[symbol]) / len(self._mtf_15m_buffer[symbol])
            self._mtf_15m_closes[symbol].append(avg)
            self._mtf_15m_buffer[symbol] = []

    # ──────────────────────────────────────────────
    # ATR
    # ──────────────────────────────────────────────

    def get_atr(self, symbol: str) -> Optional[float]:
        """Returns the Average True Range over the last `period` bars, or None during warmup."""
        bars = self._bars.get(symbol, [])
        if len(bars) < self.period + 1:
            return None

        trs = []
        bar_list = list(bars)
        for i in range(1, len(bar_list)):
            prev_close = bar_list[i - 1]["close"]
            h = bar_list[i]["high"]
            l = bar_list[i]["low"]
            tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
            trs.append(tr)
        return sum(trs[-self.period:]) / self.period

    # ──────────────────────────────────────────────
    # RSI
    # ──────────────────────────────────────────────

    @staticmethod
    def _calc_rsi(bars_or_closes) -> Optional[float]:
        """Shared RSI calculation from a sequence of dicts with 'close' key, or raw floats."""
        data = list(bars_or_closes)
        if len(data) < 2:
            return None
        # Support both {"close": x} dicts and raw floats
        closes = [b["close"] if isinstance(b, dict) else b for b in data]
        gains, losses = [], []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i - 1]
            (gains if change > 0 else losses).append(abs(change))
            (losses if change > 0 else gains).append(0)
        period = len(closes) - 1
        avg_gain = sum(gains[-period:]) / period if period else 0
        avg_loss = sum(losses[-period:]) / period if period else 0
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def get_rsi(self, symbol: str) -> Optional[float]:
        """Returns RSI on 1-minute bars, or None during warmup."""
        bars = self._bars.get(symbol, [])
        if len(bars) < self.period + 1:
            return None
        return self._calc_rsi(list(bars))

    def _calc_rsi_from_closes(self, closes: deque) -> Optional[float]:
        """Calculates RSI from a deque of close prices (used for multi-TF)."""
        if len(closes) < self.period + 1:
            return None
        return self._calc_rsi(list(closes))

    def get_rsi_5m(self, symbol: str) -> Optional[float]:
        """Returns RSI calculated on aggregated 5-minute closes."""
        closes = self._mtf_5m_closes.get(symbol)
        return self._calc_rsi_from_closes(closes) if closes else None

    def get_rsi_15m(self, symbol: str) -> Optional[float]:
        """Returns RSI calculated on aggregated 15-minute closes."""
        closes = self._mtf_15m_closes.get(symbol)
        return self._calc_rsi_from_closes(closes) if closes else None

    def get_mtf_rsi_confluence(self, symbol: str) -> Tuple[int, str]:
        """
        Returns (score, description) for multi-timeframe RSI confluence.
        score: 0 = no confluence, 1 = 2 TFs oversold, 2 = all 3 TFs oversold.
        """
        oversold = 30.0
        rsis = {
            "1m": self.get_rsi(symbol),
            "5m": self.get_rsi_5m(symbol),
            "15m": self.get_rsi_15m(symbol),
        }
        parts = [f"{tf}:{v:.1f}" for tf, v in rsis.items() if v is not None and v < oversold]
        count = len(parts)
        if count >= 3:
            return (2, f"Triple RSI Confluence ({', '.join(parts)})")
        if count >= 2:
            return (1, f"Double RSI Confluence ({', '.join(parts)})")
        return (0, "No MTF RSI Confluence")

    # ──────────────────────────────────────────────
    # EMA
    # ──────────────────────────────────────────────

    def get_ema(self, symbol: str, period: int) -> Optional[float]:
        """Returns the iterative EMA for the given period (9 or 21)."""
        if period == 9:
            return self._ema_9.get(symbol)
        if period == 21:
            return self._ema_21.get(symbol)
        return None

    # ──────────────────────────────────────────────
    # Volume
    # ──────────────────────────────────────────────

    def get_volume_sma(self, symbol: str) -> Optional[float]:
        """Returns the simple moving average of volume over the last `period` bars."""
        vols = self._volumes.get(symbol)
        if not vols:
            return None
        return sum(vols) / len(vols)

    def is_volume_spike(self, symbol: str, current_volume: float, threshold: float = 2.0) -> bool:
        """Returns True if current_volume > threshold * volume SMA."""
        sma = self.get_volume_sma(symbol)
        if sma is None or sma == 0:
            return False
        return current_volume > (sma * threshold)

    # ──────────────────────────────────────────────
    # Price helpers
    # ──────────────────────────────────────────────

    def get_last_price(self, symbol: str) -> Optional[float]:
        """Returns the most recent closing price, or None if no bars have been fed."""
        bars = self._bars.get(symbol)
        if bars and len(bars) > 0:
            return bars[-1]["close"]
        return None

    # ──────────────────────────────────────────────
    # Divergence
    # ──────────────────────────────────────────────

    def detect_bullish_divergence(self, symbol: str) -> bool:
        """
        Detects Bullish RSI Divergence: Price makes a Lower Low, but RSI makes a Higher Low.
        Requires at least 15 RSI history points.
        """
        history = list(self._rsi_history.get(symbol, []))
        if len(history) < 15:
            return False
        curr = history[-1]
        older = history[-15:-1]
        min_pt = min(older, key=lambda p: p["close"])
        return curr["close"] < min_pt["close"] and curr["rsi"] > min_pt["rsi"]
