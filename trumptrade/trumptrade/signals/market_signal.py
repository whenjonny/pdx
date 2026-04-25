"""Market-as-signal sources. Treat venue activity itself as a signal stream:

- PriceJumpSource: emits a Signal when a tracked market's mid moves > N% in M
  minutes. Powers fast-arbitrage agents (price dislocation -> attempt arb).

- VolumeSpikeSource: emits when 24h volume jumps materially above baseline.

- ArbOpportunitySource: wraps ArbScanner, emits one Signal per detected
  opportunity. Lets the same downstream pipeline consume both Trump-policy
  signals and pure market-structure signals.

These all subclass SignalSource and play nice with SourceRegistry.
"""
from __future__ import annotations
from datetime import datetime, timezone
from trumptrade.signals.base import SignalSource
from trumptrade.types import Signal


class PriceJumpSource(SignalSource):
    """Polls a list of (venue, market_id) pairs each `poll()` call. Tracks
    last seen mid; emits a Signal when |delta| / prior > threshold."""

    def __init__(self, venue_clients: dict, watch: list[tuple[str, str]],
                 threshold_pct: float = 0.05):
        self.venue_clients = venue_clients
        self.watch = list(watch)
        self.threshold_pct = threshold_pct
        self._last_mid: dict[tuple[str, str], float] = {}
        self._counter = 0

    def poll(self) -> list[Signal]:
        signals: list[Signal] = []
        for venue, market_id in self.watch:
            client = self.venue_clients.get(venue)
            if client is None:
                continue
            try:
                quote = client.get_quote(market_id)
            except Exception:
                continue
            if quote is None:
                continue
            mid = quote.yes_mid()
            if mid is None:
                continue
            key = (venue, market_id)
            prior = self._last_mid.get(key)
            self._last_mid[key] = mid
            if prior is None or prior <= 0:
                continue
            delta_pct = abs(mid - prior) / prior
            if delta_pct >= self.threshold_pct:
                self._counter += 1
                signals.append(Signal(
                    id=f"price-jump-{venue}-{market_id}-{self._counter}",
                    author=venue,
                    timestamp=datetime.now(timezone.utc),
                    text=(
                        f"Price jump on {venue} market {market_id}: "
                        f"{prior:.3f} -> {mid:.3f} ({(mid - prior)/prior:+.2%})"
                    ),
                    url=quote.market.url if hasattr(quote, "market") else None,
                    source="market_signal:price_jump",
                    metadata={
                        "venue": venue, "market_id": market_id,
                        "prior_mid": prior, "current_mid": mid,
                        "title": quote.market.title if hasattr(quote, "market") else "",
                    },
                ))
        return signals


class ArbOpportunitySource(SignalSource):
    """Each poll runs an ArbScanner over a fixed set of queries. Each
    detected opportunity becomes a Signal so downstream agents (ArbAgent)
    can act on it."""

    def __init__(self, scanner, queries: list[str], min_edge: float = 0.005):
        self.scanner = scanner
        self.queries = list(queries)
        self.min_edge = min_edge
        self._seen: set[str] = set()

    def poll(self) -> list[Signal]:
        signals: list[Signal] = []
        for q in self.queries:
            try:
                report = self.scanner.scan(q, per_venue_limit=20)
            except Exception:
                continue
            for opp in report.opportunities:
                if opp.profit_per_pair < self.min_edge:
                    continue
                # Dedup key: legs+price snapshot
                key = (
                    f"{opp.long_yes.venue}:{opp.long_yes.market_id}|"
                    f"{opp.long_no.venue}:{opp.long_no.market_id}|"
                    f"{opp.cost_per_pair:.3f}"
                )
                if key in self._seen:
                    continue
                self._seen.add(key)
                signals.append(Signal(
                    id=f"arb-{key[:40]}-{datetime.now().timestamp()}",
                    author="arb_scanner",
                    timestamp=datetime.now(timezone.utc),
                    text=q,
                    source="market_signal:arb",
                    metadata={
                        "query": q,
                        "edge": opp.profit_per_pair,
                        "cost": opp.cost_per_pair,
                        "long_yes_venue": opp.long_yes.venue,
                        "long_yes_market": opp.long_yes.market_id,
                        "long_no_venue": opp.long_no.venue,
                        "long_no_market": opp.long_no.market_id,
                    },
                ))
        return signals
