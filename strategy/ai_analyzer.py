import json
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
        Sends macroeconomic news context to Gemini API.
        Returns a dict containing sentiment_score, action, confidence, and reasoning.
        """
        if self.is_mocked or not news_text.strip():
            logger.info(f"[MOCK Gemini] Simulating macroeconomic sentiment analysis for {symbol}...")
            
            # Simple simulation logic
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

        system_prompt = (
            "You are a senior macroeconomic and quantitative financial analyst.\n"
            "Analyze the provided news context for the asset and evaluate its impact.\n"
            "You must return ONLY a structured JSON response matching the following schema, "
            "with no extra text, no markdown backticks, and no conversation:\n"
            "{\n"
            "  \"sentiment_score\": <float from -1.0 to 1.0>,\n"
            "  \"action\": <\"BUY\" or \"SELL\" or \"HOLD\">,\n"
            "  \"confidence\": <int from 0 to 100>,\n"
            "  \"reasoning\": <\"short explanation sentence\">\n"
            "}"
        )

        user_content = f"Asset: {symbol}\nNews Context:\n{news_text}"

        try:
            response = self.model.generate_content(
                contents=f"{system_prompt}\n\n{user_content}",
                generation_config={"response_mime_type": "application/json"}
            )
            raw_text = response.text.strip()
            
            # Clean potential markdown output wraps
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                if len(lines) >= 3:
                    # Strip first and last lines
                    raw_text = "\n".join(lines[1:-1])
            raw_text = raw_text.strip()

            result = json.loads(raw_text)
            logger.info(
                f"[{symbol} Gemini Result] Action: {result.get('action')} | "
                f"Score: {result.get('sentiment_score')} | Conf: {result.get('confidence')}%"
            )
            return result
        except Exception as e:
            logger.error(f"Gemini API analysis failed: {e}. Falling back to HOLD.")
            return {
                "sentiment_score": 0.0,
                "action": "HOLD",
                "confidence": 0,
                "reasoning": f"Failed to query Gemini API: {e}"
            }
