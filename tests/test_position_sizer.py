import unittest
from unittest.mock import patch
from risk_management.position_sizer import PositionSizer
from config.config_manager import RiskSettings

class TestPositionSizer(unittest.TestCase):
    def setUp(self):
        self.config = RiskSettings()
        self.config.hft_budget_pct = 0.20
        self.config.max_capital_per_trade_pct = 0.05
        self.config.max_risk_per_trade_pct = 0.01

    def test_kelly_fraction_basic(self):
        f = PositionSizer.calculate_kelly_fraction(win_rate=0.55, reward_risk_ratio=1.5, multiplier=1.0)
        # f = 0.55 - (0.45 / 1.5) = 0.55 - 0.3 = 0.25
        self.assertAlmostEqual(f, 0.25)

    def test_kelly_fraction_no_edge(self):
        # f = 0.4 - (0.6 / 1.0) = -0.2 -> 0.0
        f = PositionSizer.calculate_kelly_fraction(win_rate=0.4, reward_risk_ratio=1.0)
        self.assertEqual(f, 0.0)

    @patch("risk_management.performance_tracker.get_live_stats")
    def test_calculate_kelly_size_success(self, mock_get_live_stats):
        # Force get_live_stats to fail or return insufficient data
        mock_get_live_stats.return_value = {"sufficient_data": False}
        
        # 100k equity, 0.01 risk = 1k. 
        # ATR=5, Price=100. SL distance = 5*2.0 / 100 = 0.1 (10%)
        # Base Size = 1k / 0.1 = 10k.
        # Max cap = 100k * 0.05 = 5k.
        # Allocation = 5k.
        # Kelly = 0.55, RR = 1.5 -> f = 0.25
        # Kelly size = 5k * 0.25 = 1250
        # Sentiment = 1.0 -> modulation = 1.0. Final = 1250
        
        size = PositionSizer.calculate_kelly_size(
            symbol="BTCUSD", price=100.0, sentiment_score=1.0, 
            atr=5.0, config=self.config, 
            total_equity=100000.0, buying_power=100000.0
        )
        self.assertAlmostEqual(size, 1250.0)

    def test_calculate_kelly_size_zero_equity(self):
        size = PositionSizer.calculate_kelly_size(
            symbol="BTCUSD", price=100.0, sentiment_score=1.0, 
            atr=5.0, config=self.config, 
            total_equity=0.0, buying_power=100000.0
        )
        self.assertEqual(size, 0.0)

    def test_calculate_kelly_size_insufficient_bp(self):
        size = PositionSizer.calculate_kelly_size(
            symbol="BTCUSD", price=100.0, sentiment_score=1.0, 
            atr=5.0, config=self.config, 
            total_equity=100000.0, buying_power=500.0
        )
        # Wanted 1250, only has 500. Should return 500.
        self.assertAlmostEqual(size, 500.0)

    def test_calculate_micro_size_basic(self):
        # HFT Budget = 20k. Risk fraction = 0.01 -> size = 20k * 0.01 = 200.
        size = PositionSizer.calculate_micro_size(
            symbol="BTCUSD", config=self.config,
            total_equity=100000.0, buying_power=100000.0, risk_fraction=0.01
        )
        self.assertEqual(size, 200.0)

    def test_calculate_micro_size_insufficient_bp(self):
        size = PositionSizer.calculate_micro_size(
            symbol="BTCUSD", config=self.config,
            total_equity=100000.0, buying_power=5.0, risk_fraction=0.01
        )
        # Cannot afford minimum 10.0
        self.assertEqual(size, 0.0)

    def test_calculate_micro_size_capped_by_hft_budget(self):
        # If total equity is 500, HFT budget is 100.
        # Max size = 1% of 100 = 1.0.
        # 1.0 is less than 10.0 minimum check.
        size = PositionSizer.calculate_micro_size(
            symbol="BTCUSD", config=self.config,
            total_equity=500.0, buying_power=500.0, risk_fraction=0.01
        )
        self.assertEqual(size, 0.0)

if __name__ == "__main__":
    unittest.main()
