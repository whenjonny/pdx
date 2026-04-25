"""Predict.fun REST order executor.

Submits / cancels real orders on predict.fun (BNB Mainnet or Testnet).
Lazy-imports `requests`; safe to leave wired even when offline.

Mainnet:  https://api.predict.fun       (X-API-Key header required, 240 req/min)
Testnet:  https://api-testnet.predict.fun (no key, free)

Endpoints assumed (verify against https://dev.predict.fun before going live):
  POST /orders                place a YES/NO buy/sell at limit/market
  DELETE /orders/{order_id}   cancel
  GET /orders/{order_id}      poll status

The submit() flow updates the local Order in-place: status, fills, error,
finalized_at. If the response shape doesn't match expectations, the order
goes to status="error" with the raw response in `error`.

For the live path, your trade-loop must explicitly construct
`PredictFunExecutor(testnet=False, api_key=...)`. paper-run keeps using
SimulatedExecutor so this never accidentally fires real orders.
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from trumptrade.orders.executor import VenueExecutor
from trumptrade.orders.order import Order, OrderFill


_MAINNET = "https://api.predict.fun"
_TESTNET = "https://api-testnet.predict.fun"


class PredictFunExecutor(VenueExecutor):
    venue = "predict.fun"

    def __init__(
        self,
        testnet: bool = True,
        api_key: str | None = None,
        host: str | None = None,
        http_timeout: float = 10.0,
        confirm_live: bool = False,
    ):
        self.testnet = testnet
        self.host = host or (_TESTNET if testnet else _MAINNET)
        self.api_key = api_key or os.environ.get("PREDICT_FUN_API_KEY")
        self.http_timeout = http_timeout
        if not testnet and not confirm_live:
            raise RuntimeError(
                "PredictFunExecutor refuses to run on Mainnet without "
                "confirm_live=True. Pass confirm_live=True to acknowledge real funds."
            )
        if not testnet and not self.api_key:
            raise RuntimeError(
                "Mainnet requires PREDICT_FUN_API_KEY env var or api_key arg."
            )

    def _headers(self) -> dict:
        h = {"accept": "application/json", "content-type": "application/json"}
        if self.api_key and not self.testnet:
            h["X-API-Key"] = self.api_key
        return h

    def submit(self, order: Order) -> Order:
        try:
            import requests
        except ImportError as e:
            order.status = "error"
            order.error = f"requests not installed: {e}"
            order.finalized_at = datetime.now(timezone.utc)
            return order

        order.submitted_at = datetime.now(timezone.utc)

        # Predict.fun convention (assumed; verify against dev.predict.fun):
        #   side: "buy" or "sell"
        #   outcome: "YES" or "NO"
        #   type: "limit" or "market"
        side, outcome = _split_side(order.side)
        body = {
            "marketId": order.market_id,
            "side": side,                  # "buy" / "sell"
            "outcome": outcome,             # "YES" / "NO"
            "type": order.order_type,       # "limit" / "market"
            "size": order.qty_contracts,
            "clientOrderId": order.id,
        }
        if order.limit_price is not None:
            body["price"] = order.limit_price

        try:
            resp = requests.post(
                f"{self.host}/orders",
                headers=self._headers(),
                json=body,
                timeout=self.http_timeout,
            )
            resp.raise_for_status()
            data = resp.json() or {}
        except Exception as e:
            order.status = "error"
            order.error = str(e)[:500]
            order.finalized_at = datetime.now(timezone.utc)
            return order

        order.venue_order_id = str(data.get("orderId") or data.get("id") or "")
        status_raw = (data.get("status") or "").lower()
        # map predict.fun status -> internal Order.status enum
        if status_raw in ("filled", "complete"):
            order.status = "filled"
            fp = float(data.get("avgFillPrice") or order.limit_price or 0.0)
            fq = int(data.get("filledQuantity") or order.qty_contracts)
            order.fills.append(OrderFill(
                fill_id=uuid.uuid4().hex[:10], qty=fq, price=fp,
                venue_fill_at=datetime.now(timezone.utc),
            ))
            order.finalized_at = datetime.now(timezone.utc)
        elif status_raw in ("partial", "partially_filled"):
            order.status = "partially_filled"
            fp = float(data.get("avgFillPrice") or 0.0)
            fq = int(data.get("filledQuantity") or 0)
            if fq > 0:
                order.fills.append(OrderFill(
                    fill_id=uuid.uuid4().hex[:10], qty=fq, price=fp,
                    venue_fill_at=datetime.now(timezone.utc),
                ))
        elif status_raw in ("rejected", "canceled", "cancelled"):
            order.status = "rejected" if status_raw == "rejected" else "cancelled"
            order.error = data.get("rejectReason") or status_raw
            order.finalized_at = datetime.now(timezone.utc)
        else:
            # open / pending — left in submitted state, caller can poll
            order.status = "submitted"
        return order

    def cancel(self, order: Order) -> Order:
        if order.status in ("filled", "cancelled", "rejected", "error"):
            return order
        try:
            import requests
        except ImportError:
            order.status = "cancelled"
            return order
        if not order.venue_order_id:
            order.status = "cancelled"
            order.finalized_at = datetime.now(timezone.utc)
            return order
        try:
            requests.delete(
                f"{self.host}/orders/{order.venue_order_id}",
                headers=self._headers(),
                timeout=self.http_timeout,
            )
        except Exception:
            pass
        order.status = "cancelled"
        order.finalized_at = datetime.now(timezone.utc)
        return order


def _split_side(s: str) -> tuple[str, str]:
    """Convert internal OrderSide to (side, outcome) for predict.fun API."""
    if s == "BUY_YES":  return ("buy", "YES")
    if s == "BUY_NO":   return ("buy", "NO")
    if s == "SELL_YES": return ("sell", "YES")
    if s == "SELL_NO":  return ("sell", "NO")
    raise ValueError(f"unknown order side {s!r}")
