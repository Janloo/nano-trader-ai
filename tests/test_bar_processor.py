"""
tests/test_bar_processor.py

TDD tests for hft/bar_processor.py
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

class TestBarProcessor:
    def test_cataclysm_alert_returns_close_all_action(self):
        from hft.bar_processor import BarProcessor
        
        # Mocks
        vol_detector = MagicMock()
        vol_detector.update.return_value = (-1.5, -2.0, 0.0) # immediate dip is confirmed
        
        indicator_mgr = MagicMock()
        guard_mgr = MagicMock()
        momentum_filter = MagicMock()
        vwap_strategy = MagicMock()
        bollinger_detector = MagicMock()
        correlation_engine = MagicMock()
        volume_profile_mgr = MagicMock()
        
        processor = BarProcessor(
            vol_detector=vol_detector,
            indicator_mgr=indicator_mgr,
            guard_mgr=guard_mgr,
            momentum_filter=momentum_filter,
            vwap_strategy=vwap_strategy,
            bollinger_detector=bollinger_detector,
            correlation_engine=correlation_engine,
            volume_profile_mgr=volume_profile_mgr
        )
        
        alert_states = {"BTCUSD": {"type": "CATACLYSM", "timestamp": datetime.now(timezone.utc)}}
        
        actions = processor.process_crypto_bar(
            symbol="BTCUSD", price=50000.0, bar_time=datetime.now(timezone.utc),
            high=50100.0, low=49900.0, volume=100.0, alert_states=alert_states
        )
        
        assert len(actions) == 1
        assert actions[0]["action"] == "CLOSE_ALL"
        assert actions[0]["symbol"] == "BTCUSD"

    def test_dip_real_trading_triggers_execute_action(self):
        from hft.bar_processor import BarProcessor
        from config.config_manager import RiskConfigReader
        
        # Override config
        RiskConfigReader.read = MagicMock(return_value={
            "crypto_micro_dip_real_trading": True,
            "alpha_smart_trailing": False
        })
        
        vol_detector = MagicMock()
        # trailing_dip is -0.3%
        vol_detector.update.return_value = (None, -0.3, None)
        
        indicator_mgr = MagicMock()
        indicator_mgr.get_atr.return_value = 100.0
        indicator_mgr.get_rsi.return_value = 50.0
        
        guard_mgr = MagicMock()
        guard_mgr.is_symbol_in_cooldown.return_value = False
        guard_mgr.check_and_update_panic_state.return_value = False
        
        # We need a BULLISH bias for DIP to trigger
        with patch('data.bias_reader.BiasReader.get_bias_for_symbol', return_value={"bias": "BULLISH", "sentiment_score": 0.8}):
            processor = BarProcessor(
                vol_detector=vol_detector,
                indicator_mgr=indicator_mgr,
                guard_mgr=guard_mgr,
                momentum_filter=MagicMock(),
                vwap_strategy=MagicMock(),
                bollinger_detector=MagicMock(),
                correlation_engine=MagicMock(),
                volume_profile_mgr=MagicMock()
            )
            
            actions = processor.process_crypto_bar(
                symbol="BTCUSD", price=50000.0, bar_time=datetime.now(timezone.utc),
                high=50100.0, low=49900.0, volume=100.0, alert_states={}
            )
            
            assert len(actions) == 1
            assert actions[0]["action"] == "EXECUTE"
            assert actions[0]["is_short"] == False
            assert actions[0]["dip_pct"] == -0.3

    def test_warmup_period_blocks_execution(self):
        from hft.bar_processor import BarProcessor
        
        indicator_mgr = MagicMock()
        indicator_mgr.get_atr.return_value = None # None means warmup
        
        processor = BarProcessor(
            vol_detector=MagicMock(),
            indicator_mgr=indicator_mgr,
            guard_mgr=MagicMock(),
            momentum_filter=MagicMock(),
            vwap_strategy=MagicMock(),
            bollinger_detector=MagicMock(),
            correlation_engine=MagicMock(),
            volume_profile_mgr=MagicMock()
        )
        
        actions = processor.process_crypto_bar(
            symbol="BTCUSD", price=50000.0, bar_time=datetime.now(timezone.utc),
            high=50100.0, low=49900.0, volume=100.0, alert_states={}
        )
        
        assert len(actions) == 0

    def test_bollinger_squeeze_buy_triggers_execute_action(self):
        from hft.bar_processor import BarProcessor
        import config.config_manager
        
        vol_detector = MagicMock()
        vol_detector.update.return_value = (None, None, None)
        
        indicator_mgr = MagicMock()
        indicator_mgr.get_atr.return_value = 100.0
        indicator_mgr.get_rsi.return_value = 50.0
        indicator_mgr.is_volume_spike.return_value = True
        
        guard_mgr = MagicMock()
        guard_mgr.is_symbol_in_cooldown.return_value = False
        guard_mgr.check_and_update_panic_state.return_value = False
        
        bollinger_detector = MagicMock()
        bollinger_detector.check_signal.return_value = "SQUEEZE_BUY"
        
        momentum_filter = MagicMock()
        momentum_filter.should_allow_buy.return_value = True

        vwap_strategy = MagicMock()
        vwap_strategy.check_signal.return_value = "NEUTRAL"
        
        processor = BarProcessor(
            vol_detector=vol_detector,
            indicator_mgr=indicator_mgr,
            guard_mgr=guard_mgr,
            momentum_filter=momentum_filter,
            vwap_strategy=vwap_strategy,
            bollinger_detector=bollinger_detector,
            correlation_engine=MagicMock(),
            volume_profile_mgr=MagicMock()
        )
        
        # We need to mock BiasReader internally or just let it return NEUTRAL
        actions = processor.process_crypto_bar(
            symbol="BTCUSD", price=50000.0, bar_time=datetime.now(timezone.utc),
            high=50100.0, low=49900.0, volume=100.0, alert_states={}
        )
        
        # Because we mocked SQUEEZE_BUY and Volume Spike = True
        # It should trigger an execute action
        assert len(actions) == 1
        assert actions[0]["action"] == "EXECUTE"
        assert actions[0]["symbol"] == "BTCUSD"
        assert actions[0]["is_short"] is False
