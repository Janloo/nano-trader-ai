import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from config.settings import logger

def parse_rss_date(date_str: str) -> datetime:
    """
    Parses common RSS date strings (RFC 822 format) and returns a timezone-aware UTC datetime.
    """
    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
        "%d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ"
    ]
    
    date_str = date_str.strip()
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            continue
            
    logger.warning(f"Could not parse RSS date: '{date_str}', falling back to current UTC time.")
    return datetime.now(timezone.utc)

def fetch_financial_news(symbol: str) -> List[Dict[str, Any]]:
    """
    Fetches news items from Google News RSS feed for a symbol.
    Only returns articles published within the last 24 hours.
    """
    query = f"{symbol} ETF finance economy"
    if "BTC" in symbol.upper():
        query = "Bitcoin BTCUSD cryptocurrency market"
        
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    logger.info(f"Fetching RSS feed for '{symbol}' from: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
    except Exception as e:
        logger.error(f"Failed to download RSS feed for {symbol}: {e}")
        return []
        
    try:
        root = ET.fromstring(xml_data)
    except Exception as e:
        logger.error(f"Failed to parse RSS XML for {symbol}: {e}")
        return []
        
    articles = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    
    channel = root.find("channel")
    if channel is None:
        logger.warning(f"No channel element found in RSS feed for {symbol}")
        return []
        
    for item in channel.findall("item"):
        title_elem = item.find("title")
        desc_elem = item.find("description")
        date_elem = item.find("pubDate")
        link_elem = item.find("link")
        
        title = title_elem.text if title_elem is not None else ""
        description = desc_elem.text if desc_elem is not None else ""
        date_str = date_elem.text if date_elem is not None else ""
        link = link_elem.text if link_elem is not None else ""
        
        # Filter by publication date
        pub_date = parse_rss_date(date_str)
        if pub_date >= cutoff:
            articles.append({
                "title": title,
                "summary": description,
                "timestamp": pub_date.isoformat(),
                "link": link
            })
            
    logger.info(f"Retrieved {len(articles)} RSS news items from the last 24h for {symbol}")
    return articles


# Macro-economic feed sources for global market context
# Each tuple: (feed_name, rss_url)
_MACRO_FEEDS = [
    ("US Economy",      "https://news.google.com/rss/search?q=federal+reserve+interest+rates+inflation+economy&hl=en-US&gl=US&ceid=US:en"),
    ("Stock Markets",   "https://news.google.com/rss/search?q=stock+market+S%26P500+nasdaq+earnings&hl=en-US&gl=US&ceid=US:en"),
    ("Crypto Market",   "https://news.google.com/rss/search?q=Bitcoin+Ethereum+crypto+market+BTC&hl=en-US&gl=US&ceid=US:en"),
    ("Tech & AI",       "https://news.google.com/rss/search?q=NVIDIA+Apple+Microsoft+AI+semiconductor+earnings&hl=en-US&gl=US&ceid=US:en"),
    ("Global Macro",    "https://news.google.com/rss/search?q=global+economy+recession+GDP+central+bank&hl=en-US&gl=US&ceid=US:en"),
    ("Energy & Macro",  "https://news.google.com/rss/search?q=oil+price+energy+commodities+dollar+index&hl=en-US&gl=US&ceid=US:en"),
    ("EV & Consumer",   "https://news.google.com/rss/search?q=Tesla+Amazon+consumer+spending+retail+EV&hl=en-US&gl=US&ceid=US:en"),
]

def fetch_macro_news(max_articles: int = 40) -> List[Dict[str, Any]]:
    """
    Fetches global macroeconomic and market news from multiple RSS feeds.
    Returns a deduplicated list of recent articles for AI Universe selection.
    Uses a 48-hour window to ensure sufficient news context even after weekends.
    """
    all_articles: List[Dict[str, Any]] = []
    seen_titles: set = set()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)  # 48h window for broader context

    for feed_name, url in _MACRO_FEEDS:
        logger.info(f"Fetching macro RSS feed: {feed_name}")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                xml_data = response.read()
        except Exception as e:
            logger.warning(f"Failed to fetch macro feed '{feed_name}': {e}")
            continue

        try:
            root = ET.fromstring(xml_data)
        except Exception as e:
            logger.warning(f"Failed to parse macro feed XML '{feed_name}': {e}")
            continue

        channel = root.find("channel")
        if channel is None:
            continue

        for item in channel.findall("item"):
            title_elem = item.find("title")
            desc_elem = item.find("description")
            date_elem = item.find("pubDate")
            link_elem = item.find("link")

            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
            description = desc_elem.text if desc_elem is not None else ""
            date_str = date_elem.text if date_elem is not None else ""
            link = link_elem.text if link_elem is not None else ""

            if not title or title in seen_titles:
                continue

            pub_date = parse_rss_date(date_str)
            if pub_date >= cutoff:
                seen_titles.add(title)
                all_articles.append({
                    "title": title,
                    "summary": description,
                    "timestamp": pub_date.isoformat(),
                    "link": link,
                    "feed": feed_name
                })

    # Sort by recency and cap
    all_articles.sort(key=lambda x: x["timestamp"], reverse=True)
    result = all_articles[:max_articles]
    logger.info(f"Fetched {len(result)} unique macro news items from {len(_MACRO_FEEDS)} feeds (48h window).")
    return result

