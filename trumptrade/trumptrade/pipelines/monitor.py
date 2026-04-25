"""MonitorPipeline: ExitAgent -> OrderRouter (replaces the older
direct-write CloseExecutor path inside MonitorLoop)."""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from trumptrade.agents import ExitAgent, AgentContext
from trumptrade.orders.router import OrderRouter
from trumptrade.decisions import DecisionStore

log = logging.getLogger(__name__)


@dataclass
class MonitorTick:
    timestamp: datetime
    decisions: int = 0
    closed: int = 0
    rejected: int = 0
    errors: int = 0

    def summary(self) -> str:
        return (
            f"[monitor {self.timestamp.isoformat(timespec='seconds')}] "
            f"decisions={self.decisions} closed={self.closed} "
            f"rejected={self.rejected} errors={self.errors}"
        )


class MonitorPipeline:
    def __init__(
        self,
        exit_agent: ExitAgent,
        router: OrderRouter,
        ctx: AgentContext,
        decision_store: DecisionStore | None = None,
    ):
        self.exit_agent = exit_agent
        self.router = router
        self.ctx = ctx
        self.decision_store = decision_store

    def run_once(self) -> MonitorTick:
        tick = MonitorTick(timestamp=datetime.now(timezone.utc))

        # Refresh marks on every open position so the dashboard / report
        # see live unrealized P&L even when no exit fires this tick.
        if self.ctx.position_store is not None:
            for p in self.ctx.position_store.open_positions():
                try:
                    quote = self.exit_agent.quote_fn(p.venue, p.market_id)
                except Exception:
                    quote = None
                if quote is None:
                    continue
                if p.side == "BUY_YES":
                    mark = getattr(quote, "yes_bid", None) or getattr(quote, "last", None)
                else:
                    mark = getattr(quote, "no_bid", None) or getattr(quote, "last", None)
                if mark is None:
                    continue
                p.current_mark = mark
                p.current_volume_24h = getattr(quote, "volume_24h", None)
                p.last_polled_at = datetime.now(timezone.utc)
                self.ctx.position_store.update(p)

        try:
            decisions = self.exit_agent.tick(self.ctx)
        except Exception as e:
            log.exception("exit_agent.tick error: %s", e)
            tick.errors += 1
            return tick
        tick.decisions = len(decisions)

        if self.decision_store is not None and decisions:
            self.decision_store.record_many(decisions)

        if decisions:
            outcomes = self.router.route(decisions)
            for o in outcomes:
                if o.accepted:
                    tick.closed += 1
                else:
                    tick.rejected += 1
        return tick

    def run_forever(self, interval_sec: int = 30) -> None:
        log.info("monitor pipeline started, interval=%ds", interval_sec)
        try:
            while True:
                tick = self.run_once()
                log.info("%s", tick.summary())
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            log.info("monitor pipeline stopped by user")
