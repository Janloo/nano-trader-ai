import pytest
from unittest import mock
import os
from config.settings import TICKERS, validate_config

def test_tickers_parsing():
    """Verify that TICKERS settings are loaded as a non-empty list of uppercase strings."""
    assert isinstance(TICKERS, list)
    assert len(TICKERS) > 0
    for ticker in TICKERS:
        assert ticker.isupper()

def test_validate_config_missing_keys():
    """Verify that validate_config raises ValueError if credentials are missing."""
    with mock.patch("config.settings.APCA_API_KEY_ID", None), \
         mock.patch("config.settings.APCA_API_SECRET_KEY", None):
        with pytest.raises(ValueError) as excinfo:
            validate_config()
        assert "Alpaca API credentials missing" in str(excinfo.value)
