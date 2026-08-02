import logging
from datetime import datetime, timedelta, timezone
from backtesting.engine import BacktestEngine
from backtesting.metrics import BacktestMetrics

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

def run_dry_run():
    # Backtest last 7 days
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)
    
    print("===========================================")
    print("      DRY-RUN BACKTEST (HFT SCALPER)       ")
    print("===========================================")
    
    engine = BacktestEngine(start_date, end_date, initial_cash=10000.0)
    
    # We will run HFT on BTCUSD
    equity_curve = engine.run_hft_scalper(["BTCUSD"])
    
    metrics = BacktestMetrics.calculate_metrics(equity_curve)
    
    print("\n--- BACKTEST RESULTS ---")
    for k, v in metrics.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    run_dry_run()
