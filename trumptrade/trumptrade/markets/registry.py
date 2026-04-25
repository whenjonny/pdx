"""Market venue registry. Mirrors signal-source registry pattern: every
prediction-market client must declare metadata so downstream consumers
(arb scanner, monitor, dashboard) can pick the right venues per topic."""
from __future__ import annotations
from pathlib import Path
from typing import Iterator, Literal
from pydantic import BaseModel, Field
import yaml
from trumptrade.markets.base import PredictionMarketClient


VenueClass = Literal["regulated_us", "onchain_evm", "onchain_solana", "onchain_other", "play_money", "research"]
Cadence = Literal["real_time", "minutes", "hourly", "daily"]


class VenueMetadata(BaseModel):
    """Required metadata for any registered prediction-market venue.

    `topics` declares what kinds of events the venue typically lists. Used by
    the orchestrator to decide which venues to query for a given Trump-policy
    category. Free text but try to match playbook category names.
    """
    name: str
    venue_class: VenueClass
    base_currency: str = "USD"          # USD, USDC, USDH, BNB, ...
    chain: str | None = None             # polygon, base, bnb, ethereum, solana, ...
    auth_required_for_read: bool = False
    auth_required_for_trade: bool = True
    fee_estimate_per_dollar: float = 0.0
    update_cadence: Cadence = "real_time"
    reliability: float = Field(default=1.0, ge=0.0, le=1.0)
    topics: list[str] = Field(default_factory=list)
    supports_limit_orders: bool = False
    supports_websocket: bool = False
    description: str = ""


class VenueRegistry:
    def __init__(self):
        self._venues: dict[str, tuple[PredictionMarketClient, VenueMetadata]] = {}

    def register(self, client: PredictionMarketClient, metadata: VenueMetadata) -> None:
        if metadata.name in self._venues:
            raise ValueError(f"venue {metadata.name!r} already registered")
        self._venues[metadata.name] = (client, metadata)

    def unregister(self, name: str) -> None:
        if name not in self._venues:
            raise KeyError(name)
        del self._venues[name]

    def get(self, name: str) -> tuple[PredictionMarketClient, VenueMetadata]:
        if name not in self._venues:
            raise KeyError(name)
        return self._venues[name]

    def __contains__(self, name: str) -> bool:
        return name in self._venues

    def __len__(self) -> int:
        return len(self._venues)

    def all(self) -> Iterator[tuple[PredictionMarketClient, VenueMetadata]]:
        return iter(self._venues.values())

    def query(
        self,
        venue_class: str | None = None,
        topic: str | None = None,
        chain: str | None = None,
        min_reliability: float = 0.0,
    ) -> list[tuple[PredictionMarketClient, VenueMetadata]]:
        out = []
        for c, m in self._venues.values():
            if venue_class and m.venue_class != venue_class:
                continue
            if chain and m.chain != chain:
                continue
            if topic and m.topics and topic not in m.topics:
                continue
            if m.reliability < min_reliability:
                continue
            out.append((c, m))
        return out

    @classmethod
    def from_yaml(cls, path: Path) -> "VenueRegistry":
        registry = cls()
        with open(path) as f:
            spec = yaml.safe_load(f) or {}
        for entry in spec.get("venues", []):
            module_path, cls_name = entry["factory"].split(":")
            mod = __import__(module_path, fromlist=[cls_name])
            client_cls = getattr(mod, cls_name)
            client = client_cls(**(entry.get("args") or {}))
            registry.register(client, VenueMetadata(name=entry["name"], **entry["metadata"]))
        return registry
