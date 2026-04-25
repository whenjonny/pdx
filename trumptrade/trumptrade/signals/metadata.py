"""Source metadata. Every signal source must declare what it covers so the
registry can match sources to subscribers (e.g. "give me all sources that
cover us_policy + energy industry")."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


Cadence = Literal["real_time", "minutes", "hourly", "daily", "irregular"]


class SourceMetadata(BaseModel):
    """Required metadata for any registered signal source.

    `domain` is the broadest classification (one of):
      - us_policy           government/political signals from US executive branch
      - macro               central bank, geopolitical, commodity policy
      - corporate           company-specific news (8-K, earnings)
      - prediction_market   event probabilities (Polymarket/Kalshi as a SIGNAL source)
      - sentiment           social/retail sentiment
      - regulatory          SEC/FTC/DOJ filings
      - geopolitical        war/sanctions/treaties

    `markets` is the LIST of asset markets the signal is expected to MOVE:
      - us_equities, us_options, us_treasuries, fx, crypto, commodities,
        prediction_markets, international_equities

    `industries` is the LIST of sector exposure (free text but try to match
    the playbook category names where possible). Use empty list for cross-sector.

    `update_cadence`: how often the source produces signals.
    `auth_required`: does it need credentials?
    `cost_per_request_usd`: 0.0 if free; else marginal request cost.
    `reliability`: 0-1, subjective ToS/uptime risk (1.0 = official API).
    """
    name: str
    domain: Literal[
        "us_policy", "macro", "corporate", "prediction_market",
        "sentiment", "regulatory", "geopolitical",
    ]
    markets: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    update_cadence: Cadence = "irregular"
    auth_required: bool = False
    cost_per_request_usd: float = 0.0
    reliability: float = Field(default=1.0, ge=0.0, le=1.0)
    description: str = ""

    def matches(
        self,
        domain: str | None = None,
        market: str | None = None,
        industry: str | None = None,
    ) -> bool:
        if domain and self.domain != domain:
            return False
        if market and market not in self.markets:
            return False
        if industry and industry not in self.industries:
            return False
        return True
