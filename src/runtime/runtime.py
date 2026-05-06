"""
Runtime
───────
Drives the trading day on a fully-wired :class:`BotContext`:

  - waits for market open
  - collects opening range
  - runs the per-cycle scan / signal / risk / order pipeline
  - manages wind-down phase (no new entries, manage exits)
  - delegates EOD to :class:`EODManager` via the ``finally`` block so
    the same path covers natural exit, signal, and crash.

Signal handlers are signal-safe: they only flip ``ctx.running`` /
``ctx.shutting_down`` and write to stderr. All real work runs on the
main thread.
"""

from __future__ import annotations

import signal as sig
import sys
import time
from datetime import datetime, timedelta

from config import settings
from src.data.websocket import TickerManager
from src.indicators.indicators import add_all_indicators, drop_incomplete_last_bar
from src.indicators.market_regime import detect_regime
from src.strategy.base import Signal
from src.strategy.orb import ORBStrategy
from src.strategy.orchestrator import StrategyOrchestrator
from src.utils import journal, kill_switch
from src.utils.audit import audit
from src.utils.logger import logger

from src.runtime.context import BotContext
from src.runtime.eod import EODManager


_INTERVALS = {
    "minute": 60,
    "3minute": 180,
    "5minute": 300,
    "15minute": 900,
    "30minute": 1800,
    "60minute": 3600,
}


def _interval_seconds() -> int:
    return _INTERVALS.get(settings.TIMEFRAME, 300)


def _parse_time(time_str: str) -> datetime:
    h, m = map(int, time_str.split(":"))
    return settings.now_ist().replace(
        hour=h, minute=m, second=0, microsecond=0, tzinfo=settings.IST
    )


