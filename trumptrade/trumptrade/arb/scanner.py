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
    def __init__(
        self,
        polymarket: PredictionMarketClient,
        kalshi: PredictionMarketClient,
        use_llm_matcher: bool = False,
        fee_per_dollar: float = 0.0,
        min_edge: float = 0.005,
        match_min_similarity: float = 0.35,
    ):
        self.polymarket = polymarket
        self.kalshi = kalshi
        self.use_llm_matcher = use_llm_matcher
        self.fee_per_dollar = fee_per_dollar
        self.min_edge = min_edge
        self.match_min_similarity = match_min_similarity

    def scan(self, query: str, per_venue_limit: int = 25) -> ScanReport:
        report = ScanReport(query=query)
        poly_refs = self.polymarket.search_markets(query, limit=per_venue_limit)
        kalshi_refs = self.kalshi.search_markets(query, limit=per_venue_limit)
        if not poly_refs or not kalshi_refs:
            return report

        if self.use_llm_matcher:
            matches = match_llm(poly_refs, kalshi_refs, min_similarity=0.7)
        else:
            matches = match_rules(poly_refs, kalshi_refs, min_similarity=self.match_min_similarity)

        report.candidates = matches

        for m in matches:
            poly_q = self.polymarket.get_quote(m.polymarket.market_id)
            kal_q = self.kalshi.get_quote(m.kalshi.market_id)
            if poly_q is None or kal_q is None:
                continue
            opp = detect(m, poly_q, kal_q,
                         fee_per_dollar=self.fee_per_dollar,
                         min_edge=self.min_edge)
            if opp:
                report.opportunities.append(opp)

        report.opportunities.sort(key=lambda o: o.profit_per_dollar, reverse=True)
        return report
