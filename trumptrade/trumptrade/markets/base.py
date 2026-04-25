from __future__ import annotations
from abc import ABC, abstractmethod
from trumptrade.markets.types import MarketRef, Quote


class PredictionMarketClient(ABC):
    """Read-only interface common to Polymarket and Kalshi.

    Trading is venue-specific (Polymarket needs EIP-712 wallet signing,
    Kalshi uses JWT REST) and lives on subclasses, not in the base interface.
    """
    venue: str  # "polymarket" or "kalshi"

    @abstractmethod
    def search_markets(self, query: str, limit: int = 20, only_active: bool = True) -> list[MarketRef]:
        """Search active markets by free-text query."""
        ...

    @abstractmethod
    def get_quote(self, market_id: str) -> Quote | None:
        """Best bid/ask snapshot for a single market."""
        ...

    def get_quotes(self, market_ids: list[str]) -> dict[str, Quote]:
        """Default fan-out implementation."""
        out: dict[str, Quote] = {}
        for mid in market_ids:
            q = self.get_quote(mid)
            if q is not None:
                out[mid] = q
        return out
