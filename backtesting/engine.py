import logging
import json
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from unittest.mock import patch
import google.genai as genai

from backtesting.simulated_broker import SimulatedAlpacaClient
from backtesting.data_loader import BacktestDataLoader

logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(self, start_date: datetime, end_date: datetime, initial_cash: float = 100000.0):
        self.start_date = start_date.replace(tzinfo=timezone.utc) if start_date.tzinfo is None else start_date
        self.end_date = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date
        self.current_time = self.start_date
        
        self.data_loader = BacktestDataLoader()
        self.broker = SimulatedAlpacaClient(self.data_loader, initial_cash=initial_cash)
        self.equity_curve: List[Dict[str, Any]] = []
        
        # We store original generate_content to call it on cache miss
        self._original_generate = genai.models.Models.generate_content if hasattr(genai.models.Models, 'generate_content') else None
        
    def _mocked_generate_content(self, model, contents, *args, **kwargs):
        """Intercepts AI calls to use SQLite cache during backtests."""
        # This is a simplified cache key based on the current backtest date.
        # In a real scenario, we might hash the `contents` string.
        date_str = self.current_time.strftime("%Y-%m-%d")
        
        # We try to derive a "symbol" context or use a global key
        prompt_str = str(contents)
        cache_key = "global"
        
        # Extremely basic symbol extraction for cache keys
        if "Symbol: " in prompt_str:
            import re
            m = re.search(r"Symbol:\s*([A-Z]+)", prompt_str)
            if m:
                cache_key = m.group(1)

        cached_response = self.data_loader.get_cached_ai_response(cache_key, date_str)
        if cached_response:
            logger.info(f"[AI Cache] HIT for {cache_key} on {date_str}")
            class MockResponse:
                text = cached_response['text']
            return MockResponse()
            
        logger.info(f"[AI Cache] MISS for {cache_key} on {date_str}. Calling live API...")
        # Since google-genai is used (genai.GenerativeModel.generate_content)
        # We might be patching the class method or instance method.
        # It's better to just let it run and then cache it.
        # Actually, if we patched the instance method, we need the real one.
        raise Exception("Live API call prevented in backtest to avoid burning credits. Pre-warm cache or implement live fallback.")

    def run_macro_swing(self, universe: List[str]):
        """Runs the macro swing strategy (daily loop)"""
        logger.info(f"Starting Macro Swing Backtest from {self.start_date} to {self.end_date}")
        
        # We need a custom datetime class that we can mock
        class MockDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return self.current_time

        with patch('client.alpaca_client.AlpacaClientWrapper', return_value=self.broker), \
             patch('main_macro.AlpacaClientWrapper', return_value=self.broker), \
             patch('execution.trader.AlpacaClientWrapper', return_value=self.broker), \
             patch('strategy.ai_selector.AlpacaClientWrapper', return_value=self.broker), \
             patch('strategy.ai_analyzer.AlpacaClientWrapper', return_value=self.broker), \
             patch('strategy.ai_analyzer.genai.GenerativeModel.generate_content', side_effect=self._mocked_generate_content), \
             patch('strategy.ai_selector.genai.GenerativeModel.generate_content', side_effect=self._mocked_generate_content):
             
             while self.current_time <= self.end_date:
                 logger.info(f"--- [BACKTEST DATE] {self.current_time.strftime('%Y-%m-%d')} ---")
                 self.broker.set_simulated_time(self.current_time)
                 
                 # Fetch daily price updates for the simulated broker so it can value the portfolio
                 from alpaca.data.timeframe import TimeFrame
                 try:
                     daily_bars = self.broker.get_historical_bars(universe, TimeFrame.Day, self.current_time - timedelta(days=5), self.current_time)
                     if not daily_bars.empty:
                         for symbol in universe:
                             sym_data = daily_bars[daily_bars.index.get_level_values('symbol') == symbol]
                             if not sym_data.empty:
                                 close_price = float(sym_data.iloc[-1]['close'])
                                 self.broker.set_latest_price(symbol, close_price)
                 except Exception as e:
                     logger.warning(f"Could not update daily prices for {self.current_time}: {e}")

                 # Run the DAS cycle (Macro AI)
                 try:
                     from main_macro import run_das_cycle
                     run_das_cycle()
                 except Exception as e:
                     logger.error(f"Error in backtest cycle: {e}")
                     
                 # Record Equity
                 account = self.broker.get_account_info()
                 self.equity_curve.append({
                     'date': self.current_time.strftime("%Y-%m-%d"),
                     'equity': float(account.equity),
                     'cash': float(account.cash)
                 })
                 
                 # Advance 1 day
                 self.current_time += timedelta(days=1)
                 
        logger.info("Macro Swing Backtest Complete.")
        return self.equity_curve

    def run_hft_scalper(self, symbols: List[str], hyperparameters: Dict[str, Any] = None):
        """Runs the HFT Scalper strategy using historical 1-minute bars."""
        logger.info(f"Starting HFT Backtest from {self.start_date} to {self.end_date} on {symbols} with params {hyperparameters}")
        
        from realtime_executor import RealtimeExecutor
        from alpaca.data.timeframe import TimeFrame
        
        executor = RealtimeExecutor(symbols)
        
        # Mock disk I/O to avoid extreme slowdowns during backtesting
        from realtime_executor import WSTradeLogger
        WSTradeLogger.log_price = lambda symbol, price, timestamp: None
        
        executor._trading_client = self.broker
        
        # Inject hyperparameters
        if hyperparameters:
            if 'window_seconds' in hyperparameters:
                executor.window_seconds = hyperparameters['window_seconds']
            if 'dip_threshold_pct' in hyperparameters:
                executor.dip_threshold_pct = hyperparameters['dip_threshold_pct']
            if 'spike_threshold_pct' in hyperparameters:
                executor.spike_threshold_pct = hyperparameters['spike_threshold_pct']
            if 'rsi_threshold' in hyperparameters:
                executor.rsi_threshold = hyperparameters['rsi_threshold']
            if 'tp_multiplier' in hyperparameters:
                mult = hyperparameters['tp_multiplier']
                executor.trailing_mgr.trailing_pct *= mult
                new_levels = []
                for level in executor.trailing_mgr.escalator_levels:
                    new_levels.append({
                        "activation_pct": level["activation_pct"] * mult,
                        "close_fraction": level["close_fraction"],
                        "label": level["label"]
                    })
                executor.trailing_mgr.escalator_levels = new_levels
            
            # --- Momentum Breakout Parameters ---
            if 'squeeze_threshold' in hyperparameters:
                executor.bollinger_detector.squeeze_threshold_pct = hyperparameters['squeeze_threshold']
            
            if 'volume_multiplier' in hyperparameters:
                # We will inject this temporarily onto the executor so on_bar can use it
                executor.volume_spike_multiplier = hyperparameters['volume_multiplier']
            
            if 'tp_pct' in hyperparameters:
                executor.crypto_micro_tp_pct = hyperparameters['tp_pct']
            if 'imbalance_threshold' in hyperparameters and hasattr(executor, 'orderbook_analyzer'):
                executor.orderbook_analyzer.imbalance_threshold = hyperparameters['imbalance_threshold']
        
        # Fetch 1-minute bars for the entire period
        minute_bars = self.broker.get_historical_bars(symbols, TimeFrame.Minute, self.start_date, self.end_date)
            
        if minute_bars.empty:
            logger.error("No minute bars found for backtest period.")
            return []
            
        # Convert multi-index dataframe to a flat list of dicts sorted by timestamp
        flat_bars = minute_bars.reset_index().sort_values(by='timestamp')
        
        # Inject the historical cache into the broker to prevent expensive SQLite lookups per bar
        self.broker.set_historical_cache(minute_bars)
        
        class MockBar:
            def __init__(self, symbol, close, timestamp, high, low, volume):
                self.symbol = symbol
                self.close = close
                self.timestamp = timestamp
                self.high = high
                self.low = low
                self.volume = volume
        
        class MockDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return self.current_time

        with patch('realtime_executor.datetime', MockDateTime):
            # Optimize loop using itertuples instead of iterrows for massive speedup
            for row in flat_bars.itertuples():
                sym = row.symbol
                bar_dict = {
                    't': row.timestamp.isoformat() if hasattr(row.timestamp, 'isoformat') else str(row.timestamp),
                    'o': row.open,
                    'h': row.high,
                    'l': row.low,
                    'c': row.close,
                    'v': row.volume,
                    'vw': getattr(row, 'vwap', row.close),
                    'n': getattr(row, 'trade_count', 0)
                }
                close = float(row.close)
                ts = row.timestamp
                
                self.current_time = ts
                sym_clean = sym.replace("/", "")
                self.broker.set_simulated_time(
                    ts, 
                    price_dict={sym_clean: close},
                    high_dict={sym_clean: row.high},
                    low_dict={sym_clean: row.low}
                )
                
                bar = MockBar(sym, close, ts, row.high, row.low, row.volume)
                # Feed bar to executor
                try:
                    executor.on_bar(bar)
                except Exception as e:
                    logger.error(f"Error processing HFT bar: {e}")
                
                # Record equity at the end of each day
                if ts.hour == 23 and ts.minute == 59:
                    account = self.broker.get_account_info()
                    self.equity_curve.append({
                        'date': ts.strftime("%Y-%m-%d"),
                        'equity': float(account.equity),
                        'cash': float(account.cash)
                    })
                    
        logger.info("HFT Scalper Backtest Complete.")
        return self.equity_curve

