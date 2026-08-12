"""
hft/bar_processor.py

Extracts the core logic for processing 1-minute bars from WebSocket streams.
Evaluates indicators, strategies, and AI biases to emit trading signals.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from config.config_manager import RiskConfigReader
from data.bias_reader import BiasReader
from data.trade_logger import WSTradeLogger
from execution.guard_checks import GuardManager

logger = logging.getLogger("nano-trader-ai")

class BarProcessor:
    def __init__(self,
                 vol_detector, indicator_mgr, guard_mgr: GuardManager,
                 momentum_filter, vwap_strategy, bollinger_detector,
                 correlation_engine, volume_profile_mgr):
        self.vol_detector = vol_detector
        self.indicator_mgr = indicator_mgr
        self.guard_mgr = guard_mgr
        self.momentum_filter = momentum_filter
        self.vwap_strategy = vwap_strategy
        self.bollinger_detector = bollinger_detector
        self.correlation_engine = correlation_engine
        self.volume_profile_mgr = volume_profile_mgr
        
        # We need this to simulate self.volume_spike_multiplier which was on RealtimeExecutor
        self.volume_spike_multiplier = 2.0

    def process_crypto_bar(self, symbol: str, price: float, bar_time: datetime,
                           high: float, low: float, volume: float,
                           alert_states: Dict[str, dict]) -> List[Dict[str, Any]]:
        """
        Processes a single crypto bar, updates indicators, and evaluates strategies.
        Returns a list of action dictionaries to be executed by the caller.
        Action format:
        {"action": "CLOSE_ALL", "symbol": "BTCUSD"}
        {"action": "EXECUTE", "symbol": "BTCUSD", "is_short": False, "dip_pct": 0.0, "atr": 100.0, "bias_info": {...}}
        """
        actions = []

        # 1. Confirmation Filter for High Alerts
        alert = alert_states.get(symbol)
        if alert:
            age = (datetime.now(timezone.utc) - alert["timestamp"]).total_seconds()
            if age > 300: # 5 minutes expiry
                logger.info(f"[GUARDIAN] Alert expired for {symbol}.")
                # The caller should delete the alert state based on this or we handle it externally.
                # For now, we assume the caller manages the state expiration if it doesn't trigger.
            else:
                if alert["type"] == "CATACLYSM":
                    # Instant kill switch on a minor dip
                    imm_dip, dip, _ = self.vol_detector.update(symbol, price, bar_time, dynamic_dip_pct=-0.15)
                    if dip is not None:
                        logger.error(f"[GUARDIAN KILL SWITCH] CATACLYSM CONFIRMED for {symbol}! Liquidating!")
                        actions.append({"action": "CLOSE_ALL", "symbol": symbol})
                        return actions
                    # Block standard execution while in CATACLYSM alert!
                    return actions

        # 2. Update Indicator Manager with OHLC
        self.indicator_mgr.update(symbol, high, low, price, volume=volume)
        if volume > 0:
            self.volume_profile_mgr.add_volume(symbol, price, volume)

        # 3. Update new strategy modules
        self.momentum_filter.update(symbol, price)
        self.vwap_strategy.update(symbol, price, volume)
        self.bollinger_detector.update(symbol, price)
        self.correlation_engine.update(symbol, price)

        # 4. Check Warm-up
        atr = self.indicator_mgr.get_atr(symbol)
        rsi = self.indicator_mgr.get_rsi(symbol)
        
        if atr is None or rsi is None:
            # Silent return during 14-min warmup
            return actions

        # 5. Correlated Asset Panic Filter
        risk_config = RiskConfigReader.read()
        is_panic = self.guard_mgr.check_and_update_panic_state(
            trailing_states=self.vol_detector._trailing_state,
            threshold_pct=risk_config.get("guardian_panic_threshold_pct", -1.20),
            required_count=risk_config.get("guardian_panic_asset_count", 3),
            cooldown_min=risk_config.get("guardian_panic_cooldown_min", 3)
        )
        if is_panic:
            # Only block BUY signals. We still want to trail stops and update indicators (which we just did).
            return actions

        # 6. Read Regime and adjust DIP threshold dynamically
        base_dip = abs(risk_config.get("crypto_micro_dip_pct", 0.15))
        alpha_dynamic_dip = risk_config.get("alpha_dynamic_dip", False)
        if alpha_dynamic_dip and atr > 0 and price > 0:
            atr_pct = (atr / price) * 100.0
            mult = risk_config.get("atr_dynamic_dip_multiplier", 1.0)
            dynamic_dip = -abs(base_dip * (1 + (atr_pct * mult)))
        else:
            dynamic_dip = -abs(base_dip)
            
        immediate_dip, trailing_dip, spike_pct = self.vol_detector.update(symbol, price, bar_time, dynamic_dip_pct=dynamic_dip)
        
        # Shadow Tracking for Dips
        alpha_smart_trailing = risk_config.get("alpha_smart_trailing", False)
        dip_condition = (not alpha_smart_trailing and trailing_dip is not None) or \
                        (alpha_smart_trailing and immediate_dip is not None)
                        
        if dip_condition:
            from data.db import get_db, insert_ai_analytics
            shadow_cooldown = 1800  # 30 minutes
            with get_db() as _conn:
                last_shadow_row = _conn.execute(
                    "SELECT timestamp FROM ai_analytics WHERE action LIKE 'SHADOW_%' AND asset = ? ORDER BY timestamp DESC LIMIT 1",
                    (symbol,)
                ).fetchone()
            can_shadow = True
            if last_shadow_row:
                try:
                    last_ts = datetime.fromisoformat(last_shadow_row[0].replace("Z", "+00:00"))
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                    can_shadow = (datetime.now(timezone.utc) - last_ts).total_seconds() >= shadow_cooldown
                except Exception:
                    can_shadow = True
            
            if can_shadow:
                if not alpha_smart_trailing and trailing_dip is not None:
                    insert_ai_analytics(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        asset=symbol, price=price, action="SHADOW_BUY",
                        confidence=0.9, sentiment_score=0.0,
                        prompt_tokens=0, completion_tokens=0,
                        reasoning=f"Alpha Trailing Buy hit at {trailing_dip:.2f}%",
                        return_1h=None, return_4h=None
                    )
                elif alpha_smart_trailing and immediate_dip is not None:
                    insert_ai_analytics(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        asset=symbol, price=price, action="SHADOW_BUY",
                        confidence=0.9, sentiment_score=0.0,
                        prompt_tokens=0, completion_tokens=0,
                        reasoning=f"Alpha Classic Buy (No Trailing) hit at {immediate_dip:.2f}%",
                        return_1h=None, return_4h=None
                    )
        
        # 7. Evaluate strategies
        # (A) Bollinger Squeeze Breakout
        if risk_config.get("strategy_bollinger_enabled", True):
            self.bollinger_detector.squeeze_threshold_pct = risk_config.get("squeeze_threshold_pct", 0.005)
            bb_signal = self.bollinger_detector.check_signal(symbol, price)
            
            if bb_signal == "SQUEEZE_BUY" and not self.guard_mgr.is_symbol_in_cooldown(symbol, cooldown_seconds=15):
                momentum_ok = risk_config.get("strategy_momentum_filter_enabled", False) == False or self.momentum_filter.should_allow_buy(symbol)
                
                if momentum_ok:
                    vol_thresh = getattr(self, 'volume_spike_multiplier', 2.0)
                    if self.indicator_mgr.is_volume_spike(symbol, volume, threshold=vol_thresh):
                        bias_info = BiasReader.get_bias_for_symbol(symbol)
                        actions.append({
                            "action": "EXECUTE", "symbol": symbol, "is_short": False,
                            "dip_pct": 0.0, "atr": atr, "bias_info": bias_info
                        })
                        return actions # Stop evaluating other strategies
                        
            elif bb_signal == "SQUEEZE_SHORT":
                bias_info = BiasReader.get_bias_for_symbol(symbol)
                bias = bias_info.get("bias", "NEUTRAL")
                if bias == "BEARISH" and not self.guard_mgr.is_symbol_in_cooldown(symbol, cooldown_seconds=15):
                    vol_thresh = getattr(self, 'volume_spike_multiplier', 2.0)
                    if self.indicator_mgr.is_volume_spike(symbol, volume, threshold=vol_thresh):
                        actions.append({
                            "action": "EXECUTE", "symbol": symbol, "is_short": True,
                            "dip_pct": 0.0, "atr": atr, "bias_info": bias_info
                        })
                        return actions

        # (B) VWAP Reversion
        if risk_config.get("strategy_vwap_enabled", True):
            vwap_signal = self.vwap_strategy.check_signal(symbol, price, atr=atr, rsi=rsi)
            if vwap_signal == "VWAP_BUY" and not self.guard_mgr.is_symbol_in_cooldown(symbol, cooldown_seconds=15):
                momentum_ok = risk_config.get("strategy_momentum_filter_enabled", True) == False or self.momentum_filter.should_allow_buy(symbol)
                if momentum_ok:
                    bias_info = BiasReader.get_bias_for_symbol(symbol)
                    actions.append({
                        "action": "EXECUTE", "symbol": symbol, "is_short": False,
                        "dip_pct": 0.0, "atr": atr, "bias_info": bias_info
                    })
                    return actions

        return actions

    def process_stock_bar(self, symbol: str, price: float, bar_time: datetime,
                          high: float, low: float, target_symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Processes an incoming bar for stocks (QQQ).
        Detects +0.25% spikes and triggers crypto LEAD-LAG buying.
        """
        actions = []
        
        # Update Indicator Manager with OHLC
        self.indicator_mgr.update(symbol, high, low, price)

        immediate_dip, trailing_dip, spike_pct = self.vol_detector.update(symbol, price, bar_time)

        # QQQ Lead-Lag Trigger threshold is +0.25%
        if spike_pct is not None and spike_pct >= 0.25:
            logger.info(f"[WS LEAD-LAG] {symbol} jumped {spike_pct:.2f}%. Price: ${price:.2f}")

            # Cross-Asset Check: if QQQ spikes, look for BULLISH targets
            for target_sym in target_symbols:
                if self.guard_mgr.is_symbol_in_cooldown(target_sym, cooldown_seconds=15):
                    continue
                
                # Check warm-up status of the target asset
                atr = self.indicator_mgr.get_atr(target_sym)
                rsi = self.indicator_mgr.get_rsi(target_sym)
                target_price = self.indicator_mgr.get_last_price(target_sym)
                
                if atr is None or rsi is None or target_price is None:
                    continue

                bias_info = BiasReader.get_bias_for_symbol(target_sym)
                bias = bias_info.get("bias", "NEUTRAL")
                sentiment_score = bias_info.get("sentiment_score", 0.0)

                if bias == "BULLISH" and sentiment_score >= 0.75:
                    if rsi > 70:
                        logger.info(f"[WS FILTER] {target_sym} RSI is {rsi:.2f} (>70). Skipping Lead-Lag BUY.")
                        continue
                        
                    logger.info(f"[WS LEAD-LAG TRIGGER] QQQ Spike + BULLISH {target_sym} confirmed! Executing anticipatory BUY order...")
                    
                    actions.append({
                        "action": "EXECUTE",
                        "symbol": target_sym,
                        "price": target_price,
                        "dip_pct": spike_pct,
                        "bias_info": bias_info,
                        "is_short": False,
                        "atr": atr
                    })
        return actions
