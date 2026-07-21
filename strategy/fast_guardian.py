import logging
import google.generativeai as genai
import os

logger = logging.getLogger("nano-trader-ai")

class FastGuardian:
    """
    Ultra-fast NLP evaluation of news headlines to detect extreme market events.
    """
    def __init__(self):
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        else:
            logger.warning("[GUARDIAN] GEMINI_API_KEY not found in environment!")
            
        self.model = genai.GenerativeModel("gemini-1.5-flash-latest")
        
    def evaluate_headline(self, headline: str) -> str:
        """
        Evaluates a news headline and returns exactly one of: 
        CATACLYSM, MOONSHOT, or IGNORE.
        """
        prompt = f"""You are a Guardian AI for a high-frequency algorithmic trading bot.
Your ONLY job is to categorize this financial news headline into exactly one of these three categories:
- CATACLYSM: A catastrophic event for the asset or market (e.g., hack, lawsuit, bankruptcy, massive crash, severe regulation).
- MOONSHOT: An overwhelmingly positive event that will trigger an immediate massive pump (e.g., ETF approval, massive acquisition, unexpected bullish pivot).
- IGNORE: Any standard news, earnings, generic analysis, routine upgrades/downgrades, or non-extreme event.

Respond ONLY with the single word (CATACLYSM, MOONSHOT, or IGNORE). No explanations.

Headline: {headline}"""

        try:
            response = self.model.generate_content(prompt)
            result = response.text.strip().upper()
            if "CATACLYSM" in result:
                return "CATACLYSM"
            elif "MOONSHOT" in result:
                return "MOONSHOT"
            else:
                return "IGNORE"
        except Exception as e:
            logger.error(f"[GUARDIAN] Error evaluating headline: {e}")
            return "IGNORE"
