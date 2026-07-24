import json
import logging
import os
from data.db import log_ai_call, get_ai_call_count

logger = logging.getLogger("nano-trader-ai")

class RateLimitExceededException(Exception):
    pass

class AILimiter:
    @staticmethod
    def _get_max_calls_per_hour() -> int:
        config_path = os.path.join("config", "risk_settings.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("max_ai_calls_per_hour", 50)
            except Exception as e:
                logger.error(f"[AILimiter] Error reading config: {e}")
        return 50 # Default safe limit

    @classmethod
    def check_and_log(cls, module: str, model: str):
        """
        Checks if the AI API call is within limits.
        If yes, logs the call to the database and returns True.
        If no, raises RateLimitExceededException.
        """
        max_calls = cls._get_max_calls_per_hour()
        
        try:
            current_count = get_ai_call_count(hours=1)
            if current_count >= max_calls:
                logger.warning(f"[AILimiter] Rate limit exceeded! {current_count}/{max_calls} calls in the last hour.")
                raise RateLimitExceededException(f"AI API rate limit exceeded ({current_count}/{max_calls})")
            
            # Log the call if we are within limits
            log_ai_call(module, model)
            return True
        except RateLimitExceededException:
            raise
        except Exception as e:
            logger.error(f"[AILimiter] Database error during check: {e}")
            # If DB fails, allow the call to proceed to prevent system halt, but we log the error
            return True
