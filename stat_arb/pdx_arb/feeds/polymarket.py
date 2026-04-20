"""Polymarket price feed — read-only via Gamma + CLOB APIs."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from pdx_arb.config import PolymarketConfig
from pdx_arb.types import Venue, VenuePrice

logger = logging.getLogger(__name__)


class PolymarketFeed:
    """Read-only price feed from Polymarket's Gamma + CLOB APIs."""

    def __init__(self, config: PolymarketConfig | None = None) -> None:
        self.config = config or PolymarketConfig()
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "pdx-arb/1.0",
        })

    def _get(self, url: str, params: dict | None = None) -> Any:
        for attempt in range(3):
            try:
                r = self._session.get(url, params=params, timeout=15)
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError) as exc:
                if attempt < 2:
                    time.sleep(1.0 * (2 ** attempt))
                    logger.debug("Polymarket request retry %d: %s", attempt + 1, exc)
                else:
                    logger.error("Polymarket request failed: %s", exc)
                    raise

    def fetch_active_markets(self, limit: int = 200) -> list[dict]:
        """Fetch active binary markets with volume > 0."""
        data = self._get(f"{self.config.gamma_url}/markets", params={
            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": "volume",
            "ascending": "false",
        })
        markets = []
        for m in data:
            try:
                outcomes = json.loads(m.get("outcomes", "[]"))
                if len(outcomes) != 2:
                    continue
                prices = json.loads(m.get("outcomePrices", "[]"))
                token_ids = json.loads(m.get("clobTokenIds", "[]"))
                if len(prices) < 2 or len(token_ids) < 2:
                    continue
                markets.append({
                    "condition_id": m.get("conditionId", ""),
                    "question": m.get("question", ""),
                    "slug": m.get("slug", ""),
                    "outcomes": outcomes,
                    "yes_price": float(prices[0]),
                    "no_price": float(prices[1]),
                    "token_ids": [str(t) for t in token_ids],
                    "volume": float(m.get("volume", 0)),
                    "liquidity": float(m.get("liquidity", 0)),
                    "end_date": m.get("endDate", ""),
                    "event_slug": m.get("eventSlug", ""),
                })
            except (json.JSONDecodeError, ValueError, KeyError):
                continue
        return markets

    def get_price(self, token_ids: list[str]) -> VenuePrice:
        """Get current YES/NO prices via CLOB midpoints."""
        try:
            data = self._get(
                f"{self.config.clob_url}/midpoints",
                params={"token_ids": ",".join(token_ids)},
            )
            yes_mid = float(data.get(token_ids[0], 0))
            no_mid = float(data.get(token_ids[1], 0)) if len(token_ids) > 1 else 1.0 - yes_mid
        except Exception:
            yes_mid = 0.0
            no_mid = 0.0

        return VenuePrice(
            venue=Venue.POLYMARKET,
            yes_price=yes_mid,
            no_price=no_mid,
            liquidity=0.0,
        )

    def get_orderbook(self, token_id: str) -> dict:
        """Fetch L2 order book for a CLOB token."""
        data = self._get(f"{self.config.clob_url}/book", params={"token_id": token_id})
        bids = [(float(b["price"]), float(b["size"])) for b in data.get("bids", [])]
        asks = [(float(a["price"]), float(a["size"])) for a in data.get("asks", [])]
        return {"bids": bids, "asks": asks}

    def estimate_fill_price(self, token_id: str, side: str, size_usd: float) -> float:
        """Estimate fill price by walking the order book."""
        book = self.get_orderbook(token_id)
        levels = book["asks"] if side == "buy" else book["bids"]
        if not levels:
            return 0.0
        remaining = size_usd
        total_cost = 0.0
        for price, qty in levels:
            fill = min(remaining, qty * price)
            total_cost += fill
            remaining -= fill
            if remaining <= 0:
                break
        if size_usd <= 0:
            return 0.0
        return total_cost / size_usd
