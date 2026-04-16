"""
Logger Setup
────────────
Uses loguru for clean, colorful, structured logging.
Logs to console + daily rotating log files.
"""

import sys
from pathlib import Path

from loguru import logger

from config import settings


def setup_logger():
    """Configure logging for the trading bot."""
    # Remove default handler
    logger.remove()

    # Console output — colorful, concise
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{message}</cyan>"
        ),
        level=settings.LOG_LEVEL,
        colorize=True,
    )

    # Main log file — daily rotation
    log_dir = settings.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_dir / "bot_{time:YYYY-MM-DD}.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG",
        rotation="00:00",  # New file every day at midnight
        retention="30 days",
        compression="zip",
    )

    # Trade-specific log file
    trade_log_dir = settings.TRADE_LOG_DIR
    trade_log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(trade_log_dir / "trades_{time:YYYY-MM-DD}.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        level="INFO",
        rotation="00:00",
        retention="90 days",
        filter=lambda record: "PAPER" in record["message"] or "LIVE" in record["message"],
    )


# Auto-setup on import
setup_logger()
