"""Tests for the event-driven backtest system."""

from __future__ import annotations

import numpy as np
import pytest

from pdx_backtest.data import generate_binary_path, generate_negrisk_scenario, generate_cross_platform_path
from pdx_backtest.event_engine import (
    EventEngine, MarketSimulator, OrderBookSimulator,
    MarketTick, OrderSubmitted, OrderFill, OrderReject, Settlement,
)
from pdx_backtest.friction import FrictionParams
from pdx_backtest.metrics import compute_metrics
from pdx_backtest.oms import OrderManagementSystem
from pdx_backtest.portfolio import Portfolio, Position, ClosedTrade
from pdx_backtest.risk_manager import RiskLimits, RiskManager
from pdx_backtest.strategies.event_strategies import (
    EventNegRiskRebalancer,
    EventSingleBinaryRebalancer,
    EventStatArb,
    EventCrossVenueArb,
    EventLongshotBiasExploiter,
)


# ---------------------------------------------------------------------------
# Event engine basics
# ---------------------------------------------------------------------------


class TestEventEngine:
    def test_event_ordering(self):
        engine = EventEngine(seed=1)
        events = []
        engine.register(MarketTick, lambda e: events.append(e.timestamp))
        engine.schedule(MarketTick(timestamp=3.0, market_id="a", yes_price=0.5, no_price=0.5))
        engine.schedule(MarketTick(timestamp=1.0, market_id="b", yes_price=0.5, no_price=0.5))
        engine.schedule(MarketTick(timestamp=2.0, market_id="c", yes_price=0.5, no_price=0.5))
        engine.run()
        assert events == [1.0, 2.0, 3.0]

    def test_run_until(self):
        engine = EventEngine(seed=1)
        for i in range(10):
            engine.schedule(MarketTick(timestamp=float(i), market_id="m", yes_price=0.5, no_price=0.5))
        engine.run(until=5.0)
        assert engine.clock == 5.0
        assert engine.pending > 0

    def test_handler_can_schedule_events(self):
        engine = EventEngine(seed=1)
        fired = []
        def handler(e):
            fired.append(e.timestamp)
            if e.timestamp < 3.0:
                engine.schedule(MarketTick(timestamp=e.timestamp + 1.0, market_id="m", yes_price=0.5, no_price=0.5))
        engine.register(MarketTick, handler)
        engine.schedule(MarketTick(timestamp=0.0, market_id="m", yes_price=0.5, no_price=0.5))
        engine.run()
        assert fired == [0.0, 1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# Market simulator
# ---------------------------------------------------------------------------


class TestMarketSimulator:
    def test_binary_market_ticks(self):
        engine = EventEngine(seed=1)
        rng = np.random.default_rng(1)
        ms = MarketSimulator(engine, rng)
        path = generate_binary_path(n_steps=50, seed=1)
        ms.load_binary_market("test_market", path)

        ticks = []
        engine.register(MarketTick, lambda e: ticks.append(e))
        engine.run()

        assert len(ticks) == 50
        assert all(t.market_id == "test_market" for t in ticks)
        assert all(0.001 <= t.yes_price <= 0.999 for t in ticks)

    def test_settlement_events(self):
        engine = EventEngine(seed=1)
        rng = np.random.default_rng(1)
        ms = MarketSimulator(engine, rng)
        path = generate_binary_path(n_steps=10, seed=1)
        ms.load_binary_market("m1", path)
        ms.schedule_settlements(20.0)

        settlements = []
        engine.register(Settlement, lambda e: settlements.append(e))
        engine.run()

        assert len(settlements) == 1
        assert settlements[0].market_id == "m1"
        assert settlements[0].outcome in ("yes", "no")

    def test_cross_venue_ticks(self):
        engine = EventEngine(seed=1)
        rng = np.random.default_rng(1)
        ms = MarketSimulator(engine, rng)
        path = generate_cross_platform_path(n_steps=50, seed=1)
        ms.load_cross_venue("poly_1", "predict_1", path)

        ticks = []
        engine.register(MarketTick, lambda e: ticks.append(e))
        engine.run()

        poly_ticks = [t for t in ticks if t.market_id == "poly_1"]
        predict_ticks = [t for t in ticks if t.market_id == "predict_1"]
        assert len(poly_ticks) == 50
        assert len(predict_ticks) == 50

    def test_negrisk_ticks(self):
        engine = EventEngine(seed=1)
        rng = np.random.default_rng(1)
        ms = MarketSimulator(engine, rng)
        snaps = generate_negrisk_scenario(n_outcomes=5, n_snapshots=20, seed=1)
        ms.load_negrisk("event_0", snaps)

        ticks = []
        engine.register(MarketTick, lambda e: ticks.append(e))
        engine.run()

        assert len(ticks) == 20 * 5  # 5 outcomes * 20 snapshots


# ---------------------------------------------------------------------------
# OMS
# ---------------------------------------------------------------------------


class TestOMS:
    def _setup_engine(self, friction=None):
        engine = EventEngine(seed=42)
        rng = np.random.default_rng(42)
        f = friction or FrictionParams.none()
        oms = OrderManagementSystem(engine, default_friction=f, rng=rng)
        return engine, oms

    def test_market_order_fills(self):
        engine, oms = self._setup_engine()
        fills = []
        engine.register(OrderFill, lambda e: fills.append(e))

        engine.schedule(MarketTick(timestamp=0.0, market_id="m1", yes_price=0.5, no_price=0.5))
        engine.schedule(OrderSubmitted(
            timestamp=1.0, order_id="O1", market_id="m1",
            side="buy_yes", order_type="market", size=100.0, strategy_name="test",
        ))
        engine.run()

        assert len(fills) == 1
        assert fills[0].order_id == "O1"
        assert fills[0].fill_size > 0

    def test_execution_failure(self):
        engine, oms = self._setup_engine(FrictionParams(execution_failure_rate=1.0))
        rejects = []
        engine.register(OrderReject, lambda e: rejects.append(e))

        engine.schedule(MarketTick(timestamp=0.0, market_id="m1", yes_price=0.5, no_price=0.5))
        engine.schedule(OrderSubmitted(
            timestamp=1.0, order_id="O1", market_id="m1",
            side="buy_yes", order_type="market", size=100.0, strategy_name="test",
        ))
        engine.run()

        assert len(rejects) == 1
        assert "execution_failure" in rejects[0].reason


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


class TestPortfolio:
    def test_open_and_settle(self):
        engine = EventEngine(seed=42)
        portfolio = Portfolio(engine, initial_capital=10_000.0)

        engine.schedule(MarketTick(timestamp=0.0, market_id="m1", yes_price=0.5, no_price=0.5))
        engine.schedule(OrderFill(
            timestamp=1.0, order_id="O1", market_id="m1",
            side="buy_yes", fill_size=100.0, fill_price=0.5,
            strategy_name="test",
        ))
        engine.schedule(Settlement(timestamp=10.0, market_id="m1", outcome="yes", settlement_price=1.0))
        engine.run()

        assert portfolio.cash == pytest.approx(10_000.0 - 100.0 + 200.0)
        assert len(portfolio.closed_trades) == 1
        assert portfolio.closed_trades[0].pnl > 0

    def test_equity_tracking(self):
        engine = EventEngine(seed=42)
        portfolio = Portfolio(engine, initial_capital=10_000.0)
        assert portfolio.equity == 10_000.0

        engine.schedule(OrderFill(
            timestamp=1.0, order_id="O1", market_id="m1",
            side="buy_yes", fill_size=500.0, fill_price=0.5,
            strategy_name="test",
        ))
        engine.schedule(MarketTick(timestamp=2.0, market_id="m1", yes_price=0.6, no_price=0.4))
        engine.run()

        assert portfolio.equity > 10_000.0


# ---------------------------------------------------------------------------
# Risk manager
# ---------------------------------------------------------------------------


class TestRiskManager:
    def test_drawdown_halt(self):
        engine = EventEngine(seed=42)
        portfolio = Portfolio(engine, initial_capital=1_000.0)
        limits = RiskLimits(max_drawdown_pct=0.10)
        rm = RiskManager(engine, portfolio, limits)

        engine.schedule(OrderFill(
            timestamp=1.0, order_id="O1", market_id="m1",
            side="buy_yes", fill_size=200.0, fill_price=0.5,
            strategy_name="test",
        ))
        engine.schedule(MarketTick(timestamp=2.0, market_id="m1", yes_price=0.2, no_price=0.8))
        engine.schedule(OrderSubmitted(
            timestamp=3.0, order_id="O2", market_id="m2",
            side="buy_yes", order_type="market", size=100.0, strategy_name="test",
        ))
        engine.run()

        assert rm.is_rejected("O2")

    def test_size_multiplier(self):
        engine = EventEngine(seed=42)
        portfolio = Portfolio(engine, initial_capital=10_000.0)
        limits = RiskLimits(
            reduce_size_after_drawdown_pct=0.05,
            max_drawdown_pct=0.15,
            min_size_multiplier=0.25,
        )
        rm = RiskManager(engine, portfolio, limits)
        assert rm.recommended_size_multiplier() == 1.0

    def test_trade_size_limits(self):
        engine = EventEngine(seed=42)
        portfolio = Portfolio(engine, initial_capital=10_000.0)
        limits = RiskLimits(max_single_trade_notional=100.0)
        rm = RiskManager(engine, portfolio, limits)

        engine.schedule(OrderSubmitted(
            timestamp=1.0, order_id="O1", market_id="m1",
            side="buy_yes", order_type="market", size=500.0, strategy_name="test",
        ))
        engine.run()

        assert rm.is_rejected("O1")


# ---------------------------------------------------------------------------
# Strategy integration
# ---------------------------------------------------------------------------


class TestStrategies:
    def _build_system(self, initial_capital=100_000.0):
        engine = EventEngine(seed=42)
        rng = np.random.default_rng(42)
        portfolio = Portfolio(engine, initial_capital=initial_capital)
        risk_mgr = RiskManager(engine, portfolio, RiskLimits(
            max_open_positions=200, max_strategy_positions=80,
        ))
        oms = OrderManagementSystem(
            engine, default_friction=FrictionParams.polymarket(),
            rng=rng, risk_manager=risk_mgr,
        )
        OrderBookSimulator(engine, rng)
        ms = MarketSimulator(engine, rng)
        return engine, portfolio, risk_mgr, oms, ms

    def test_negrisk_generates_trades(self):
        engine, portfolio, rm, oms, ms = self._build_system()
        snaps = generate_negrisk_scenario(n_outcomes=5, n_snapshots=100, seed=1)
        ms.load_negrisk("ev0", snaps)
        ms.schedule_settlements(110.0)

        strat = EventNegRiskRebalancer(engine, oms, rm, threshold=0.01, capital_per_trade=500.0)
        engine.run()

        assert strat._filled_count > 0

    def test_stat_arb_generates_trades(self):
        engine, portfolio, rm, oms, ms = self._build_system()
        for i in range(5):
            path = generate_binary_path(n_steps=200, seed=42 + i)
            ms.load_binary_market(f"binary_{i}", path)
        ms.schedule_settlements(210.0)

        strat = EventStatArb(engine, oms, rm, ema_span=20, min_edge=0.02, bankroll=5000.0)
        engine.run()

        assert strat._filled_count > 0

    def test_cross_venue_generates_trades(self):
        engine, portfolio, rm, oms, ms = self._build_system()
        for i in range(3):
            path = generate_cross_platform_path(n_steps=200, seed=42 + i)
            ms.load_cross_venue(f"poly_{i}", f"predict_{i}", path)
        ms.schedule_settlements(210.0)

        strat = EventCrossVenueArb(engine, oms, rm, min_spread=0.01, capital_per_trade=500.0)
        for i in range(3):
            strat.register_pair(f"poly_{i}", f"predict_{i}")
        engine.run()

        assert strat._filled_count > 0

    def test_end_to_end_deterministic(self):
        """Same seed produces same results."""
        results = []
        for _ in range(2):
            engine, portfolio, rm, oms, ms = self._build_system()
            path = generate_binary_path(n_steps=100, seed=42)
            ms.load_binary_market("m0", path)
            ms.schedule_settlements(110.0)

            EventSingleBinaryRebalancer(engine, oms, rm, threshold=0.005, capital_per_trade=500.0)
            engine.run()
            results.append(portfolio.total_pnl)

        assert results[0] == pytest.approx(results[1])

    def test_risk_manager_blocks_excessive_trades(self):
        engine, portfolio, rm, oms, ms = self._build_system(initial_capital=1_000.0)
        rm._limits.max_strategy_loss = 100.0

        for i in range(10):
            path = generate_binary_path(n_steps=200, seed=42 + i)
            ms.load_binary_market(f"m_{i}", path)
        ms.schedule_settlements(210.0)

        strat = EventStatArb(engine, oms, rm, ema_span=10, min_edge=0.01, bankroll=5000.0)
        engine.run()

        strat_pnl = portfolio.strategy_pnl(strat.name)
        assert strat_pnl > -1000.0

    def test_portfolio_summary_has_required_fields(self):
        engine, portfolio, rm, oms, ms = self._build_system()
        s = portfolio.summary()
        required = ["initial_capital", "cash", "equity", "total_pnl",
                     "realized_pnl", "n_closed_trades", "win_rate"]
        for field in required:
            assert field in s
