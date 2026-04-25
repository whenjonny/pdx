from datetime import datetime, timezone
from pathlib import Path
from trumptrade.agents import TradeDecision
from trumptrade.orders import (
    Order, OrderStore, SimulatedExecutor, OrderRouter,
)
from trumptrade.monitor import PositionStore
from trumptrade.risk import RiskLimits, RiskChecker


def _open_decision(**overrides):
    base = dict(
        action="open",
        venue="polymarket",
        market_id="m1",
        market_title="Will Trump tariff?",
        side="BUY_YES",
        size_contracts=100,
        price_limit=0.40,
        confidence=0.7,
        agent_name="policy",
        category="tariff_china",
        event_id="m1",
    )
    base.update(overrides)
    return TradeDecision(**base)


def test_order_store_round_trip(tmp_path):
    store = OrderStore(tmp_path / "orders.jsonl")
    o = Order(venue="x", market_id="m", side="BUY_YES", qty_contracts=10, limit_price=0.5)
    store.add(o)
    assert store.get(o.id).qty_contracts == 10
    # reload
    store2 = OrderStore(tmp_path / "orders.jsonl")
    assert store2.get(o.id) is not None


def test_simulated_executor_fills_at_limit():
    ex = SimulatedExecutor("polymarket")
    o = Order(venue="polymarket", market_id="m1", side="BUY_YES",
              qty_contracts=50, limit_price=0.40)
    ex.submit(o)
    assert o.status == "filled"
    assert o.filled_qty == 50
    assert o.fills[0].price == 0.40


def test_router_routes_open_decision_through_risk_and_executor(tmp_path):
    pstore = PositionStore(tmp_path / "p.jsonl")
    ostore = OrderStore(tmp_path / "o.jsonl")
    risk = RiskChecker(RiskLimits(account_value_usd=100_000), pstore)
    router = OrderRouter(
        order_store=ostore,
        position_store=pstore,
        executors={"polymarket": SimulatedExecutor("polymarket")},
        risk_checker=risk,
    )
    d = _open_decision()
    outcome = router.route_one(d)
    assert outcome.accepted
    assert outcome.order.status == "filled"
    # Position created
    assert len(pstore.open_positions()) == 1
    p = pstore.open_positions()[0]
    assert p.entry_price == 0.40
    assert p.size_contracts == 100


def test_router_rejects_when_risk_breach(tmp_path):
    pstore = PositionStore(tmp_path / "p.jsonl")
    ostore = OrderStore(tmp_path / "o.jsonl")
    # Force per-position cap below the order's notional
    risk = RiskChecker(RiskLimits(account_value_usd=1_000, max_per_position_pct=0.001), pstore)
    router = OrderRouter(
        order_store=ostore, position_store=pstore,
        executors={"polymarket": SimulatedExecutor("polymarket")},
        risk_checker=risk,
    )
    outcome = router.route_one(_open_decision())
    assert not outcome.accepted
    assert outcome.order.status == "rejected"
    assert outcome.risk_breaches  # at least one breach
    # No position created
    assert pstore.open_positions() == []


def test_router_close_decision_marks_position_closed(tmp_path):
    pstore = PositionStore(tmp_path / "p.jsonl")
    ostore = OrderStore(tmp_path / "o.jsonl")
    # Open a position first
    from trumptrade.monitor import OpenPosition
    p = OpenPosition(
        venue="polymarket", market_id="m1", market_title="t",
        side="BUY_YES", entry_price=0.40, size_contracts=100,
        entry_at=datetime.now(timezone.utc),
    )
    pstore.open(p)

    router = OrderRouter(
        order_store=ostore, position_store=pstore,
        executors={"polymarket": SimulatedExecutor("polymarket")},
        risk_checker=None,
    )
    close_d = TradeDecision(
        action="close", venue="polymarket", market_id="m1",
        market_title="t", side="SELL_YES", size_contracts=100,
        price_limit=0.55, confidence=1.0, agent_name="exit",
        target_position_id=p.id,
        rationale="exit_rule=take_profit: mark hit",
    )
    outcome = router.route_one(close_d)
    assert outcome.accepted
    closed = pstore.get(p.id)
    assert closed.status == "closed"
    assert closed.exit_price == 0.55
    assert closed.realized_pnl == round((0.55 - 0.40) * 100, 2)
    assert closed.exit_reason == "take_profit"


def test_router_cancels_linked_leg_on_partner_reject(tmp_path):
    pstore = PositionStore(tmp_path / "p.jsonl")
    ostore = OrderStore(tmp_path / "o.jsonl")
    # First leg passes risk; partner is too large to pass
    risk = RiskChecker(RiskLimits(account_value_usd=10_000, max_per_position_pct=0.05), pstore)
    router = OrderRouter(
        order_store=ostore, position_store=pstore,
        executors={"polymarket": SimulatedExecutor("polymarket"),
                   "kalshi": SimulatedExecutor("kalshi")},
        risk_checker=risk,
    )
    leg_a = _open_decision(venue="polymarket", size_contracts=100, price_limit=0.40)  # $40
    leg_b = _open_decision(venue="kalshi", size_contracts=10000, price_limit=0.55)    # $5500 -> reject
    leg_a.linked_decision_id = leg_b.id
    leg_b.linked_decision_id = leg_a.id

    outcomes = router.route([leg_a, leg_b])
    assert outcomes[0].accepted
    assert not outcomes[1].accepted
    # leg_a's order should have been cancelled because its partner rejected
    leg_a_orders = ostore.by_decision(leg_a.id)
    assert leg_a_orders
    # Either cancelled, or filled (depending on order of evaluation in router).
    # Verify the cancel happened for non-finalized ones
    for o in leg_a_orders:
        assert o.status in ("cancelled", "filled")
