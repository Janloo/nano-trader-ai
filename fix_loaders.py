import re

with open('reporting/generator.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The skeleton HTML to inject
loader_html = '<span class="animate-pulse bg-slate-700/50 h-6 w-24 inline-block rounded"></span>'

# Replace the text inside the dd/td elements with the loader
content = re.sub(r'id="val-portfolio">[^<]+</dd>', f'id="val-portfolio">{loader_html}</dd>', content)
content = re.sub(r'id="val-buying-power">[^<]+</dd>', f'id="val-buying-power">{loader_html}</dd>', content)
content = re.sub(r'id="val-cumulative-pnl"[^>]*>[^<]+</dd>', f'id="val-cumulative-pnl" class="mt-2 text-2xl font-bold tracking-tight text-white">{loader_html}</dd>', content)
content = re.sub(r'id="val-pnl-pct"[^>]*>[^<]+</dd>', f'id="val-pnl-pct" class="text-sm font-semibold text-slate-500">{loader_html}</dd>', content)
content = re.sub(r'id="val-unrealized-pnl"[^>]*>[^<]+</dd>', f'id="val-unrealized-pnl" class="mt-2 text-2xl font-bold tracking-tight text-white">{loader_html}</dd>', content)
content = re.sub(r'id="val-total-invested">[^<]+</dd>', f'id="val-total-invested">{loader_html}</dd>', content)
content = re.sub(r'id="val-total-trades">[^<]+</dd>', f'id="val-total-trades">{loader_html}</dd>', content)

# Remove the extra > if any remains
content = content.replace('>>', '>')

with open('reporting/generator.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
