"""Predict.fun read-only client. BNB Mainnet REST API.

Docs: https://dev.predict.fun/
Mainnet host: https://api.predict.fun/
Testnet host: https://api-testnet.predict.fun/  (no API key needed)
Rate limit: 240 req/min.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Optional
from trumptrade.markets.base import PredictionMarketClient
from trumptrade.markets.types import MarketRef, Quote


_MAINNET = "https://api.predict.fun"
_TESTNET = "https://api-testnet.predict.fun"


class PredictFunClient(PredictionMarketClient):
    venue = "predict.fun"

    def __init__(
        self,
        host: str | None = None,
        api_key: str | None = None,
        http_timeout: float = 10.0,
        testnet: bool = False,
    ):
        self.host = host or (_TESTNET if testnet else _MAINNET)
        self.api_key = api_key or os.environ.get("PREDICT_FUN_API_KEY")
        self.http_timeout = http_timeout
        self.testnet = testnet

    def _headers(self) -> dict:
        h = {"accept": "application/json"}
        if self.api_key and not self.testnet:
            h["X-API-Key"] = self.api_key
        return h

    def search_markets(self, query: str, limit: int = 25, only_active: bool = True) -> list[MarketRef]:
        try:
            import requests
        except ImportError as e:
            raise ImportError("PredictFunClient requires requests. pip install requests") from e
        params = {"limit": min(limit, 100)}
        if only_active:
            params["status"] = "open"
        try:
            r = requests.get(f"{self.host}/markets", params=params,
                             headers=self._headers(), timeout=self.http_timeout)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []

        q = (query or "").lower().strip()
        refs: list[MarketRef] = []
        items = data.get("markets") or data.get("data") or data
        if not isinstance(items, list):
            return []
        for m in items:
            title = m.get("question") or m.get("title") or ""
            description = m.get("description") or m.get("subtitle") or ""
            if q and q not in (title + " " + description).lower():
                continue
            refs.append(_market_to_ref(m))
            if len(refs) >= limit:
                break
        return refs

    def get_quote(self, market_id: str) -> Quote | None:
        try:
            import requests
        except ImportError as e:
            raise ImportError("PredictFunClient requires requests. pip install requests") from e
        try:
            r = requests.get(f"{self.host}/markets/{market_id}",
                             headers=self._headers(), timeout=self.http_timeout)
            r.raise_for_status()
            m = r.json()
        except Exception:
            return None
        if not m:
            return None
        if "market" in m:  # some endpoints wrap
            m = m["market"]

        return Quote(
            market=_market_to_ref(m),
            yes_bid=_f(m.get("yesBid") or m.get("yes_bid")),
            yes_ask=_f(m.get("yesAsk") or m.get("yes_ask")),
            no_bid=_f(m.get("noBid") or m.get("no_bid")),
            no_ask=_f(m.get("noAsk") or m.get("no_ask")),
            last=_f(m.get("lastPrice") or m.get("last_price")),
            volume_24h=_f(m.get("volume24h") or m.get("volume_24h")),
            fetched_at=datetime.now(timezone.utc),
        )


def _f(x) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
        # predict.fun may return prices in basis points; but typical 0-1 scale
        if v > 1.0 and v <= 100.0:
            return v / 100.0  # heuristic: 0-100 cents
        return v
    except (TypeError, ValueError):
        return None


def _market_to_ref(m: dict) -> MarketRef:
    closes_raw = m.get("endDate") or m.get("close_time") or m.get("expirationDate")
    closes_at = None
    if closes_raw:
        try:
            closes_at = datetime.fromisoformat(str(closes_raw).replace("Z", "+00:00"))
        except Exception:
            closes_at = None
    mid = m.get("id") or m.get("marketId") or m.get("slug") or ""
    slug = m.get("slug")
    return MarketRef(
        venue="predict.fun",
        market_id=str(mid),
        title=m.get("question") or m.get("title") or "",
        description=m.get("description") or "",
        category=m.get("category"),
        closes_at=closes_at,
        url=f"https://predict.fun/market/{slug}" if slug else None,
        metadata={"chain": "bnb"},
    )
