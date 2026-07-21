import unittest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from strategy.fast_guardian import FastGuardian

class TestFastGuardian(unittest.TestCase):
    def setUp(self):
        # We mock the Gemini model so we don't make real API calls in CI
        self.guardian = FastGuardian()
        self.guardian.model = MagicMock()

    def test_cataclysm_evaluation(self):
        mock_response = MagicMock()
        mock_response.text = "CATACLYSM"
        self.guardian.model.generate_content.return_value = mock_response
        
        result = self.guardian.evaluate_headline("Coinbase halts all withdrawals following massive SEC lawsuit and internal hack.")
        self.assertEqual(result, "CATACLYSM")

    def test_moonshot_evaluation(self):
        mock_response = MagicMock()
        mock_response.text = "MOONSHOT"
        self.guardian.model.generate_content.return_value = mock_response
        
        result = self.guardian.evaluate_headline("US Government officially adopts Bitcoin as strategic reserve, allocating $50B.")
        self.assertEqual(result, "MOONSHOT")
        
    def test_ignore_evaluation(self):
        mock_response = MagicMock()
        mock_response.text = "IGNORE"
        self.guardian.model.generate_content.return_value = mock_response
        
        result = self.guardian.evaluate_headline("Apple's Q3 earnings are in-line with Wall Street expectations, revenue up 2%.")
        self.assertEqual(result, "IGNORE")
        
    def test_unexpected_response_format(self):
        mock_response = MagicMock()
        mock_response.text = "The answer is CATACLYSM due to reasons."
        self.guardian.model.generate_content.return_value = mock_response
        
        # Our internal logic looks for "CATACLYSM" in the string
        result = self.guardian.evaluate_headline("Some bad news")
        self.assertEqual(result, "CATACLYSM")

if __name__ == '__main__':
    unittest.main()
