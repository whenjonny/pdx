"""Polymarket read-only client.

Uses two endpoints (no auth needed):
  - Gamma API (https://gamma-api.polymarket.com)         market metadata + search
  - CLOB API  (https://clob.polymarket.com)              orderbook / prices

Trading on Polymarket requires EIP-712 wallet signing — NOT implemented here.
For executing arb opportunities you'll get a trade plan and sign manually,
or wire `py-clob-client` separately.

Docs: https://docs.polymarket.com/api-reference/introduction
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from trumptrade.markets.base import PredictionMarketClient
from trumptrade.markets.types import MarketRef, Quote


_GAMMA = "https://gamma-api.polymarket.com"
_CLOB = "https://clob.polymarket.com"


class PolymarketClient(PredictionMarketClient):
    venue = "polymarket"

    def __init__(self, http_timeout: float = 10.0):
        self.http_timeout = http_timeout

    # ----- search ---------------------------------------------------------
    def search_markets(self, query: str, limit: int = 20, only_active: bool = True) -> list[MarketRef]:
        """Use Gamma `/events` for free-text search; flatten to one MarketRef per
        binary YES/NO outcome inside an event. Polymarket events can be multi-
        outcome — we currently only emit binary YES/NO refs, ignoring multi-leg
        outcomes (e.g. "Will Trump win [PA] [MI] [WI]" is split into per-state
        binary markets, which is what we want for arb)."""
        try:
            import requests
        except ImportError as e:
            raise ImportError("PolymarketClient requires requests. pip install requests") from e

        params: dict[str, Any] = {"limit": limit, "closed": "false" if only_active else "true"}
        if query:
            params["q"] = query
        try:
            resp = requests.get(f"{_GAMMA}/events", params=params, timeout=self.http_timeout)
            resp.raise_for_status()
            events = resp.json()
        except Exception:
            return []

        refs: list[MarketRef] = []
        for ev in events or []:
            for m in ev.get("markets", []) or []:
                # Polymarket "market" object: has clobTokenIds for YES/NO
                refs.append(_market_to_ref(ev, m))
                if len(refs) >= limit:
                    return refs
        return refs

    # ----- quote ----------------------------------------------------------
    def get_quote(self, market_id: str) -> Quote | None:
        """`market_id` here is the Polymarket condition_id. We fetch the YES
        token's orderbook midpoint via CLOB; NO is derived as 1 - YES."""
        try:
            import requests
        except ImportError as e:
            raise ImportError("PolymarketClient requires requests. pip install requests") from e

        try:
            # Resolve market metadata to get YES token id
            mr = requests.get(f"{_GAMMA}/markets/{market_id}", timeout=self.http_timeout)
            mr.raise_for_status()
            m = mr.json()
            yes_token = _yes_token_id(m)
            if yes_token is None:
                return None

            # YES side prices
            buy = requests.get(f"{_CLOB}/price", params={"token_id": yes_token, "side": "buy"},
                               timeout=self.http_timeout).json()
            sell = requests.get(f"{_CLOB}/price", params={"token_id": yes_token, "side": "sell"},
                                timeout=self.http_timeout).json()
            yes_ask = float(buy.get("price")) if buy.get("price") else None
            yes_bid = float(sell.get("price")) if sell.get("price") else None
        except Exception:
            return None

        return Quote(
            market=_market_to_ref(m, m),
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=(1.0 - yes_ask) if yes_ask is not None else None,
            no_ask=(1.0 - yes_bid) if yes_bid is not None else None,
            last=float(m.get("lastTradePrice")) if m.get("lastTradePrice") else None,
            volume_24h=float(m.get("volume24hr")) if m.get("volume24hr") else None,
            fetched_at=datetime.now(timezone.utc),
        )


def _market_to_ref(event: dict, market: dict) -> MarketRef:
    title = market.get("question") or event.get("title") or ""
    description = market.get("description") or event.get("description") or ""
    closes_at_raw = market.get("endDate") or event.get("endDate")
    closes_at = None
    if closes_at_raw:
        try:
            closes_at = datetime.fromisoformat(closes_at_raw.replace("Z", "+00:00"))
        except Exception:
            closes_at = None
    slug = market.get("slug") or event.get("slug")
    url = f"https://polymarket.com/event/{slug}" if slug else None
    return MarketRef(
        venue="polymarket",
        market_id=market.get("conditionId") or market.get("id") or "",
        title=title,
        description=description,
        category=event.get("category"),
        closes_at=closes_at,
        url=url,
        metadata={
            "clob_token_yes": _yes_token_id(market),
            "clob_token_no": _no_token_id(market),
        },
    )


def _yes_token_id(m: dict) -> str | None:
    tokens = m.get("clobTokenIds")
    if isinstance(tokens, list) and len(tokens) >= 1:
        return tokens[0]
    if isinstance(tokens, str):
        # sometimes returned as JSON string
        import json
        try:
            arr = json.loads(tokens)
            if arr:
                return arr[0]
        except Exception:
            return None
    return None


def _no_token_id(m: dict) -> str | None:
    tokens = m.get("clobTokenIds")
    if isinstance(tokens, list) and len(tokens) >= 2:
        return tokens[1]
    if isinstance(tokens, str):
        import json
        try:
            arr = json.loads(tokens)
            if len(arr) >= 2:
                return arr[1]
        except Exception:
            return None
    return None
