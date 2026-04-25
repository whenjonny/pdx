"""SimulatedExecutor: instant fill at the order's limit price (or quote-mid
if provided). Stateless — no real trading. Use as the paper-trade backbone.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Callable
from trumptrade.orders.executor import VenueExecutor
from trumptrade.orders.order import Order, OrderFill


# Optional quote provider — given (venue, market_id) returns a Quote-like with
# yes_ask / no_ask / yes_bid / no_bid; if None, fall back to limit_price.
QuoteFn = Callable[[str, str], object]


class SimulatedExecutor(VenueExecutor):
    venue = "simulated"

    def __init__(self, venue_name: str, quote_fn: QuoteFn | None = None):
        # Override the abstract `venue` attribute so the executor identifies
        # which logical venue it stands in for.
        self.venue = venue_name
        self.quote_fn = quote_fn

    def submit(self, order: Order) -> Order:
        now = datetime.now(timezone.utc)
        order.submitted_at = now

        fill_price = self._infer_fill_price(order)
        if fill_price is None:
            order.status = "error"
            order.error = "no fill price available (no quote_fn and no limit_price)"
            order.finalized_at = now
            return order

        order.fills.append(OrderFill(
            fill_id=uuid.uuid4().hex[:10],
            qty=order.qty_contracts,
            price=fill_price,
            venue_fill_at=now,
        ))
        order.status = "filled"
        order.finalized_at = now
        order.venue_order_id = f"sim-{uuid.uuid4().hex[:8]}"
        return order

    def cancel(self, order: Order) -> Order:
        if order.status in ("filled", "cancelled", "rejected", "error"):
            return order
        order.status = "cancelled"
        order.finalized_at = datetime.now(timezone.utc)
        return order

    def _infer_fill_price(self, order: Order) -> float | None:
        if self.quote_fn:
            try:
                q = self.quote_fn(order.venue, order.market_id)
            except Exception:
                q = None
            if q is not None:
                if order.side == "BUY_YES" and getattr(q, "yes_ask", None) is not None:
                    return float(q.yes_ask)
                if order.side == "BUY_NO" and getattr(q, "no_ask", None) is not None:
                    return float(q.no_ask)
                if order.side == "SELL_YES" and getattr(q, "yes_bid", None) is not None:
                    return float(q.yes_bid)
                if order.side == "SELL_NO" and getattr(q, "no_bid", None) is not None:
                    return float(q.no_bid)
        return order.limit_price
