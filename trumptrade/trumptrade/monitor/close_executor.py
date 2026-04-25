"""Generates close orders. Three modes: alert / paper / live.

`alert` only logs the decision and prints; `paper` writes a paper-trade
record; `live` would actually submit through the venue client. Live is
intentionally not wired without an explicit per-venue trader subclass.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from trumptrade.monitor.position import OpenPosition, ExitReason


Mode = Literal["alert", "paper", "live"]


@dataclass
class CloseOrder:
    position_id: str
    venue: str
    market_id: str
    side: str            # SELL_YES | SELL_NO (mirror of open)
    price_hint: float    # the bid we'd hit
    size_contracts: int
    reason: ExitReason
    detail: str = ""
    emitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def render(self) -> str:
        return (
            f"[CLOSE {self.reason}] {self.side} {self.size_contracts} {self.market_id} on "
            f"{self.venue} @ ~{self.price_hint:.3f}  ({self.detail})"
        )


class CloseExecutor:
    def __init__(self, mode: Mode = "alert", log_path: Path | str | None = None,
                 venue_clients: dict | None = None):
        self.mode = mode
        self.log_path = Path(log_path) if log_path else None
        self.venue_clients = venue_clients or {}

    def close(self, position: OpenPosition, price_hint: float, reason: ExitReason,
              detail: str = "") -> CloseOrder:
        order = CloseOrder(
            position_id=position.id,
            venue=position.venue,
            market_id=position.market_id,
            side="SELL_YES" if position.side == "BUY_YES" else "SELL_NO",
            price_hint=price_hint,
            size_contracts=position.size_contracts,
            reason=reason,
            detail=detail,
        )

        print(order.render())
        if self.log_path:
            self._persist(order)

        if self.mode == "alert":
            return order   # don't actually submit

        if self.mode == "paper":
            # Reference impl: just log; subclasses can hook a paper-trade venue
            return order

        if self.mode == "live":
            client = self.venue_clients.get(position.venue)
            if client is None:
                raise RuntimeError(
                    f"live close for venue {position.venue!r} requires a wired client"
                )
            submit_fn = getattr(client, "submit_close", None)
            if submit_fn is None:
                raise RuntimeError(
                    f"venue client for {position.venue!r} does not implement submit_close()"
                )
            submit_fn(order)
            return order

        raise ValueError(f"unknown mode {self.mode!r}")

    def _persist(self, order: CloseOrder) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(json.dumps({
                "position_id": order.position_id,
                "venue": order.venue,
                "market_id": order.market_id,
                "side": order.side,
                "price_hint": order.price_hint,
                "size_contracts": order.size_contracts,
                "reason": order.reason,
                "detail": order.detail,
                "emitted_at": order.emitted_at.isoformat(),
            }) + "\n")
