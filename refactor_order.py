import re

with open('realtime_executor.py', encoding='utf-8') as f:
    content = f.read()

# 1. Imports
content = content.replace(
    'from execution.guard_checks import GuardManager\n',
    'from execution.guard_checks import GuardManager\nfrom execution.order_builder import OrderBuilder\nfrom execution.order_executor import OrderExecutor\n'
)

# 2. Init OrderExecutor
content = content.replace(
    'self.guard_mgr = GuardManager()',
    'self.guard_mgr = GuardManager()\n        self.order_executor = None'
)

# Initialize it inside _init_trading_client if needed or just whenever.
# But wait, we can't initialize it in __init__ because we don't have the trading client yet.
# Let's initialize it in _init_trading_client
init_client_str = '''        if self._trading_client is None and not self.dry_run:
            from alpaca.trading.client import TradingClient
            is_paper = True  # Always paper for safety
            self._trading_client = TradingClient(
                api_key=APCA_API_KEY_ID,
                secret_key=APCA_API_SECRET_KEY,
                paper=is_paper
            )
            self.order_executor = OrderExecutor(self._trading_client, self.guard_mgr)'''

content = re.sub(r'        if self\._trading_client is None and not self\.dry_run:\n.*?\n            \)\n', init_client_str + '\n', content, flags=re.DOTALL)

# Now, let's find the execution block. The execution block starts at `order_symbol = symbol` or earlier.
# In realtime_executor.py:
#                         # Dynamic TP/SL using ATR if available, else fallback
#                         if atr > 0:
#                             ...
#                         # Set cooldown
#                         self.guard_mgr.register_trade(symbol)
#                         return order_id
# We will use regex to replace from `# Determine dynamic TP multiplier` down to `return order_id` with our new classes.

regex_block = r'                        # Determine dynamic TP multiplier.*?self\.guard_mgr\.register_trade\(symbol\)\n                        return order_id'

replacement_block = '''                        regimes = RegimeConfigReader.read()
                        regime = regimes.get(symbol, {}).get("regime", "UNKNOWN")
                        
                        order_req = OrderBuilder.build_order(
                            symbol=symbol, price=price, size_usd=size_usd,
                            is_crypto=is_crypto, is_short=is_short, atr=atr,
                            sma_sl=None, config=risk_config, regime=regime
                        )
                        
                        order_id = self.order_executor.execute_order(
                            order_request=order_req, price=price, size_usd=size_usd,
                            change_pct=change_pct, bias_type=bias_type, sentiment_score=sentiment_score,
                            reasoning=reasoning, is_short=is_short
                        )
                        return order_id'''

content = re.sub(regex_block, replacement_block, content, flags=re.DOTALL)

with open('realtime_executor.py', 'w', encoding='utf-8') as f:
    f.write(content)
