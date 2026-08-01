import os
import json
import unittest
from unittest.mock import patch, mock_open
from config.config_manager import ConfigManager, RiskSettings

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

if __name__ == "__main__":
    unittest.main()
