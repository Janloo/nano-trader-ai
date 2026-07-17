import argparse
import sys
import time
from datetime import datetime, timezone, timedelta
import pandas as pd

from config.settings import (
    validate_config, TICKERS, APCA_API_KEY_ID, APCA_API_SECRET_KEY, logger
)
from client.alpaca_client import AlpacaClientWrapper
from strategy.ai_analyzer import GeminiSentimentStrategy
from execution.trader import AITrader
from news_collector import fetch_financial_news
from alpaca.data.timeframe import TimeFrame

def run_iteration(client: AlpacaClientWrapper, strategy: GeminiSentimentStrategy, executor: AITrader, dry_run: bool):
    """Executes a single quantitative trade cycle: RSS Scrape -> Gemini AI Analyzer -> Order Execution -> Reporting."""
    logger.info("Starting nano-trader-ai AI quantitative scanning iteration...")
    
    if dry_run:
        logger.info("=== DRY RUN MODE: No orders will be submitted, and live API is bypassed ===")
        positions = []
        account_equity = 100000.00
        account_buying_power = 400000.00
        logger.info(f"Mock Account Equity: ${account_equity:.2f} | Buying Power: ${account_buying_power:.2f}")
    else:
        try:
            account = client.get_account_info()
            positions = client.get_positions()
            logger.info(f"Account Equity: ${float(account.equity):.2f} | Buying Power: ${float(account.buying_power):.2f}")
        except Exception as e:
            logger.error(f"Error fetching account details from Alpaca: {e}")
            return

    iteration_sentiments = []
    
    for ticker in TICKERS:
        logger.info(f"Processing ticker: {ticker}")
        
        # 1. Fetch RSS news feed from last 24 hours
        news_list = fetch_financial_news(ticker)
        
        # Compile titles and descriptions into context text for Gemini
        news_text = ""
        for index, art in enumerate(news_list, 1):
            news_text += f"{index}. Title: {art['title']}\nSummary: {art['summary']}\n\n"
            
        # 2. Retrieve latest price for fallback / trade logs
        if dry_run:
            current_price = 740.00 if "SPY" in ticker else 64000.00
        else:
            try:
                # Fetch recent bar to obtain last close price
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=5)
                bars_df = client.get_historical_bars([ticker], TimeFrame.Day, start_date, end_date)
                if not bars_df.empty:
                    if isinstance(bars_df.index, pd.MultiIndex):
                        ticker_bars = bars_df.xs(ticker, level=0)
                    else:
                        ticker_bars = bars_df
                    current_price = float(ticker_bars["close"].iloc[-1])
                else:
                    current_price = 100.0
            except Exception as e:
                logger.warning(f"Could not parse current price for {ticker}: {e}. Defaulting to 100.0")
                current_price = 100.0

        # 3. Analyze news sentiment with Gemini
        ai_decision = strategy.analyze_news_text(ticker, news_text)
        iteration_sentiments.append(ai_decision.get("sentiment_score", 0.0))
        
        # 4. Execute trades based on AI quantitative rules
        raw_news_titles = [art['title'] for art in news_list]
        executor.execute_ai_decision(ticker, ai_decision, current_price, positions, raw_news_titles)

    # 5. Compute average macroeconomic sentiment for this snapshot
    avg_sentiment = sum(iteration_sentiments) / len(iteration_sentiments) if iteration_sentiments else 0.0

    # 6. Log portfolio state
    if dry_run:
        equity = 100000.00
        buying_power = 400000.00
        unrealized_pnl = 0.00
    else:
        try:
            equity = float(account.equity)
            buying_power = float(account.buying_power)
            unrealized_pnl = sum(float(getattr(p, 'unrealized_pl', 0.0)) for p in positions)
        except Exception as e:
            logger.error(f"Error calculating portfolio metrics: {e}")
            equity = 100000.00
            buying_power = 400000.00
            unrealized_pnl = 0.00

    executor.log_portfolio_status(equity, buying_power, unrealized_pnl, avg_sentiment)

    # Update historical AI feedback loop metrics
    try:
        from execution.tracker import update_feedback_loop_metrics
        update_feedback_loop_metrics(client)
    except Exception as e:
        logger.error(f"Failed to update feedback loop metrics: {e}")

    # 7. Auto-generate visual dashboard HTML report
    try:
        from reporting.generator import generate_dashboard
        generate_dashboard()
    except Exception as e:
        logger.error(f"Failed to auto-generate HTML dashboard: {e}")

    logger.info("Iteration completed.")

def main():
    parser = argparse.ArgumentParser(description="nano-trader-ai Gemini quantitative bot entry point")
    parser.add_argument("--dry-run", action="store_true", help="Run the bot in mock simulation dry-run mode.")
    parser.add_argument("--loop", action="store_true", help="Run the bot in a continuous loop.")
    parser.add_argument("--interval", type=int, default=3600, help="Loop interval in seconds (default: 3600).")
    args = parser.parse_args()

    # If not in dry-run, validate keys exist
    if not args.dry_run:
        try:
            validate_config()
        except ValueError as e:
            logger.error(f"Config validation error: {e}")
            logger.error("To test the bot without live credentials, please run with the '--dry-run' argument.")
            sys.exit(1)

    # Initialize components
    if args.dry_run:
        client = None
    else:
        client = AlpacaClientWrapper()
        
    strategy = GeminiSentimentStrategy()
    executor = AITrader(client)

    # Start Control Room HTTP Server backend (only in loop mode)
    server = None
    if args.loop:
        from server import DashboardServer
        server = DashboardServer(host="127.0.0.1", port=8000)
        server.start()

    try:
        if args.loop:
            logger.info(f"Starting bot in loop mode. Interval: {args.interval} seconds.")
            while True:
                run_iteration(client, strategy, executor, args.dry_run)
                logger.info(f"Sleeping for {args.interval} seconds...")
                time.sleep(args.interval)
        else:
            run_iteration(client, strategy, executor, args.dry_run)
    except KeyboardInterrupt:
        logger.info("Shutting down bot gracefully.")
    finally:
        if server:
            server.stop()

if __name__ == "__main__":
    main()
