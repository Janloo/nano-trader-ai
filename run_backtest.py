import logging
import argparse
from datetime import datetime, timedelta, timezone
from backtesting.engine import BacktestEngine
from backtesting.metrics import BacktestMetrics

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

def run_backtest(days, symbols):
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    print("===========================================")
    print(f"      DRY-RUN BACKTEST (HFT SCALPER)      ")
    print(f"      Period: {days} days")
    print(f"      Symbols: {', '.join(symbols)}")
    print("===========================================")
    
    engine = BacktestEngine(start_date, end_date, initial_cash=10000.0)
    
    # Use current optimal parameters as defaults (squeeze 0.005)
    params = {'squeeze_threshold': 0.005}
    equity_curve = engine.run_hft_scalper(symbols, hyperparameters=params)
    
    if not equity_curve:
        print("Backtest returned empty equity curve. No data or errors occurred.")
        return

    metrics = BacktestMetrics.calculate_metrics(equity_curve)
    
    print("\\n--- BACKTEST RESULTS ---")
    for k, v in metrics.items():
        print(f"{k}: {v}")
        
    return metrics

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run HFT Backtest')
    parser.add_argument('--days', type=int, default=3, help='Number of days to backtest')
    parser.add_argument('--symbols', nargs='+', default=['SOL/USD'], help='Symbols to trade')
    
    args = parser.parse_args()
    
    run_backtest(args.days, args.symbols)
