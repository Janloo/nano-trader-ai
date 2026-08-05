import sys
with open('realtime_executor.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if 'if size_usd > buying_power:' in line:
        lines[i] = line.replace('if size_usd > buying_power:', 'if size_usd >= buying_power * 0.98:')

with open('realtime_executor.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
