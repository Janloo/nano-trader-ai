import re

with open('realtime_executor.py', encoding='utf-8') as f:
    content = f.read()

# Add import
import_statement = "from hft.bar_processor import BarProcessor\n"
content = content.replace("from config.config_manager import config_manager\n", "from config.config_manager import config_manager\n" + import_statement)

# Initialize BarProcessor
init_bar_processor = """        self.bar_processor = BarProcessor(
            vol_detector=self.vol_detector,
            indicator_mgr=self.indicator_mgr,
            guard_mgr=self.guard_mgr,
            momentum_filter=self.momentum_filter,
            vwap_strategy=self.vwap_strategy,
            bollinger_detector=self.bollinger_detector,
            correlation_engine=self.correlation_engine,
            volume_profile_mgr=self.volume_profile_mgr
        )"""
content = re.sub(r'        self\.volume_profile_mgr = VolumeProfileManager\(\)', '        self.volume_profile_mgr = VolumeProfileManager()\n' + init_bar_processor, content)

# Replace on_bar
# Find the start of on_bar
on_bar_start = content.find("    def on_bar(self, bar):")
on_stock_bar_start = content.find("    def on_stock_bar(self, bar):")

# The block to replace is from on_bar to just before on_stock_bar
replacement = """    def on_bar(self, bar):
        \"\"\"
        Called on each incoming 1-minute bar from the WebSocket stream.
        Delegates to BarProcessor and executes the returned actions.
        \"\"\"
        symbol_raw = bar.symbol  # e.g. "BTC/USD"
        symbol = symbol_raw.replace("/", "")  # "BTCUSD"
        price = float(bar.close)
        bar_time = bar.timestamp if hasattr(bar, "timestamp") else datetime.now(timezone.utc)

        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)
            
        self.current_time = bar_time
        high = float(bar.high) if hasattr(bar, "high") else price
        low = float(bar.low) if hasattr(bar, "low") else price
        volume = float(bar.volume) if hasattr(bar, "volume") else 0.0
        
        WSTradeLogger.log_price(symbol, price, bar_time)
        self._manage_trailing_stops(price, symbol)

        actions = self.bar_processor.process_crypto_bar(
            symbol=symbol, price=price, bar_time=bar_time,
            high=high, low=low, volume=volume,
            alert_states=self.alert_states
        )
        
        for action in actions:
            if action["action"] == "CLOSE_ALL":
                try:
                    self._init_trading_client()
                    self._trading_client.close_position(action["symbol"])
                    WSTradeLogger.write_logbook(f"[EMERGENCY] Chiusura d'emergenza su {action['symbol']} completata.")
                    # Remove alert
                    if action["symbol"] in self.alert_states:
                        del self.alert_states[action["symbol"]]
                except Exception:
                    pass
            elif action["action"] == "EXECUTE":
                self._execute_order(
                    symbol=action["symbol"],
                    price=price,
                    dip_pct=action["dip_pct"],
                    bias_info=action["bias_info"],
                    is_short=action["is_short"],
                    atr=action["atr"]
                )

"""

content = content[:on_bar_start] + replacement + content[on_stock_bar_start:]

with open('realtime_executor.py', 'w', encoding='utf-8') as f:
    f.write(content)
