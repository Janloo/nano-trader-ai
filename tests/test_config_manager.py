import os
import json
import unittest
import pytest
from unittest.mock import patch, mock_open
from config.config_manager import ConfigManager, RiskSettings, RiskConfigReader, RegimeConfigReader


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.manager = ConfigManager()
        self.mock_json = {
            "max_capital_per_trade_pct": 0.1,
            "hft_budget_pct": 0.5
        }

    @patch("os.path.exists", return_value=True)
    def test_load_valid_config(self, mock_exists):
        with patch("builtins.open", mock_open(read_data=json.dumps(self.mock_json))):
            config = self.manager.load_risk_settings()
            self.assertEqual(config.max_capital_per_trade_pct, 0.1)
            self.assertEqual(config.hft_budget_pct, 0.5)
            # Check default fallback
            self.assertEqual(config.use_kelly_criterion, True)

    @patch("os.path.exists", return_value=False)
    def test_load_missing_file_returns_defaults(self, mock_exists):
        config = self.manager.load_risk_settings()
        self.assertIsInstance(config, RiskSettings)
        self.assertEqual(config.hft_budget_pct, 0.20)

    @patch("os.path.exists", return_value=True)
    @patch("time.sleep", return_value=None)
    def test_load_retry_on_empty_file(self, mock_sleep, mock_exists):
        # Simulate an empty file (during atomic replace) returning JSONDecodeError/ValueError
        with patch("builtins.open", mock_open(read_data="")) as m_open:
            config = self.manager.load_risk_settings(max_retries=3)
            # Should retry 3 times and fallback to defaults
            self.assertEqual(m_open.call_count, 3)
            self.assertEqual(config.hft_budget_pct, 0.20)


class TestRiskConfigReader:
    def test_returns_dict(self):
        result = RiskConfigReader.read()
        assert isinstance(result, dict)
        assert "hft_budget_pct" in result

    def test_returns_defaults_on_missing_file(self, tmp_path):
        # Point config path to non-existent file
        with patch("config.config_manager.ConfigManager._config_path",
                   str(tmp_path / "nonexistent.json")):
            result = RiskConfigReader.read()
        assert result["hft_budget_pct"] == 0.20


class TestRegimeConfigReader:
    def test_returns_empty_dict_when_file_missing(self, tmp_path):
        with patch("config.config_manager.RegimeConfigReader.REGIME_FILE",
                   str(tmp_path / "market_regime.json")):
            result = RegimeConfigReader.read()
        assert result == {}

    def test_reads_regime_correctly(self, tmp_path):
        regime_file = tmp_path / "market_regime.json"
        regime_data = {"BTCUSD": {"regime": "BULL_TREND", "adx": 28.5}}
        regime_file.write_text(json.dumps(regime_data))
        with patch("config.config_manager.RegimeConfigReader.REGIME_FILE", str(regime_file)):
            result = RegimeConfigReader.read()
        assert result["BTCUSD"]["regime"] == "BULL_TREND"

    def test_returns_empty_dict_on_corrupt_file(self, tmp_path):
        regime_file = tmp_path / "market_regime.json"
        regime_file.write_text("{ not valid json }")
        with patch("config.config_manager.RegimeConfigReader.REGIME_FILE", str(regime_file)):
            result = RegimeConfigReader.read()
        assert result == {}


if __name__ == "__main__":
    unittest.main()
