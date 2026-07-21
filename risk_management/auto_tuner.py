import os
import json
import logging
from config.settings import logger
from data.db import get_ai_analytics_completed_feedback

RISK_SETTINGS_PATH = os.path.join("config", "risk_settings.json")

class AutoTuner:
    """
    Auto-tunes Kelly Criterion parameters based on empirical AI trade performance.
    """
    
    @classmethod
    def tune_kelly_criterion(cls, min_samples=10):
        try:
            completed_logs = get_ai_analytics_completed_feedback()
            
            if len(completed_logs) < min_samples:
                logger.info(f"[Auto-Tuner] Not enough samples for Kelly tuning ({len(completed_logs)}/{min_samples}).")
                return
                
            winning_trades = 0
            losing_trades = 0
            total_win_return = 0.0
            total_loss_return = 0.0
            
            for log in completed_logs:
                # Prefer 4h return, fallback to 1h
                ret = log.get("return_4h")
                if ret is None:
                    ret = log.get("return_1h")
                
                if ret is None:
                    continue
                    
                # A trade is a "Win" if return is > 0
                if ret > 0:
                    winning_trades += 1
                    total_win_return += ret
                elif ret < 0:
                    losing_trades += 1
                    total_loss_return += abs(ret)
                    
            total_trades = winning_trades + losing_trades
            if total_trades < min_samples:
                logger.info(f"[Auto-Tuner] Not enough valid samples for Kelly tuning ({total_trades}/{min_samples}).")
                return
                
            win_rate = winning_trades / total_trades
            
            avg_win = (total_win_return / winning_trades) if winning_trades > 0 else 0
            avg_loss = (total_loss_return / losing_trades) if losing_trades > 0 else 0
            
            if avg_loss > 0:
                reward_risk_ratio = avg_win / avg_loss
            else:
                # If no losses, give a conservative high ratio to not explode Kelly
                reward_risk_ratio = 2.0
                
            # Cap realistic ratios to avoid overleveraging on small sample sizes
            reward_risk_ratio = min(max(reward_risk_ratio, 0.5), 3.0)
            
            # Read existing config
            with open(RISK_SETTINGS_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
                
            old_win_rate = config.get("win_rate_estimate", 0.55)
            old_ratio = config.get("reward_risk_ratio_estimate", 1.5)
            
            # Update only if noticeably different
            if abs(old_win_rate - win_rate) > 0.001 or abs(old_ratio - reward_risk_ratio) > 0.01:
                config["win_rate_estimate"] = round(win_rate, 4)
                config["reward_risk_ratio_estimate"] = round(reward_risk_ratio, 4)
                
                with open(RISK_SETTINGS_PATH, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=4)
                    
                logger.info(f"[Auto-Tuner] Tuned Kelly Criterion: Win Rate {old_win_rate:.2f} -> {win_rate:.2f}, R/R {old_ratio:.2f} -> {reward_risk_ratio:.2f} (Total Trades: {total_trades})")
            
        except Exception as e:
            logger.error(f"[Auto-Tuner] Failed to auto-tune Kelly criterion: {e}")
