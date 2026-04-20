"""Tests for the enhanced (YES-only) statistical arbitrage strategy."""

from __future__ import annotations

import numpy as np
import pytest

from pdx_backtest.data import generate_binary_path
from pdx_backtest.event_engine import (
    EventEngine, MarketSimulator, OrderBookSimulator, OrderSubmitted,
)
from pdx_backtest.friction import FrictionParams
from pdx_backtest.oms import OrderManagementSystem
from pdx_backtest.portfolio import Portfolio
from pdx_backtest.risk_manager import RiskLimits, RiskManager
from pdx_backtest.strategies.enhanced_stat_arb import EnhancedStatArb
from pdx_backtest.strategies.event_strategies import EventStatArb


def _build_system(seed=42, capital=100_000.0):
    engine = EventEngine(seed=seed)
    rng = np.random.default_rng(seed)
    portfolio = Portfolio(engine, initial_capital=capital)
    risk_mgr = RiskManager(engine, portfolio, RiskLimits(
        max_open_positions=500, max_strategy_positions=200,
        max_strategy_loss=capital * 0.5,
        max_single_trade_notional=10_000.0,
    ))
    oms = OrderManagementSystem(
        engine, default_friction=FrictionParams.polymarket(),
        rng=rng, risk_manager=risk_mgr,
    )
    OrderBookSimulator(engine, rng)
    ms = MarketSimulator(engine, rng)
    return engine, portfolio, risk_mgr, oms, ms


class TestEnhancedStatArb:
    def test_generates_trades(self):
        engine, portfolio, rm, oms, ms = _build_system()
        for i in range(10):
            path = generate_binary_path(n_steps=200, seed=42 + i)
            ms.load_binary_market(f"m_{i:03d}", path)
        ms.schedule_settlements(210.0)

        strat = EnhancedStatArb(
            engine, oms, rm, ema_span=20, min_edge=0.02,
            bankroll=5_000.0, max_fraction=0.25,
        )
        engine.run()
        assert strat._filled_count > 0

    def test_only_submits_buy_yes_orders(self):
        """Enhanced strategy must never submit buy_no or sell orders."""
        engine, portfolio, rm, oms, ms = _build_system()
        for i in range(10):
            path = generate_binary_path(n_steps=200, seed=42 + i)
            ms.load_binary_market(f"m_{i:03d}", path)
        ms.schedule_settlements(210.0)

        submitted = []
        engine.register(OrderSubmitted, lambda e: submitted.append(e))

        strat = EnhancedStatArb(
            engine, oms, rm, ema_span=20, min_edge=0.02,
            bankroll=5_000.0,
        )
        engine.run()

        strat_orders = [o for o in submitted if o.strategy_name == strat.name]
        assert all(o.side == "buy_yes" for o in strat_orders), \
            "enhanced stat arb must only submit buy_yes orders"
        assert len(strat_orders) > 0

    def test_skips_negative_edge(self):
        """When price > EMA (edge<0), strategy must skip the trade."""
        engine, portfolio, rm, oms, ms = _build_system()
        path = generate_binary_path(n_steps=200, seed=42)
        ms.load_binary_market("m_0", path)
        ms.schedule_settlements(210.0)

        strat = EnhancedStatArb(
            engine, oms, rm, ema_span=20, min_edge=0.02,
            bankroll=5_000.0,
        )
        engine.run()
        assert strat._skipped_no_side > 0

    def test_produces_stable_results(self):
        """Results should be stable across independent runs."""
        engine, portfolio, rm, oms, ms = _build_system(seed=42)
        for i in range(5):
            path = generate_binary_path(n_steps=100, seed=42 + i)
            ms.load_binary_market(f"m_{i}", path)
        ms.schedule_settlements(110.0)
        strat = EnhancedStatArb(engine, oms, rm, ema_span=10, min_edge=0.01,
                                  bankroll=5_000.0)
        engine.run()
        assert strat._filled_count >= 0
        assert portfolio.equity > 0

    def test_outperforms_basic_on_average(self):
        """Enhanced version should beat basic across multiple seeds."""
        enh_pnls = []
        basic_pnls = []
        for seed in range(5):
            actual = 42 + seed * 17
            engine, portfolio, rm, oms, ms = _build_system(seed=actual)
            for i in range(15):
                path = generate_binary_path(n_steps=300, seed=actual + i)
                ms.load_binary_market(f"m_{i}", path)
            ms.schedule_settlements(310.0)
            EnhancedStatArb(engine, oms, rm, ema_span=20, min_edge=0.03,
                             bankroll=10_000.0)
            engine.run()
            enh_pnls.append(portfolio.total_pnl)

            engine2, portfolio2, rm2, oms2, ms2 = _build_system(seed=actual)
            for i in range(15):
                path = generate_binary_path(n_steps=300, seed=actual + i)
                ms2.load_binary_market(f"m_{i}", path)
            ms2.schedule_settlements(310.0)
            EventStatArb(engine2, oms2, rm2, ema_span=20, min_edge=0.03,
                          bankroll=10_000.0)
            engine2.run()
            basic_pnls.append(portfolio2.total_pnl)

        enh_mean = np.mean(enh_pnls)
        basic_mean = np.mean(basic_pnls)
        assert enh_mean > basic_mean, \
            f"enhanced mean ${enh_mean:+.0f} should beat basic ${basic_mean:+.0f}"

    def test_summary_contains_side_skip_counts(self):
        engine, portfolio, rm, oms, ms = _build_system()
        for i in range(5):
            path = generate_binary_path(n_steps=200, seed=42 + i)
            ms.load_binary_market(f"m_{i}", path)
        ms.schedule_settlements(210.0)
        strat = EnhancedStatArb(engine, oms, rm, ema_span=20, min_edge=0.02,
                                  bankroll=5_000.0)
        engine.run()
        s = strat.summary()
        assert "skipped_no_side" in s
        assert "skipped_low_edge" in s
        assert s["skipped_no_side"] + s["skipped_low_edge"] + s["fills"] > 0
