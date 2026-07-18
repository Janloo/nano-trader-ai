import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta, date
import pandas as pd

from config.settings import (
    validate_config, APCA_API_KEY_ID, APCA_API_SECRET_KEY, logger
)
from client.alpaca_client import AlpacaClientWrapper
from strategy.ai_selector import GeminiAssetSelector, load_universe
from execution.trader import AITrader
from news_collector import fetch_macro_news
from alpaca.data.timeframe import TimeFrame


# Weekend days (Mon=0 ... Sun=6)
_WEEKEND_DAYS = {5, 6}  # Saturday, Sunday

# NYSE market hours in ET (Eastern Time)
_NYSE_OPEN_H = 9
_NYSE_OPEN_M = 30
_NYSE_CLOSE_H = 16
_NYSE_CLOSE_M = 0


def _is_weekend() -> bool:
    return date.today().weekday() in _WEEKEND_DAYS


def _is_nyse_open() -> bool:
    """
    Returns True if the current UTC time falls within NYSE trading hours
    (Mon-Fri 09:30-16:00 Eastern Time = 13:30-20:00 UTC, no DST adjustment).
    Uses a simple UTC offset approach: ET is UTC-4 (EDT summer) / UTC-5 (EST winter).
    """
    now_utc = datetime.now(timezone.utc)
    # Determine ET offset: last Sun March → last Sun Nov = EDT (UTC-4), else EST (UTC-5)
    # Approximate: months 3-10 inclusive → EDT
    month = now_utc.month
    utc_offset_hours = -4 if 3 <= month <= 10 else -5
    et_hour = (now_utc.hour + utc_offset_hours) % 24
    et_minute = now_utc.minute
    weekday = now_utc.weekday()  # Mon=0 ... Fri=4

    if weekday >= 5:  # Sat/Sun
        return False
    if (et_hour, et_minute) < (_NYSE_OPEN_H, _NYSE_OPEN_M):
        return False
    if (et_hour, et_minute) >= (_NYSE_CLOSE_H, _NYSE_CLOSE_M):
        return False
    return True


def _market_status_str() -> str:
    """Returns a human-readable market status string."""
    if _is_weekend():
        return "WEEKEND - US equity markets closed (crypto active 24/7)"
    if _is_nyse_open():
        return "OPEN - NYSE trading hours active"
    return "CLOSED - Outside NYSE trading hours (crypto active 24/7)"


def _save_daily_selection(selected_assets: list, macro_article_count: int):
    """Persists the current AI selection to data/daily_selection.json for the dashboard."""
    selection_path = os.path.join("data", "state", "daily_selection.json")
    os.makedirs(os.path.dirname(selection_path), exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "macro_articles_analyzed": macro_article_count,
        "selected_assets": selected_assets
    }
    try:
        with open(selection_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save daily_selection.json: {e}")


def _write_market_bias(bias_assets: list, macro_article_count: int):
    """
    Atomically writes market_bias.json for the WebSocket executor.
    Uses write-to-tmp + os.replace() to prevent partial reads during concurrent access.
    Bias expires after 2 hours (set in expires_at).
    """
    bias_path = os.path.join("data", "state", "market_bias.json")
    tmp_path = bias_path + ".tmp"
    os.makedirs(os.path.dirname(bias_path), exist_ok=True)

    now = datetime.now(timezone.utc)
    payload = {
        "target_assets": bias_assets,
        "timestamp": now.isoformat(),
        "expires_at": (now + timedelta(hours=2)).isoformat(),
        "macro_articles_analyzed": macro_article_count
    }

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
        os.replace(tmp_path, bias_path)
        logger.info(f"[DAS Phase 3] market_bias.json written with {len(bias_assets)} asset(s). Expires at {payload['expires_at']}")
    except Exception as e:
        logger.error(f"Failed to write market_bias.json: {e}")
        # Clean up tmp file if it exists
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _fetch_price(client: AlpacaClientWrapper, ticker: str, dry_run: bool) -> float:
    """Fetches the latest close price for a ticker. Returns a mock value in dry-run mode."""
    if dry_run:
        mock_prices = {"BTCUSD": 64000.00, "ETHUSD": 3200.00}
        return mock_prices.get(ticker, 250.00)
    try:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=5)
        bars_df = client.get_historical_bars([ticker], TimeFrame.Day, start_date, end_date)
        if not bars_df.empty:
            ticker_bars = bars_df.xs(ticker, level=0) if isinstance(bars_df.index, pd.MultiIndex) else bars_df
            return float(ticker_bars["close"].iloc[-1])
    except Exception as e:
        logger.warning(f"Could not fetch price for {ticker}: {e}. Defaulting to 100.0")
    return 100.0


