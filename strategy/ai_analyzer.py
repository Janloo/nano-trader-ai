import json
import os
import google.generativeai as genai
from strategy.base import BaseStrategy
from config.settings import GEMINI_API_KEY, logger

class GeminiSentimentStrategy(BaseStrategy):
    def __init__(self):
        self.api_key = GEMINI_API_KEY
        self.is_mocked = not self.api_key or "YOUR_GEMINI_API_KEY" in self.api_key
        
        if not self.is_mocked:
            logger.info("Initializing Gemini API client wrapper.")
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel("gemini-2.0-flash")
        else:
            logger.warning("No valid GEMINI_API_KEY found in .env. Running in MOCK sentiment analysis mode.")

    def analyze(self, symbol: str, bars_df=None, news_df=None) -> float:
        """
        Implements BaseStrategy analyze. This will not be the primary entry point
        for this strategy class, but is retained for compatibility.
        """
        # Return 0.0 by default since it requires text to parse
        return 0.0

    def analyze_news_text(self, symbol: str, news_text: str) -> dict:
        """
        Wrapper around analyze_all_assets for backwards compatibility.
        """
        res = self.analyze_all_assets({symbol: news_text})
        return res.get(symbol, {
            "sentiment_score": 0.0,
            "action": "HOLD",
            "confidence": 0,
            "reasoning": "Batch analysis failed to return result for this symbol."
        })

    def analyze_all_assets(self, assets_news: dict) -> dict:
        """
        Sends aggregated news context for all assets to Gemini API in a single call.
        Returns a dict mapping symbol -> decision dict (sentiment_score, action, confidence, reasoning).
        """
        if self.is_mocked:
            logger.info("[MOCK Gemini] Simulating aggregated sentiment analysis...")
            results = {}
            for symbol, news_text in assets_news.items():
                results[symbol] = self._mock_analyze(symbol, news_text)
            return results

        system_prompt = (
            "You are a senior macroeconomic and quantitative financial analyst.\n"
            "Analyze the provided news context for the following assets. Evaluate their macroeconomic impact and return a decision for each asset.\n"
            "You must return ONLY a structured JSON response mapping each symbol to its decision matching the following schema, "
            "with no extra text, no markdown backticks, and no conversation:\n"
            "{\n"
            "  \"SYMBOL_NAME\": {\n"
            "    \"sentiment_score\": <float from -1.0 to 1.0>,\n"
            "    \"action\": <\"BUY\" or \"SELL\" or \"HOLD\">,\n"
            "    \"confidence\": <int from 0 to 100>,\n"
            "    \"reasoning\": <\"short explanation sentence\">\n"
            "  }\n"
            "}"
        )

        user_content = "Assets and news contexts to analyze:\n"
        for symbol, news_text in assets_news.items():
            user_content += f"=== Asset: {symbol} ===\nNews:\n{news_text}\n\n"

        max_retries = 3
        backoff = 30
        last_error = ""

        for attempt in range(max_retries):
            try:
                from strategy.ai_limiter import AILimiter, RateLimitExceededException
                AILimiter.check_and_log("GeminiAssetAnalyzer", "gemini-2.0-flash")
            except RateLimitExceededException:
                logger.warning("[DAS] AI rate limit exceeded for Asset Analyzer. Falling back to HOLD.")
                fallback = {}
                for sym in assets_news.keys():
                    fallback[sym] = {
                        "sentiment_score": 0.0,
                        "action": "HOLD",
                        "confidence": 0,
                        "reasoning": "AI Rate Limit Exceeded. Defaulting to HOLD."
                    }
                return fallback
            except Exception as e:
                logger.error(f"[DAS] AILimiter check failed: {e}")

            try:
                response = self.model.generate_content(
                    contents=f"{system_prompt}\n\n{user_content}",
                    generation_config={"response_mime_type": "application/json"}
                )
                raw_text = response.text.strip()
                
                if raw_text.startswith("```"):
                    lines = raw_text.split("\n")
                    if len(lines) >= 3:
                        raw_text = "\n".join(lines[1:-1]).strip()
                    else:
                        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
                
                parsed = json.loads(raw_text)
                
                # Verify that all requested symbols exist in parsed result
                for symbol in assets_news.keys():
                    if symbol not in parsed:
                        parsed[symbol] = {
                            "sentiment_score": 0.0,
                            "action": "HOLD",
                            "confidence": 0,
                            "reasoning": "Symbol was omitted from Gemini JSON output."
                        }
                    else:
                        logger.info(
                            f"[{symbol} Gemini Result] Action: {parsed[symbol].get('action')} | "
                            f"Score: {parsed[symbol].get('sentiment_score')} | Conf: {parsed[symbol].get('confidence')}%"
                        )
                return parsed

            except Exception as e:
                last_error = str(e)
                if any(err in last_error for err in ["429", "503", "500", "502"]) or "quota" in last_error.lower():
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Gemini API rate limit/server error hit. Retrying in {backoff} seconds "
                            f"(Attempt {attempt + 1}/{max_retries})..."
                        )
                        import time
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                logger.error(f"Gemini API attempt {attempt + 1} failed: {e}")

        # If retries exceeded, write warning to human logbook and raise exception
        from datetime import datetime
        log_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [API WARNING] Quota Gemini esaurita. Il bot riprovera' al prossimo ciclo orario."
        log_path = os.path.join("data", "archives", "human_logbook.txt")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except Exception as e_log:
            logger.error(f"Failed to write to human logbook: {e_log}")
            
        # Return fallback HOLD decisions for all symbols
        fallback = {}
        for symbol in assets_news.keys():
            fallback[symbol] = {
                "sentiment_score": 0.0,
                "action": "HOLD",
                "confidence": 0,
                "reasoning": f"Gemini API rate limit or error persisted: {last_error}"
            }
        return fallback

    def _mock_analyze(self, symbol: str, news_text: str) -> dict:
        text_lower = news_text.lower()
        if "surged" in text_lower or "profit" in text_lower or "rally" in text_lower or "bullish" in text_lower:
            score = 0.85
            action = "BUY"
            confidence = 90
        elif "drop" in text_lower or "fall" in text_lower or "loss" in text_lower or "bearish" in text_lower:
            score = -0.75
            action = "SELL"
            confidence = 80
        else:
            score = 0.15
            action = "HOLD"
            confidence = 60
            
        return {
            "sentiment_score": score,
            "action": action,
            "confidence": confidence,
            "reasoning": f"Mock analysis: Headlines suggest standard market activity for {symbol}."
        }
