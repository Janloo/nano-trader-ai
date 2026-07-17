import pytest
from news_collector import parse_rss_date, fetch_financial_news
from datetime import datetime, timezone

def test_parse_rss_date():
    """Verify parsing RFC-822 date strings from RSS feeds into timezone-aware UTC datetime."""
    date_str = "Fri, 17 Jul 2026 15:30:00 GMT"
    dt = parse_rss_date(date_str)
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2026
    assert dt.month == 7
    assert dt.day == 17

def test_fetch_financial_news_structure():
    """Verify that RSS fetching returns a list of dictionaries with expected news keys."""
    res = fetch_financial_news("SPY")
    assert isinstance(res, list)
    if res:
        first = res[0]
        assert "title" in first
        assert "summary" in first
        assert "timestamp" in first
        assert "link" in first
