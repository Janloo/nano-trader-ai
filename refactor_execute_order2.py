import re

with open('realtime_executor.py', encoding='utf-8') as f:
    content = f.read()

# We want to replace from `    def _execute_order(` up to `    def on_bar(`
start_idx = content.find("    def _execute_order(")
end_idx = content.find("    def on_bar(")

new_execute_order = """    def _execute_order(self, symbol: str, price: float, change_pct: float,
                       bias_info: dict, is_short: bool = False, atr: float = 0.0) -> str:
        \"\"\"
        Places a Bracket Order with dynamic TP/SL using the new execution components.
        \"\"\"
        from config.config_manager import RiskConfigReader, RegimeConfigReader
        from execution.position_sizer import PositionSizer
        
        risk_config = RiskConfigReader.read()
        sentiment_score = bias_info.get("sentiment_score", 0.0)
        reasoning = bias_info.get("reasoning", "")
        bias_type = "BEARISH" if is_short else "BULLISH"
        
        is_crypto = symbol.endswith("USD")
        
        # L2 Wall Check
        imbalance = self.orderbook_analyzer.check_imbalance(symbol)
        if not is_short and imbalance == "BEARISH_WALL":
            logger.warning(f"[L2 FILTER] {symbol} has a huge BEARISH WALL. Skipping LONG execution.")
            return None
        if is_short and imbalance == "BULLISH_WALL":
            logger.warning(f"[L2 FILTER] {symbol} has a huge BULLISH WALL. Skipping SHORT execution.")
            return None

        # Crypto short block
        if is_short and is_crypto:
            logger.warning(f"[WS] Cannot short Crypto {symbol} on Alpaca. Skipping execution.")
            return None

        try:
            self._init_trading_client()
            account = self._trading_client.get_account()
            total_equity = float(account.equity)
            buying_power = float(account.buying_power)
        except Exception as e:
            logger.warning(f"[WS] Failed to get account info: {e}")
            total_equity = 10000.0
            buying_power = 10000.0

        size_usd = PositionSizer.calculate_micro_size(
            symbol, risk_config, total_equity, buying_power
        )

        if self.dry_run:
            logger.info(
                f"[WS DRY-RUN] Would {bias_type} ${size_usd:.2f} of {symbol} at ${price:.2f} "
                f"(Change: {change_pct:.2f}%, Bias: {bias_type}, Score: {sentiment_score:.2f}, ATR: {atr:.4f})"
            )
            return f"dry-ws-{int(time.time())}"

        try:
            self._init_trading_client()
            bands = self.bollinger_detector._calc_bands(symbol)
            sma_sl = bands["sma"] if bands else None
            
            regimes = RegimeConfigReader.read()
            symbol_regime = regimes.get(symbol, {}).get("regime", "UNKNOWN")
            
            order_data = OrderBuilder.build_order(
                symbol=symbol, price=price, size_usd=size_usd,
                is_crypto=is_crypto, is_short=is_short, atr=atr,
                sma_sl=sma_sl, config=risk_config, regime=symbol_regime
            )
            
            if self.order_executor is None:
                self.order_executor = OrderExecutor(self._trading_client, self.guard_mgr)
                
            order_id = self.order_executor.execute_order(
                order_request=order_data,
                price=price,
                size_usd=size_usd,
                change_pct=change_pct,
                bias_type=bias_type,
                sentiment_score=sentiment_score,
                reasoning=reasoning,
                is_short=is_short
            )
            return order_id
        except Exception as e:
            logger.error(f"[WS] Order execution setup failed for {symbol}: {e}")
            return None

"""

content = content[:start_idx] + new_execute_order + content[end_idx:]

with open('realtime_executor.py', 'w', encoding='utf-8') as f:
    f.write(content)
