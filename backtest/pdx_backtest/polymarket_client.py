"""Polymarket API client — Gamma (market data) + CLOB (trading/prices).

Endpoints:
  Gamma:  https://gamma-api.polymarket.com
  CLOB:   https://clob.polymarket.com
  WS:     wss://ws-subscriptions-clob.polymarket.com/ws/market

No authentication required for read-only endpoints.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

_SESSION: Optional[requests.Session] = None


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({
            "Accept": "application/json",
            "User-Agent": "pdx-backtest/1.0",
        })
    return _SESSION


def _get(url: str, params: dict | None = None,
         retries: int = 3, backoff: float = 2.0) -> Any:
    for attempt in range(retries):
        try:
            r = _session().get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt < retries - 1:
                wait = backoff * (2 ** attempt)
                logger.warning("Request failed (%s), retrying in %.1fs…", exc, wait)
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Market metadata (Gamma API)
# ---------------------------------------------------------------------------


@dataclass
class MarketInfo:
    condition_id: str
    question: str
    slug: str
    outcomes: list[str]
    outcome_prices: list[float]
    token_ids: list[str]
    volume: float
    liquidity: float
    active: bool
    closed: bool
    group_item_title: str
    end_date: str
    event_slug: str = ""
    event_title: str = ""

    @property
    def is_binary(self) -> bool:
        return len(self.outcomes) == 2


@dataclass
class EventInfo:
    slug: str
    title: str
    markets: list[MarketInfo] = field(default_factory=list)

    @property
    def is_multi_outcome(self) -> bool:
        return len(self.markets) > 2


def fetch_markets(
    limit: int = 100,
    active: bool = True,
    closed: bool = False,
    order: str = "volume",
    ascending: bool = False,
    offset: int = 0,
) -> list[MarketInfo]:
    """Fetch market listings from the Gamma API."""
    params = {
        "limit": limit,
        "active": str(active).lower(),
        "closed": str(closed).lower(),
        "order": order,
        "ascending": str(ascending).lower(),
        "offset": offset,
    }
    data = _get(f"{GAMMA_BASE}/markets", params)
    markets = []
    for m in data:
        try:
            prices = json.loads(m.get("outcomePrices", "[]"))
            token_ids = json.loads(m.get("clobTokenIds", "[]"))
            markets.append(MarketInfo(
                condition_id=m.get("conditionId", ""),
                question=m.get("question", ""),
                slug=m.get("slug", ""),
                outcomes=json.loads(m.get("outcomes", "[]")),
                outcome_prices=[float(p) for p in prices],
                token_ids=[str(t) for t in token_ids],
                volume=float(m.get("volume", 0)),
                liquidity=float(m.get("liquidity", 0)),
                active=m.get("active", False),
                closed=m.get("closed", True),
                group_item_title=m.get("groupItemTitle", ""),
                end_date=m.get("endDate", ""),
                event_slug=m.get("eventSlug", ""),
                event_title=m.get("eventTitle", ""),
            ))
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.debug("Skipping malformed market: %s", exc)
    return markets


def fetch_events(
    limit: int = 50,
    active: bool = True,
    closed: bool = False,
) -> list[EventInfo]:
    """Fetch events (groups of related markets) from the Gamma API."""
    params = {
        "limit": limit,
        "active": str(active).lower(),
        "closed": str(closed).lower(),
    }
    data = _get(f"{GAMMA_BASE}/events", params)
    events = []
    for ev in data:
        event = EventInfo(
            slug=ev.get("slug", ""),
            title=ev.get("title", ""),
        )
        for m in ev.get("markets", []):
            try:
                prices = json.loads(m.get("outcomePrices", "[]"))
                token_ids = json.loads(m.get("clobTokenIds", "[]"))
                event.markets.append(MarketInfo(
                    condition_id=m.get("conditionId", ""),
                    question=m.get("question", ""),
                    slug=m.get("slug", ""),
                    outcomes=json.loads(m.get("outcomes", "[]")),
                    outcome_prices=[float(p) for p in prices],
                    token_ids=[str(t) for t in token_ids],
                    volume=float(m.get("volume", 0)),
                    liquidity=float(m.get("liquidity", 0)),
                    active=m.get("active", False),
                    closed=m.get("closed", True),
                    group_item_title=m.get("groupItemTitle", ""),
                    end_date=m.get("endDate", ""),
                    event_slug=ev.get("slug", ""),
                    event_title=ev.get("title", ""),
                ))
            except (json.JSONDecodeError, ValueError, KeyError):
                continue
        events.append(event)
    return events


def fetch_multi_outcome_events(
    min_markets: int = 3,
    limit: int = 50,
) -> list[EventInfo]:
    """Fetch events that have 3+ outcome markets (NegRisk candidates)."""
    events = fetch_events(limit=limit, active=True, closed=False)
    return [e for e in events if len(e.markets) >= min_markets]


# ---------------------------------------------------------------------------
# Price history (CLOB API)
# ---------------------------------------------------------------------------


@dataclass
class PriceCandle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def fetch_price_history(
    token_id: str,
    interval: str = "max",
    fidelity: int = 60,
) -> list[PriceCandle]:
    """Fetch OHLC price history for a CLOB token.

    Parameters
    ----------
    token_id : str
        The CLOB token ID (from MarketInfo.token_ids).
    interval : str
        Time window: "1d", "1w", "1m", "3m", "max".
    fidelity : int
        Candle resolution in minutes (1, 5, 15, 60, etc.).
    """
    data = _get(f"{CLOB_BASE}/prices-history", params={
        "market": token_id,
        "interval": interval,
        "fidelity": fidelity,
    })
    candles = []
    history = data if isinstance(data, list) else data.get("history", [])
    for c in history:
        candles.append(PriceCandle(
            timestamp=int(c.get("t", 0)),
            open=float(c.get("o", 0)),
            high=float(c.get("h", 0)),
            low=float(c.get("l", 0)),
            close=float(c.get("c", 0)),
            volume=float(c.get("v", 0)),
        ))
    return candles


# ---------------------------------------------------------------------------
# Order book snapshot (CLOB API)
# ---------------------------------------------------------------------------


@dataclass
class OrderBookSnapshot:
    token_id: str
    timestamp: float
    bids: list[tuple[float, float]]  # (price, size)
    asks: list[tuple[float, float]]
    midpoint: float


def fetch_orderbook(token_id: str) -> OrderBookSnapshot:
    """Fetch current order book for a CLOB token."""
    data = _get(f"{CLOB_BASE}/book", params={"token_id": token_id})
    bids = [(float(b["price"]), float(b["size"])) for b in data.get("bids", [])]
    asks = [(float(a["price"]), float(a["size"])) for a in data.get("asks", [])]
    mid = (bids[0][0] + asks[0][0]) / 2 if bids and asks else 0.0
    return OrderBookSnapshot(
        token_id=token_id,
        timestamp=time.time(),
        bids=bids,
        asks=asks,
        midpoint=mid,
    )


def fetch_midpoint(token_id: str) -> float:
    """Fetch current midpoint price for a CLOB token."""
    data = _get(f"{CLOB_BASE}/midpoint", params={"token_id": token_id})
    return float(data.get("mid", 0))


def fetch_midpoints(token_ids: list[str]) -> dict[str, float]:
    """Fetch current midpoints for multiple tokens."""
    data = _get(f"{CLOB_BASE}/midpoints", params={
        "token_ids": ",".join(token_ids),
    })
    return {k: float(v) for k, v in data.items()}
