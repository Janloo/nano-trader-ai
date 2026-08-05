import sys

with open('realtime_executor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace dip_pct in market panic with imm_dip_pct
content = content.replace(
    'state.get("dip_pct", 0) <= threshold_pct',
    'state.get("imm_dip_pct", 0) <= threshold_pct'
)

# Replace the VolatilityDetector update to store imm_dip_pct
content = content.replace(
    'pct_change_high = ((price - window_high) / window_high) * 100.0',
    'pct_change_high = ((price - window_high) / window_high) * 100.0\n        if window_high > 0 and len(window) > 1:\n            state["imm_dip_pct"] = ((price - window[-2][1]) / window[-2][1]) * 100.0'
)

with open('realtime_executor.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Modifications applied successfully.")
