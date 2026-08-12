import re

with open('realtime_executor.py', encoding='utf-8') as f:
    content = f.read()

start_idx = content.find("    def on_stock_bar(")
end_idx = content.find("    def _run_simulation(")

replacement = """    def on_stock_bar(self, bar):
        \"\"\"
        Called on each incoming bar for stocks (QQQ).
        Delegates to BarProcessor and executes returned actions.
        \"\"\"
        symbol = bar.symbol
        price = float(bar.close)
        bar_time = bar.timestamp if hasattr(bar, "timestamp") else datetime.now(timezone.utc)

        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)

        high = float(bar.high) if hasattr(bar, "high") else price
        low = float(bar.low) if hasattr(bar, "low") else price

        actions = self.bar_processor.process_stock_bar(
            symbol=symbol, price=price, bar_time=bar_time,
            high=high, low=low, target_symbols=self.target_symbols
        )
        
        for action in actions:
            if action["action"] == "EXECUTE":
                # We can't really execute short on QQQ here anyway, but it's passed as False
                self._execute_order(
                    symbol=action["symbol"],
                    price=action["price"],
                    dip_pct=action["dip_pct"],
                    bias_info=action["bias_info"],
                    is_short=action["is_short"],
                    atr=action["atr"]
                )
                self._last_order_time[action["symbol"]] = datetime.now(timezone.utc)

"""

content = content[:start_idx] + replacement + content[end_idx:]

with open('realtime_executor.py', 'w', encoding='utf-8') as f:
    f.write(content)
