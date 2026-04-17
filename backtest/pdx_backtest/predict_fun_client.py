"""predict.fun API client -- market data and orderbook snapshots.

Endpoints:
  Mainnet:  https://api.predict.fun/        (API key required via x-api-key header)
  Testnet:  https://api-testnet.predict.fun/ (no API key, 240 rpm)
  Docs:     https://api.predict.fun/docs

Uses testnet by default.  Set the PREDICT_FUN_API_KEY environment
variable to use the mainnet endpoint instead.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

MAINNET_BASE = "https://api.predict.fun"
TESTNET_BASE = "https://api-testnet.predict.fun"

_SESSION: Optional[requests.Session] = None


def _api_key() -> str | None:
    """Return the predict.fun API key from the environment, or None."""
    return os.environ.get("PREDICT_FUN_API_KEY")


def _base_url() -> str:
    """Return mainnet base URL if an API key is set, otherwise testnet."""
    return MAINNET_BASE if _api_key() else TESTNET_BASE


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "pdx-backtest/1.0",
        }
        key = _api_key()
        if key:
            headers["x-api-key"] = key
        _SESSION.headers.update(headers)
    return _SESSION


def _get(url: str, params: dict | None = None,
         retries: int = 2, backoff: float = 1.0) -> Any:
    for attempt in range(retries):
        try:
            r = _session().get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt < retries - 1:
                wait = backoff * (2 ** attempt)
                logger.warning("Request failed (%s), retrying in %.1fs...", exc, wait)
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PredictOutcome:
    """A single outcome within a predict.fun market."""
    name: str
    index_set: str
    on_chain_id: str
    status: str


@dataclass
class PredictMarket:
    """A predict.fun market object."""
    id: str
    title: str
    question: str
    description: str
    status: str
    trading_status: str
    is_neg_risk: bool
    is_yield_bearing: bool
    fee_rate_bps: int
    outcomes: list[PredictOutcome]
    condition_id: str
    oracle_question_id: str
    resolver_address: str
    polymarket_condition_ids: list[str]
    kalshi_market_ticker: str | None
    category_slug: str
    decimal_precision: int
    spread_threshold: float
    share_threshold: float
    created_at: str


@dataclass
class PredictOrderBook:
    """Orderbook snapshot for a predict.fun market."""
    market_id: str
    update_timestamp_ms: int
    asks: list[tuple[float, float]]  # (price, quantity)
    bids: list[tuple[float, float]]  # (price, quantity)

    @property
    def midpoint(self) -> float:
        if self.bids and self.asks:
            return (self.bids[0][0] + self.asks[0][0]) / 2
        return 0.0


@dataclass
class PredictMarketStats:
    """Market statistics for a predict.fun market."""
    market_id: str
    volume: float
    trade_count: int
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_outcome(raw: dict) -> PredictOutcome:
    return PredictOutcome(
        name=raw.get("name", ""),
        index_set=raw.get("indexSet", ""),
        on_chain_id=raw.get("onChainId", ""),
        status=raw.get("status", ""),
    )


def _parse_market(m: dict) -> PredictMarket:
    outcomes_raw = m.get("outcomes", [])
    outcomes = [_parse_outcome(o) for o in outcomes_raw]
    return PredictMarket(
        id=m.get("id", ""),
        title=m.get("title", ""),
        question=m.get("question", ""),
        description=m.get("description", ""),
        status=m.get("status", ""),
        trading_status=m.get("tradingStatus", ""),
        is_neg_risk=bool(m.get("isNegRisk", False)),
        is_yield_bearing=bool(m.get("isYieldBearing", False)),
        fee_rate_bps=int(m.get("feeRateBps", 0)),
        outcomes=outcomes,
        condition_id=m.get("conditionId", ""),
        oracle_question_id=m.get("oracleQuestionId", ""),
        resolver_address=m.get("resolverAddress", ""),
        polymarket_condition_ids=m.get("polymarketConditionIds", []) or [],
        kalshi_market_ticker=m.get("kalshiMarketTicker"),
        category_slug=m.get("categorySlug", ""),
        decimal_precision=int(m.get("decimalPrecision", 2)),
        spread_threshold=float(m.get("spreadThreshold", 0)),
        share_threshold=float(m.get("shareThreshold", 0)),
        created_at=m.get("createdAt", ""),
    )


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------


def fetch_markets(
    status: str = "OPEN",
    limit: int = 100,
    cursor: str | None = None,
) -> list[PredictMarket]:
    """Fetch market listings from the predict.fun API.

    Parameters
    ----------
    status : str
        Filter by trading status, e.g. "OPEN".
    limit : int
        Maximum number of markets to return.  The API paginates via
        cursor, so this function fetches pages until *limit* is reached.
    cursor : str | None
        Pagination cursor for resuming a previous listing.
    """
    base = _base_url()
    markets: list[PredictMarket] = []

    while len(markets) < limit:
        params: dict[str, Any] = {"status": status}
        if cursor:
            params["cursor"] = cursor

        data = _get(f"{base}/v1/markets", params)

        if not data.get("success", False):
            logger.warning("predict.fun /v1/markets returned success=false")
            break

        for m in data.get("data", []):
            try:
                markets.append(_parse_market(m))
            except (ValueError, KeyError) as exc:
                logger.debug("Skipping malformed market: %s", exc)

        cursor = data.get("cursor")
        if not cursor:
            break

    return markets[:limit]


def fetch_market(market_id: str) -> PredictMarket:
    """Fetch a single market by ID.

    Parameters
    ----------
    market_id : str
        The predict.fun market identifier.
    """
    base = _base_url()
    data = _get(f"{base}/v1/markets/{market_id}")
    return _parse_market(data)


def fetch_orderbook(market_id: str) -> PredictOrderBook:
    """Fetch the current orderbook for a predict.fun market.

    Parameters
    ----------
    market_id : str
        The predict.fun market identifier.
    """
    base = _base_url()
    data = _get(f"{base}/v1/markets/{market_id}/orderbook")
    bids = [(float(b[0]), float(b[1])) for b in data.get("bids", [])]
    asks = [(float(a[0]), float(a[1])) for a in data.get("asks", [])]
    return PredictOrderBook(
        market_id=data.get("marketId", market_id),
        update_timestamp_ms=int(data.get("updateTimestampMs", 0)),
        asks=asks,
        bids=bids,
    )


def fetch_market_stats(market_id: str) -> PredictMarketStats:
    """Fetch market statistics (volume, trade count, etc.).

    Parameters
    ----------
    market_id : str
        The predict.fun market identifier.
    """
    base = _base_url()
    data = _get(f"{base}/v1/markets/{market_id}/stats")
    return PredictMarketStats(
        market_id=market_id,
        volume=float(data.get("volume", 0)),
        trade_count=int(data.get("tradeCount", 0)),
        raw=data,
    )


def fetch_markets_with_polymarket_ids() -> dict[str, PredictMarket]:
    """Fetch all open markets that have Polymarket condition IDs.

    Returns a mapping from each Polymarket ``conditionId`` to the
    corresponding :class:`PredictMarket`.  A single predict.fun market
    may map to multiple Polymarket condition IDs, so every ID gets its
    own entry in the returned dict.

    This is useful for cross-platform arbitrage detection: look up a
    Polymarket condition ID and immediately get the predict.fun market.
    """
    markets = fetch_markets(status="OPEN", limit=500)
    mapping: dict[str, PredictMarket] = {}
    for mkt in markets:
        if not mkt.polymarket_condition_ids:
            continue
        for poly_id in mkt.polymarket_condition_ids:
            mapping[poly_id] = mkt
    return mapping