def run_iteration(
    client: AlpacaClientWrapper,
    selector: GeminiAssetSelector,
    executor: AITrader,
    dry_run: bool
):
    """
    Dynamic Asset Selection (DAS) trade cycle:
      Phase 1 — Fetch global macro news headlines
      Phase 2 — AI selects up to 2 assets from the universe
      Phase 3 — Fetch prices + execute orders for selected assets
      Phase 4 — Log portfolio snapshot + regenerate dashboard
    """
    logger.info("Starting nano-trader-ai DAS quantitative scanning iteration...")

    # --- Account info ---
    if dry_run:
        logger.info("=== DRY RUN MODE: No orders will be submitted ===")
        positions = []
        account_equity = 100000.00
        account_buying_power = 400000.00
        logger.info(f"Mock Account Equity: ${account_equity:.2f} | Buying Power: ${account_buying_power:.2f}")
    else:
        try:
            account = client.get_account_info()
            positions = client.get_positions()
            account_equity = float(account.equity)
            account_buying_power = float(account.buying_power)
            logger.info(f"Account Equity: ${account_equity:.2f} | Buying Power: ${account_buying_power:.2f}")
        except Exception as e:
            logger.error(f"Error fetching account details: {e}")
            return

    from news_collector import fetch_macro_news, fetch_alpaca_news

    # ─────────────────────────────────────────────
    # Phase 1: Fetch global macro news & specific asset news
    # ─────────────────────────────────────────────
    logger.info("[DAS Phase 1] Fetching global macro news...")
    macro_articles = fetch_macro_news(max_articles=30)

    feed_payload = []
    macro_news_text = "--- GLOBAL MACRO NEWS ---\n"
    for idx, art in enumerate(macro_articles, 1):
        feed_payload.append({
            "source": art.get('feed', 'Macro News'),
            "title": art.get('title', ''),
            "summary": art.get("summary", ""),
            "link": art.get("link", "#"),
            "timestamp": art.get("timestamp", datetime.now(timezone.utc).isoformat())
        })
        macro_news_text += f"{idx}. [{art.get('feed', 'News')}] {art['title']}\n"
        if art.get("summary"):
            macro_news_text += f"   Summary: {art['summary'][:200]}\n"
        macro_news_text += "\n"

    logger.info("[DAS Phase 1] Fetching asset-specific Alpaca news...")
    universe_config = load_universe()
    universe_assets = universe_config.get("assets", [])
    
    # Pre-fetch specific Alpaca news for the universe to give the AI an edge
    macro_news_text += "\n--- ASSET-SPECIFIC NEWS (ALPACA) ---\n"
    for asset in universe_assets:
        symbol = asset["symbol"]
        alpaca_articles = fetch_alpaca_news(symbol, APCA_API_KEY_ID, APCA_API_SECRET_KEY)
        if alpaca_articles:
            macro_news_text += f"\nLatest news for {symbol}:\n"
            for idx, art in enumerate(alpaca_articles[:3], 1): # Top 3 per asset to save tokens
                feed_payload.append({
                    "source": f"Alpaca - {symbol}",
                    "title": art.get('title', ''),
                    "summary": art.get("summary", ""),
                    "link": art.get("link", "#"),
                    "timestamp": art.get("timestamp", datetime.now(timezone.utc).isoformat())
                })
                macro_news_text += f"{idx}. {art['title']}\n"
                if art.get("summary"):
                    macro_news_text += f"   Summary: {art['summary'][:150]}\n"

    # Save collected news to a JSON file for the dashboard
    try:
        with open("market_news.json", "w", encoding="utf-8") as f:
            json.dump(feed_payload, f, indent=4)
        logger.info(f"Saved {len(feed_payload)} news items to market_news.json")
    except Exception as e:
        logger.error(f"Failed to write market_news.json: {e}")

    if not macro_news_text.strip() or len(macro_news_text) < 100:
        macro_news_text = "No news articles retrieved in the last 24 hours."
        logger.warning("[DAS Phase 1] No news found — proceeding with empty context.")

    # ─────────────────────────────────────────────
    # Phase 2: AI selects assets from universe
    # ─────────────────────────────────────────────
    logger.info("[DAS Phase 2] Running AI asset selection from universe...")
    sentiment_threshold = universe_config.get("sentiment_threshold", 0.75)

    selected_assets = selector.select_assets(universe_assets, macro_news_text)
    _save_daily_selection(selected_assets, len(macro_articles))

    if not selected_assets:
        logger.warning("[DAS Phase 2] AI returned no asset selections. Skipping trade execution.")
    else:
        symbols_selected = [a["symbol"] for a in selected_assets]
        logger.info(f"[DAS Phase 2] AI selected: {symbols_selected}")
        # Send Telegram notification for the AI selection
        try:
            from notifications.telegram_notifier import notify_das_selection
            notify_das_selection(selected_assets, len(macro_articles))
        except Exception as e:
            logger.warning(f"Telegram selection notification failed: {e}")

    # ─────────────────────────────────────────────
    # Phase 3: Write market_bias.json for WebSocket executor
    # ─────────────────────────────────────────────
    market_status = _market_status_str()
    logger.info(f"[DAS Phase 3] Market status: {market_status}")
    logger.info("[DAS Phase 3] Writing market bias for real-time executor...")
    iteration_sentiments = []

    bias_assets = []
    sentiment_threshold = universe_config.get("sentiment_threshold", 0.75)

    for asset in selected_assets:
        symbol = asset["symbol"]
        sentiment_score = asset.get("sentiment_score", 0.0)
        reasoning = asset.get("reasoning", "")
        asset_type = asset.get("type", "unknown")
        iteration_sentiments.append(sentiment_score)

        # Determine bias from sentiment score
        if sentiment_score >= sentiment_threshold:
            bias = "BULLISH"
        elif sentiment_score <= -sentiment_threshold:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        bias_assets.append({
            "symbol": symbol,
            "bias": bias,
            "sentiment_score": sentiment_score,
            "reasoning": reasoning,
            "asset_type": asset_type
        })

        logger.info(
            f"[DAS Phase 3] {symbol} | Bias: {bias} | "
            f"Score: {sentiment_score:.2f} | Type: {asset_type}"
        )

    # Write market_bias.json atomically (write to .tmp then replace)
    _write_market_bias(bias_assets, len(macro_articles))

    # ─────────────────────────────────────────────
    # Phase 4: Portfolio snapshot + dashboard
    # ─────────────────────────────────────────────
    avg_sentiment = (
        sum(iteration_sentiments) / len(iteration_sentiments)
        if iteration_sentiments else 0.0
    )

    if dry_run:
        equity = account_equity
        buying_power = account_buying_power
        unrealized_pnl = 0.00
    else:
        try:
            equity = float(account.equity)
            buying_power = float(account.buying_power)
            unrealized_pnl = sum(float(getattr(p, "unrealized_pl", 0.0)) for p in positions)
        except Exception as e:
            logger.error(f"Error calculating portfolio metrics: {e}")
            equity = account_equity
            buying_power = account_buying_power
            unrealized_pnl = 0.00

    executor.log_portfolio_status(equity, buying_power, unrealized_pnl, avg_sentiment)

    try:
        from execution.tracker import update_feedback_loop_metrics
        update_feedback_loop_metrics(client)
    except Exception as e:
        logger.error(f"Failed to update feedback loop metrics: {e}")

    try:
        from reporting.generator import generate_dashboard
        generate_dashboard()
    except Exception as e:
        logger.error(f"Failed to auto-generate HTML dashboard: {e}")

    logger.info("DAS Iteration completed.")


