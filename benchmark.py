import os
import csv
import argparse
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from backtesting.engine import BacktestEngine
from backtesting.metrics import BacktestMetrics

def run_benchmark(note: str, days: int = 30, equity: float = 300.0, symbols: List[str] = None):
    if symbols is None:
        symbols = ['SOLUSD', 'ETHUSD', 'BTCUSD', 'DOGEUSD']

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    print(f"===========================================")
    print(f"      RUNNING REGRESSION BENCHMARK         ")
    print(f"      Period: {days} days")
    print(f"      Symbols: {','.join(symbols)}")
    print(f"      Note: {note}")
    print(f"===========================================")

    engine = BacktestEngine(start_date, end_date, initial_cash=equity)
    
    # Use current optimal parameters as defaults
    params = {'squeeze_threshold': 0.005}
    equity_curve = engine.run_hft_scalper(symbols, hyperparameters=params)
    
    if not equity_curve:
        print("Backtest returned empty equity curve. No data or errors occurred.")
        return

    metrics = BacktestMetrics.calculate_metrics(equity_curve)
    
    # Save to CSV
    csv_path = os.path.join("data", "benchmark_history.csv")
    file_exists = os.path.isfile(csv_path)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    row = {
        "Timestamp": timestamp,
        "Note": note,
        "Initial_Equity": metrics.get("initial_equity", equity),
        "Final_Equity": metrics.get("final_equity", equity),
        "Total_Return_Pct": metrics.get("total_return_pct", 0.0),
        "Max_Drawdown_Pct": metrics.get("max_drawdown_pct", 0.0),
        "Sharpe_Ratio": metrics.get("sharpe_ratio", 0.0),
        "Days_Simulated": metrics.get("days_simulated", 0)
    }
    
    fieldnames = ["Timestamp", "Note", "Initial_Equity", "Final_Equity", "Total_Return_Pct", "Max_Drawdown_Pct", "Sharpe_Ratio", "Days_Simulated"]
    
    with open(csv_path, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
        
    print(f"\n[BENCHMARK COMPLETE] Saved to {csv_path}")
    print(f"Return: {row['Total_Return_Pct']}% | Drawdown: {row['Max_Drawdown_Pct']}% | Sharpe: {row['Sharpe_Ratio']}")

def print_grid():
    csv_path = os.path.join("data", "benchmark_history.csv")
    if not os.path.isfile(csv_path):
        print("No benchmark history found.")
        return
        
    print("\n--- BENCHMARK HISTORY GRID ---")
    print(f"{'Date':<20} | {'Return %':<10} | {'Max DD %':<10} | {'Sharpe':<10} | {'Note'}")
    print("-" * 80)
    
    with open(csv_path, mode='r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            ret = f"{float(row['Total_Return_Pct']):.2f}"
            dd = f"{float(row['Max_Drawdown_Pct']):.2f}"
            sharpe = f"{float(row['Sharpe_Ratio']):.2f}"
            
            print(f"{row['Timestamp']:<20} | {ret:<10} | {dd:<10} | {sharpe:<10} | {row['Note']}")
    print("-" * 80)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run regression benchmark.")
    parser.add_argument("--note", type=str, help="Description of the engine modification", default="")
    parser.add_argument("--view", action="store_true", help="View the benchmark history grid")
    args = parser.parse_args()
    
    if args.view:
        print_grid()
    elif not args.note:
        print("Error: Please provide a description for this benchmark run using --note 'Your message'")
        print("Example: python benchmark.py --note 'Baseline before modifying indicator_manager'")
    else:
        run_benchmark(args.note)
