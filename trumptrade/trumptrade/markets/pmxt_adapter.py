"""pmxt adapter — wraps the pmxt SDK (https://github.com/pmxt-dev/pmxt) so any
venue pmxt supports can be added without writing a custom client.

pmxt is "CCXT for prediction markets" and supports Polymarket, Kalshi,
Limitless, Smarkets, Myriad, Probable, Baozi, etc. via a single Python API.

Install:  pip install pmxt   (also requires Node.js on PATH for sidecar)

Usage:
    from trumptrade.markets.pmxt_adapter import PMXTClient
    c = PMXTClient(exchange="limitless")
    refs = c.search_markets("Trump tariff", limit=20)
    quote = c.get_quote(refs[0].market_id)

Lazy-imports pmxt so the rest of trumptrade works without it.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional
from trumptrade.markets.base import PredictionMarketClient
from trumptrade.markets.types import MarketRef, Quote


class PMXTClient(PredictionMarketClient):
    """Generic pmxt-backed client. Set `venue` per instance via `exchange=...`."""

    def __init__(self, exchange: str, **kwargs: Any):
        self.venue = exchange
        self.exchange_id = exchange
        self._kwargs = kwargs
        self._client = None  # lazy

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import pmxt
        except ImportError as e:
            raise ImportError(
                "PMXTClient requires pmxt. Install: `pip install pmxt` and ensure "
                "Node.js is on PATH (pmxt runs a Node sidecar on :3847)."
            ) from e
        # pmxt.create("limitless", {...}) is the canonical entry; fall back to
        # ExchangeClass(...) if user wired a specific class.
        if hasattr(pmxt, "create"):
            self._client = pmxt.create(self.exchange_id, self._kwargs)
        elif hasattr(pmxt, self.exchange_id):
            cls = getattr(pmxt, self.exchange_id)
            self._client = cls(**self._kwargs)
        else:
            raise RuntimeError(f"pmxt has no exchange {self.exchange_id!r}")
        return self._client

    def search_markets(self, query: str, limit: int = 25, only_active: bool = True) -> list[MarketRef]:
        c = self._get_client()
        try:
            markets = c.fetch_markets() if hasattr(c, "fetch_markets") else c.fetchMarkets()
        except Exception:
            return []
        q = (query or "").lower().strip()
        refs: list[MarketRef] = []
        for m in markets or []:
            title = (m.get("title") or m.get("question") or "")
            descr = (m.get("description") or "")
            if q and q not in (title + " " + descr).lower():
                continue
            if only_active and not _is_active(m):
                continue
            refs.append(_to_market_ref(m, self.exchange_id))
            if len(refs) >= limit:
                break
        return refs

    def get_quote(self, market_id: str) -> Quote | None:
        c = self._get_client()
        try:
            ob = c.fetch_order_book(market_id) if hasattr(c, "fetch_order_book") else c.fetchOrderBook(market_id)
            ticker = c.fetch_ticker(market_id) if hasattr(c, "fetch_ticker") else c.fetchTicker(market_id)
        except Exception:
            return None
        ref = _to_market_ref({"id": market_id, **(ticker or {})}, self.exchange_id)
        # pmxt order book schema: {"bids": [[price, size], ...], "asks": [[price, size], ...]}
        bids = (ob or {}).get("bids") or []
        asks = (ob or {}).get("asks") or []
        # pmxt uses symbol-per-outcome model, so YES/NO are separate symbols.
        # For binary markets the outcome convention encodes YES/NO in market_id.
        # We treat the supplied market_id's bid/ask as YES side; NO derived as 1-x.
        yes_ask = float(asks[0][0]) if asks else None
        yes_bid = float(bids[0][0]) if bids else None
        return Quote(
            market=ref,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=(1.0 - yes_ask) if yes_ask is not None else None,
            no_ask=(1.0 - yes_bid) if yes_bid is not None else None,
            last=_f((ticker or {}).get("last") or (ticker or {}).get("lastPrice")),
            volume_24h=_f((ticker or {}).get("baseVolume") or (ticker or {}).get("volume24h")),
            fetched_at=datetime.now(timezone.utc),
        )


def _f(x) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _is_active(m: dict) -> bool:
    if "active" in m:
        return bool(m.get("active"))
    if "status" in m:
        return str(m.get("status")).lower() in ("open", "active")
    return True


def _to_market_ref(m: dict, venue: str) -> MarketRef:
    closes_raw = m.get("endDate") or m.get("close_time") or m.get("expiry")
    closes_at = None
    if closes_raw:
        try:
            closes_at = datetime.fromisoformat(str(closes_raw).replace("Z", "+00:00"))
        except Exception:
            closes_at = None
    return MarketRef(
        venue=venue,
        market_id=str(m.get("id") or m.get("symbol") or ""),
        title=m.get("title") or m.get("question") or "",
        description=m.get("description") or "",
        category=m.get("category"),
        closes_at=closes_at,
        url=m.get("url"),
        metadata={"pmxt_raw": True},
    )