def main():
    parser = argparse.ArgumentParser(description="nano-trader-ai DAS quantitative bot")
    parser.add_argument("--dry-run", action="store_true", help="Mock simulation mode.")
    parser.add_argument("--loop", action="store_true", help="Run in continuous loop.")
    parser.add_argument("--interval", type=int, default=3600, help="Loop interval in seconds.")
    args = parser.parse_args()

    if not args.dry_run:
        try:
            validate_config()
        except ValueError as e:
            logger.error(f"Config validation error: {e}")
            logger.error("Run with --dry-run for testing without live credentials.")
            sys.exit(1)

    client = None if args.dry_run else AlpacaClientWrapper()
    selector = GeminiAssetSelector()
    executor = AITrader(client)

    server = None
    if args.loop:
        from server import DashboardServer
        server = DashboardServer(host="127.0.0.1", port=8000)
        server.start()

    try:
        if args.loop:
            logger.info(f"Starting DAS bot in loop mode. Interval: {args.interval}s.")
            while True:
                run_iteration(client, selector, executor, args.dry_run)
                logger.info(f"Sleeping for {args.interval} seconds...")
                time.sleep(args.interval)
        else:
            run_iteration(client, selector, executor, args.dry_run)
    except KeyboardInterrupt:
        logger.info("Shutting down bot gracefully.")
    finally:
        if server:
            server.stop()


if __name__ == "__main__":
    main()
