"""
notifications/telegram_notifier.py

Sends real-time Telegram messages for trade executions and daily AI selections.
Configure by setting TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file.

Setup:
  1. Create a bot via @BotFather on Telegram → copy the token
  2. Send /start to your bot, then visit:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     to find your chat_id
  3. Add to .env:
     TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
     TELEGRAM_CHAT_ID=987654321
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, logger


def _is_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def _send(text: str) -> bool:
    """Sends a message via Telegram Bot API. Returns True on success."""
    if not _is_configured():
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning(f"[Telegram] Failed to send notification: {e}")
        return False


def notify_trade_executed(symbol: str, action: str, notional: float,
                           price: float, sentiment_score: float,
                           reasoning: str, order_id: str):
    """Sends a trade execution notification."""
    emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"
    score_emoji = "📈" if sentiment_score >= 0 else "📉"

    text = (
        f"{emoji} <b>Trade Executed — {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Action:</b> {action}  |  <b>Notional:</b> ${notional:.2f}\n"
        f"<b>Price:</b> ${price:,.4f}\n"
        f"{score_emoji} <b>Sentiment:</b> {sentiment_score:+.2f}\n"
        f"<b>AI Reasoning:</b> {reasoning[:200]}\n"
        f"<b>Order ID:</b> <code>{order_id}</code>\n"
        f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
    )
    sent = _send(text)
    if sent:
        logger.info(f"[Telegram] Trade notification sent for {symbol} {action}.")


def notify_das_selection(selected_assets: list, macro_count: int):
    """Sends an AI asset selection summary at the start of each cycle."""
    if not selected_assets:
        return
    lines = [f"🤖 <b>AI Selection of the Hour</b> ({macro_count} macro articles analyzed)\n━━━━━━━━━━━━━━━━━━"]
    for asset in selected_assets:
        sym = asset.get("symbol", "?")
        score = asset.get("sentiment_score", 0.0)
        reason = asset.get("reasoning", "")[:120]
        asset_type = asset.get("type", "?")
        type_tag = "🔵 Crypto" if asset_type == "crypto" else "📊 Equity"
        score_bar = "▓" * int(abs(score) * 10) + "░" * (10 - int(abs(score) * 10))
        lines.append(
            f"\n<b>{sym}</b> ({type_tag})\n"
            f"Score: {score:+.2f}  [{score_bar}]\n"
            f"<i>{reason}</i>"
        )
    lines.append(f"\n<i>{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC</i>")
    _send("\n".join(lines))


def notify_market_hours_skip(reason: str):
    """Sends a notification when the bot skips execution due to market hours."""
    if not _is_configured():
        return
    _send(f"⏸ <b>Nano-Trader-AI</b>\n{reason}")


def notify_quota_warning():
    """Sends a notification when Gemini quota is exhausted."""
    _send(
        "⚠️ <b>Nano-Trader-AI Warning</b>\n"
        "Gemini API quota esaurita.\n"
        "Il bot e' passato al fallback crypto e riprovera' al prossimo ciclo."
    )
