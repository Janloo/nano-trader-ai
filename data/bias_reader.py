"""
data/bias_reader.py

Reads market_bias.json safely, handling concurrent writes and expiry.
Extracted from realtime_executor.py as a standalone module with single responsibility.
"""
import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger("nano-trader-ai")

BIAS_FILE = os.path.join("data", "state", "market_bias.json")

_NEUTRAL_BIAS = {
    "bias": "NEUTRAL",
    "sentiment_score": 0.0,
    "reasoning": "Bias expired or unavailable.",
}


class BiasReader:
    """Reads market_bias.json safely, handling concurrent writes and expiry."""

    @staticmethod
    def read() -> Dict:
        """
        Returns the current bias dict, or a neutral/expired stub if stale or missing.
        Thread-safe: reads atomically from the filesystem.
        """
        try:
            if not os.path.exists(BIAS_FILE):
                return {"target_assets": [], "expired": True}

            with open(BIAS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Check expiry
            expires_at_str = data.get("expires_at", "")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > expires_at:
                    logger.warning("[BiasReader] Market bias is EXPIRED. Treating as NEUTRAL.")
                    data["expired"] = True
                    return data

            data["expired"] = False
            return data

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[BiasReader] Failed to parse market_bias.json (concurrent write?): {e}")
            return {"target_assets": [], "expired": True}
        except Exception as e:
            logger.error(f"[BiasReader] Error reading market_bias.json: {e}")
            return {"target_assets": [], "expired": True}

    @staticmethod
    def get_bias_for_symbol(symbol: str) -> Dict:
        """
        Returns bias info for a specific symbol, or NEUTRAL defaults if not found or expired.
        """
        data = BiasReader.read()
        if data.get("expired", True):
            return dict(_NEUTRAL_BIAS, reasoning=f"Bias expired or unavailable.")

        for asset in data.get("target_assets", []):
            if asset.get("symbol") == symbol:
                return asset

        return dict(_NEUTRAL_BIAS, reasoning=f"{symbol} not in current AI selection.")
