"""Cross-market arbitrage detector.

Two distinct opportunity types on binary YES/NO event contracts:

1) DIRECT ARB: For the SAME event resolved on both venues, if YES is cheap on
   one and expensive on the other, buy cheap YES + buy NO on the expensive
   side. Locks in profit if `yes_ask_cheap + no_ask_expensive < 1.0`.

   profit_per_$1 = 1.0 - (yes_ask_cheap + no_ask_expensive)

   Risk: only IF the two events resolve identically. Resolution-source mismatch
   ruins this — verify resolution rules before sizing.

2) DIRECTIONAL SPREAD: One venue's YES price diverges from the other beyond a
   threshold. Take the cheaper side; close when convergence happens. Not risk-
   free, but lower beta than outright bets.

This module covers (1) — strict cross-market arb. (2) is left to the analyzer
in the trumptrade pipeline.
"""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel
from trumptrade.markets.types import Quote
from trumptrade.arb.matcher import MatchCandidate


class ArbLeg(BaseModel):
    venue: str
    market_id: str
    title: str
    side: str        # "BUY_YES" | "BUY_NO"
    price: float     # the ask we'd hit
    qty_contracts: int = 1
    url: str | None = None


class ArbOpportunity(BaseModel):
    """A cross-market lock if executed at the listed asks."""
    long_yes: ArbLeg
    long_no: ArbLeg
    cost_per_pair: float       # yes_ask_cheap + no_ask_expensive
    profit_per_pair: float     # 1.0 - cost_per_pair (gross, no fees)
    profit_per_dollar: float   # profit_per_pair / cost_per_pair
    similarity: float          # match confidence
    rationale: str
    detected_at: datetime


def detect(
    match: MatchCandidate,
    poly_quote: Quote,
    kalshi_quote: Quote,
    fee_per_dollar: float = 0.0,    # combined round-trip fee estimate
    min_edge: float = 0.005,        # require >= 50bps gross profit per pair
) -> ArbOpportunity | None:
    """Given a matched (polymarket, kalshi) pair plus quotes, find the cheapest
    YES side and pair it with the cheapest NO on the other side. Return None
    if the round-trip cost is >= 1.0 (no arb)."""

    poly_yes = poly_quote.yes_ask
    poly_no  = poly_quote.no_ask
    kal_yes  = kalshi_quote.yes_ask
    kal_no   = kalshi_quote.no_ask
    if None in (poly_yes, poly_no, kal_yes, kal_no):
        return None

    # Two pairings:
    #   A: long YES on Polymarket + long NO on Kalshi
    #   B: long YES on Kalshi    + long NO on Polymarket
    pairings = [
        (
            ArbLeg(
                venue="polymarket", market_id=match.polymarket.market_id,
                title=match.polymarket.title, side="BUY_YES", price=poly_yes,
                url=match.polymarket.url,
            ),
            ArbLeg(
                venue="kalshi", market_id=match.kalshi.market_id,
                title=match.kalshi.title, side="BUY_NO", price=kal_no,
                url=match.kalshi.url,
            ),
            poly_yes + kal_no,
        ),
        (
            ArbLeg(
                venue="kalshi", market_id=match.kalshi.market_id,
                title=match.kalshi.title, side="BUY_YES", price=kal_yes,
                url=match.kalshi.url,
            ),
            ArbLeg(
                venue="polymarket", market_id=match.polymarket.market_id,
                title=match.polymarket.title, side="BUY_NO", price=poly_no,
                url=match.polymarket.url,
            ),
            kal_yes + poly_no,
        ),
    ]
    pairings.sort(key=lambda p: p[2])
    yes_leg, no_leg, cost = pairings[0]

    profit = 1.0 - cost - fee_per_dollar
    if profit < min_edge:
        return None

    return ArbOpportunity(
        long_yes=yes_leg,
        long_no=no_leg,
        cost_per_pair=round(cost, 4),
        profit_per_pair=round(profit, 4),
        profit_per_dollar=round(profit / cost, 4) if cost > 0 else 0.0,
        similarity=match.similarity,
        rationale=match.rationale,
        detected_at=datetime.now(tz=poly_quote.fetched_at.tzinfo),
    )
