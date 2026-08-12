import re

with open('realtime_executor.py', encoding='utf-8') as f:
    content = f.read()

# We need to replace the big chunk in _execute_order from line 489 to 622
# The chunk starts around `from alpaca.trading.requests import LimitOrderRequest`
# and ends right before `def on_bar(self, bar):` (or what is now just before `on_bar`)

# Let's find `if self.dry_run:` and keep it.
# Then after `else:`, we replace everything until the end of the method.

# Locate `if self.dry_run:`
dry_run_idx = content.find("        if self.dry_run:")

# Locate the start of `    def on_bar(self, bar):` (if it's there? Wait, `on_bar` is now different, we replaced it)
on_bar_idx = content.find("    def on_bar(self, bar):")

# Verify we found both
if dry_run_idx != -1 and on_bar_idx != -1:
    
    # We will replace from `        else:` inside _execute_order up to `on_bar`
    # Let's find `        else:` after `dry_run_idx`
    else_idx = content.find("        else:\n", dry_run_idx)
    
    replacement = """        else:
            try:
                self._init_trading_client()
                
                # Fetch SMA for Stop Loss
                bands = self.bollinger_detector._calc_bands(symbol)
                sma_sl = bands["sma"] if bands else None
                
                from config.config_manager import RegimeConfigReader
                regimes = RegimeConfigReader.read()
                symbol_regime = regimes.get(symbol, {}).get("regime", "UNKNOWN")
                
                # Order Builder
                order_data = OrderBuilder.build_order(
                    symbol=symbol,
                    price=price,
                    size_usd=size_usd,
                    is_crypto=is_crypto,
                    is_short=is_short,
                    atr=atr,
                    sma_sl=sma_sl,
                    config=typed_config,
                    regime=symbol_regime
                )
                
                # Order Executor
                sentiment_score = bias_info.get("sentiment_score", 0.0)
                reasoning = bias_info.get("reasoning", "")
                bias_type = "BEARISH" if is_short else "BULLISH"
                
                if self.order_executor is None:
                    self.order_executor = OrderExecutor(self._trading_client, self.guard_mgr)
                    
                order_id = self.order_executor.execute_order(
                    order_request=order_data,
                    price=price,
                    size_usd=size_usd,
                    change_pct=change_pct,
                    bias_type=bias_type,
                    sentiment_score=sentiment_score,
                    reasoning=reasoning,
                    is_short=is_short
                )
                return order_id
                
            except Exception as e:
                logger.error(f"[WS] Order execution setup failed for {symbol}: {e}")
                return None

"""
    
    content = content[:else_idx] + replacement + content[on_bar_idx:]

with open('realtime_executor.py', 'w', encoding='utf-8') as f:
    f.write(content)
