"""
Notification Module
───────────────────
Sends trade alerts and daily reports to Telegram.
Optional — works without Telegram configured.
"""

import requests

from config import settings
from src.utils.logger import logger


class Notifier:
    """Send notifications via Telegram."""

    def __init__(self):
        self.enabled = (
            settings.TELEGRAM_ENABLED
            and settings.TELEGRAM_BOT_TOKEN
            and settings.TELEGRAM_CHAT_ID
        )
        if self.enabled:
            logger.info("Telegram notifications enabled")
        else:
            logger.info("Telegram notifications disabled")

    def send(self, message: str):
        """Send a message to Telegram."""
        if not self.enabled:
            return

        try:
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            }
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")

    def send_trade_alert(
        self,
        action: str,
        symbol: str,
        price: float,
        quantity: int,
        stop_loss: float,
        target: float,
        reason: str,
        is_paper: bool = True,
    ):
        """Send a formatted trade alert."""
        mode = "PAPER" if is_paper else "LIVE"
        emoji = "🟢" if action == "BUY" else "🔴"
        msg = (
            f"{emoji} <b>[{mode}] {action} {symbol}</b>\n"
            f"Price: Rs {price:.2f}\n"
            f"Qty: {quantity}\n"
            f"SL: Rs {stop_loss:.2f}\n"
            f"Target: Rs {target:.2f}\n"
            f"Reason: {reason}"
        )
        self.send(msg)

    def send_close_alert(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        reason: str,
        is_paper: bool = True,
    ):
        """Send a trade close notification."""
        mode = "PAPER" if is_paper else "LIVE"
        emoji = "✅" if pnl > 0 else "❌"
        msg = (
            f"{emoji} <b>[{mode}] CLOSED {symbol}</b>\n"
            f"Entry: Rs {entry_price:.2f}\n"
            f"Exit: Rs {exit_price:.2f}\n"
            f"P&L: Rs {pnl:+.2f}\n"
            f"Reason: {reason}"
        )
        self.send(msg)

    def send_daily_report(self, report: dict):
        """Send end-of-day summary."""
        mode = "PAPER" if report.get("is_paper") else "LIVE"
        total_pnl = report.get("total_pnl", 0)
        emoji = "📈" if total_pnl >= 0 else "📉"

        msg = (
            f"{emoji} <b>[{mode}] Daily Report</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Total Trades: {report.get('total_trades', 0)}\n"
            f"Wins: {report.get('wins', 0)} | Losses: {report.get('losses', 0)}\n"
            f"Win Rate: {report.get('win_rate', 0):.1f}%\n"
            f"<b>Total P&L: Rs {total_pnl:+.2f}</b>\n"
            f"Capital: Rs {report.get('capital', 0):,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        self.send(msg)
