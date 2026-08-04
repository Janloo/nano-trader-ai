import logging
import itertools
import pandas as pd
from datetime import datetime, timedelta, timezone
from backtesting.engine import BacktestEngine
from backtesting.metrics import BacktestMetrics

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("Optimizer")

# Disable chatty logs from the trading engine to speed up backtesting by 100x
logging.getLogger("nano-trader-ai").setLevel(logging.WARNING)
logging.getLogger("backtesting.simulated_broker").setLevel(logging.WARNING)

def run_grid_search(months: int = 1, initial_cash: float = 200.0, target_symbol: str = "SOL/USD"):
    # Define backtest window, snapped to midnight to maximize cache hits
    end_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=30 * months)
    
    logger.info(f"Starting Grid Search HPO for {target_symbol}")
    logger.info(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Grid Search Parameters
    param_grid = {
        'squeeze_threshold': [0.002, 0.003, 0.004], # 0.2%, 0.3%, 0.4% squeeze band width (Mean is 0.5%)
        'volume_multiplier': [1.5, 2.0],    # 1.5x, 2x volume spike
        'tp_pct': [0.5, 1.0, 2.0]           # 0.5%, 1%, 2% take profit
    }
    
    keys = list(param_grid.keys())
    combinations = list(itertools.product(*[param_grid[k] for k in keys]))
    
    logger.info(f"Total combinations to evaluate: {len(combinations)}")
    
    results = []
    
    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        logger.info(f"--- Evaluando {i+1}/{len(combinations)}: {params} ---")
        
        try:
            # Re-initialize engine to reset state and simulated broker
            engine = BacktestEngine(start_date, end_date, initial_cash=initial_cash)
            
            # The engine and data loader will automatically use the chunked SQLite cache
            # so the first iteration will download data, and subsequent ones will be instant.
            equity_curve = engine.run_hft_scalper([target_symbol], hyperparameters=params)
            
            metrics = BacktestMetrics.calculate_metrics(equity_curve)
            
            result_row = {**params, **metrics}
            results.append(result_row)
            
            logger.info(f"Result: Return={metrics.get('total_return_pct')}%, Sharpe={metrics.get('sharpe_ratio')}, MaxDD={metrics.get('max_drawdown_pct')}%")
            
        except Exception as e:
            logger.error(f"Failed combination {params}: {e}", exc_info=True)
            
    # Save results
    if results:
        df = pd.DataFrame(results)
        df = df.sort_values(by='total_return_pct', ascending=False)
        
        import os
        os.makedirs("data", exist_ok=True)
        out_path = "data/optimization_results.csv"
        df.to_csv(out_path, index=False)
        logger.info(f"Optimization complete. Saved to {out_path}")
        
        print("\n=== TOP 3 CONFIGURATIONS ===")
        print(df.head(3).to_string(index=False))
    else:
        logger.error("No results obtained.")

if __name__ == "__main__":
    # Test 1 month Volume Profile Pivot
    run_grid_search(months=1)
