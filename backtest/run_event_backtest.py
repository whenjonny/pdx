#!/usr/bin/env python3
"""Event-driven backtest runner with production-grade risk management.

Replaces the time-series iteration approach (run_backtest.py) with a
discrete-event simulation where:

  - Strategies react to MarketTick events (never see true_prob)
  - Orders flow through OMS with realistic friction at execution time
  - Risk manager gate-keeps every order with 13 pre-trade checks
  - Portfolio tracks real-time MTM equity, drawdown, and PnL
  - Settlements close positions at market resolution

Usage:
    python run_event_backtest.py [--markets N] [--seed S] [--capital C]
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from pdx_backtest.data import (
    generate_binary_path,
    generate_cross_platform_path,
    generate_multi_outcome_paths,
)
from pdx_backtest.event_engine import (
    EventEngine,
    MarketSimulator,
    OrderBookSimulator,
    MarketTick,
    OrderFill,
    OrderReject,
    Settlement,
    RiskAlert,
)
from pdx_backtest.friction import FrictionParams
from pdx_backtest.metrics import compute_metrics
from pdx_backtest.oms import OrderManagementSystem
from pdx_backtest.portfolio import Portfolio
from pdx_backtest.risk_manager import RiskLimits, RiskManager
from pdx_backtest.strategies.event_strategies import (
    EventNegRiskRebalancer,
    EventSingleBinaryRebalancer,
    EventStatArb,
    EventCrossVenueArb,
    EventLongshotBiasExploiter,
)


def _section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def run_event_backtest(
    n_markets: int = 30,
    seed: int = 42,
    initial_capital: float = 100_000.0,
    n_steps: int = 500,
) -> dict:
    """Run the full event-driven backtest.

    Returns a dict with portfolio summary, risk summary, OMS summary,
    and per-strategy metrics.
    """
    rng = np.random.default_rng(seed)
    t0 = time.time()

    # ------------------------------------------------------------------
    # Phase 1: Build the event engine and infrastructure
    # ------------------------------------------------------------------
    _section("Phase 1: Initializing event engine")

    engine = EventEngine(seed=seed)

    # Portfolio must be created first (risk manager needs it)
    portfolio = Portfolio(engine, initial_capital=initial_capital)

    # Risk manager — registered before OMS so pre-trade checks run first
    limits = RiskLimits(
        max_drawdown_pct=0.15,
        max_portfolio_notional=initial_capital * 5,
        max_daily_loss=initial_capital * 0.05,
        max_open_positions=200,
        max_strategy_notional=initial_capital * 2,
        max_strategy_loss=initial_capital * 0.10,
        max_strategy_positions=80,
        max_single_trade_notional=5_000.0,
        min_single_trade_notional=10.0,
        max_position_pct_of_liquidity=0.15,
        max_single_market_exposure_pct=0.30,
        max_orders_per_minute=240,
        cooldown_after_n_rejects=10,
        cooldown_duration=30.0,
        reduce_size_after_drawdown_pct=0.05,
        min_size_multiplier=0.25,
    )
    risk_mgr = RiskManager(engine, portfolio, limits)

    # OMS — with per-venue friction and risk manager integration
    friction_map = {
        "poly_": FrictionParams.polymarket(),
        "predict_": FrictionParams.predict_fun(),
    }
    oms = OrderManagementSystem(
        engine,
        friction=friction_map,
        default_friction=FrictionParams.polymarket(),
        rng=rng,
        execution_latency_ms=200.0,
        risk_manager=risk_mgr,
    )

    # Orderbook simulator
    ob_sim = OrderBookSimulator(engine, rng, n_levels=5, base_size=5_000.0)

    print(f"  Engine ready  |  Capital: ${initial_capital:,.0f}  |  Seed: {seed}")
    print(f"  Risk limits: DD={limits.max_drawdown_pct:.0%}, "
          f"daily_loss=${limits.max_daily_loss:,.0f}, "
          f"max_trade=${limits.max_single_trade_notional:,.0f}")

    # ------------------------------------------------------------------
    # Phase 2: Generate synthetic data and load into market simulator
    # ------------------------------------------------------------------
    _section("Phase 2: Generating market data")

    market_sim = MarketSimulator(engine, rng)

    # Binary markets
    print(f"  Generating {n_markets} binary markets ({n_steps} steps each)...")
    binary_paths = [
        generate_binary_path(n_steps=n_steps, seed=seed + i)
        for i in range(n_markets)
    ]
    for i, path in enumerate(binary_paths):
        market_sim.load_binary_market(f"binary_{i:03d}", path, tick_interval=1.0)

    # NegRisk multi-outcome markets
    n_negrisk = max(5, n_markets // 3)
    print(f"  Generating {n_negrisk} NegRisk markets (5 outcomes, 200 snapshots)...")
    negrisk_scenarios = generate_multi_outcome_paths(
        n_markets=n_negrisk, n_outcomes=5, n_snapshots=200, seed=seed + 1000,
    )
    for i, snapshots in enumerate(negrisk_scenarios):
        market_sim.load_negrisk(f"negrisk_{i:03d}", snapshots, tick_interval=1.0)

    # Cross-venue markets (Polymarket vs predict.fun)
    n_cross = max(5, n_markets // 3)
    print(f"  Generating {n_cross} cross-venue market pairs...")
    cross_paths = [
        generate_cross_platform_path(n_steps=n_steps, seed=seed + 2000 + i)
        for i in range(n_cross)
    ]
    for i, path in enumerate(cross_paths):
        market_sim.load_cross_venue(
            f"poly_cv_{i:03d}", f"predict_cv_{i:03d}",
            path, tick_interval=1.0,
        )

    # Schedule settlements after all ticks
    settlement_time = float(n_steps + 10)
    market_sim.schedule_settlements(settlement_time)

    total_events = engine.pending
    print(f"  Total events scheduled: {total_events:,}")

    # ------------------------------------------------------------------
    # Phase 3: Register strategies
    # ------------------------------------------------------------------
    _section("Phase 3: Registering strategies")

    strategies = []

    # 1. NegRisk Rebalancer
    negrisk_strat = EventNegRiskRebalancer(
        engine, oms, risk_mgr,
        threshold=0.01,
        capital_per_trade=1_000.0,
    )
    strategies.append(negrisk_strat)
    print(f"  [1] {negrisk_strat.name}: threshold=1%, capital=$1,000")

    # 2. Single Binary Rebalancer
    binary_strat = EventSingleBinaryRebalancer(
        engine, oms, risk_mgr,
        threshold=0.005,
        capital_per_trade=1_000.0,
    )
    strategies.append(binary_strat)
    print(f"  [2] {binary_strat.name}: threshold=0.5%, capital=$1,000")

    # 3. Statistical Arbitrage
    stat_strat = EventStatArb(
        engine, oms, risk_mgr,
        ema_span=20,
        min_edge=0.03,
        bankroll=10_000.0,
    )
    strategies.append(stat_strat)
    print(f"  [3] {stat_strat.name}: EMA(20), min_edge=3%, bankroll=$10,000")

    # 4. Cross-Venue Arbitrage
    cv_strat = EventCrossVenueArb(
        engine, oms, risk_mgr,
        poly_fee_bps=0.0,
        predict_fee_bps=150.0,
        min_spread=0.015,
        capital_per_trade=1_000.0,
        settlement_risk_bps=50.0,
        max_concurrent=10,
    )
    # Register cross-venue pairs
    for i in range(n_cross):
        cv_strat.register_pair(f"poly_cv_{i:03d}", f"predict_cv_{i:03d}")
    strategies.append(cv_strat)
    print(f"  [4] {cv_strat.name}: {n_cross} pairs, min_spread=1.5%")

    # 5. Longshot Bias Exploiter
    ls_strat = EventLongshotBiasExploiter(
        engine, oms, risk_mgr,
        sell_zone=(0.02, 0.10),
        buy_zone=(0.90, 0.98),
        capital_per_trade=500.0,
    )
    strategies.append(ls_strat)
    print(f"  [5] {ls_strat.name}: sell=$0.02-0.10, buy=$0.90-0.98")

    # ------------------------------------------------------------------
    # Phase 4: Run the simulation
    # ------------------------------------------------------------------
    _section("Phase 4: Running event simulation")

    events_processed = engine.run(until=settlement_time + 1.0)
    elapsed = time.time() - t0

    n_ticks = sum(1 for e in events_processed if isinstance(e, MarketTick))
    n_fills = sum(1 for e in events_processed if isinstance(e, OrderFill))
    n_rejects = sum(1 for e in events_processed if isinstance(e, OrderReject))
    n_settlements = sum(1 for e in events_processed if isinstance(e, Settlement))
    n_alerts = sum(1 for e in events_processed if isinstance(e, RiskAlert))

    print(f"  Events processed: {len(events_processed):,}")
    print(f"  MarketTicks: {n_ticks:,}  |  Fills: {n_fills}  |  "
          f"Rejects: {n_rejects}  |  Settlements: {n_settlements}")
    print(f"  Risk alerts: {n_alerts}  |  Elapsed: {elapsed:.1f}s")

    # ------------------------------------------------------------------
    # Phase 5: Results
    # ------------------------------------------------------------------
    _section("Phase 5: Portfolio Results")

    port_summary = portfolio.summary()
    print(f"\n  Initial capital:   ${port_summary['initial_capital']:>12,.2f}")
    print(f"  Final equity:      ${port_summary['equity']:>12,.2f}")
    print(f"  Total PnL:         ${port_summary['total_pnl']:>+12,.2f}")
    print(f"  Realized PnL:      ${port_summary['realized_pnl']:>+12,.2f}")
    print(f"  Closed trades:     {port_summary['n_closed_trades']:>12d}")
    print(f"  Open positions:    {port_summary['n_open_positions']:>12d}")
    print(f"  Win rate:          {port_summary['win_rate']:>12.1%}")

    # ------------------------------------------------------------------
    # Phase 6: Per-strategy breakdown
    # ------------------------------------------------------------------
    _section("Phase 6: Strategy Breakdown")

    strat_names = list(set(t.strategy_name for t in portfolio.closed_trades))
    strat_names.sort()

    header = (
        f"  {'Strategy':<30s} {'Trades':>6s} {'PnL':>12s} "
        f"{'Win%':>7s} {'Sharpe':>8s} {'MDD':>8s} {'AvgPnL':>10s}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    strategy_metrics = {}
    for sname in strat_names:
        trades = portfolio.closed_trades_for_strategy(sname)
        if not trades:
            continue
        returns = np.array([
            t.pnl / t.notional if t.notional > 0 else 0.0 for t in trades
        ])
        pnl_arr = np.array([t.pnl for t in trades])
        total_pnl = float(pnl_arr.sum())
        wins = sum(1 for t in trades if t.pnl > 0)
        win_rate = wins / len(trades) if trades else 0.0
        avg_pnl = total_pnl / len(trades) if trades else 0.0

        metrics = compute_metrics(
            returns=returns,
            pnl_per_trade=pnl_arr,
            periods_per_year=8760,
            capital_base=initial_capital / len(strat_names) if strat_names else initial_capital,
        )
        strategy_metrics[sname] = metrics

        print(
            f"  {sname:<30s} {len(trades):>6d} ${total_pnl:>+11,.2f} "
            f"{win_rate:>6.1%} {metrics.sharpe:>+8.2f} "
            f"{metrics.max_drawdown:>+7.1%} ${avg_pnl:>+9,.2f}"
        )

    if not strat_names:
        print("  (no closed trades)")

    # ------------------------------------------------------------------
    # Phase 7: Risk Manager Report
    # ------------------------------------------------------------------
    _section("Phase 7: Risk Management Report")

    risk_summary = risk_mgr.summary()
    print(f"  Global halt:       {'YES' if risk_summary['halted'] else 'No'}")
    print(f"  Peak equity:       ${risk_summary['peak_equity']:>12,.2f}")
    print(f"  Current drawdown:  {risk_summary['current_drawdown']:>12.2%}")
    print(f"  Size multiplier:   {risk_summary['size_multiplier']:>12.2f}")
    print(f"  Rejected orders:   {risk_summary['rejected_orders']:>12d}")
    print(f"  Risk alerts:       {risk_summary['n_alerts']:>12d}")

    if risk_summary["halted_strategies"]:
        print(f"  Halted strategies: {', '.join(risk_summary['halted_strategies'])}")

    if risk_summary["alerts_by_type"]:
        print("\n  Alert breakdown:")
        for atype, count in risk_summary["alerts_by_type"].items():
            print(f"    {atype}: {count}")

    # ------------------------------------------------------------------
    # Phase 8: OMS Execution Report
    # ------------------------------------------------------------------
    _section("Phase 8: Execution Quality Report")

    oms_summary = oms.summary()
    print(f"  Total orders:      {oms_summary['total_orders']:>12d}")
    print(f"  Fills:             {oms_summary['fills']:>12d}")
    print(f"  Rejects:           {oms_summary['rejects']:>12d}")
    print(f"  Fill rate:         {oms_summary['fill_rate']:>12.1%}")
    print(f"  Filled notional:   ${oms_summary['total_filled_notional']:>12,.2f}")

    if oms_summary["reject_reasons"]:
        print("\n  Reject reasons:")
        for reason, count in sorted(
            oms_summary["reject_reasons"].items(), key=lambda x: -x[1]
        ):
            print(f"    {reason}: {count}")

    # ------------------------------------------------------------------
    # Phase 9: Comparison table
    # ------------------------------------------------------------------
    _section("Phase 9: Summary Comparison")

    # Overall portfolio metrics
    returns = portfolio.get_returns()
    pnl = portfolio.get_pnl_per_trade()
    if len(returns) > 0:
        overall = compute_metrics(
            returns=returns,
            pnl_per_trade=pnl,
            periods_per_year=8760,
            capital_base=initial_capital,
        )
        print(f"\n  Overall Portfolio Metrics:")
        print(f"    Total return:    {overall.total_return:>+10.2%}")
        print(f"    Sharpe:          {overall.sharpe:>+10.2f}")
        print(f"    Sortino:         {overall.sortino:>+10.2f}")
        print(f"    Max drawdown:    {overall.max_drawdown:>+10.2%}")
        print(f"    Win rate:        {overall.win_rate:>10.1%}")
        print(f"    Profit factor:   {overall.profit_factor:>10.2f}")
        print(f"    N trades:        {overall.n_trades:>10d}")

    print(f"\n  Elapsed time: {elapsed:.1f}s")
    print(f"  Events/sec:   {len(events_processed) / max(elapsed, 0.001):,.0f}")

    return {
        "portfolio": port_summary,
        "risk": risk_summary,
        "oms": oms_summary,
        "strategy_metrics": strategy_metrics,
        "elapsed": elapsed,
        "n_events": len(events_processed),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Event-driven backtest")
    parser.add_argument("--markets", type=int, default=30, help="Number of markets")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--capital", type=float, default=100_000.0, help="Initial capital")
    parser.add_argument("--steps", type=int, default=500, help="Steps per market")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║       PDX Event-Driven Backtest — Production Risk Simulation       ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    result = run_event_backtest(
        n_markets=args.markets,
        seed=args.seed,
        initial_capital=args.capital,
        n_steps=args.steps,
    )

    # Exit code: 0 if profitable, 1 if loss (useful for CI)
    sys.exit(0 if result["portfolio"]["total_pnl"] >= 0 else 1)


if __name__ == "__main__":
    main()
