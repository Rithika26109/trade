"""
Trading Bot — Main Entry Point
───────────────────────────────
Orchestrates the entire trading day:
1. Login to Zerodha
2. Scan stocks
3. Collect opening range
4. Run strategy loop
5. Manage positions
6. Square off and report

Usage:
    python main.py              # Uses TRADING_MODE from .env (default: paper)
    python main.py --live       # Force live mode
    python main.py --paper      # Force paper mode
"""

import argparse
import signal as sig
import sys
import time
from datetime import datetime, timedelta, date

import pandas as pd

from config import settings
from src.auth.login import ZerodhaAuth
from src.data.market_data import MarketData
from src.data.websocket import TickerManager
from src.execution.order_manager import OrderManager
from src.execution.position_manager import PositionManager
from src.indicators.indicators import add_all_indicators
from src.risk.risk_manager import RiskManager
from src.scanner.stock_scanner import StockScanner
from src.strategy.base import Signal, TradeSignal
from src.strategy.orb import ORBStrategy
from src.strategy.rsi_ema import RSIEMAStrategy
from src.strategy.vwap_supertrend import VWAPSupertrendStrategy
from src.utils.db import TradeDB
from src.utils.logger import logger
from src.utils.notifier import Notifier


class TradingBot:
    """Main trading bot orchestrator."""

    def __init__(self, mode: str = None):
        self.mode = mode or settings.TRADING_MODE
        self.running = False
        self._shutting_down = False

        # Components (initialized in setup)
        self.kite = None
        self.market_data = None
        self.ticker = None
        self.order_manager = None
        self.position_manager = None
        self.risk_manager = None
        self.strategy = None
        self.scanner = None
        self.db = TradeDB()
        self.notifier = Notifier()

        # Today's state
        self._logged_order_ids: set[str] = set()
        self.todays_watchlist: list[str] = []
        self.instrument_tokens: dict[str, int] = {}  # symbol → token
        self.token_to_symbol: dict[int, str] = {}  # token → symbol

    def setup(self):
        """Initialize all components."""
        logger.info("=" * 60)
        logger.info(f"  TRADING BOT STARTING — Mode: {self.mode.upper()}")
        logger.info("=" * 60)

        # ── Validate config ──
        settings.validate_config()

        # ── Check if market is open today ──
        if not settings.is_market_day():
            today = settings.now_ist().date()
            logger.info(f"Market closed today ({today} — weekend or holiday). Exiting.")
            sys.exit(0)

        # ── Authentication ──
        if self.mode == "live" or self.mode == "paper":
            try:
                auth = ZerodhaAuth()
                self.kite = auth.login()
                self.market_data = MarketData(self.kite)
                self.market_data.load_instruments("NSE")
                logger.info("Zerodha connected successfully")
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                if self.mode == "live":
                    logger.error("Cannot run live mode without Zerodha connection. Exiting.")
                    sys.exit(1)
                logger.warning("Running in offline paper mode with limited functionality")
                self.kite = None

        # ── Order & Position Management ──
        self.order_manager = OrderManager(self.kite)
        self.order_manager.is_paper = self.mode == "paper"
        self.position_manager = PositionManager(self.order_manager, db=self.db)
        self.risk_manager = RiskManager(self.order_manager)

        # ── Crash Recovery ──
        self._recover_orphaned_positions()

        # ── Strategy Selection ──
        strategy_name = settings.STRATEGY
        if strategy_name == "ORB":
            self.strategy = ORBStrategy()
        elif strategy_name == "RSI_EMA":
            self.strategy = RSIEMAStrategy()
        elif strategy_name == "VWAP_SUPERTREND":
            self.strategy = VWAPSupertrendStrategy()
        else:
            logger.warning(f"Unknown strategy '{strategy_name}', defaulting to ORB")
            self.strategy = ORBStrategy()

        logger.info(f"Strategy: {self.strategy.name}")

        # ── Scanner ──
        if self.market_data:
            self.scanner = StockScanner(self.market_data)

        # ── Update capital from Zerodha (live mode) ──
        if self.kite and self.mode == "live":
            try:
                margins = self.kite.margins()
                available = margins["equity"]["available"]["live_balance"]
                self.risk_manager.update_capital(available)
                logger.info(f"Live capital: Rs {available:,.2f}")
            except Exception:
                logger.warning("Could not fetch margins, using configured capital")

        self.notifier.send(
            f"🤖 Trading Bot started in <b>{self.mode.upper()}</b> mode\n"
            f"Strategy: {self.strategy.name}\n"
            f"Capital: Rs {self.risk_manager.capital:,.2f}"
        )

    def run(self):
        """Main bot loop — runs for one trading day."""
        self.setup()
        self.running = True

        # Handle Ctrl+C gracefully
        sig.signal(sig.SIGINT, self._shutdown_handler)
        sig.signal(sig.SIGTERM, self._shutdown_handler)

        try:
            # ── Step 1: Wait for market pre-open ──
            self._wait_until(settings.MARKET_OPEN, "market open")

            # ── Step 2: Scan for today's stocks ──
            self._scan_stocks()

            # ── Step 3: Collect opening range ──
            self._collect_opening_range()

            # ── Step 4: Main trading loop ──
            self._trading_loop()

            # ── Step 5: End of day ──
            self._end_of_day()

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            self.notifier.send(f"🚨 Bot crashed: {e}")
        finally:
            self.running = False
            self._cleanup()

    def _scan_stocks(self):
        """Select today's stocks to trade."""
        if self.scanner:
            self.todays_watchlist = self.scanner.scan()
        else:
            self.todays_watchlist = settings.WATCHLIST[:5]

        if not self.todays_watchlist:
            self.todays_watchlist = settings.WATCHLIST[:5]

        # Map symbols to instrument tokens
        if self.market_data:
            for symbol in self.todays_watchlist:
                try:
                    token = self.market_data.get_instrument_token(symbol)
                    self.instrument_tokens[symbol] = token
                    self.token_to_symbol[token] = symbol
                except Exception as e:
                    logger.warning(f"Could not get token for {symbol}: {e}")

        logger.info(f"Today's watchlist: {self.todays_watchlist}")

    def _collect_opening_range(self):
        """Wait for the opening range period and record highs/lows."""
        if not isinstance(self.strategy, ORBStrategy):
            logger.info("Strategy doesn't need opening range, skipping...")
            self._wait_until(settings.TRADING_START, "trading start")
            return

        orb_minutes = settings.ORB_PERIOD_MINUTES
        orb_end_time = self._parse_time(settings.MARKET_OPEN) + timedelta(minutes=orb_minutes)
        orb_end_str = orb_end_time.strftime("%H:%M")

        logger.info(f"Collecting opening range ({orb_minutes} min)...")
        self._wait_until(orb_end_str, "opening range complete")

        # Fetch opening range for each stock
        if self.market_data:
            for symbol in self.todays_watchlist:
                try:
                    orb = self.market_data.get_opening_range(symbol, minutes=orb_minutes)
                    if orb:
                        self.strategy.set_opening_range(symbol, orb["high"], orb["low"], orb["open"])
                    else:
                        logger.warning(f"No opening range data for {symbol}")
                except Exception as e:
                    logger.error(f"Error getting opening range for {symbol}: {e}")

    def _trading_loop(self):
        """
        Main trading loop — runs every candle interval.
        Fetches data, calculates indicators, checks signals, manages positions.
        """
        logger.info("=" * 40)
        logger.info("  TRADING LOOP STARTED")
        logger.info("=" * 40)

        interval_seconds = self._get_interval_seconds()

        while self.running:
            now = settings.now_ist()

            # Check if we should stop trading
            stop_time = self._parse_time(settings.STOP_NEW_TRADES)
            if now >= stop_time:
                logger.info("Trading window closed")
                break

            loop_start = time.time()

            try:
                self._run_single_cycle()
            except Exception as e:
                logger.error(f"Error in trading cycle: {e}")

            # Wait for next candle
            elapsed = time.time() - loop_start
            sleep_time = max(0, interval_seconds - elapsed)
            if sleep_time > 0 and self.running:
                time.sleep(sleep_time)

    def _run_single_cycle(self):
        """Execute one cycle of the trading loop."""
        # Get current prices for position monitoring
        current_prices = {}
        if self.market_data:
            try:
                current_prices = self.market_data.get_ltp(self.todays_watchlist)
            except Exception as e:
                logger.error(f"Error fetching prices: {e}")
                return

        # ── Check existing position exits (stop-loss / target) ──
        self.position_manager.check_exits(current_prices)

        # ── Log closed trades + update capital ──
        for order in self.order_manager.orders:
            if order.pnl != 0 and order.order_id not in self._logged_order_ids:
                self.db.log_trade(order)
                self.risk_manager.record_trade_result(order.pnl)
                self.risk_manager.update_capital(self.risk_manager.capital + order.pnl)
                self._logged_order_ids.add(order.order_id)

        # ── Update unrealized P&L for risk circuit breaker ──
        unrealized = self.position_manager.get_unrealized_pnl(current_prices)
        self.risk_manager.set_unrealized_pnl(unrealized)

        # ── Check risk status ──
        risk_status = self.risk_manager.get_status()
        if risk_status["is_paused"]:
            return

        # ── Analyze each stock for signals ──
        for symbol in self.todays_watchlist:
            # Skip if we already have a position
            if self.position_manager.has_position(symbol):
                continue

            try:
                # Fetch latest candle data
                df = self.market_data.get_todays_candles(
                    symbol, interval=settings.TIMEFRAME
                )
                if df.empty or len(df) < 5:
                    continue

                # Calculate indicators
                df = add_all_indicators(df)

                # Get strategy signal
                signal = self.strategy.analyze(df, symbol)
                if signal.signal == Signal.HOLD:
                    continue

                # Risk check + position sizing
                approved = self.risk_manager.evaluate(signal)
                if approved is None:
                    continue

                # Place the trade
                order = self.order_manager.place_order(approved)
                if order:
                    self.position_manager.add_position(order)
                    self.notifier.send_trade_alert(
                        action=signal.signal.value,
                        symbol=signal.symbol,
                        price=signal.price,
                        quantity=signal.quantity,
                        stop_loss=signal.stop_loss,
                        target=signal.target,
                        reason=signal.reason,
                        is_paper=self.order_manager.is_paper,
                    )

            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")

        # ── Print status every cycle ──
        pnl = self.order_manager.get_todays_pnl()
        positions = self.position_manager.get_position_count()
        trades = self.order_manager.get_todays_trade_count()
        unrealized = self.position_manager.get_unrealized_pnl(current_prices)

        logger.info(
            f"Trades: {trades}/{settings.MAX_TRADES_PER_DAY} | "
            f"Open: {positions} | "
            f"Realized P&L: Rs {pnl:+.2f} | "
            f"Unrealized: Rs {unrealized:+.2f}"
        )

    def _end_of_day(self):
        """End of day: square off all positions, generate report."""
        logger.info("=" * 40)
        logger.info("  END OF DAY")
        logger.info("=" * 40)

        # ── Force close all open positions ──
        if self.position_manager.get_position_count() > 0:
            logger.info("Squaring off all open positions...")
            current_prices = {}
            if self.market_data:
                try:
                    current_prices = self.market_data.get_ltp(self.todays_watchlist)
                except Exception:
                    pass
            self.position_manager.force_close_all(current_prices, "End of day square-off")

        # ── Log remaining trades and clear open positions ──
        for order in self.order_manager.orders:
            if order.order_id not in self._logged_order_ids:
                self.db.log_trade(order)
                self._logged_order_ids.add(order.order_id)
        self.db.clear_open_positions()

        # ── Generate daily report ──
        report = self._generate_daily_report()
        self._print_daily_report(report)
        self.notifier.send_daily_report(report)

        # Save to DB
        self.db.save_daily_summary(
            total_trades=report["total_trades"],
            winning_trades=report["wins"],
            losing_trades=report["losses"],
            total_pnl=report["total_pnl"],
            max_drawdown=report.get("max_drawdown", 0),
            capital=self.risk_manager.capital,
            is_paper=self.order_manager.is_paper,
        )

    def _generate_daily_report(self) -> dict:
        """Generate end-of-day performance report."""
        orders = self.order_manager.orders
        total = len(orders)
        wins = sum(1 for o in orders if o.pnl > 0)
        losses = sum(1 for o in orders if o.pnl < 0)
        total_pnl = sum(o.pnl for o in orders)
        win_rate = (wins / total * 100) if total > 0 else 0

        return {
            "date": str(settings.now_ist().date()),
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "capital": self.risk_manager.capital,
            "is_paper": self.order_manager.is_paper,
            "strategy": self.strategy.name,
            "trades": [
                {
                    "symbol": o.symbol,
                    "signal": o.signal.value,
                    "entry": o.executed_price,
                    "pnl": o.pnl,
                    "reason": o.reason,
                }
                for o in orders
            ],
        }

    def _print_daily_report(self, report: dict):
        """Print a formatted daily report to console."""
        mode = "PAPER" if report["is_paper"] else "LIVE"
        pnl = report["total_pnl"]
        pnl_symbol = "+" if pnl >= 0 else ""

        logger.info("─" * 50)
        logger.info(f"  [{mode}] DAILY REPORT — {report['date']}")
        logger.info(f"  Strategy: {report['strategy']}")
        logger.info("─" * 50)
        logger.info(f"  Total Trades:  {report['total_trades']}")
        logger.info(f"  Wins:          {report['wins']}")
        logger.info(f"  Losses:        {report['losses']}")
        logger.info(f"  Win Rate:      {report['win_rate']:.1f}%")
        logger.info(f"  Total P&L:     Rs {pnl_symbol}{pnl:.2f}")
        logger.info(f"  Capital:       Rs {report['capital']:,.2f}")
        logger.info("─" * 50)

        for t in report["trades"]:
            pnl_str = f"Rs {'+' if t['pnl'] >= 0 else ''}{t['pnl']:.2f}"
            logger.info(f"  {t['signal']} {t['symbol']} @ {t['entry']:.2f} → {pnl_str}")

        logger.info("─" * 50)

    # ── Utility Methods ──

    def _wait_until(self, time_str: str, label: str):
        """Wait until a specific time (HH:MM format)."""
        target = self._parse_time(time_str)
        now = settings.now_ist()

        if now >= target:
            return

        wait_seconds = (target - now).total_seconds()
        logger.info(f"Waiting {wait_seconds:.0f}s for {label} ({time_str})...")

        while settings.now_ist() < target and self.running:
            time.sleep(1)

    def _parse_time(self, time_str: str) -> datetime:
        """Parse 'HH:MM' string to today's datetime in IST."""
        h, m = map(int, time_str.split(":"))
        return settings.now_ist().replace(hour=h, minute=m, second=0, microsecond=0, tzinfo=settings.IST)

    def _get_interval_seconds(self) -> int:
        """Convert timeframe setting to seconds."""
        intervals = {
            "minute": 60,
            "3minute": 180,
            "5minute": 300,
            "15minute": 900,
            "30minute": 1800,
            "60minute": 3600,
        }
        return intervals.get(settings.TIMEFRAME, 300)

    def _recover_orphaned_positions(self):
        """Recover open positions from a previous crashed session."""
        try:
            orphaned = self.db.get_open_positions()
            if not orphaned:
                return

            logger.warning(f"Found {len(orphaned)} orphaned positions from previous session")
            self.notifier.send(f"⚠️ Found {len(orphaned)} orphaned positions — attempting recovery")

            for row in orphaned:
                symbol = row["symbol"]
                logger.warning(
                    f"  Orphaned: {row['signal']} {symbol} qty={row['quantity']} "
                    f"entry={row['entry_price']:.2f}"
                )

            # Clear from DB — positions are either already closed by broker (intraday MIS)
            # or need manual intervention
            self.db.clear_open_positions()
            logger.info("Orphaned positions cleared from recovery table")
        except Exception as e:
            logger.error(f"Crash recovery failed: {e}")

    def _shutdown_handler(self, signum, frame):
        """Handle shutdown signals gracefully — force close positions immediately."""
        if self._shutting_down:
            return  # Prevent re-entrant calls
        self._shutting_down = True
        logger.warning("Shutdown signal received — closing positions...")
        self.running = False
        try:
            self._end_of_day()
        except Exception as e:
            logger.error(f"Error during emergency shutdown: {e}")

    def _cleanup(self):
        """Clean up resources."""
        if self.ticker:
            self.ticker.stop()
        logger.info("Bot shutdown complete")


def main():
    parser = argparse.ArgumentParser(description="Intraday Trading Bot")
    parser.add_argument("--live", action="store_true", help="Run in live trading mode")
    parser.add_argument("--paper", action="store_true", help="Run in paper trading mode")
    args = parser.parse_args()

    mode = None
    if args.live:
        mode = "live"
    elif args.paper:
        mode = "paper"

    bot = TradingBot(mode=mode)
    bot.run()


if __name__ == "__main__":
    main()
