import os
import json
import traceback
from datetime import datetime, timezone
from config.settings import logger
import threading

ERROR_FILE_PATH = os.path.join("data", "state", "system_errors.json")
_error_lock = threading.Lock()

def log_system_error(module: str, error: Exception, context: str = ""):
    """Logs a fail-safe exception to be displayed on the UI without crashing the bot."""
    os.makedirs(os.path.dirname(ERROR_FILE_PATH), exist_ok=True)
    
    error_msg = str(error)
    trace = traceback.format_exc()
    
    logger.error(f"[FAIL-SAFE] {module} Error: {error_msg}. Context: {context}\n{trace}")
    
    with _error_lock:
        try:
            errors = []
            if os.path.exists(ERROR_FILE_PATH):
                with open(ERROR_FILE_PATH, "r", encoding="utf-8") as f:
                    try:
                        errors = json.load(f)
                    except json.JSONDecodeError:
                        errors = []
                        
            errors.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "module": module,
                "error": error_msg,
                "context": context
            })
            
            # Keep only the last 10 errors to avoid bloat
            errors = errors[-10:]
            
            with open(ERROR_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(errors, f, indent=4)
                
            # Check for Dead Man's Switch
            try:
                from execution.emergency import EmergencyLiquidator
                if not EmergencyLiquidator.is_locked() and len(errors) >= 5:
                    now = datetime.now(timezone.utc)
                    # Parse timestamps of the last 5 errors
                    recent_errors = errors[-5:]
                    first_err_time = datetime.fromisoformat(recent_errors[0]["timestamp"])
                    if (now - first_err_time).total_seconds() <= 180:
                        # 5 errors in 3 minutes -> TRIGGER EMERGENCY
                        reason = "5 crash errors logged within 3 minutes."
                        EmergencyLiquidator.trigger_lockdown(reason)
                        threading.Thread(target=EmergencyLiquidator.liquidate_all_positions, daemon=True).start()
            except Exception as e:
                logger.error(f"Failed to check Dead Man's Switch: {e}")
                
        except Exception as e:
            logger.error(f"Could not write to system_errors.json: {e}")

def get_system_errors() -> list:
    """Retrieves the list of active system errors for the UI."""
    if os.path.exists(ERROR_FILE_PATH):
        try:
            with open(ERROR_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def clear_system_errors():
    """Clears the system errors after they have been acknowledged."""
    with _error_lock:
        if os.path.exists(ERROR_FILE_PATH):
            try:
                os.remove(ERROR_FILE_PATH)
            except Exception:
                pass
