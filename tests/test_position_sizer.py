import unittest
import sys
import os

# Add parent directory to path to import risk_management
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from risk_management.position_sizer import PositionSizer

class TestPositionSizer(unittest.TestCase):
    def test_kelly_fraction_positive(self):
        # W = 0.55, R = 1.5 -> f = 0.55 - (0.45 / 1.5) = 0.55 - 0.30 = 0.25
        f = PositionSizer.calculate_kelly_fraction(0.55, 1.5, multiplier=1.0)
        self.assertAlmostEqual(f, 0.25)
        
        # With Half-Kelly multiplier
        f_half = PositionSizer.calculate_kelly_fraction(0.55, 1.5, multiplier=0.5)
        self.assertAlmostEqual(f_half, 0.125)

    def test_kelly_fraction_negative_edge(self):
        # W = 0.40, R = 1.0 -> f = 0.40 - (0.60 / 1.0) = -0.20 -> capped at 0.0
        f = PositionSizer.calculate_kelly_fraction(0.40, 1.0)
        self.assertEqual(f, 0.0)

    def test_calculate_position_size_atr(self):
        risk_config = {
            "max_capital_per_trade_pct": 0.1,
            "max_risk_per_trade_pct": 0.02,
            "atr_stop_loss_multiplier": 2.0,
            "use_kelly_criterion": False
        }
        total_equity = 10000.0
        buying_power = 10000.0
        atr = 5.0
        price = 100.0
        
        # sl_distance = (5 * 2) / 100 = 0.10 (10%)
        # risk_amount = 10000 * 0.02 = 200
        # pos_size = 200 / 0.10 = 2000
        # capped by max capital = 1000 (10% of bp) -> allocation = 1000
        # modulation (sentiment=1.0) = 1.0
        
        size = PositionSizer.calculate_position_size("AAPL", price, 1.0, atr, risk_config, total_equity, buying_power, 0)
        self.assertEqual(size, 1000.0)
        
        # Test lower sentiment
        # sentiment = 0.75 -> modulation = 0.5
        size_low_sent = PositionSizer.calculate_position_size("AAPL", price, 0.75, atr, risk_config, total_equity, buying_power, 0)
        self.assertEqual(size_low_sent, 500.0)

    def test_calculate_position_size_with_kelly(self):
        risk_config = {
            "max_capital_per_trade_pct": 1.0, # no cap
            "max_risk_per_trade_pct": 0.02,
            "atr_stop_loss_multiplier": 2.0,
            "use_kelly_criterion": True,
            "kelly_fraction_multiplier": 0.5,
            "historical_win_rate": 0.55,
            "historical_reward_risk": 1.5
        }
        total_equity = 10000.0
        buying_power = 10000.0
        atr = 5.0
        price = 100.0
        
        # Kelly fraction = 0.125 (from above)
        # base allocation = 2000
        # with Kelly = 2000 * 0.125 = 250
        # sentiment 1.0 -> modulation 1.0 -> final = 250
        
        size = PositionSizer.calculate_position_size("AAPL", price, 1.0, atr, risk_config, total_equity, buying_power, 0)
        self.assertAlmostEqual(size, 250.0)

if __name__ == '__main__':
    unittest.main()
