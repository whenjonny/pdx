"""ArbAgent: takes a market-signal (e.g. price-jump on venue A) and
emits two coordinated `open` decisions (long YES on cheap venue + long NO on
rich venue) when a cross-market lock exists.

Powered by the existing arb.scanner / arb.detector. Each emitted
TradeDecision carries `linked_decision_id` so the OrderRouter can keep the
two legs together (atomic submission, atomic close).
"""
from __future__ import annotations
from trumptrade.agents.base import Agent, AgentContext, TradeDecision
from trumptrade.types import Signal


class ArbAgent(Agent):
    name = "arb"

    def __init__(
        self,
        polymarket_client,
        kalshi_client,
        scanner_factory=None,
        default_size_contracts: int = 100,
        min_edge: float = 0.005,
        match_min_similarity: float = 0.35,
    ):
        from trumptrade.arb import ArbScanner
        self.scanner = (scanner_factory or ArbScanner)(
            polymarket=polymarket_client,
            kalshi=kalshi_client,
            min_edge=min_edge,
            match_min_similarity=match_min_similarity,
        )
        self.default_size_contracts = default_size_contracts

    def analyze(self, signal: Signal, ctx: AgentContext) -> list[TradeDecision]:
        # Use the signal text as the query — works for Trump posts naturally,
        # and for market_signal sources we put the affected category there.
        query = (signal.text or signal.metadata.get("query") or "").strip()
        if not query:
            return []
        report = self.scanner.scan(query, per_venue_limit=20)
        decisions: list[TradeDecision] = []
        for opp in report.opportunities[:10]:    # cap output volume
            yes_d = TradeDecision(
                action="open",
                venue=opp.long_yes.venue,
                market_id=opp.long_yes.market_id,
                market_title=opp.long_yes.title,
                side="BUY_YES",
                size_contracts=self.default_size_contracts,
                price_limit=opp.long_yes.price,
                confidence=opp.similarity,
                rationale=f"arb leg YES @ {opp.long_yes.price:.3f}; pair edge +{opp.profit_per_pair:.3f}",
                agent_name=self.name,
                source_signal_id=signal.id,
                target_arb_close_cost=opp.cost_per_pair,
            )
            no_d = TradeDecision(
                action="open",
                venue=opp.long_no.venue,
                market_id=opp.long_no.market_id,
                market_title=opp.long_no.title,
                side="BUY_NO",
                size_contracts=self.default_size_contracts,
                price_limit=opp.long_no.price,
                confidence=opp.similarity,
                rationale=f"arb leg NO @ {opp.long_no.price:.3f}; pair edge +{opp.profit_per_pair:.3f}",
                agent_name=self.name,
                source_signal_id=signal.id,
                target_arb_close_cost=opp.cost_per_pair,
                linked_decision_id=yes_d.id,
            )
            yes_d.linked_decision_id = no_d.id
            decisions.extend([yes_d, no_d])
        return decisions
