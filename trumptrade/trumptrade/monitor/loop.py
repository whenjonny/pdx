"""Main monitoring loop. Polls every venue once per tick, evaluates rules,
fires close orders. WebSocket upgrade is left to a subclass."""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import Callable
from trumptrade.monitor.position import OpenPosition
from trumptrade.monitor.store import PositionStore
from trumptrade.monitor.exit_rules import ExitRule, MarketContext, build_default_rules
from trumptrade.monitor.close_executor import CloseExecutor

log = logging.getLogger(__name__)

# A function that, given (venue_name, market_id), returns a Quote-like object
# with yes_bid / yes_ask / no_bid / no_ask / volume_24h / closes_at attributes.
QuoteFn = Callable[[str, str], object]

# Optional: a function returning {"category": str, "triggered_at": dt} when a
# walkback was detected; None if not.
WalkbackFn = Callable[[OpenPosition], dict | None]


class MonitorLoop:
    def __init__(
        self,
        store: PositionStore,
        rules: list[ExitRule] | None = None,
        executor: CloseExecutor | None = None,
        quote_fn: QuoteFn | None = None,
        walkback_fn: WalkbackFn | None = None,
    ):
        self.store = store
        self.rules = rules or build_default_rules()
        self.executor = executor or CloseExecutor(mode="alert")
        self.quote_fn = quote_fn or (lambda v, m: None)
        self.walkback_fn = walkback_fn or (lambda p: None)

    def run_once(self) -> dict:
        """One sweep over all open positions. Returns counters dict for
        observability."""
        stats = {"polled": 0, "closed": 0, "skipped_no_quote": 0, "errors": 0}
        for p in list(self.store.open_positions()):
            try:
                quote = self.quote_fn(p.venue, p.market_id)
            except Exception as e:
                log.warning("quote_fn error %s/%s: %s", p.venue, p.market_id, e)
                stats["errors"] += 1
                continue

            if quote is None:
                stats["skipped_no_quote"] += 1
                continue

            stats["polled"] += 1
            ctx = self._build_context(p, quote)
            mark = ctx.current_yes_bid if p.side == "BUY_YES" else ctx.current_no_bid
            p.current_mark = mark
            p.current_volume_24h = ctx.volume_24h
            p.last_polled_at = datetime.now(timezone.utc)
            self.store.update(p)

            for rule in self.rules:
                d = rule.evaluate(p, ctx)
                if d.should_close:
                    self.executor.close(p, price_hint=mark or p.entry_price,
                                        reason=d.reason, detail=d.detail)
                    if self.executor.mode in ("paper", "live"):
                        self.store.close(p.id, exit_price=mark or p.entry_price,
                                         reason=d.reason)
                    stats["closed"] += 1
                    break  # first triggered rule wins
        return stats

    def run_forever(self, interval_sec: int = 30) -> None:
        log.info("monitor loop started, interval=%ds, mode=%s", interval_sec, self.executor.mode)
        try:
            while True:
                stats = self.run_once()
                log.info("monitor tick: %s", stats)
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            log.info("monitor loop stopped by user")

    def _build_context(self, p: OpenPosition, quote) -> MarketContext:
        wb = self.walkback_fn(p)
        return MarketContext(
            current_yes_bid=getattr(quote, "yes_bid", None),
            current_yes_ask=getattr(quote, "yes_ask", None),
            current_no_bid=getattr(quote, "no_bid", None),
            current_no_ask=getattr(quote, "no_ask", None),
            last_trade=getattr(quote, "last", None),
            volume_24h=getattr(quote, "volume_24h", None),
            closes_at=getattr(getattr(quote, "market", None), "closes_at", None),
            walkback_triggered=wb is not None,
            walkback_category=(wb or {}).get("category"),
        )
