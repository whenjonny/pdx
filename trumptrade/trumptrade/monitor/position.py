from __future__ import annotations
import uuid
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


PositionStatus = Literal["open", "closing", "closed"]


ExitReason = Literal[
    "arb_convergence",      # locked spread closed; pull profit
    "walkback",             # Trump reversed -> close
    "time_decay",           # market expires soon
    "stop_loss",            # mark moved against by N%
    "take_profit",          # mark hit target
    "liquidity_drop",       # 24h volume too thin
    "manual",               # user override
    "risk_breach",          # risk limit forces close
]


class OpenPosition(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    venue: str
    market_id: str
    market_title: str
    side: Literal["BUY_YES", "BUY_NO"]
    entry_price: float
    size_contracts: int
    entry_at: datetime
    base_currency: str = "USD"

    # Exit parameters set at open time
    take_profit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    max_hold_until: Optional[datetime] = None

    # Arb-pair coordination — if this position is one leg of an arb, the
    # combined-cost target signals when to peel the pair off
    target_arb_close_cost: Optional[float] = None
    linked_position_id: Optional[str] = None

    # Provenance
    source_signal_id: Optional[str] = None
    source_alert_id: Optional[str] = None
    note: str = ""

    # Live state (mutated by monitor loop)
    current_mark: Optional[float] = None
    current_volume_24h: Optional[float] = None
    last_polled_at: Optional[datetime] = None
    status: PositionStatus = "open"
    exit_reason: Optional[ExitReason] = None
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None

    @property
    def notional_at_entry(self) -> float:
        return round(self.entry_price * self.size_contracts, 2)

    @property
    def unrealized_pnl(self) -> Optional[float]:
        if self.current_mark is None:
            return None
        # For binary contracts, entry was paid; mark is current YES (or NO) mid
        return round((self.current_mark - self.entry_price) * self.size_contracts, 2)

    def mark_closed(self, exit_price: float, reason: ExitReason, at: datetime) -> None:
        self.status = "closed"
        self.exit_reason = reason
        self.closed_at = at
        self.exit_price = exit_price
        self.realized_pnl = round((exit_price - self.entry_price) * self.size_contracts, 2)
