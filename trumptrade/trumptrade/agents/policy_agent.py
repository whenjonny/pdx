"""PolicyAgent: Trump policy signal -> open decisions on prediction markets.

Pipeline:
  signal -> classifier -> Classification (category, sentiment, confidence)
         -> for each venue carrying that category, search for matching markets
         -> emit `open` TradeDecision per market with side derived from sentiment

This is the core "Trump signal -> trade" agent. It REPLACES the older
basket-on-stocks path for prediction-market trading.
"""
from __future__ import annotations
from typing import Callable
from trumptrade.agents.base import Agent, AgentContext, TradeDecision
from trumptrade.types import Signal, Classification


# Classification helper: function (Signal, playbook) -> Classification
ClassifyFn = Callable[[Signal, dict], Classification]


def _sentiment_to_side(sentiment: str) -> str | None:
    """Map sentiment to YES/NO buy on a "policy will happen" market."""
    if sentiment == "hawkish":
        return "BUY_YES"
    if sentiment == "dovish":
        return "BUY_NO"
    return None


class PolicyAgent(Agent):
    name = "policy"

    def __init__(
        self,
        classify_fn: ClassifyFn,
        per_venue_market_limit: int = 5,
        default_size_contracts: int = 100,
        confidence_floor: float = 0.55,
    ):
        self.classify_fn = classify_fn
        self.per_venue_market_limit = per_venue_market_limit
        self.default_size_contracts = default_size_contracts
        self.confidence_floor = confidence_floor

    def analyze(self, signal: Signal, ctx: AgentContext) -> list[TradeDecision]:
        c = self.classify_fn(signal, ctx.playbook)
        if c.category == "unknown":
            return []
        eff = c.confidence * c.follow_through
        if eff < self.confidence_floor:
            return []
        side = _sentiment_to_side(c.sentiment)
        if side is None:
            return []

        decisions: list[TradeDecision] = []
        if ctx.venue_registry is None:
            return []

        venues = ctx.venue_registry.query(topic=c.category)
        if not venues:
            venues = list(ctx.venue_registry.all())

        # build a search query string from category keywords
        cat_cfg = (ctx.playbook.get("categories") or {}).get(c.category) or {}
        keywords = cat_cfg.get("keywords") or [c.category.replace("_", " ")]
        query = keywords[0]

        for client, vmeta in venues:
            try:
                refs = client.search_markets(query, limit=self.per_venue_market_limit)
            except Exception:
                continue
            for ref in refs:
                decisions.append(TradeDecision(
                    action="open",
                    venue=vmeta.name,
                    market_id=ref.market_id,
                    market_title=ref.title,
                    side=side,
                    size_contracts=int(self.default_size_contracts * eff),
                    confidence=round(eff, 3),
                    rationale=(
                        f"policy={c.category}/{c.sentiment} fc={c.follow_through:.2f} "
                        f"conf={c.confidence:.2f} | quote: \"{c.original_excerpt[:100]}\""
                    ),
                    agent_name=self.name,
                    source_signal_id=signal.id,
                    category=c.category,
                    event_id=ref.market_id,
                    suggested_stop_loss=None,        # policy bets have no fixed stop yet
                    suggested_take_profit=None,
                    suggested_max_hold_until=ref.closes_at,
                ))
        return decisions
