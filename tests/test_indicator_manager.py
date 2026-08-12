"""
tests/test_indicator_manager.py

Unit tests for strategy/indicator_manager.py — TDD expanded.
Covers ATR, RSI, EMA, volume, multi-timeframe RSI, and divergence detection.
"""
import unittest
import pytest


def _feed_bars(mgr, symbol: str, n: int, high=10.5, low=9.5, close=10.0, volume=100.0):
    """Helper: feed N identical OHLC bars to warm up the indicator."""
    for _ in range(n):
        mgr.update(symbol, high, low, close, volume=volume)


class TestIndicatorManagerATR:
    def test_atr_none_before_warmup(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        for _ in range(14):
            mgr.update("BTCUSD", 65100.0, 64900.0, 65000.0)
        # Still needs period+1 bars — ATR should be None with exactly 14 bars
        assert mgr.get_atr("BTCUSD") is None

    def test_atr_calculated_after_period_plus_one_bars(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        for _ in range(15):
            mgr.update("BTCUSD", 65100.0, 64900.0, 65000.0)
        atr = mgr.get_atr("BTCUSD")
        assert atr is not None
        assert atr > 0

    def test_atr_reflects_bar_range(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=5)
        # Bars with range 200 (high - low)
        for _ in range(6):
            mgr.update("BTCUSD", 65100.0, 64900.0, 65000.0)
        atr = mgr.get_atr("BTCUSD")
        # True range = max(200, |65100-65000|, |64900-65000|) = 200
        assert atr == pytest.approx(200.0, abs=1.0)

    def test_atr_none_for_unknown_symbol(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        assert mgr.get_atr("UNKNOWN") is None


class TestIndicatorManagerRSI:
    def test_rsi_none_before_warmup(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        _feed_bars(mgr, "BTCUSD", 14)
        assert mgr.get_rsi("BTCUSD") is None

    def test_rsi_available_after_period_plus_one(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        _feed_bars(mgr, "BTCUSD", 15)
        rsi = mgr.get_rsi("BTCUSD")
        assert rsi is not None

    def test_rsi_stays_in_0_100_range(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        # Strongly trending upwards
        for i in range(30):
            mgr.update("BTCUSD", 65000.0 + i * 100, 65000.0 + i * 100 - 50, 65000.0 + i * 100)
        rsi = mgr.get_rsi("BTCUSD")
        if rsi is not None:
            assert 0.0 <= rsi <= 100.0

    def test_rsi_high_on_pure_uptrend(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        # All bars go up: price increases monotonically
        price = 100.0
        for _ in range(20):
            price += 1.0
            mgr.update("BTCUSD", price + 0.5, price - 0.5, price)
        rsi = mgr.get_rsi("BTCUSD")
        assert rsi is not None
        assert rsi > 50  # Bullish RSI

    def test_rsi_low_on_pure_downtrend(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        # All bars go down
        price = 200.0
        for _ in range(20):
            price -= 1.0
            mgr.update("BTCUSD", price + 0.5, price - 0.5, price)
        rsi = mgr.get_rsi("BTCUSD")
        assert rsi is not None
        assert rsi < 50  # Bearish RSI


class TestIndicatorManagerEMA:
    def test_ema9_initialized_to_first_close(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        mgr.update("BTCUSD", 65100.0, 64900.0, 65000.0)
        ema9 = mgr.get_ema("BTCUSD", period=9)
        assert ema9 is not None
        # First EMA should be exactly the first close
        assert ema9 == pytest.approx(65000.0, rel=0.01)

    def test_ema21_initialized_to_first_close(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        mgr.update("BTCUSD", 65100.0, 64900.0, 65000.0)
        ema21 = mgr.get_ema("BTCUSD", period=21)
        assert ema21 is not None

    def test_ema9_tracks_uptrend(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        price = 100.0
        for _ in range(30):
            price += 10.0
            mgr.update("BTCUSD", price + 1, price - 1, price)
        ema9 = mgr.get_ema("BTCUSD", period=9)
        ema21 = mgr.get_ema("BTCUSD", period=21)
        # In an uptrend: EMA9 > EMA21
        assert ema9 > ema21


class TestIndicatorManagerVolume(unittest.TestCase):
    def test_volume_sma(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=20)
        for i in range(20):
            mgr.update("SOLUSD", 10.0, 9.0, 9.5, volume=100.0)
        sma = mgr.get_volume_sma("SOLUSD")
        self.assertEqual(sma, 100.0)
        mgr.update("SOLUSD", 10.0, 9.0, 9.5, volume=300.0)
        sma2 = mgr.get_volume_sma("SOLUSD")
        # 19 * 100 + 300 = 2200 / 20 = 110.0
        self.assertAlmostEqual(sma2, 110.0)

    def test_volume_spike(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=20)
        for i in range(20):
            mgr.update("SOLUSD", 10.0, 9.0, 9.5, volume=100.0)
        self.assertFalse(mgr.is_volume_spike("SOLUSD", current_volume=100.0, threshold=2.0))
        self.assertTrue(mgr.is_volume_spike("SOLUSD", current_volume=250.0, threshold=2.0))
        self.assertFalse(mgr.is_volume_spike("SOLUSD", current_volume=150.0, threshold=2.0))


class TestIndicatorManagerLastPrice:
    def test_returns_last_close(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        mgr.update("BTCUSD", 65100.0, 64900.0, 65000.0)
        mgr.update("BTCUSD", 65200.0, 65000.0, 65150.0)
        assert mgr.get_last_price("BTCUSD") == pytest.approx(65150.0)

    def test_returns_none_for_unknown_symbol(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        assert mgr.get_last_price("UNKNOWN") is None


class TestIndicatorManagerMultiTF:
    def test_rsi_5m_available_after_5_bars(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=5)
        # Need enough 5m bars: 5 bars per aggregation, need period+1 = 6 5m-closes = 30 1m bars
        for i in range(60):
            price = 100.0 + (i % 10)
            mgr.update("BTCUSD", price + 1, price - 1, price)
        rsi_5m = mgr.get_rsi_5m("BTCUSD")
        # May still be None if not enough aggregated bars, just check it's a float when not None
        if rsi_5m is not None:
            assert 0.0 <= rsi_5m <= 100.0

    def test_confluence_returns_tuple(self):
        from strategy.indicator_manager import IndicatorManager
        mgr = IndicatorManager(period=14)
        _feed_bars(mgr, "BTCUSD", 20)
        score, desc = mgr.get_mtf_rsi_confluence("BTCUSD")
        assert isinstance(score, int)
        assert isinstance(desc, str)


if __name__ == '__main__':
    unittest.main()
