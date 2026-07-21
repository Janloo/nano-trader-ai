import time
import os
import re
import sys
import json

log_file = r"c:\sources\nano-trader-ai\data\logs\nano_trader.log"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def read_new_lines_non_locking(filename, last_pos):
    if not os.path.exists(filename):
        return last_pos, []
    
    lines = []
    try:
        # Open, read, and close immediately
        with open(filename, "r", encoding="utf-8") as f:
            f.seek(0, os.SEEK_END)
            current_end = f.tell()
            
            # If file is smaller than last_pos, it was rotated
            if current_end < last_pos:
                last_pos = 0
                
            f.seek(last_pos)
            lines = f.readlines()
            last_pos = f.tell()
    except PermissionError:
        # File might be rotating, ignore this tick
        pass
    except Exception:
        pass
        
    return last_pos, lines

def monitor():
    print("Monitoring started (non-locking)...", flush=True)
    
    # Initialize positions
    log_pos = 0
    if os.path.exists(log_file):
        log_pos = os.path.getsize(log_file)
        
    last_trade_id = 0
    try:
        from data.db import get_trades, get_new_trades
        trades = get_trades(limit=1)
        if trades:
            last_trade_id = trades[0]["id"]
    except Exception:
        pass
    
    while True:
        log_pos, log_lines = read_new_lines_non_locking(log_file, log_pos)
        for l_line in log_lines:
            l_lower = l_line.lower()
            if "[error]" in l_lower or "exception" in l_lower or "getaddrinfo" in l_lower:
                print(f"[ALARM_ERROR] {l_line.strip()}", flush=True)
            elif "score: " in l_lower:
                m = re.search(r"score:\s*([0-9\.]+)", l_lower)
                if m:
                    try:
                        score = float(m.group(1))
                        if score >= 0.75:
                            print(f"[ALARM_OPPORTUNITY] {l_line.strip()}", flush=True)
                    except:
                        pass
        
        try:
            from data.db import get_new_trades
            new_trades = get_new_trades(last_trade_id)
            for t in new_trades:
                print(f"[ALARM_TRADE] {json.dumps(t)}", flush=True)
                last_trade_id = max(last_trade_id, t["id"])
        except Exception:
            pass
            
        time.sleep(1)

if __name__ == "__main__":
    monitor()
