"""
EODManager
──────────
End-of-day shutdown sequence: square off positions, persist trade
results, generate the daily report, send Telegram summary, save daily
summary row, and trigger ``scripts/eod_commit.py`` so the journal +
metrics land in git for the post-close review routine.

Idempotent via ``ctx.eod_done`` — :meth:`Runtime.run` invokes this once
on the natural path AND from its ``finally`` block, so signal/exception
shutdowns also produce a report.
"""

from __future__ import annotations

import subprocess

from config import settings
from src.utils.logger import logger

from src.runtime.context import BotContext


def _parse_time(time_str: str):
    h, m = map(int, time_str.split(":"))
    return settings.now_ist().replace(
        hour=h, minute=m, second=0, microsecond=0, tzinfo=settings.IST
    )


class EODManager:
    """Runs the end-of-day shutdown / reporting sequence."""

    def __init__(self, ctx: BotContext):
        self.ctx = ctx

    def run(self) -> None:
        ctx = self.ctx
        if ctx.eod_done:
            return
        ctx.eod_done = True

        now = settings.now_ist()
        stop_time = _parse_time(settings.STOP_NEW_TRADES)
        if now < stop_time and not ctx.shutting_down:
            logger.error(
                f"[BUG] EOD called at {now.strftime('%H:%M:%S')} — "
                f"before STOP_NEW_TRADES ({settings.STOP_NEW_TRADES}). "
                f"Possible premature EOD. Investigate process signals."
            )
        logger.info("=" * 40)
        logger.info(f"  END OF DAY ({now.strftime('%H:%M:%S')} IST)")
        logger.info("=" * 40)

        # Square off open positions
        if ctx.position_manager.get_position_count() > 0:
            logger.info("Squaring off all open positions...")
            current_prices: dict = {}
            if ctx.market_data:
                try:
                    current_prices = ctx.market_data.get_ltp(ctx.todays_watchlist)
                except Exception:
                    pass
            ctx.position_manager.force_close_all(current_prices, "End of day square-off")

        # Persist remaining trades / capital adjustments
        for order in ctx.order_manager.orders:
            if not order.is_open and order.order_id not in ctx.logged_order_ids:
                ctx.db.log_trade(order)
                ctx.risk_manager.record_trade_result(
                    order.pnl,
                    symbol=order.symbol,
                    exit_reason=getattr(order, "exit_reason", None),
                )
                ctx.risk_manager.update_capital(ctx.risk_manager.capital + order.pnl)
                ctx.logged_order_ids.add(order.order_id)
            elif order.is_open and order.order_id not in ctx.logged_order_ids:
                logger.error(
                    f"[EOD] {order.symbol} still open after square-off — "
                    f"broker close likely failed. Check manually."
                )
        ctx.db.clear_open_positions()

        # Daily report
        report = self._generate_daily_report()
        self._print_daily_report(report)
        ctx.notifier.send_daily_report(report)

        ctx.db.save_daily_summary(
            total_trades=report["total_trades"],
            winning_trades=report["wins"],
            losing_trades=report["losses"],
            total_pnl=report["total_pnl"],
            max_drawdown=report.get("max_drawdown", 0),
            capital=ctx.risk_manager.capital,
            is_paper=ctx.order_manager.is_paper,
        )

        # Commit journal/events to git for the post-close review routine.
        try:
            subprocess.run(
                ["python3", "scripts/eod_commit.py"],
                cwd=str(settings.BASE_DIR),
                timeout=45,
                check=False,
            )
        except Exception as e:
            logger.warning(f"[EOD] eod_commit.py failed: {e}")

    def _generate_daily_report(self) -> dict:
        ctx = self.ctx
        orders = ctx.order_manager.orders
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
            "capital": ctx.risk_manager.capital,
            "is_paper": ctx.order_manager.is_paper,
            "strategy": ctx.strategy.name if ctx.strategy else "",
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

    @staticmethod
    def _print_daily_report(report: dict) -> None:
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
