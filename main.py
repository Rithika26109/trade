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
from src.data.market_data import MarketData, resample_to_htf
from src.data.websocket import TickerManager
from src.execution.order_manager import Order, OrderManager, OrderStatus
from src.execution.position_manager import PositionManager
from src.indicators.indicators import add_all_indicators, drop_incomplete_last_bar
from src.indicators.market_regime import detect_regime, MarketRegime
from src.risk.risk_manager import RiskManager
from src.scanner.stock_scanner import StockScanner
from src.strategy.base import Signal, TradeSignal
from src.strategy.mean_reversion import MeanReversionStrategy
from src.strategy.orchestrator import StrategyOrchestrator
from src.strategy.orb import ORBStrategy
from src.strategy.pairs import PairsTradingStrategy
from src.strategy.rsi_ema import RSIEMAStrategy
from src.strategy.vwap_supertrend import VWAPSupertrendStrategy
from src.utils.db import TradeDB
from src.utils.logger import logger
from src.utils.notifier import Notifier
from src.utils.audit import audit
from src.utils.compliance import ComplianceError, startup_compliance_check
from src.utils import kill_switch
from src.utils import journal
from src.utils.plan_loader import load_plan, git_pull, DailyPlan


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
        # Phase 3C: last regime observed per symbol (for outcome attribution)
        self._last_dir_regime: dict[str, str] = {}
        self._last_vol_regime: dict[str, str] = {}
        # Today's Claude-Routine plan (None if missing/invalid — falls back
        # to static WATCHLIST + default settings caps).
        self.daily_plan: DailyPlan | None = None

    def setup(self):
        """Initialize all components."""
        logger.info("=" * 60)
        logger.info(f"  TRADING BOT STARTING — Mode: {self.mode.upper()}")
        logger.info("=" * 60)

        # ── Validate config ──
        settings.validate_config()

        # ── Pull the latest daily plan from the routines repo ──
        # Best-effort: a failed pull (offline, conflict) just means we use
        # whatever's already on disk — or no plan at all.
        git_pull()
        self.daily_plan = load_plan()
        if self.daily_plan:
            audit(
                "plan_loaded",
                date=self.daily_plan.date,
                symbols=self.daily_plan.watchlist,
                overrides=self.daily_plan.risk_overrides,
                lessons=self.daily_plan.lessons_applied,
            )

        # ── SEBI compliance gate (Phase 4) ──
        try:
            compliance = startup_compliance_check(self.mode)
        except ComplianceError as ce:
            logger.error(f"[COMPLIANCE] Halting: {ce}")
            audit("compliance_failed", error=str(ce), mode=self.mode)
            sys.exit(3)

        # ── Fail fast if kill-switch is already engaged ──
        if kill_switch.is_engaged():
            reason = kill_switch.reason() or "pre-existing kill-switch"
            logger.error(f"[KILL_SWITCH] engaged ({reason}) — refusing to start.")
            audit("kill_switch_triggered", phase="startup", reason=reason)
            sys.exit(4)

        audit("startup", compliance=compliance)

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
                logger.error(
                    "Auth failed — cannot run paper trading without market data. "
                    "Paper mode needs real-time prices; offline simulation is not supported."
                )
                self.notifier.send("Auth failed — bot cannot start without market data.")
                sys.exit(1)

        # ── Order & Position Management ──
        self.order_manager = OrderManager(self.kite, market_data=self.market_data)
        self.order_manager.is_paper = self.mode == "paper"
        self.position_manager = PositionManager(self.order_manager, db=self.db)
        self.risk_manager = RiskManager(self.order_manager, db=self.db)
        # Let RiskManager query circuit limits / prev-close from MarketData.
        self.risk_manager.market_data = self.market_data
        # Wire paper-mode capital callback for rejection simulation.
        self.order_manager._get_available_capital = lambda: self.risk_manager.capital

        # Apply daily-plan risk overrides (already clamped by plan_loader).
        if self.daily_plan and self.daily_plan.risk_overrides:
            self.risk_manager.apply_runtime_overrides(
                max_trades=self.daily_plan.risk_overrides.get("max_trades"),
                risk_per_trade_pct=self.daily_plan.risk_overrides.get("risk_per_trade_pct"),
                max_open_positions=self.daily_plan.risk_overrides.get("max_open_positions"),
            )

        # ── Crash Recovery ──
        self._recover_orphaned_positions()

        # ── Post-recovery broker reconciliation (live only) ──
        if self.mode == "live" and self.kite:
            report = self.order_manager.reconcile_with_broker()
            if not report.get("clean", True):
                logger.error(
                    "Broker reconciliation FAILED at startup. "
                    f"Details: {report}. Refusing to start trading until "
                    "positions are reconciled manually."
                )
                self.notifier.send(
                    f"🚨 Broker drift at startup — bot halting.\n{report}"
                )
                sys.exit(2)

        # ── Strategy Selection ──
        strategy_name = settings.STRATEGY
        if strategy_name == "ORB":
            self.strategy = ORBStrategy()
        elif strategy_name == "RSI_EMA":
            self.strategy = RSIEMAStrategy()
        elif strategy_name == "VWAP_SUPERTREND":
            self.strategy = VWAPSupertrendStrategy()
        elif strategy_name == "MEAN_REVERSION":
            self.strategy = MeanReversionStrategy()
        elif strategy_name == "PAIRS":
            self.strategy = PairsTradingStrategy(market_data=self.market_data)
        elif strategy_name == "MULTI":
            self.strategy = StrategyOrchestrator()
        else:
            logger.warning(f"Unknown strategy '{strategy_name}', defaulting to ORB")
            self.strategy = ORBStrategy()

        # Wire pairs strategy into orchestrator if market_data is available
        if isinstance(self.strategy, StrategyOrchestrator) and self.market_data:
            self.strategy.add_pairs_strategy(self.market_data)

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

            # ── Step 2: Fetch India VIX for volatility scaling ──
            self._fetch_vix()

            # ── Step 3: Scan for today's stocks ──
            self._scan_stocks()

            # ── Step 4: Start WebSocket for real-time exits ──
            self._start_websocket()

            # ── Step 5: Collect opening range ──
            self._collect_opening_range()

            # ── Step 6: Main trading loop ──
            self._trading_loop()

            # ── Step 7: End of day ──
            self._end_of_day()

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            self.notifier.send(f"🚨 Bot crashed: {e}")
        finally:
            self.running = False
            self._cleanup()

    def _fetch_vix(self):
        """Fetch India VIX for volatility-adjusted position sizing."""
        if not self.market_data or not getattr(settings, 'VOLATILITY_SCALING_ENABLED', False):
            return
        try:
            vix_data = self.market_data.get_ltp(["INDIA VIX"], exchange="NSE")
            if "INDIA VIX" in vix_data:
                self.risk_manager.set_vix_level(vix_data["INDIA VIX"])
            else:
                logger.warning("Could not fetch India VIX — using default sizing")
        except Exception as e:
            logger.warning(f"VIX fetch failed: {e} — using default sizing")

    def _start_websocket(self):
        """Start WebSocket for real-time stop-loss/target monitoring."""
        if not self.kite or not self.instrument_tokens:
            return
        # WebSocket doesn't work with enctoken auth — skip to avoid
        # infinite reconnect spam. The polling loop handles exits fine.
        if not self.kite.access_token:
            logger.info("WebSocket skipped (enctoken auth — using polling fallback)")
            return
        try:
            self.ticker = TickerManager(
                api_key=settings.KITE_API_KEY,
                access_token=self.kite.access_token,
            )
            tokens = list(self.instrument_tokens.values())
            self.ticker.subscribe(tokens, mode="quote")
            self.ticker.on_tick(self._on_tick)
            # Broker-side order state changes (SLM triggers, fills, rejects).
            self.ticker.on_order_update(self.order_manager.handle_order_update)
            self.ticker.start(threaded=True)
            logger.info(f"WebSocket started — monitoring {len(tokens)} instruments")
        except Exception as e:
            logger.warning(f"WebSocket start failed: {e} — using polling fallback")

    def _on_tick(self, ticks: list[dict]):
        """Real-time tick handler for immediate stop-loss/target exits."""
        for tick in ticks:
            token = tick.get("instrument_token")
            symbol = self.token_to_symbol.get(token)
            if not symbol:
                continue

            price = tick.get("last_price")
            if price is None:
                continue

            # Check if any open position needs immediate exit
            pos = self.position_manager.get_position(symbol)
            if pos:
                exit_reason = self.position_manager._should_exit(pos, price)
                if exit_reason:
                    # Queue the exit — don't process in WebSocket thread
                    self.position_manager.pending_exits.put(
                        (pos.order_id, price, exit_reason)
                    )

    def _scan_stocks(self):
        """Select today's stocks to trade."""
        # Plan wins over scanner: if the morning routine picked a watchlist,
        # use it verbatim. This is the whole point of the Routines integration.
        if self.daily_plan and self.daily_plan.watchlist:
            self.todays_watchlist = list(self.daily_plan.watchlist)
            logger.info(f"[PLAN] Using plan watchlist ({len(self.todays_watchlist)} symbols)")
        elif self.scanner:
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
        # ORB data needed for ORB strategy or MULTI mode (which includes ORB)
        needs_orb = isinstance(self.strategy, ORBStrategy) or isinstance(self.strategy, StrategyOrchestrator)
        if not needs_orb:
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
            # Get the ORB strategy instance (either direct or from orchestrator)
            orb_strat = self.strategy
            if isinstance(self.strategy, StrategyOrchestrator):
                orb_strat = self.strategy.orb_strategy

            for symbol in self.todays_watchlist:
                try:
                    orb = self.market_data.get_opening_range(symbol, minutes=orb_minutes)
                    if orb and orb_strat:
                        orb_strat.set_opening_range(symbol, orb["high"], orb["low"], orb["open"])
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
        reconcile_every = getattr(settings, "BROKER_RECONCILE_CYCLES", 0)
        cycle_count = 0

        while self.running:
            now = settings.now_ist()

            # ── Kill-switch: halt new entries and flatten positions ──
            if kill_switch.is_engaged():
                reason = kill_switch.reason() or "engaged"
                logger.error(f"[KILL_SWITCH] Halting trading loop ({reason}).")
                audit("kill_switch_triggered", phase="loop", reason=reason)
                self.notifier.send(f"🛑 Kill-switch engaged: {reason}. Flattening.")
                self.running = False
                break

            # Check if we should stop trading
            stop_time = self._parse_time(settings.STOP_NEW_TRADES)
            square_off_time = self._parse_time(settings.FORCE_SQUARE_OFF)
            loop_start = time.time()

            if now >= square_off_time:
                logger.info(
                    f"Square-off time reached (now={now.strftime('%H:%M:%S')} "
                    f">= {settings.FORCE_SQUARE_OFF})"
                )
                break
            if now >= stop_time:
                # Wind-down phase: no new trades, but keep managing open positions
                if self.position_manager.get_position_count() == 0:
                    logger.info("Trading window closed, no open positions — ending.")
                    break
                self._run_wind_down_cycle()
                elapsed = time.time() - loop_start
                sleep_time = max(0, interval_seconds - elapsed)
                if sleep_time > 0 and self.running:
                    time.sleep(sleep_time)
                continue

            try:
                self._run_single_cycle()
            except Exception as e:
                logger.error(f"Error in trading cycle: {e}")

            # Periodic broker reconciliation (live only). If drift is
            # detected, halt new entries but let existing positions run.
            cycle_count += 1
            if (
                self.mode == "live"
                and reconcile_every > 0
                and cycle_count % reconcile_every == 0
                and self.kite
            ):
                try:
                    report = self.order_manager.reconcile_with_broker()
                    if not report.get("clean", True):
                        logger.warning(
                            "[RECONCILE] Drift mid-session — pausing new trades."
                        )
                        self.notifier.send(f"⚠️ Broker drift: {report}")
                        self.running = False  # Stop opening new positions
                except Exception as e:
                    logger.error(f"Periodic reconcile failed: {e}")

            # Wait for next candle
            elapsed = time.time() - loop_start
            sleep_time = max(0, interval_seconds - elapsed)
            if sleep_time > 0 and self.running:
                time.sleep(sleep_time)

    def _run_wind_down_cycle(self):
        """Wind-down phase: manage existing positions (trailing stops, exits) but no new trades."""
        current_prices = {}
        if self.market_data:
            try:
                current_prices = self.market_data.get_ltp(self.todays_watchlist)
            except Exception as e:
                logger.error(f"[WIND-DOWN] Error fetching prices: {e}")
                return

        # Check exits (stop-loss / target / trailing)
        self.position_manager.check_exits(current_prices)

        # Log any closed trades
        for order in self.order_manager.orders:
            if not order.is_open and order.order_id not in self._logged_order_ids:
                self.db.log_trade(order)
                self.risk_manager.record_trade_result(order.pnl)
                self.risk_manager.update_capital(self.risk_manager.capital + order.pnl)
                tracker = getattr(self, "_regime_perf_tracker", None)
                if tracker is not None:
                    dir_key = self._last_dir_regime.get(order.symbol, "UNKNOWN")
                    vol_key = self._last_vol_regime.get(order.symbol, "NORMAL")
                    tracker.record(order.strategy, dir_key, vol_key, order.pnl)
                self._logged_order_ids.add(order.order_id)

        # Update P&L tracking
        unrealized = self.position_manager.get_unrealized_pnl(current_prices)
        realized = self.order_manager.get_todays_pnl()
        self.risk_manager.set_unrealized_pnl(unrealized)
        self.risk_manager.update_intraday_equity(realized, unrealized)

        positions = self.position_manager.get_position_count()
        logger.info(
            f"[WIND-DOWN] Open: {positions} | "
            f"Realized P&L: Rs {realized:+.2f} | "
            f"Unrealized: Rs {unrealized:+.2f}"
        )

    def _run_single_cycle(self):
        """Execute one cycle of the trading loop with multi-TF analysis and regime detection."""
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
        # (JSONL exit event is now emitted inside order_manager.close_position
        #  so it's never lost even if the bot crashes between close and here.)
        for order in self.order_manager.orders:
            if not order.is_open and order.order_id not in self._logged_order_ids:
                self.db.log_trade(order)
                self.risk_manager.record_trade_result(order.pnl)
                self.risk_manager.update_capital(self.risk_manager.capital + order.pnl)
                # Phase 3C: feed regime-perf tracker
                tracker = getattr(self.strategy, "tracker", None)
                if tracker is not None:
                    dir_key = self._last_dir_regime.get(order.symbol, "UNKNOWN")
                    vol_key = self._last_vol_regime.get(order.symbol, "NORMAL")
                    tracker.record(order.strategy, dir_key, vol_key, order.pnl)
                self._logged_order_ids.add(order.order_id)

        # ── Update unrealized P&L and intraday drawdown tracking ──
        unrealized = self.position_manager.get_unrealized_pnl(current_prices)
        realized = self.order_manager.get_todays_pnl()
        self.risk_manager.set_unrealized_pnl(unrealized)
        self.risk_manager.update_intraday_equity(realized, unrealized)

        # ── Check risk status ──
        risk_status = self.risk_manager.get_status()
        if risk_status["is_paused"]:
            return

        # ── Analyze each stock for signals ──
        regime = None
        for symbol in self.todays_watchlist:
            # Skip if we already have a position
            if self.position_manager.has_position(symbol):
                continue

            try:
                # Fetch latest candle data (primary timeframe)
                df = self.market_data.get_todays_candles(
                    symbol, interval=settings.TIMEFRAME
                )
                if df.empty or len(df) < 5:
                    continue

                # Drop partial trailing bar so indicators only see closed
                # candles — matches backtest (`next()` fires on bar close).
                df = drop_incomplete_last_bar(df, self._get_interval_seconds())
                if df.empty or len(df) < 5:
                    continue

                # Calculate indicators on primary timeframe
                df = add_all_indicators(df)

                # ── Multi-timeframe analysis ──
                df_htf = None
                regime = None
                vol_regime = None

                if getattr(settings, 'ENABLE_REGIME_DETECTION', False):
                    # Fetch multi-day 15-min history (not just today's
                    # resampled candles) so EMA/Supertrend warm-up matches
                    # backtest. Cached once per day inside MarketData.
                    df_htf = self.market_data.get_htf_data(
                        symbol, interval="15minute", days=5
                    )
                    df_htf = drop_incomplete_last_bar(df_htf, 15 * 60)
                    if not df_htf.empty and len(df_htf) >= 5:
                        df_htf = add_all_indicators(df_htf)
                        regime = detect_regime(df_htf)

                # Phase 3C: volatility regime from intraday df
                if getattr(settings, "ENABLE_VOLATILITY_REGIME", False):
                    try:
                        from src.indicators.market_regime import detect_volatility_regime
                        vol_regime = detect_volatility_regime(df)
                    except Exception:
                        vol_regime = None

                # Attribution cache for regime-perf tracker
                self._last_dir_regime[symbol] = regime.value if regime is not None else "UNKNOWN"
                self._last_vol_regime[symbol] = vol_regime.value if vol_regime is not None else "NORMAL"

                # Get strategy signal with multi-TF context (orchestrator accepts vol_regime)
                try:
                    signal = self.strategy.analyze(
                        df, symbol, df_htf=df_htf, regime=regime, vol_regime=vol_regime
                    )
                except TypeError:
                    signal = self.strategy.analyze(df, symbol, df_htf=df_htf, regime=regime)
                if signal.signal == Signal.HOLD:
                    logger.debug(
                        f"[SIGNAL] {symbol} -> HOLD | "
                        f"strategy={signal.strategy} | reason={signal.reason}"
                    )
                    continue

                # ── Daily-plan bias filter ──
                # If the pre-market routine flagged this symbol long-only,
                # short-only, or avoid, veto signals that go the wrong way.
                if self.daily_plan is not None:
                    if not self.daily_plan.allows_direction(symbol, signal.signal.value):
                        bias = self.daily_plan.get_bias(symbol)
                        logger.info(
                            f"[PLAN] Vetoed {signal.signal.value} on {symbol} "
                            f"(bias={bias})"
                        )
                        journal.emit_event(
                            "skipped_due_to_bias",
                            symbol=symbol,
                            signal=signal.signal.value,
                            bias=bias,
                            price=signal.price,
                            reason=signal.reason,
                        )
                        continue

                # Risk check + position sizing
                approved = self.risk_manager.evaluate(signal)
                if approved is None:
                    logger.debug(
                        f"[RISK] {symbol} -> REJECTED | "
                        f"signal={signal.signal.value} | reason={signal.reason}"
                    )
                    continue

                # Place the trade
                order = self.order_manager.place_order(approved)
                if order:
                    self.position_manager.add_position(order)
                    journal.emit_event(
                        "entry",
                        symbol=symbol,
                        signal=signal.signal.value,
                        strategy=signal.strategy,
                        price=approved.executed_price if hasattr(approved, "executed_price") else signal.price,
                        quantity=approved.quantity,
                        stop_loss=signal.stop_loss,
                        target=signal.target,
                        reason=signal.reason,
                        bias=self.daily_plan.get_bias(symbol) if self.daily_plan else None,
                        conviction=self.daily_plan.conviction_by_symbol.get(symbol) if self.daily_plan else None,
                    )
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
            + (f" | Regime: {regime.value}" if regime else "")
        )

    def _end_of_day(self):
        """End of day: square off all positions, generate report."""
        now = settings.now_ist()
        stop_time = self._parse_time(settings.STOP_NEW_TRADES)
        if now < stop_time and not self._shutting_down:
            logger.error(
                f"[BUG] _end_of_day called at {now.strftime('%H:%M:%S')} — "
                f"before STOP_NEW_TRADES ({settings.STOP_NEW_TRADES}). "
                f"Possible premature EOD. Investigate process signals."
            )
        logger.info("=" * 40)
        logger.info(f"  END OF DAY ({now.strftime('%H:%M:%S')} IST)")
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
        # (JSONL exit events already emitted by close_position; only DB + risk updates here.)
        for order in self.order_manager.orders:
            if not order.is_open and order.order_id not in self._logged_order_ids:
                self.db.log_trade(order)
                self.risk_manager.record_trade_result(order.pnl)
                self.risk_manager.update_capital(self.risk_manager.capital + order.pnl)
                self._logged_order_ids.add(order.order_id)
            elif order.is_open and order.order_id not in self._logged_order_ids:
                logger.error(
                    f"[EOD] {order.symbol} still open after square-off — "
                    f"broker close likely failed. Check manually."
                )
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

        # ── Commit journal + events to git so the EOD review routine
        # (scheduled for ~16:30 IST) picks up today's data. Best effort. ──
        try:
            import subprocess
            subprocess.run(
                ["python3", "scripts/eod_commit.py"],
                cwd=str(settings.BASE_DIR),
                timeout=45,
                check=False,
            )
        except Exception as e:
            logger.warning(f"[EOD] eod_commit.py failed: {e}")

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
        """Recover open positions from a previous crashed session.

        LIVE: reconstruct Order objects from the DB and inject them into
        order_manager and position_manager so that reconcile_with_broker()
        can diff against actual broker state.

        PAPER: no broker to check; just clear the stale DB rows.
        """
        try:
            orphaned = self.db.get_open_positions()
            if not orphaned:
                if self.mode == "paper" or not self.kite:
                    self.db.clear_open_positions()
                return

            logger.warning(
                f"Found {len(orphaned)} orphaned positions from previous session"
            )
            for row in orphaned:
                logger.warning(
                    f"  Orphaned: {row['signal']} {row['symbol']} "
                    f"qty={row['quantity']} entry={row['entry_price']:.2f}"
                )

            if self.mode == "paper" or not self.kite:
                # No broker to reconcile with — safe to drop stale rows.
                self.db.clear_open_positions()
                return

            # Live mode: reconstruct in-memory state from DB so that
            # reconcile_with_broker() can compare against actual broker positions.
            for row in orphaned:
                order = Order(
                    order_id=row["order_id"],
                    symbol=row["symbol"],
                    exchange=row.get("exchange", "NSE"),
                    signal=Signal(row["signal"]),
                    quantity=row["quantity"],
                    price=row["entry_price"],
                    stop_loss=row["stop_loss"],
                    target=row["target"],
                    order_type="MARKET",
                    status=OrderStatus.EXECUTED,
                    executed_price=row["entry_price"],
                    is_paper=bool(row.get("is_paper", 0)),
                    is_open=True,
                    reason=row.get("reason", ""),
                    strategy=row.get("strategy", ""),
                )
                self.order_manager.orders.append(order)
                self.position_manager.open_positions.append(order)
                logger.info(
                    f"Recovered position: {order.signal.value} {order.symbol} "
                    f"qty={order.quantity}"
                )

            logger.info("Live mode: broker reconciliation will verify state next.")
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
        audit("shutdown", mode=self.mode)
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
