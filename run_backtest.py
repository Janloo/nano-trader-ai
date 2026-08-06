import logging
import argparse
from datetime import datetime, timedelta, timezone
from backtesting.engine import BacktestEngine
from backtesting.metrics import BacktestMetrics

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

def run_backtest(days, symbols, equity=10000.0, quiet=False):
    if quiet:
        logging.getLogger().setLevel(logging.CRITICAL)
        logging.getLogger('nano-trader-ai').setLevel(logging.CRITICAL)
        logging.getLogger('backtesting.engine').setLevel(logging.CRITICAL)
    else:
        logging.getLogger().setLevel(logging.INFO)

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    if not quiet:
        print("===========================================")
        print(f"      DRY-RUN BACKTEST (HFT SCALPER)      ")
        print(f"      Period: {days} days")
        print(f"      Symbols: {', '.join(symbols)}")
        print(f"      Equity: ${equity}")
        print("===========================================")
    
    engine = BacktestEngine(start_date, end_date, initial_cash=equity)
    
    # Use current optimal parameters as defaults (squeeze 0.005)
    params = {'squeeze_threshold': 0.005}
    equity_curve = engine.run_hft_scalper(symbols, hyperparameters=params)
    
    if not equity_curve:
        if not quiet: print("Backtest returned empty equity curve. No data or errors occurred.")
        return None

    metrics = BacktestMetrics.calculate_metrics(equity_curve)
    
    print("\\n--- BACKTEST RESULTS ---")
    for k, v in metrics.items():
        print(f"{k}: {v}")
        
    return metrics

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run HFT Backtest')
    parser.add_argument('--days', type=int, default=3, help='Number of days to backtest')
    parser.add_argument('--symbols', nargs='+', default=['SOL/USD'], help='Symbols to trade')
    parser.add_argument('--equity', type=float, default=10000.0, help='Initial cash equity')
    parser.add_argument('--quiet', action='store_true', help='Suppress logs for batch processing')
    
    args = parser.parse_args()
    
    run_backtest(args.days, args.symbols, args.equity, args.quiet)
