import json, os

risk_path = os.path.join('data', 'state', 'risk_config.json')
if os.path.exists(risk_path):
    with open(risk_path) as f:
        risk = json.load(f)
    print('=== RISK CONFIG ===')
    for k, v in risk.items():
        print(f'  {k}: {v}')
else:
    print('risk_config.json NOT FOUND')

# Check market bias
bias_path = os.path.join('data', 'state', 'market_bias.json')
if os.path.exists(bias_path):
    with open(bias_path) as f:
        bias = json.load(f)
    print('\n=== MARKET BIAS ===')
    ts = bias.get('timestamp', 'N/A')
    print(f'  timestamp: {ts}')
    for asset in bias.get('target_assets', []):
        sym = asset.get('symbol')
        b = asset.get('bias')
        score = asset.get('sentiment_score')
        print(f'  {sym}: bias={b}, score={score}')
else:
    print('market_bias.json NOT FOUND')

# Check logbook for recent activity
logbook_path = os.path.join('data', 'archives', 'human_logbook.txt')
if os.path.exists(logbook_path):
    with open(logbook_path) as f:
        lines = f.readlines()
    print('\n=== LAST 20 LOGBOOK ENTRIES ===')
    for line in lines[-20:]:
        print(' ', line.strip())
