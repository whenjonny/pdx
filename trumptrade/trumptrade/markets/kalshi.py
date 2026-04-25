"""Kalshi read-only client.

Public endpoints (`/trade-api/v2/markets`, `/trade-api/v2/markets/{ticker}`)
do NOT require authentication for browsing/quoting. Trading does — login via
email/password returns a 24-hour JWT.

Docs: https://trading-api.readme.io/reference/getmarkets
Live host: https://api.elections.kalshi.com (regulated US events) /
           https://demo-api.kalshi.co (demo)
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Optional
from trumptrade.markets.base import PredictionMarketClient
from trumptrade.markets.types import MarketRef, Quote


_DEFAULT_HOST = "https://api.elections.kalshi.com"


class KalshiClient(PredictionMarketClient):
    venue = "kalshi"

    def __init__(self, host: str | None = None, http_timeout: float = 10.0,
                 email: str | None = None, password: str | None = None):
        self.host = host or os.environ.get("KALSHI_HOST", _DEFAULT_HOST)
        self.http_timeout = http_timeout
        self.email = email or os.environ.get("KALSHI_EMAIL")
        self.password = password or os.environ.get("KALSHI_PASSWORD")
        self._jwt: Optional[str] = None

    # ----- auth (only needed for trading; reads are public) ----------------
    def login(self) -> str | None:
        if not (self.email and self.password):
            return None
        try:
            import requests
        except ImportError as e:
            raise ImportError("KalshiClient requires requests. pip install requests") from e
        try:
            r = requests.post(f"{self.host}/trade-api/v2/login",
                              json={"email": self.email, "password": self.password},
                              timeout=self.http_timeout)
            r.raise_for_status()
            self._jwt = r.json().get("token")
            return self._jwt
        except Exception:
            return None

    # ----- search ----------------------------------------------------------
    def search_markets(self, query: str, limit: int = 20, only_active: bool = True) -> list[MarketRef]:
        try:
            import requests
        except ImportError as e:
            raise ImportError("KalshiClient requires requests. pip install requests") from e
        params = {"limit": min(limit, 1000)}
        if only_active:
            params["status"] = "open"
        try:
            r = requests.get(f"{self.host}/trade-api/v2/markets", params=params, timeout=self.http_timeout)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []

        # Kalshi search isn't full-text on the API; do client-side filter.
        q = (query or "").lower().strip()
        refs: list[MarketRef] = []
        for m in data.get("markets") or []:
            title = (m.get("title") or m.get("yes_sub_title") or "")
            subtitle = (m.get("subtitle") or "")
            blob = f"{title} {subtitle}".lower()
            if q and q not in blob:
                continue
            refs.append(_market_to_ref(m))
            if len(refs) >= limit:
                break
        return refs

    # ----- quote -----------------------------------------------------------
    def get_quote(self, market_id: str) -> Quote | None:
        try:
            import requests
        except ImportError as e:
            raise ImportError("KalshiClient requires requests. pip install requests") from e
        try:
            r = requests.get(f"{self.host}/trade-api/v2/markets/{market_id}", timeout=self.http_timeout)
            r.raise_for_status()
            data = r.json()
            m = data.get("market") or {}
        except Exception:
            return None
        if not m:
            return None

        # Kalshi prices are in cents (0-100). Normalize to 0-1.
        def cents(v):
            if v is None:
                return None
            try:
                return float(v) / 100.0
            except Exception:
                return None

        return Quote(
            market=_market_to_ref(m),
            yes_bid=cents(m.get("yes_bid")),
            yes_ask=cents(m.get("yes_ask")),
            no_bid=cents(m.get("no_bid")),
            no_ask=cents(m.get("no_ask")),
            last=cents(m.get("last_price")),
            volume_24h=float(m.get("volume_24h")) if m.get("volume_24h") else None,
            fetched_at=datetime.now(timezone.utc),
        )


def _market_to_ref(m: dict) -> MarketRef:
    closes_at_raw = m.get("close_time") or m.get("expected_expiration_time")
    closes_at = None
    if closes_at_raw:
        try:
            closes_at = datetime.fromisoformat(closes_at_raw.replace("Z", "+00:00"))
        except Exception:
            closes_at = None
    ticker = m.get("ticker") or m.get("market_ticker") or ""
    return MarketRef(
        venue="kalshi",
        market_id=ticker,
        title=m.get("title") or m.get("yes_sub_title") or "",
        description=m.get("subtitle") or m.get("rules_primary") or "",
        category=m.get("category"),
        closes_at=closes_at,
        url=f"https://kalshi.com/markets/{ticker}" if ticker else None,
        metadata={"event_ticker": m.get("event_ticker")},
    )
