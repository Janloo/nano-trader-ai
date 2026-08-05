import sys
with open('realtime_executor.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if 'logger.error(f"[WS] Insufficient balance error caught for {symbol}.")' in line:
        lines[i] = line.replace('logger.error(f"[WS] Insufficient balance error caught for {symbol}.")', 'logger.error(f"[WS] Insufficient balance error caught for {symbol}. Reason: {e}")')
    if 'self._global_buy_cooldown_until = time.time() + 3600' in line:
        lines[i] = line.replace('self._global_buy_cooldown_until = time.time() + 3600', 'import datetime as _dt\n                    now_ts = _dt.datetime.now(_dt.timezone.utc).timestamp()\n                    self._global_buy_cooldown_until = now_ts + 3600')

with open('realtime_executor.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
