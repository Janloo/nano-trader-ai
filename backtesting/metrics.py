import pandas as pd
import numpy as np
from typing import List, Dict, Any

class BacktestMetrics:
    @staticmethod
    def calculate_metrics(equity_curve: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not equity_curve:
            return {"error": "No equity curve data"}
            
        df = pd.DataFrame(equity_curve)
        if 'equity' not in df.columns:
            return {"error": "Invalid equity curve format"}
            
        initial_equity = df['equity'].iloc[0]
        final_equity = df['equity'].iloc[-1]
        
        # 1. Total Return
        total_return_pct = ((final_equity - initial_equity) / initial_equity) * 100.0
        
        # 2. Max Drawdown
        df['peak'] = df['equity'].cummax()
        df['drawdown'] = (df['equity'] - df['peak']) / df['peak']
        max_drawdown_pct = df['drawdown'].min() * 100.0
        
        # 3. Sharpe Ratio (approximate daily)
        df['daily_return'] = df['equity'].pct_change()
        mean_return = df['daily_return'].mean()
        std_return = df['daily_return'].std()
        
        # Annualized Sharpe (assuming 252 trading days for stocks, 365 for crypto. Let's use 365)
        sharpe_ratio = 0.0
        if std_return > 0:
            sharpe_ratio = (mean_return / std_return) * np.sqrt(365)
            
        return {
            "initial_equity": round(initial_equity, 2),
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return_pct, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "days_simulated": len(df)
        }
