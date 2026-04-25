"""Offline mock prediction-market client. Synthesizes markets and quotes
deterministically so paper-runs work without network access. Used in tests
and the demo `paper-run` flow when sandboxing blocks Polymarket/Kalshi."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from trumptrade.markets.base import PredictionMarketClient
from trumptrade.markets.types import MarketRef, Quote


class MockMarketClient(PredictionMarketClient):
    """Search returns N synthesized markets per query; quote returns a
    deterministic price derived from market_id hash so backtests are stable."""

    def __init__(self, venue_name: str = "mock", per_query_markets: int = 3,
                 base_yes_price: float = 0.45,
                 price_drift_per_call: float = 0.0,
                 random_walk_amplitude: float = 0.0):
        self.venue = venue_name
        self.per_query_markets = per_query_markets
        self.base_yes_price = base_yes_price
        self.price_drift_per_call = price_drift_per_call
        self.random_walk_amplitude = random_walk_amplitude
        self._call_count: dict[str, int] = {}

    def search_markets(self, query: str, limit: int = 25, only_active: bool = True) -> list[MarketRef]:
        n = min(limit, self.per_query_markets)
        out: list[MarketRef] = []
        for i in range(n):
            mid = f"{self.venue}-{_slug(query)}-{i}"
            out.append(MarketRef(
                venue=self.venue,
                market_id=mid,
                title=f"Will [{query}] resolve YES? (#{i})",
                description=f"Mock market for offline demo on {self.venue}",
                category=None,
                closes_at=datetime.now(timezone.utc) + timedelta(days=14 + i),
                url=f"https://example.invalid/{mid}",
            ))
        return out

    def get_quote(self, market_id: str) -> Quote:
        # base mid: spread around base_yes_price by a small amount
        h = (sum(ord(c) for c in market_id) % 11) - 5
        mid = self.base_yes_price + 0.02 * h
        # drift over time (each call = one tick)
        c_count = self._call_count.get(market_id, 0)
        self._call_count[market_id] = c_count + 1
        mid += self.price_drift_per_call * c_count
        # mild random walk (deterministic per-market hash)
        if self.random_walk_amplitude:
            import math
            mid += self.random_walk_amplitude * math.sin(h + c_count * 0.7)
        mid = max(0.05, min(0.95, mid))
        spread = 0.02
        return Quote(
            market=MarketRef(
                venue=self.venue, market_id=market_id,
                title=market_id, closes_at=datetime.now(timezone.utc) + timedelta(days=10),
                url=f"https://example.invalid/{market_id}",
            ),
            yes_bid=round(mid - spread / 2, 4),
            yes_ask=round(mid + spread / 2, 4),
            no_bid=round(1 - mid - spread / 2, 4),
            no_ask=round(1 - mid + spread / 2, 4),
            last=round(mid, 4),
            volume_24h=10_000.0,
            fetched_at=datetime.now(timezone.utc),
        )


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in (s or "x").lower()).strip("-") or "x"
