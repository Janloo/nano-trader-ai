import os
import json
import logging
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# Logger configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

log_dir = os.path.join("data", "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "nano_trader.log")

from logging.handlers import TimedRotatingFileHandler
file_handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=7)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    handlers=[stream_handler, file_handler]
)
logger = logging.getLogger("nano-trader-ai")

# Load local credentials if synced from browser
local_config_path = os.path.join("config", "local_credentials.json")
local_config = {}
if os.path.exists(local_config_path):
    try:
        with open(local_config_path, "r", encoding="utf-8") as f:
            local_config = json.load(f)
            logger.info("Loaded credentials from local_credentials.json (localStorage sync)")
    except Exception as e:
        logger.error(f"Error loading local_credentials.json: {e}")

# API Keys
APCA_API_KEY_ID = local_config.get("api_key", os.getenv("APCA_API_KEY_ID"))
APCA_API_SECRET_KEY = local_config.get("secret_key", os.getenv("APCA_API_SECRET_KEY"))
APCA_API_BASE_URL = local_config.get("base_url", os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets"))
GEMINI_API_KEY = local_config.get("gemini_key", os.getenv("GEMINI_API_KEY"))

# Telegram notifications (optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Trading parameters
TICKERS_STR = os.getenv("TICKERS", "SPY,BTCUSD")
TICKERS = [t.strip().upper() for t in TICKERS_STR.split(",") if t.strip()]

try:
    TRADE_AMOUNT_USD = float(os.getenv("TRADE_AMOUNT_USD", "5.00"))
except ValueError:
    logger.warning("Invalid TRADE_AMOUNT_USD in environment, defaulting to 5.00")
    TRADE_AMOUNT_USD = 5.00

# Strategy settings
RSI_PERIOD = 14
SMA_FAST_PERIOD = 50
SMA_SLOW_PERIOD = 200

def validate_config():
    """Validates that necessary credentials are present."""
    if not APCA_API_KEY_ID or not APCA_API_SECRET_KEY:
        raise ValueError(
            "Alpaca API credentials missing. Please define APCA_API_KEY_ID and "
            "APCA_API_SECRET_KEY in your environment or .env file."
        )
    if not GEMINI_API_KEY:
        raise ValueError(
            "Gemini API key missing. Please define GEMINI_API_KEY in your environment or .env file."
        )
    if "YOUR_GEMINI_API_KEY" in GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is using the default placeholder value. Real Gemini API requests will be bypassed/mocked.")
