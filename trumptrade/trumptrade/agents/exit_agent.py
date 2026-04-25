"""ExitAgent: wraps the monitor-layer exit rules and emits `close` decisions
for any open position whose rules trigger.

Driven by a tick (no external signal needed). Each open position is
evaluated once per call; the first triggered rule wins per position.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Callable, Optional
from trumptrade.agents.base import Agent, AgentContext, TradeDecision
from trumptrade.types import Signal
from trumptrade.monitor.exit_rules import (
    ExitRule, MarketContext, build_default_rules,
)


# Quote lookup signature: (venue, market_id) -> quote-like or None
QuoteFn = Callable[[str, str], object]
# Walkback lookup signature: (position) -> {"category": ...} or None
WalkbackFn = Callable[[object], Optional[dict]]


class ExitAgent(Agent):
    """Synthetic agent: doesn't take a real signal — invoke `tick()` with the
    monitoring system to convert open positions into close decisions.
    `analyze(signal, ctx)` is implemented for interface symmetry but ignores
    `signal`.
    """
    name = "exit"

    def __init__(
        self,
        rules: list[ExitRule] | None = None,
        quote_fn: Optional[QuoteFn] = None,
        walkback_fn: Optional[WalkbackFn] = None,
    ):
        self.rules = rules or build_default_rules()
        self.quote_fn = quote_fn or (lambda v, m: None)
        self.walkback_fn = walkback_fn or (lambda p: None)

    def analyze(self, signal: Signal, ctx: AgentContext) -> list[TradeDecision]:
        return self.tick(ctx)

    def tick(self, ctx: AgentContext) -> list[TradeDecision]:
        if ctx.position_store is None:
            return []
        decisions: list[TradeDecision] = []
        for p in ctx.position_store.open_positions():
            try:
                quote = self.quote_fn(p.venue, p.market_id)
            except Exception:
                quote = None
            mc = self._build_ctx(p, quote)

            for rule in self.rules:
                d = rule.evaluate(p, mc)
                if not d.should_close:
                    continue
                mark = (mc.current_yes_bid if p.side == "BUY_YES" else mc.current_no_bid) or p.entry_price
                close_side = "SELL_YES" if p.side == "BUY_YES" else "SELL_NO"
                decisions.append(TradeDecision(
                    action="close",
                    venue=p.venue,
                    market_id=p.market_id,
                    market_title=p.market_title,
                    side=close_side,
                    size_contracts=p.size_contracts,
                    price_limit=mark,
                    confidence=1.0,
                    rationale=f"exit_rule={rule.name}: {d.detail}",
                    agent_name=self.name,
                    target_position_id=p.id,
                    category=None,
                ))
                break
        return decisions

    def _build_ctx(self, position, quote) -> MarketContext:
        wb = self.walkback_fn(position)
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
