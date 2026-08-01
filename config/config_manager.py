import os
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class RiskSettings:
    max_capital_per_trade_pct: float = 0.05
    max_risk_per_trade_pct: float = 0.02
    max_open_positions_per_asset: int = 1
    atr_stop_loss_multiplier: float = 2.0
    global_max_stocks_pct: float = 1.0
    global_max_crypto_pct: float = 1.0
    global_min_cash_pct: float = 0.0
    hft_budget_pct: float = 0.20
    alpha_smart_trailing: bool = True
    alpha_inverse_hedge: bool = True
    alpha_dynamic_dip: bool = True
    crypto_micro_dip_pct: float = 0.15
    crypto_micro_tp_pct: float = 0.30
    crypto_max_grid_layers: int = 5
    use_kelly_criterion: bool = True
    kelly_fraction_multiplier: float = 1.0
    historical_win_rate: float = 0.55
    historical_reward_risk: float = 1.5
    win_rate_estimate: float = 0.50
    reward_risk_ratio_estimate: float = 1.5
    strategy_momentum_filter_enabled: bool = True

class ConfigManager:
    _instance = None
    _config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "risk_settings.json")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def load_risk_settings(self, max_retries=5, retry_delay=0.1) -> RiskSettings:
        """
        Loads risk_settings.json with atomic-like retry logic to handle concurrent writes from the dashboard.
        """
        if not os.path.exists(self._config_path):
            logger.warning(f"Config file {self._config_path} not found. Using defaults.")
            return RiskSettings()

        for attempt in range(max_retries):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if not content.strip():
                        raise ValueError("Empty file")
                    
                    data = json.loads(content)
                    # Convert dict to dataclass with default fallbacks for missing fields
                    return RiskSettings(**{k: v for k, v in data.items() if hasattr(RiskSettings, k)})
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug(f"Attempt {attempt + 1}: Failed to parse config JSON ({e}). Retrying...")
                time.sleep(retry_delay)
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Unexpected error reading config: {e}")
                time.sleep(retry_delay)
        
        logger.error(f"Failed to load risk settings after {max_retries} attempts. Falling back to defaults.")
        return RiskSettings()

config_manager = ConfigManager()
