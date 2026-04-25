"""OrderRouter: ties together TradeDecisions, RiskChecker, OrderStore,
VenueExecutors, and PositionStore.

Flow per decision:
  1. translate decision -> Order(s)
  2. risk check (open decisions only — closes are not gated on risk)
  3. submit to venue executor
  4. on fill, update PositionStore (open: insert; close: mark closed)

Linked decisions (arb pair):
  Both legs are submitted; if EITHER leg fails risk or rejects, both are
  cancelled (best-effort) so we never carry naked legs.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from trumptrade.agents.base import TradeDecision
from trumptrade.orders.order import Order
from trumptrade.orders.store import OrderStore
from trumptrade.orders.executor import VenueExecutor
from trumptrade.monitor.position import OpenPosition


@dataclass
class RouteOutcome:
    decision_id: str
    accepted: bool
    order: Optional[Order] = None
    reason: str = ""
    risk_breaches: list = field(default_factory=list)


def _decision_to_order(d: TradeDecision) -> Order:
    return Order(
        venue=d.venue,
        market_id=d.market_id,
        market_title=d.market_title,
        side=d.side,
        order_type="limit" if d.price_limit is not None else "market",
        qty_contracts=int(d.size_contracts),
        limit_price=d.price_limit,
        decision_id=d.id,
        agent_name=d.agent_name,
        source_signal_id=d.source_signal_id,
        position_id=d.target_position_id,
    )


class OrderRouter:
    def __init__(
        self,
        order_store: OrderStore,
        position_store,            # PositionStore
        executors: dict[str, VenueExecutor],
        risk_checker=None,
    ):
        self.order_store = order_store
        self.position_store = position_store
        self.executors = executors
        self.risk_checker = risk_checker

    # ---- public API --------------------------------------------------------

    def route_one(self, d: TradeDecision) -> RouteOutcome:
        if d.action in ("no_action",):
            return RouteOutcome(decision_id=d.id, accepted=False, reason="no_action")

        order = _decision_to_order(d)
        self.order_store.add(order)

        # Risk gate (open decisions only — closes are emergency exits)
        if d.is_open() and self.risk_checker is not None:
            verdict = self.risk_checker.check(
                venue=d.venue,
                category=d.category,
                event_id=d.event_id,
                intended_notional=order.notional,
            )
            if not verdict.allowed:
                order.status = "rejected"
                order.error = "; ".join(b.rule for b in verdict.breaches)
                order.finalized_at = datetime.now(timezone.utc)
                self.order_store.update(order)
                return RouteOutcome(decision_id=d.id, accepted=False,
                                    order=order, reason="risk_rejected",
                                    risk_breaches=verdict.breaches)
            if verdict.notional_allowed > 0 and order.limit_price:
                # Down-size to allowed notional
                shares_allowed = int(verdict.notional_allowed / order.limit_price)
                if 0 < shares_allowed < order.qty_contracts:
                    order.qty_contracts = shares_allowed
                    order.notes = f"down-sized to risk-allowed {shares_allowed}"
                    self.order_store.update(order)

        executor = self.executors.get(d.venue)
        if executor is None:
            order.status = "error"
            order.error = f"no executor for venue {d.venue!r}"
            order.finalized_at = datetime.now(timezone.utc)
            self.order_store.update(order)
            return RouteOutcome(decision_id=d.id, accepted=False, order=order,
                                reason="no_executor")

        try:
            executor.submit(order)
        except Exception as e:
            order.status = "error"
            order.error = str(e)
            order.finalized_at = datetime.now(timezone.utc)
            self.order_store.update(order)
            return RouteOutcome(decision_id=d.id, accepted=False, order=order,
                                reason=f"executor_error: {e}")
        self.order_store.update(order)

        if order.status == "filled":
            self._reconcile_to_position(d, order)

        return RouteOutcome(
            decision_id=d.id,
            accepted=order.status in ("filled", "submitted", "partially_filled"),
            order=order,
            reason=order.status,
        )

    def route(self, decisions: list[TradeDecision]) -> list[RouteOutcome]:
        """Routes a batch. Linked legs are submitted; if any rejects, others
        with same linked_decision_id chain are cancelled best-effort."""
        outcomes: list[RouteOutcome] = []
        by_id: dict[str, TradeDecision] = {d.id: d for d in decisions}
        rejected_ids: set[str] = set()

        for d in decisions:
            # If our linked partner already rejected, skip this leg
            if d.linked_decision_id and d.linked_decision_id in rejected_ids:
                outcomes.append(RouteOutcome(
                    decision_id=d.id, accepted=False,
                    reason="linked_leg_rejected",
                ))
                continue
            r = self.route_one(d)
            outcomes.append(r)
            if not r.accepted and d.linked_decision_id:
                rejected_ids.add(d.id)
                # Best effort: cancel the partner if it was already submitted
                partner = by_id.get(d.linked_decision_id)
                if partner is not None:
                    self._cancel_decision_orders(partner.id)
        return outcomes

    # ---- internals ---------------------------------------------------------

    def _reconcile_to_position(self, d: TradeDecision, order: Order) -> None:
        """Update PositionStore based on the filled order."""
        fill_price = order.avg_fill_price or order.limit_price or 0.0

        if d.is_open():
            pos = OpenPosition(
                venue=d.venue,
                market_id=d.market_id,
                market_title=d.market_title,
                side="BUY_YES" if d.side == "BUY_YES" else "BUY_NO",
                entry_price=fill_price,
                size_contracts=order.filled_qty,
                entry_at=datetime.now(timezone.utc),
                source_signal_id=d.source_signal_id,
                source_alert_id=d.source_alert_id,
                take_profit_price=d.suggested_take_profit,
                stop_loss_price=d.suggested_stop_loss,
                max_hold_until=d.suggested_max_hold_until,
                target_arb_close_cost=d.target_arb_close_cost,
                note=f"category:{d.category}" if d.category else "",
            )
            self.position_store.open(pos)
            order.position_id = pos.id
            self.order_store.update(order)
        elif d.is_close() and d.target_position_id:
            try:
                self.position_store.close(
                    d.target_position_id,
                    exit_price=fill_price,
                    reason=_close_reason_from_rationale(d.rationale),
                )
            except KeyError:
                pass

    def _cancel_decision_orders(self, decision_id: str) -> None:
        for o in self.order_store.by_decision(decision_id):
            if o.status not in ("filled", "cancelled", "rejected", "error"):
                executor = self.executors.get(o.venue)
                if executor is not None:
                    try:
                        executor.cancel(o)
                    except Exception:
                        o.status = "cancelled"
                self.order_store.update(o)


def _close_reason_from_rationale(text: str):
    """Pick out exit_rule=... from an ExitAgent-produced rationale, fall back
    to 'manual'."""
    if "exit_rule=" in text:
        try:
            tag = text.split("exit_rule=", 1)[1].split(":", 1)[0].strip()
            valid = {"arb_convergence", "walkback", "stop_loss", "take_profit",
                     "time_decay", "liquidity_drop", "manual", "risk_breach"}
            if tag in valid:
                return tag
        except Exception:
            pass
    return "manual"
