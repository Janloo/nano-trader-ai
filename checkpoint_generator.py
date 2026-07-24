import json
import os
import urllib.request
from datetime import datetime
from config.settings import logger

CHECKPOINT_FILE = "data/archives/daily_checkpoints.json"

def create_daily_checkpoint():
    try:
        # Get portfolio data from Alpaca
        from alpaca.trading.client import TradingClient
        from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY
        
        client = TradingClient(APCA_API_KEY_ID, APCA_API_SECRET_KEY, paper=True)
        account = client.get_account()
        equity = float(account.equity)
        cash = float(account.buying_power)
        
        # Get analytics data from local server
        real_pnl = 0.0
        shadow_pnl = 0.0
        real_winrate = 0.0
        try:
            req = urllib.request.Request("http://localhost:8000/api/analytics")
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    real_pnl = data.get("real", {}).get("final_pnl", 0.0)
                    shadow_pnl = data.get("shadow", {}).get("final_pnl", 0.0)
                    real_winrate = data.get("real", {}).get("win_rate", 0.0)
        except Exception as e:
            logger.error(f"[CHECKPOINT] Could not fetch analytics: {e}")
            
        checkpoint = {
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "equity": round(equity, 2),
            "cash": round(cash, 2),
            "real_pnl_pct": real_pnl,
            "shadow_pnl_pct": shadow_pnl,
            "real_winrate": real_winrate
        }
        
        # Load existing checkpoints
        checkpoints = []
        if os.path.exists(CHECKPOINT_FILE):
            with open(CHECKPOINT_FILE, "r") as f:
                try:
                    checkpoints = json.load(f)
                except json.JSONDecodeError:
                    pass
                    
        # Replace if today already exists, else append
        updated = False
        for i, c in enumerate(checkpoints):
            if c.get("date") == checkpoint["date"]:
                checkpoints[i] = checkpoint
                updated = True
                break
                
        if not updated:
            checkpoints.append(checkpoint)
            
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(checkpoints, f, indent=4)
            
        # Log to logbook
        from realtime_executor import WSTradeLogger
        msg = f"[CHECKPOINT] Giornata conclusa. Equity: ${equity:,.2f} | PnL Reale: {real_pnl}% | Shadow PnL: {shadow_pnl}%"
        WSTradeLogger.write_logbook(msg)
        
        logger.info(f"[CHECKPOINT] Successfully saved checkpoint for {checkpoint['date']}")
        
    except Exception as e:
        logger.error(f"[CHECKPOINT] Error creating checkpoint: {e}")

if __name__ == "__main__":
    create_daily_checkpoint()
