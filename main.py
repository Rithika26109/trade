"""
Trading Bot — entry point.

Three small classes orchestrate the day:

    Bootstrap → builds and wires everything, returns a BotContext
    Runtime   → drives the trading loop on that context
    EODManager → end-of-day square-off, reporting, git commit

Keeping them split makes each piece independently mockable and keeps
this file thin.
"""

from __future__ import annotations

import argparse

from config import settings
from src.runtime import Bootstrap, BotContext, Runtime


class TradingBot:
    """Thin shell — Bootstrap builds the context, Runtime runs the day."""

    def __init__(self, mode: str | None = None):
        self.mode = mode or settings.TRADING_MODE
        self.ctx: BotContext | None = None

    def run(self) -> None:
        self.ctx = Bootstrap(self.mode).setup()
        Runtime(self.ctx).run()


def main():
    parser = argparse.ArgumentParser(description="Intraday Trading Bot")
    parser.add_argument("--live", action="store_true", help="Run in live trading mode")
    parser.add_argument("--paper", action="store_true", help="Run in paper trading mode")
    args = parser.parse_args()

    mode = "live" if args.live else "paper" if args.paper else None
    TradingBot(mode=mode).run()


if __name__ == "__main__":
    main()
