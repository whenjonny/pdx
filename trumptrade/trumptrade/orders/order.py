from __future__ import annotations
import uuid
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


OrderStatus = Literal[
    "pending",      # in store, not yet routed
    "rejected",     # risk check or pre-flight failed
    "submitted",    # sent to venue
    "filled",
    "partially_filled",
    "cancelled",
    "error",
]


OrderSide = Literal["BUY_YES", "BUY_NO", "SELL_YES", "SELL_NO"]
OrderType = Literal["market", "limit"]


class OrderFill(BaseModel):
    fill_id: str
    qty: int
    price: float
    venue_fill_at: Optional[datetime] = None


class Order(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    venue: str
    market_id: str
    market_title: str = ""
    side: OrderSide
    order_type: OrderType = "limit"
    qty_contracts: int
    limit_price: Optional[float] = None
    status: OrderStatus = "pending"

    # Provenance
    decision_id: Optional[str] = None
    agent_name: Optional[str] = None
    source_signal_id: Optional[str] = None

    # Linked legs (e.g. arb pair)
    linked_order_id: Optional[str] = None

    # Resulting position (for opens) or position being closed (for closes)
    position_id: Optional[str] = None

    # Fills
    fills: list[OrderFill] = Field(default_factory=list)

    # Audit
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    submitted_at: Optional[datetime] = None
    finalized_at: Optional[datetime] = None
    venue_order_id: Optional[str] = None
    notes: str = ""
    error: Optional[str] = None

    @property
    def is_open_action(self) -> bool:
        return self.side in ("BUY_YES", "BUY_NO")

    @property
    def is_close_action(self) -> bool:
        return self.side in ("SELL_YES", "SELL_NO")

    @property
    def filled_qty(self) -> int:
        return sum(f.qty for f in self.fills)

    @property
    def avg_fill_price(self) -> Optional[float]:
        total = self.filled_qty
        if total <= 0:
            return None
        return sum(f.qty * f.price for f in self.fills) / total

    @property
    def notional(self) -> float:
        if self.limit_price is None:
            return 0.0
        return round(self.qty_contracts * self.limit_price, 2)
