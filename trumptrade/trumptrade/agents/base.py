"""Agent layer: signals -> formalized TradeDecisions.

Every agent reads a Signal (or a bundle of signals + state) and produces a
list of structured decisions. Decisions are then fed into orders.OrderRouter
which applies pre-trade risk checks and dispatches to a venue executor.

This module owns the contract; concrete agents (policy / arb / exit / ...)
implement the analysis logic.
"""
from __future__ import annotations
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field
from trumptrade.types import Signal


DecisionAction = Literal["open", "close", "scale_in", "scale_out", "no_action"]


class TradeDecision(BaseModel):
    """Output of any agent. Routed through OrderRouter."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    action: DecisionAction
    venue: str
    market_id: str
    market_title: str = ""
    side: str = ""                                 # BUY_YES | BUY_NO | SELL_YES | SELL_NO
    size_contracts: int = 0
    price_limit: Optional[float] = None             # max ask (buys) / min bid (sells)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    agent_name: str
    source_signal_id: Optional[str] = None
    source_alert_id: Optional[str] = None
    target_position_id: Optional[str] = None        # for close / scale_out
    suggested_stop_loss: Optional[float] = None
    suggested_take_profit: Optional[float] = None
    suggested_max_hold_until: Optional[datetime] = None
    target_arb_close_cost: Optional[float] = None   # for arb pair coordination
    linked_decision_id: Optional[str] = None        # arb leg pairing
    category: Optional[str] = None
    event_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now())

    def is_open(self) -> bool:
        return self.action in ("open", "scale_in")

    def is_close(self) -> bool:
        return self.action in ("close", "scale_out")


@dataclass
class AgentContext:
    """Anything an agent needs from the rest of the system. Kept dataclass
    so agents don't carry circular imports."""
    playbook: dict
    position_store: object | None = None    # PositionStore
    venue_registry: object | None = None    # VenueRegistry
    risk_checker: object | None = None      # RiskChecker
    extra: dict | None = None


class Agent(ABC):
    name: str = "agent"

    @abstractmethod
    def analyze(self, signal: Signal, ctx: AgentContext) -> list[TradeDecision]:
        ...
