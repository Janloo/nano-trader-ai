import re

with open('reporting/generator.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace list joins
content = content.replace('{"".join(open_positions_rows)}', '')
content = content.replace('{"".join(trades_rows)}', '')
content = content.replace('{"".join(ai_rows)}', '')
content = content.replace('{"".join(ws_rows)}', '')
content = content.replace('{"".join(alpaca_orders_rows)}', '')
content = content.replace('{"".join(logbook_rows)}', '')

# Replace single variables
content = re.sub(r'\{current_equity:,\.2f\}', '0.00', content)
content = re.sub(r'\{current_buying_power:,\.2f\}', '0.00', content)
content = re.sub(r'\{cumulative_pnl:,\.2f\}', '0.00', content)
content = re.sub(r'\{pnl_pct:\.2f\}', '0.00', content)
content = re.sub(r'\{current_unrealized_pnl:,\.2f\}', '0.00', content)
content = re.sub(r'\{total_invested:,\.2f\}', '0.00', content)
content = content.replace('{total_trades}', '0')
content = content.replace('{das_ts_str}', '')
content = content.replace('{das_articles_count}', '0')
content = content.replace('{das_health_badge}', '')
content = content.replace('{das_cards_html}', '')
content = content.replace('{news_feed_html}', '')

with open('reporting/generator.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
