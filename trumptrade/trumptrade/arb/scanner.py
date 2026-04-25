"""ArbScanner: orchestrate matching + quote fetching + arb detection.

Designed to be called either:
  - Standalone (`trumptrade arb-scan --query "tariff"`) for browsing
  - From the trumptrade pipeline (a Trump tariff signal -> scan tariff arbs)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from trumptrade.markets.base import PredictionMarketClient
from trumptrade.markets.types import Quote
from trumptrade.arb.matcher import match_rules, match_llm, MatchCandidate
from trumptrade.arb.detector import detect, ArbOpportunity


@dataclass
class ScanReport:
    query: str
    candidates: list[MatchCandidate] = field(default_factory=list)
    opportunities: list[ArbOpportunity] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"=== arb scan: {self.query!r} ===",
            f"candidate matches : {len(self.candidates)}",
            f"arb opportunities : {len(self.opportunities)}",
        ]
        for o in self.opportunities[:20]:
            lines.append(
                f"  +{o.profit_per_pair:.3f}/pair  ({o.profit_per_dollar:+.2%})  "
                f"sim={o.similarity:.2f}\n"
                f"      LONG_YES  {o.long_yes.venue:10s} {o.long_yes.title[:50]:<50s} @ {o.long_yes.price:.3f}\n"
                f"      LONG_NO   {o.long_no.venue:10s} {o.long_no.title[:50]:<50s} @ {o.long_no.price:.3f}\n"
                f"      url_yes : {o.long_yes.url}\n"
                f"      url_no  : {o.long_no.url}"
            )
        return "\n".join(lines)


class ArbScanner:
    """Scans for cross-venue arbitrage. Generic: supply any two
    `PredictionMarketClient`s (Polymarket / Kalshi / Predict.fun / ...).
    Field names `polymarket` / `kalshi` are kept as backward-compatible
    aliases."""

    def __init__(
        self,
        venue_a: PredictionMarketClient | None = None,
        venue_b: PredictionMarketClient | None = None,
        use_llm_matcher: bool = False,
        fee_per_dollar: float = 0.0,
        min_edge: float = 0.005,
        match_min_similarity: float = 0.35,
        polymarket: PredictionMarketClient | None = None,    # bw-compat
        kalshi: PredictionMarketClient | None = None,        # bw-compat
    ):
        self.venue_a = venue_a or polymarket
        self.venue_b = venue_b or kalshi
        if self.venue_a is None or self.venue_b is None:
            raise ValueError("ArbScanner requires two venue clients (venue_a, venue_b).")
        self.use_llm_matcher = use_llm_matcher
        self.fee_per_dollar = fee_per_dollar
        self.min_edge = min_edge
        self.match_min_similarity = match_min_similarity

    # backwards-compat properties for older code that referenced .polymarket / .kalshi
    @property
    def polymarket(self):
        return self.venue_a

    @property
    def kalshi(self):
        return self.venue_b

    def scan(self, query: str, per_venue_limit: int = 25) -> ScanReport:
        report = ScanReport(query=query)
        a_refs = self.venue_a.search_markets(query, limit=per_venue_limit)
        b_refs = self.venue_b.search_markets(query, limit=per_venue_limit)
        if not a_refs or not b_refs:
            return report

        if self.use_llm_matcher:
            matches = match_llm(a_refs, b_refs, min_similarity=0.7)
        else:
            matches = match_rules(a_refs, b_refs, min_similarity=self.match_min_similarity)

        report.candidates = matches

        for m in matches:
            a_q = self.venue_a.get_quote(m.polymarket.market_id)
            b_q = self.venue_b.get_quote(m.kalshi.market_id)
            if a_q is None or b_q is None:
                continue
            opp = detect(m, a_q, b_q,
                         fee_per_dollar=self.fee_per_dollar,
                         min_edge=self.min_edge)
            if opp:
                report.opportunities.append(opp)

        report.opportunities.sort(key=lambda o: o.profit_per_dollar, reverse=True)
        return report
