import json
import subprocess
import sys

SETTINGS_PATH = 'config/risk_settings.json'

def load_settings():
    with open(SETTINGS_PATH, 'r') as f:
        return json.load(f)

def save_settings(data):
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(data, f, indent=4)

def run_variant(name, mods):
    print(f"\n--- Running Variant: {name} ---")
    
    settings = load_settings()
    for k, v in mods.items():
        settings[k] = v
    save_settings(settings)
    
    cmd = [
        ".\\.venv\\Scripts\\python.exe", "run_backtest.py", 
        "--days", "180", 
        "--symbols", "BTCUSD", "ETHUSD", "DOGEUSD", "SOLUSD", 
        "--equity", "300.0", 
        "--quiet"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("ERRORS:", result.stderr)

VARIANTS = [
    {
        "name": "1. Full Kelly Aggressivo",
        "mods": {
            "max_risk_per_trade_pct": 0.20,
            "kelly_fraction_multiplier": 1.5,
            "strategy_vwap_enabled": True
        }
    },
    {
        "name": "2. Micro-Scalping",
        "mods": {
            "crypto_micro_tp_pct": 0.15,
            "atr_stop_loss_multiplier": 0.8,
            "max_risk_per_trade_pct": 0.05,
            "kelly_fraction_multiplier": 1.0,
            "strategy_vwap_enabled": True
        }
    },
    {
        "name": "3. Deep Martingale DCA",
        "mods": {
            "crypto_max_grid_layers": 10,
            "crypto_micro_dip_pct": 0.2,
            "crypto_micro_tp_pct": 0.3,
            "atr_stop_loss_multiplier": 2.0,
            "strategy_vwap_enabled": True
        }
    },
    {
        "name": "4. Breakout Iper-Sensibile",
        "mods": {
            "squeeze_threshold_pct": 0.001,
            "crypto_max_grid_layers": 5,
            "strategy_vwap_enabled": True
        }
    },
    {
        "name": "5. Momentum Igniting (No Filters)",
        "mods": {
            "strategy_momentum_filter_enabled": False,
            "strategy_vwap_enabled": True,
            "squeeze_threshold_pct": 0.005
        }
    }
]

if __name__ == "__main__":
    original = load_settings()
    try:
        for v in VARIANTS:
            save_settings(original)
            run_variant(v["name"], v["mods"])
    finally:
        save_settings(original)
        print("\nOriginal settings restored.")
