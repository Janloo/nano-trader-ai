import sys

with open('realtime_executor.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('state["imm_dip_pct"]', 't_state["imm_dip_pct"]')

with open('realtime_executor.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Modifications applied successfully.")