class Runtime:
    """Drives one trading day on a populated BotContext."""

    def __init__(self, ctx: BotContext):
        self.ctx = ctx
        self.eod = EODManager(ctx)

    # ── Public entry ────────────────────────────────────────────────────

    def run(self) -> None:
        ctx = self.ctx
        ctx.running = True

        sig.signal(sig.SIGINT, self._shutdown_handler)
        sig.signal(sig.SIGTERM, self._shutdown_handler)

        try:
            self._wait_until(settings.MARKET_OPEN, "market open")
            self._fetch_vix()
            self._scan_stocks()
            self._start_websocket()
            self._collect_opening_range()
            self._trading_loop()
            self.eod.run()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            ctx.notifier.send(f"🚨 Bot crashed: {e}")
        finally:
            ctx.running = False
            # Cover signal / exception paths that bypass the explicit
            # eod.run() above. EODManager has its own idempotency guard
            # (ctx.eod_done) so a clean run won't double-execute.
            if not ctx.eod_done and ctx.position_manager is not None:
                try:
                    self.eod.run()
                except Exception as e:
                    logger.error(f"Error during shutdown EOD: {e}")
            self._cleanup()

    # ── Pre-loop steps ──────────────────────────────────────────────────

    def _fetch_vix(self) -> None:
        ctx = self.ctx
        if not ctx.market_data or not getattr(settings, "VOLATILITY_SCALING_ENABLED", False):
            return
        try:
            vix_data = ctx.market_data.get_ltp(["INDIA VIX"], exchange="NSE")
            if "INDIA VIX" in vix_data:
                ctx.risk_manager.set_vix_level(vix_data["INDIA VIX"])
            else:
                logger.warning("Could not fetch India VIX — using default sizing")
        except Exception as e:
            logger.warning(f"VIX fetch failed: {e} — using default sizing")

    def _scan_stocks(self) -> None:
        ctx = self.ctx
        if ctx.daily_plan and ctx.daily_plan.watchlist:
            ctx.todays_watchlist = list(ctx.daily_plan.watchlist)
            logger.info(f"[PLAN] Using plan watchlist ({len(ctx.todays_watchlist)} symbols)")
        elif ctx.scanner:
            ctx.todays_watchlist = ctx.scanner.scan()
        else:
            ctx.todays_watchlist = settings.WATCHLIST[:5]

        if not ctx.todays_watchlist:
            ctx.todays_watchlist = settings.WATCHLIST[:5]

        if ctx.market_data:
            for symbol in ctx.todays_watchlist:
                try:
                    token = ctx.market_data.get_instrument_token(symbol)
                    ctx.instrument_tokens[symbol] = token
                    ctx.token_to_symbol[token] = symbol
                except Exception as e:
                    logger.warning(f"Could not get token for {symbol}: {e}")

        logger.info(f"Today's watchlist: {ctx.todays_watchlist}")

    def _start_websocket(self) -> None:
        ctx = self.ctx
        if not ctx.kite or not ctx.instrument_tokens:
            return
        # WebSocket doesn't work with enctoken auth — skip to avoid
        # infinite reconnect spam. The polling loop handles exits fine.
        if not ctx.kite.access_token:
            logger.info("WebSocket skipped (enctoken auth — using polling fallback)")
            return
        try:
            ctx.ticker = TickerManager(
                api_key=settings.KITE_API_KEY,
                access_token=ctx.kite.access_token,
            )
            tokens = list(ctx.instrument_tokens.values())
            ctx.ticker.subscribe(tokens, mode="quote")
            ctx.ticker.on_tick(self._on_tick)
            ctx.ticker.on_order_update(ctx.order_manager.handle_order_update)
            ctx.ticker.start(threaded=True)
            logger.info(f"WebSocket started — monitoring {len(tokens)} instruments")
        except Exception as e:
            logger.warning(f"WebSocket start failed: {e} — using polling fallback")

    def _on_tick(self, ticks: list[dict]) -> None:
        ctx = self.ctx
        for tick in ticks:
            token = tick.get("instrument_token")
            symbol = ctx.token_to_symbol.get(token)
            if not symbol:
                continue
            price = tick.get("last_price")
            if price is None:
                continue
            pos = ctx.position_manager.get_position(symbol)
            if pos:
                exit_reason = ctx.position_manager._should_exit(pos, price)
                if exit_reason:
                    ctx.position_manager.pending_exits.put(
                        (pos.order_id, price, exit_reason)
                    )

    def _collect_opening_range(self) -> None:
        ctx = self.ctx
        needs_orb = isinstance(ctx.strategy, ORBStrategy) or isinstance(
            ctx.strategy, StrategyOrchestrator
        )
        if not needs_orb:
            logger.info("Strategy doesn't need opening range, skipping...")
            self._wait_until(settings.TRADING_START, "trading start")
            return

        orb_minutes = settings.ORB_PERIOD_MINUTES
        orb_end_time = _parse_time(settings.MARKET_OPEN) + timedelta(minutes=orb_minutes)
        orb_end_str = orb_end_time.strftime("%H:%M")

        logger.info(f"Collecting opening range ({orb_minutes} min)...")
        self._wait_until(orb_end_str, "opening range complete")

        if ctx.market_data:
            orb_strat = ctx.strategy
            if isinstance(ctx.strategy, StrategyOrchestrator):
                orb_strat = ctx.strategy.orb_strategy

            for symbol in ctx.todays_watchlist:
                try:
                    orb = ctx.market_data.get_opening_range(symbol, minutes=orb_minutes)
                    if orb and orb_strat:
                        orb_strat.set_opening_range(
                            symbol, orb["high"], orb["low"], orb["open"]
                        )
                    else:
                        logger.warning(f"No opening range data for {symbol}")
                except Exception as e:
                    logger.error(f"Error getting opening range for {symbol}: {e}")

    # ── Main loop ───────────────────────────────────────────────────────

    def _trading_loop(self) -> None:
        ctx = self.ctx
        logger.info("=" * 40)
        logger.info("  TRADING LOOP STARTED")
        logger.info("=" * 40)

        interval_seconds = _interval_seconds()
        reconcile_every = getattr(settings, "BROKER_RECONCILE_CYCLES", 0)
        cycle_count = 0

        while ctx.running:
            now = settings.now_ist()

            if kill_switch.is_engaged():
                reason = kill_switch.reason() or "engaged"
                logger.error(f"[KILL_SWITCH] Halting trading loop ({reason}).")
                audit("kill_switch_triggered", phase="loop", reason=reason)
                ctx.notifier.send(f"🛑 Kill-switch engaged: {reason}. Flattening.")
                ctx.running = False
                break

            stop_time = _parse_time(settings.STOP_NEW_TRADES)
            square_off_time = _parse_time(settings.FORCE_SQUARE_OFF)
            loop_start = time.time()

            if now >= square_off_time:
                logger.info(
                    f"Square-off time reached (now={now.strftime('%H:%M:%S')} "
                    f">= {settings.FORCE_SQUARE_OFF})"
                )
                break
            if now >= stop_time:
                if ctx.position_manager.get_position_count() == 0:
                    logger.info("Trading window closed, no open positions — ending.")
                    break
                self._run_wind_down_cycle()
                elapsed = time.time() - loop_start
                sleep_time = max(0, interval_seconds - elapsed)
                if sleep_time > 0 and ctx.running:
                    time.sleep(sleep_time)
                continue

            try:
                self._run_single_cycle()
            except Exception as e:
                logger.error(f"Error in trading cycle: {e}")

            cycle_count += 1
            if (
                ctx.mode == "live"
                and reconcile_every > 0
                and cycle_count % reconcile_every == 0
                and ctx.kite
            ):
                try:
                    report = ctx.order_manager.reconcile_with_broker()
                    if not report.get("clean", True):
                        logger.warning(
                            "[RECONCILE] Drift mid-session — pausing new trades."
                        )
                        ctx.notifier.send(f"⚠️ Broker drift: {report}")
                        ctx.running = False
                except Exception as e:
                    logger.error(f"Periodic reconcile failed: {e}")

            elapsed = time.time() - loop_start
            sleep_time = max(0, interval_seconds - elapsed)
            if sleep_time > 0 and ctx.running:
                time.sleep(sleep_time)

    def _run_wind_down_cycle(self) -> None:
        ctx = self.ctx
        current_prices = {}
        if ctx.market_data:
            try:
                current_prices = ctx.market_data.get_ltp(ctx.todays_watchlist)
            except Exception as e:
                logger.error(f"[WIND-DOWN] Error fetching prices: {e}")
                return

        ctx.position_manager.check_exits(current_prices)

        for order in ctx.order_manager.orders:
            if not order.is_open and order.order_id not in ctx.logged_order_ids:
                ctx.db.log_trade(order)
                ctx.risk_manager.record_trade_result(
                    order.pnl,
                    symbol=order.symbol,
                    exit_reason=getattr(order, "exit_reason", None),
                )
                ctx.risk_manager.update_capital(ctx.risk_manager.capital + order.pnl)
                tracker = getattr(ctx.strategy, "tracker", None)
                if tracker is not None:
                    dir_key = ctx.last_dir_regime.get(order.symbol, "UNKNOWN")
                    vol_key = ctx.last_vol_regime.get(order.symbol, "NORMAL")
                    tracker.record(order.strategy, dir_key, vol_key, order.pnl)
                ctx.logged_order_ids.add(order.order_id)

        unrealized = ctx.position_manager.get_unrealized_pnl(current_prices)
        realized = ctx.order_manager.get_todays_pnl()
        ctx.risk_manager.set_unrealized_pnl(unrealized)
        ctx.risk_manager.update_intraday_equity(realized, unrealized)

        positions = ctx.position_manager.get_position_count()
        logger.info(
            f"[WIND-DOWN] Open: {positions} | "
            f"Realized P&L: Rs {realized:+.2f} | "
            f"Unrealized: Rs {unrealized:+.2f}"
        )

    def _run_single_cycle(self) -> None:
        ctx = self.ctx
        now_str = settings.now_ist().strftime("%H:%M")
        watchlist_str = ", ".join(ctx.todays_watchlist) if ctx.todays_watchlist else "(none)"
        logger.info(f"── {now_str} | Watching: {watchlist_str} ──")

        current_prices = {}
        if ctx.market_data:
            try:
                current_prices = ctx.market_data.get_ltp(ctx.todays_watchlist)
            except Exception as e:
                logger.error(f"Error fetching prices: {e}")
                return

        ctx.position_manager.check_exits(current_prices)

        for order in ctx.order_manager.orders:
            if not order.is_open and order.order_id not in ctx.logged_order_ids:
                ctx.db.log_trade(order)
                ctx.risk_manager.record_trade_result(
                    order.pnl,
                    symbol=order.symbol,
                    exit_reason=getattr(order, "exit_reason", None),
                )
                ctx.risk_manager.update_capital(ctx.risk_manager.capital + order.pnl)
                tracker = getattr(ctx.strategy, "tracker", None)
                if tracker is not None:
                    dir_key = ctx.last_dir_regime.get(order.symbol, "UNKNOWN")
                    vol_key = ctx.last_vol_regime.get(order.symbol, "NORMAL")
                    tracker.record(order.strategy, dir_key, vol_key, order.pnl)
                ctx.logged_order_ids.add(order.order_id)

        unrealized = ctx.position_manager.get_unrealized_pnl(current_prices)
        realized = ctx.order_manager.get_todays_pnl()
        ctx.risk_manager.set_unrealized_pnl(unrealized)
        ctx.risk_manager.update_intraday_equity(realized, unrealized)

        risk_status = ctx.risk_manager.get_status()
        if risk_status["is_paused"]:
            return

        regime = None
        for symbol in ctx.todays_watchlist:
            if ctx.position_manager.has_position(symbol):
                continue

            try:
                df = ctx.market_data.get_todays_candles(
                    symbol, interval=settings.TIMEFRAME
                )
                if df.empty or len(df) < 5:
                    continue

                df = drop_incomplete_last_bar(df, _interval_seconds())
                if df.empty or len(df) < 5:
                    continue

                df = add_all_indicators(df)

                df_htf = None
                regime = None
                vol_regime = None

                if getattr(settings, "ENABLE_REGIME_DETECTION", False):
                    df_htf = ctx.market_data.get_htf_data(
                        symbol, interval="15minute", days=5
                    )
                    df_htf = drop_incomplete_last_bar(df_htf, 15 * 60)
                    if not df_htf.empty and len(df_htf) >= 5:
                        df_htf = add_all_indicators(df_htf)
                        regime = detect_regime(df_htf)

                if getattr(settings, "ENABLE_VOLATILITY_REGIME", False):
                    try:
                        from src.indicators.market_regime import detect_volatility_regime
                        vol_regime = detect_volatility_regime(df)
                    except Exception:
                        vol_regime = None

                ctx.last_dir_regime[symbol] = regime.value if regime is not None else "UNKNOWN"
                ctx.last_vol_regime[symbol] = vol_regime.value if vol_regime is not None else "NORMAL"

                try:
                    signal = ctx.strategy.analyze(
                        df, symbol, df_htf=df_htf, regime=regime, vol_regime=vol_regime
                    )
                except TypeError:
                    signal = ctx.strategy.analyze(df, symbol, df_htf=df_htf, regime=regime)
                if signal.signal == Signal.HOLD:
                    logger.debug(
                        f"[SIGNAL] {symbol} -> HOLD | "
                        f"strategy={signal.strategy} | reason={signal.reason}"
                    )
                    continue

                # Daily-plan bias filter
                if ctx.daily_plan is not None:
                    if not ctx.daily_plan.allows_direction(symbol, signal.signal.value):
                        bias = ctx.daily_plan.get_bias(symbol)
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

                approved = ctx.risk_manager.evaluate(signal)
                if approved is None:
                    logger.debug(
                        f"[RISK] {symbol} -> REJECTED | "
                        f"signal={signal.signal.value} | reason={signal.reason}"
                    )
                    continue

                order = ctx.order_manager.place_order(approved)
                if order:
                    ctx.position_manager.add_position(order)
                    try:
                        ctx.strategy.mark_signal_executed(approved)
                    except Exception as e:
                        logger.debug(f"mark_signal_executed failed: {e}")
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
                        bias=ctx.daily_plan.get_bias(symbol) if ctx.daily_plan else None,
                        conviction=ctx.daily_plan.conviction_by_symbol.get(symbol) if ctx.daily_plan else None,
                    )
                    ctx.notifier.send_trade_alert(
                        action=signal.signal.value,
                        symbol=signal.symbol,
                        price=signal.price,
                        quantity=signal.quantity,
                        stop_loss=signal.stop_loss,
                        target=signal.target,
                        reason=signal.reason,
                        is_paper=ctx.order_manager.is_paper,
                    )

            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")

        pnl = ctx.order_manager.get_todays_pnl()
        trades = ctx.order_manager.get_todays_trade_count()
        unrealized = ctx.position_manager.get_unrealized_pnl(current_prices)

        open_positions = ctx.position_manager.open_positions
        if open_positions:
            open_str = ", ".join(
                f"{p.symbol}({'↑' if p.signal == Signal.BUY else '↓'}@{p.executed_price:.0f})"
                for p in open_positions
            )
        else:
            open_str = "none"

        logger.info(
            f"Trades: {trades}/{settings.MAX_TRADES_PER_DAY} | "
            f"Holding: {open_str} | "
            f"Realized: ₹{pnl:+.2f} | "
            f"Unrealized: ₹{unrealized:+.2f}"
            + (f" | Regime: {regime.value}" if regime else "")
        )

    # ── Lifecycle helpers ───────────────────────────────────────────────

    def _wait_until(self, time_str: str, label: str) -> None:
        ctx = self.ctx
        target = _parse_time(time_str)
        now = settings.now_ist()
        if now >= target:
            return
        wait_seconds = (target - now).total_seconds()
        logger.info(f"Waiting {wait_seconds:.0f}s for {label} ({time_str})...")
        while settings.now_ist() < target and ctx.running:
            time.sleep(1)

    def _shutdown_handler(self, signum, frame):
        """Signal-safe handler — flips flags only.

        sqlite writes, telegram POSTs, and git subprocesses can deadlock
        or re-enter locks held by the main thread. We only flip flags;
        the trading loop sees ``ctx.running = False`` and exits, then
        ``run()``'s finally block runs EOD on the main thread.
        """
        ctx = self.ctx
        if ctx.shutting_down:
            return
        ctx.shutting_down = True
        ctx.running = False
        try:
            sys.stderr.write(
                f"\n[SHUTDOWN] signal {signum} received — winding down on main thread.\n"
            )
            sys.stderr.flush()
        except Exception:
            pass

    def _cleanup(self) -> None:
        ctx = self.ctx
        if ctx.ticker:
            ctx.ticker.stop()
        audit("shutdown", mode=ctx.mode)
        logger.info("Bot shutdown complete")
