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
