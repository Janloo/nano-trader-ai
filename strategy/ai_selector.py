"""
strategy/ai_selector.py

Dynamic Asset Selection (DAS) engine.
Uses Gemini as a quantitative Portfolio Manager to autonomously select
the top 2 assets from the configured market universe based on macro news.
"""
import json
import os
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

from google import genai
from google.genai import types
from config.settings import GEMINI_API_KEY, logger


def load_universe() -> Dict[str, Any]:
    """Loads the market universe configuration from config/market_universe.json."""
    universe_path = os.path.join("config", "market_universe.json")
    try:
        with open(universe_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"market_universe.json not found at {universe_path}. Using defaults.")
        return {
            "assets": [
                {"symbol": "BTCUSD", "type": "crypto", "name": "Bitcoin / USD"},
                {"symbol": "SPY",    "type": "equity", "name": "S&P 500 ETF"},
            ],
            "max_selections": 2,
            "sentiment_threshold": 0.75
        }
    except Exception as e:
        logger.error(f"Error loading market_universe.json: {e}. Using defaults.")
        return {
            "assets": [
                {"symbol": "BTCUSD", "type": "crypto", "name": "Bitcoin / USD"},
                {"symbol": "SPY",    "type": "equity", "name": "S&P 500 ETF"},
            ],
            "max_selections": 2,
            "sentiment_threshold": 0.75
        }


class GeminiAssetSelector:
    """
    Queries Gemini Flash as a Portfolio Manager to dynamically select
    the best assets from the universe given current macro news headlines.
    """

    def __init__(self):
        self.api_key = GEMINI_API_KEY
        self.is_mocked = not self.api_key or "YOUR_GEMINI_API_KEY" in self.api_key

        if not self.is_mocked:
            self.client = genai.Client(api_key=self.api_key)
            self.model_name = "gemini-3.5-flash"
        else:
            logger.warning("[DAS] No GEMINI_API_KEY found. Running Asset Selector in MOCK mode.")

    def select_assets(self, universe_assets: List[Dict], macro_news_text: str) -> List[Dict]:
        """
        Selects up to max_selections assets from universe_assets based on macro_news_text.

        Returns a list of selected asset dicts:
        [
          {"symbol": "NVDA", "type": "equity", "sentiment_score": 0.90, "reasoning": "..."},
          ...
        ]
        """
        config = load_universe()
        max_sel = config.get("max_selections", 2)

        if self.is_mocked:
            return self._mock_select(universe_assets, max_sel)

        # Build universe symbol list for the prompt
        universe_lines = "\n".join(
            f"  - {a['symbol']} ({a['name']}, {a['type']})"
            for a in universe_assets
        )

        system_prompt = (
            "You are a quantitative Portfolio Manager AI.\n"
            "Analyze the global macroeconomic and market news provided below.\n"
            f"Select a MAXIMUM of {max_sel} assets from the Universe that show the strongest "
            "bullish (or bearish) catalyst in the last 24 hours.\n"
            "For each selected asset, provide a sentiment_score between -1.0 (extreme bearish) "
            "and +1.0 (extreme bullish), and a concise one-sentence reasoning.\n\n"
            "IMPORTANT: Return ONLY valid JSON with no markdown, no backticks, no extra text:\n"
            "{\n"
            '  "selected_assets": [\n'
            '    {"symbol": "BTCUSD", "sentiment_score": 0.85, "reasoning": "Institutional adoption surging."},\n'
            '    {"symbol": "NVDA",   "sentiment_score": 0.90, "reasoning": "Record earnings beat estimates."}\n'
            "  ]\n"
            "}\n\n"
            f"Available Universe:\n{universe_lines}"
        )

        user_content = f"Latest macro news headlines (last 24h):\n\n{macro_news_text}"

        max_retries = 3
        backoff = 30
        last_error = ""

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=f"{system_prompt}\n\n{user_content}",
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                raw_text = response.text.strip()

                # Strip markdown fences if present
                if raw_text.startswith("```"):
                    lines = raw_text.split("\n")
                    raw_text = "\n".join(lines[1:-1]).strip() if len(lines) >= 3 else raw_text.replace("```json", "").replace("```", "").strip()

                parsed = json.loads(raw_text)
                selected = parsed.get("selected_assets", [])

                # Validate symbols are in universe
                universe_symbols = {a["symbol"] for a in universe_assets}
                asset_type_map = {a["symbol"]: a["type"] for a in universe_assets}
                valid = []
                for item in selected:
                    sym = item.get("symbol", "")
                    if sym in universe_symbols:
                        item["type"] = asset_type_map.get(sym, "unknown")
                        item["selected_at"] = datetime.now(timezone.utc).isoformat()
                        valid.append(item)

                logger.info(f"[DAS] AI selected {len(valid)} asset(s): {[v['symbol'] for v in valid]}")
                return valid[:max_sel]

            except Exception as e:
                last_error = str(e)
                if "429" in last_error or "quota" in last_error.lower():
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"[DAS] Gemini 429 rate limit. Retrying in {backoff}s "
                            f"(Attempt {attempt + 1}/{max_retries})..."
                        )
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                logger.error(f"[DAS] Gemini attempt {attempt + 1} failed: {e}")

        # Quota exhausted: write to logbook and fall back to safe crypto defaults
        self._write_logbook_warning(last_error)
        return self._fallback_selection(universe_assets, max_sel)

    def _mock_select(self, universe_assets: List[Dict], max_sel: int) -> List[Dict]:
        """Mock selection: returns first crypto asset + first equity asset from universe."""
        logger.info("[DAS MOCK] Simulating AI asset selection...")
        cryptos = [a for a in universe_assets if a.get("type") == "crypto"]
        equities = [a for a in universe_assets if a.get("type") == "equity"]

        selected = []
        if cryptos:
            selected.append({
                "symbol": cryptos[0]["symbol"],
                "type": "crypto",
                "sentiment_score": 0.80,
                "reasoning": f"Mock: Strong momentum in crypto market for {cryptos[0]['name']}.",
                "selected_at": datetime.now(timezone.utc).isoformat()
            })
        if equities and len(selected) < max_sel:
            selected.append({
                "symbol": equities[0]["symbol"],
                "type": "equity",
                "sentiment_score": 0.78,
                "reasoning": f"Mock: Macro indicators support bullish outlook for {equities[0]['name']}.",
                "selected_at": datetime.now(timezone.utc).isoformat()
            })
        return selected[:max_sel]

    def _fallback_selection(self, universe_assets: List[Dict], max_sel: int) -> List[Dict]:
        """Fallback when API is exhausted: prefer crypto assets (trade 24/7)."""
        logger.warning("[DAS] API exhausted — falling back to safe crypto-first selection.")
        cryptos = [a for a in universe_assets if a.get("type") == "crypto"]
        selected = []
        for asset in cryptos[:max_sel]:
            selected.append({
                "symbol": asset["symbol"],
                "type": asset["type"],
                "sentiment_score": 0.0,
                "reasoning": "Fallback selection: Gemini API quota exhausted. Defaulting to crypto HOLD.",
                "selected_at": datetime.now(timezone.utc).isoformat()
            })
        return selected

    def _write_logbook_warning(self, error: str):
        """Writes a warning entry to data/human_logbook.txt."""
        
        err_msg = str(error).replace("\n", " ")
        log_msg = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[API WARNING] DAS: Errore Gemini API nella selezione asset: {err_msg}. "
            "Il bot riprovera' al prossimo ciclo orario."
        )
        log_path = os.path.join("data", "archives", "human_logbook.txt")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except Exception as e:
            logger.error(f"[DAS] Failed to write to human logbook: {e}")
