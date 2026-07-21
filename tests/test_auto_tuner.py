import unittest
import sys
import os
import json
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from risk_management.auto_tuner import AutoTuner

class TestAutoTuner(unittest.TestCase):
    def setUp(self):
        self.test_config_path = "test_risk_settings.json"
        with open(self.test_config_path, "w") as f:
            json.dump({
                "win_rate_estimate": 0.50,
                "reward_risk_ratio_estimate": 1.0,
                "use_kelly_criterion": True
            }, f)
            
    def tearDown(self):
        if os.path.exists(self.test_config_path):
            os.remove(self.test_config_path)

    @patch("risk_management.auto_tuner.RISK_SETTINGS_PATH", "test_risk_settings.json")
    @patch("risk_management.auto_tuner.get_ai_analytics_completed_feedback")
    def test_tune_kelly_criterion_insufficient_samples(self, mock_get_logs):
        # Provide only 5 samples (min 10)
        mock_get_logs.return_value = [{"return_4h": 1.0} for _ in range(5)]
        
        AutoTuner.tune_kelly_criterion(min_samples=10)
        
        with open("test_risk_settings.json", "r") as f:
            config = json.load(f)
            
        # Should remain unchanged
        self.assertEqual(config["win_rate_estimate"], 0.50)
        
    @patch("risk_management.auto_tuner.RISK_SETTINGS_PATH", "test_risk_settings.json")
    @patch("risk_management.auto_tuner.get_ai_analytics_completed_feedback")
    def test_tune_kelly_criterion_update(self, mock_get_logs):
        # Provide 10 samples: 6 wins (avg 2.0%), 4 losses (avg -1.0%)
        # Win rate: 60%
        # R/R: 2.0 / 1.0 = 2.0
        logs = []
        for _ in range(6):
            logs.append({"return_4h": 2.0})
        for _ in range(4):
            logs.append({"return_4h": -1.0})
            
        mock_get_logs.return_value = logs
        
        AutoTuner.tune_kelly_criterion(min_samples=10)
        
        with open("test_risk_settings.json", "r") as f:
            config = json.load(f)
            
        self.assertEqual(config["win_rate_estimate"], 0.60)
        self.assertEqual(config["reward_risk_ratio_estimate"], 2.0)
        
    @patch("risk_management.auto_tuner.RISK_SETTINGS_PATH", "test_risk_settings.json")
    @patch("risk_management.auto_tuner.get_ai_analytics_completed_feedback")
    def test_tune_kelly_criterion_all_wins(self, mock_get_logs):
        # 10 wins, 0 losses
        logs = [{"return_4h": 1.5} for _ in range(10)]
        mock_get_logs.return_value = logs
        
        AutoTuner.tune_kelly_criterion(min_samples=10)
        
        with open("test_risk_settings.json", "r") as f:
            config = json.load(f)
            
        self.assertEqual(config["win_rate_estimate"], 1.0)
        # R/R ratio should default to conservative 2.0 when there are no losses
        self.assertEqual(config["reward_risk_ratio_estimate"], 2.0)

if __name__ == '__main__':
    unittest.main()
