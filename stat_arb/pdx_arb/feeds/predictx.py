"""predictX price feed — reads from on-chain CPMM + backend API."""

from __future__ import annotations

import logging
import math
import time
from typing import Any

import requests

from pdx_arb.config import PredictXConfig
from pdx_arb.types import Venue, VenuePrice

logger = logging.getLogger(__name__)

USDC_DECIMALS = 6
PRICE_SCALE = 1_000_000


class PredictXFeed:
    """Price feed from the predictX platform.

    Reads prices via the backend REST API for speed, falling back to
    direct on-chain calls via web3 when the backend is unavailable.
    """

    def __init__(self, config: PredictXConfig | None = None) -> None:
        self.config = config or PredictXConfig()
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._w3 = None
        self._contract_mgr = None

    def _get_api(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.config.backend_url.rstrip('/')}{path}"
        try:
            r = self._session.get(url, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            logger.debug("predictX API request failed: %s", exc)
            return None

    def _init_web3(self):
        """Lazy-init web3 connection for on-chain reads."""
        if self._w3 is not None:
            return
        try:
            from web3 import Web3
            self._w3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
            if not self._w3.is_connected():
                logger.warning("Web3 not connected to %s", self.config.rpc_url)
                self._w3 = None
        except ImportError:
            logger.warning("web3 not installed, on-chain reads disabled")

    def _get_sdk_client(self):
        """Lazy-init the PDX SDK client for on-chain reads."""
        if self._contract_mgr is not None:
            return self._contract_mgr
        if not self.config.market_address or not self.config.private_key:
            return None
        try:
            import sys
            import os
            sdk_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "predictX", "sdk")
            if sdk_path not in sys.path:
                sys.path.insert(0, sdk_path)
            from pdx_sdk.client import PDXClient
            self._contract_mgr = PDXClient(
                rpc_url=self.config.rpc_url,
                private_key=self.config.private_key,
                market_address=self.config.market_address,
                usdc_address=self.config.usdc_address,
                backend_url=self.config.backend_url,
            )
            return self._contract_mgr
        except Exception as exc:
            logger.debug("Failed to init PDX SDK: %s", exc)
            return None

    def fetch_active_markets(self) -> list[dict]:
        """Fetch all active (unresolved) markets from the backend."""
        data = self._get_api("/api/markets")
        if data is None:
            return self._fetch_markets_onchain()
        markets = []
        for m in (data if isinstance(data, list) else data.get("markets", [])):
            if m.get("resolved", False):
                continue
            price_yes = m.get("priceYes", 0)
            price_no = m.get("priceNo", 0)
            if isinstance(price_yes, int) and price_yes > 1:
                price_yes = price_yes / PRICE_SCALE
                price_no = price_no / PRICE_SCALE
            markets.append({
                "market_id": m.get("id", 0),
                "question": m.get("question", ""),
                "price_yes": float(price_yes),
                "price_no": float(price_no),
                "reserve_yes": m.get("reserveYes", 0),
                "reserve_no": m.get("reserveNo", 0),
                "k": m.get("k", 0),
                "deadline": m.get("deadline", 0),
                "total_deposited": m.get("totalDeposited", 0),
                "fees_accrued": m.get("feesAccrued", 0),
            })
        return markets

    def _fetch_markets_onchain(self) -> list[dict]:
        """Fallback: read markets directly from the smart contract."""
        client = self._get_sdk_client()
        if client is None:
            return []
        try:
            all_markets = client.list_markets()
            return [
                {
                    "market_id": m.id,
                    "question": m.question,
                    "price_yes": m.priceYes / PRICE_SCALE,
                    "price_no": m.priceNo / PRICE_SCALE,
                    "reserve_yes": m.reserveYes,
                    "reserve_no": m.reserveNo,
                    "k": m.k,
                    "deadline": m.deadline,
                    "total_deposited": m.totalDeposited,
                    "fees_accrued": m.feesAccrued,
                }
                for m in all_markets
                if not m.resolved
            ]
        except Exception as exc:
            logger.error("On-chain market fetch failed: %s", exc)
            return []

    def get_price(self, market_id: int) -> VenuePrice:
        """Get current price for a predictX market."""
        data = self._get_api(f"/api/markets/{market_id}")
        if data is not None:
            price_yes = data.get("priceYes", 0)
            price_no = data.get("priceNo", 0)
            if isinstance(price_yes, int) and price_yes > 1:
                price_yes = price_yes / PRICE_SCALE
                price_no = price_no / PRICE_SCALE
            reserve_yes = data.get("reserveYes", 0)
            reserve_no = data.get("reserveNo", 0)
            liquidity = (reserve_yes + reserve_no) / PRICE_SCALE if reserve_yes > PRICE_SCALE else 0
            return VenuePrice(
                venue=Venue.PREDICTX,
                yes_price=float(price_yes),
                no_price=float(price_no),
                liquidity=liquidity,
            )
        return VenuePrice(venue=Venue.PREDICTX, yes_price=0, no_price=0, liquidity=0)

    def estimate_slippage(self, market_id: int, side: str, size_usd: float) -> float:
        """Estimate price impact of a trade on the CPMM.

        Returns the effective price after slippage (0-1 scale).
        For a CPMM: tokens_out = reserveOut - k / (reserveIn + amountIn)
        Effective price = amountIn / tokens_out
        """
        data = self._get_api(f"/api/markets/{market_id}")
        if data is None:
            return 0.0
        reserve_yes = data.get("reserveYes", 0)
        reserve_no = data.get("reserveNo", 0)
        k = data.get("k", 0)
        if k == 0 or reserve_yes == 0 or reserve_no == 0:
            return 0.0

        amount_in = size_usd * PRICE_SCALE
        fee_rate = self.config.fee_bps_normal / 10_000
        amount_after_fee = amount_in * (1 - fee_rate)

        if side == "buy_yes":
            tokens_out = reserve_yes - k / (reserve_no + amount_after_fee)
        else:
            tokens_out = reserve_no - k / (reserve_yes + amount_after_fee)

        if tokens_out <= 0:
            return 1.0
        effective_price = amount_in / tokens_out / PRICE_SCALE
        return min(effective_price, 1.0)
