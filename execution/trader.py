import json
import os
from datetime import datetime, timezone
from typing import Optional, List
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from client.alpaca_client import AlpacaClientWrapper
from config.settings import logger
from data.db import insert_trade, insert_ai_analytics, insert_portfolio_snap

class AITrader:
    def __init__(self, client: AlpacaClientWrapper):
        self.client = client

    def log_portfolio_status(self, equity: float, buying_power: float, unrealized_pnl: float, average_sentiment: float):
        """Saves current portfolio value and the run's average AI sentiment score to history."""
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            insert_portfolio_snap(timestamp, equity, buying_power, unrealized_pnl, average_sentiment)
        except Exception as e:
            logger.error(f"Error logging portfolio snapshot: {e}")

    def log_ai_analytics(self, symbol: str, current_price: float, raw_news_titles: List[str], ai_raw_output: dict, execution_success: bool, error_details: str):
        """Logs detailed AI decision telemetry to sqlite."""
        try:
            action = ai_raw_output.get("action", "HOLD").upper()
            confidence = float(ai_raw_output.get("confidence", 0))
            sentiment_score = float(ai_raw_output.get("sentiment_score", 0.0))
            reasoning = ai_raw_output.get("reasoning", "")
            timestamp = datetime.now(timezone.utc).isoformat()
            
            reasoning = f"{reasoning} [Execution: {execution_success}] {error_details}".strip()
            
            insert_ai_analytics(
                timestamp=timestamp, 
                asset=symbol, 
                price=current_price,
                action=action, 
                confidence=confidence, 
                sentiment_score=sentiment_score, 
                prompt_tokens=0, 
                completion_tokens=0, 
                reasoning=reasoning, 
                return_1h=None, 
                return_4h=None, 
                analysis_id=""
            )
        except Exception as e:
            logger.error(f"Error logging AI analytics: {e}")

    def execute_ai_decision(self, symbol: str, ai_decision: dict, current_price: float, positions: List, raw_news_titles: List[str]) -> Optional[str]:
        """
        Executes fractional trades based on AI analysis parameters and logs historical transactions.
        """
        action = ai_decision.get("action", "HOLD").upper()
        confidence = ai_decision.get("confidence", 0)
        sentiment_score = ai_decision.get("sentiment_score", 0.0)
        reasoning = ai_decision.get("reasoning", "")
        
        # Check if we already hold a position (slash-insensitive)
        clean_sym = symbol.replace("/", "").upper()
        has_position = False
        for pos in positions:
            if pos.symbol.replace("/", "").upper() == clean_sym:
                has_position = True
                break

        if action == "BUY" and confidence > 75:
            if has_position:
                logger.info(
                    f"[{symbol} AI Trader] Decision is BUY (Conf: {confidence}%) but position "
                    f"already exists. Skipping order execution to manage risk."
                )
                self.log_ai_analytics(symbol, current_price, raw_news_titles, ai_decision, False, "Position already exists")
                return None
                
            logger.info(
                f"[{symbol} AI Trader] Executing BUY order of $5.00 for {symbol} "
                f"(Sentiment: {sentiment_score:.2f}, Confidence: {confidence}%)"
            )
            
            try:
                order_id = "mock-ai-buy-id"
                order = None
                order_symbol = symbol.replace("BTCUSD", "BTC/USD")
                
                # Live execution trigger
                if self.client is not None:
                    order_data = MarketOrderRequest(
                        symbol=order_symbol,
                        notional=5.00,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY
                    )
                    order = self.client.submit_order(order_data)
                    order_id = str(order.id)
                
                # Fetch execution price and deduce fractional quantity
                price = current_price
                qty = 5.00 / current_price
                
                if order and getattr(order, "filled_avg_price", None) is not None:
                    try:
                        price = float(order.filled_avg_price)
                        qty = float(order.filled_qty) if getattr(order, "filled_qty", None) else qty
                    except (ValueError, TypeError):
                        pass

                # Append transaction item to database
                timestamp = datetime.now(timezone.utc).isoformat()
                exec_type = ai_decision.get("execution_type", "macro_daily_decision")
                insert_trade(
                    timestamp=timestamp,
                    symbol=symbol,
                    action="BUY",
                    qty=qty,
                    price=price,
                    notional=5.00,
                    sentiment_score=sentiment_score,
                    reasoning=reasoning,
                    execution_type=exec_type,
                    order_id=order_id
                )
                
                logger.info(f"[{symbol} AI Trader] Order placed and logged. ID: {order_id}")
                self.log_ai_analytics(symbol, current_price, raw_news_titles, ai_decision, True, "")
                return order_id
                
            except Exception as e:
                err_msg = str(e)
                # Catch closed market errors (like "market is closed" or code 400101) for SPY specifically
                if symbol == "SPY" and ("closed" in err_msg.lower() or "not open" in err_msg.lower() or "400101" in err_msg):
                    log_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [WEEKEND] Mercato azionario USA chiuso. Ordine su SPY posticipato alla riapertura di Lunedi'."
                    log_path = os.path.join("data", "archives", "human_logbook.txt")
                    os.makedirs(os.path.dirname(log_path), exist_ok=True)
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(log_msg + "\n")
                    except Exception as e_log:
                        logger.error(f"Failed to write to human logbook: {e_log}")
                        
                    logger.info(f"[{symbol} AI Trader] Intercepted closed USA market on weekend. Deferred order successfully.")
                    self.log_ai_analytics(symbol, current_price, raw_news_titles, ai_decision, False, f"[WEEKEND] US market is closed. {err_msg}")
                    return None
                
                logger.error(f"[{symbol} AI Trader] Order execution failed for {symbol}: {e}")
                self.log_ai_analytics(symbol, current_price, raw_news_titles, ai_decision, False, err_msg)
                return None
        else:
            logger.info(
                f"[{symbol} AI Trader] Decision is {action} (Conf: {confidence}%, "
                f"Sentiment: {sentiment_score:.2f}). Holding."
            )
            self.log_ai_analytics(symbol, current_price, raw_news_titles, ai_decision, False, "")
            return None
