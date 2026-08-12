import re

with open('realtime_executor.py', encoding='utf-8') as f:
    content = f.read()

# 1. Init GuardManager
content = content.replace(
    'self.panic_cooldown_until: float = 0.0',
    'self.guard_mgr = GuardManager()'
)

# 2. Delete _check_market_panic definition
content = re.sub(r'    def _check_market_panic.*?return False\n\n', '', content, flags=re.DOTALL)

# 3. Delete _is_on_cooldown definition
content = re.sub(r'    def _is_on_cooldown.*?return elapsed < cooldown_target\n', '', content, flags=re.DOTALL)

# 4. Replace panic usage
replacement_panic = '''        risk_config = RiskConfigReader.read()
        if self.guard_mgr.check_and_update_panic_state(
            trailing_states=self.vol_detector._trailing_state,
            threshold_pct=risk_config.get("guardian_panic_threshold_pct", -1.20),
            required_count=risk_config.get("guardian_panic_asset_count", 3),
            cooldown_min=risk_config.get("guardian_panic_cooldown_min", 3)
        ):'''
content = content.replace('if self._check_market_panic():', replacement_panic)

# 5. Replace _global_buy_cooldown_until
content = content.replace('self._global_buy_cooldown_until = now_ts + 3600', 'self.guard_mgr.trigger_global_error_cooldown(60)')

# 6. Replace all _is_on_cooldown usages
content = re.sub(
    r'self\._is_on_cooldown\((.*?)\)', 
    r'self.guard_mgr.is_symbol_in_cooldown(\1, cooldown_seconds=15 if \1.endswith("USD") else ORDER_COOLDOWN_SECONDS)', 
    content
)

# 7. Replace register trade
content = re.sub(r'self\._last_order_time\[symbol\] = .*?\n', 'self.guard_mgr.register_trade(symbol)\n', content)

with open('realtime_executor.py', 'w', encoding='utf-8') as f:
    f.write(content)
