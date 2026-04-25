from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


Outcome = Literal["YES", "NO"]


class MarketRef(BaseModel):
    """A canonical reference to a single binary YES/NO market on a venue."""
    venue: Literal["polymarket", "kalshi"]
    market_id: str
    title: str
    description: str = ""
    category: Optional[str] = None
    closes_at: Optional[datetime] = None
    url: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class Quote(BaseModel):
    """Best bid/ask for both YES and NO sides of a binary market.

    Prices are in USD on a 0-1 scale (a.k.a. probability). For Polymarket
    the YES and NO contracts are separate tokens and prices roughly sum to 1.
    For Kalshi a single contract has yes_bid/yes_ask/no_bid/no_ask.
    """
    market: MarketRef
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None
    no_bid: Optional[float] = None
    no_ask: Optional[float] = None
    last: Optional[float] = None
    volume_24h: Optional[float] = None
    fetched_at: datetime

    def yes_mid(self) -> Optional[float]:
        if self.yes_bid is not None and self.yes_ask is not None:
            return (self.yes_bid + self.yes_ask) / 2
        return self.last

    def no_mid(self) -> Optional[float]:
        if self.no_bid is not None and self.no_ask is not None:
            return (self.no_bid + self.no_ask) / 2
        if self.last is not None:
            return 1.0 - self.last
        return None
