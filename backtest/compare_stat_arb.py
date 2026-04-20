"""Head-to-head comparison of basic vs enhanced statistical arbitrage."""

from __future__ import annotations

import numpy as np

from pdx_backtest.data import generate_binary_path
from pdx_backtest.event_engine import (
    EventEngine, MarketSimulator, OrderBookSimulator,
)
from pdx_backtest.friction import FrictionParams
from pdx_backtest.metrics import compute_metrics
from pdx_backtest.oms import OrderManagementSystem
from pdx_backtest.portfolio import Portfolio
from pdx_backtest.risk_manager import RiskLimits, RiskManager
from pdx_backtest.strategies.enhanced_stat_arb import EnhancedStatArb
from pdx_backtest.strategies.event_strategies import EventStatArb


def _build_system(seed: int, initial_capital: float = 100_000.0):
    engine = EventEngine(seed=seed)
    rng = np.random.default_rng(seed)
    portfolio = Portfolio(engine, initial_capital=initial_capital)
    risk_mgr = RiskManager(engine, portfolio, RiskLimits(
        max_open_positions=500, max_strategy_positions=200,
        max_strategy_loss=initial_capital * 0.5,
        max_single_trade_notional=10_000.0,
    ))
    oms = OrderManagementSystem(
        engine, default_friction=FrictionParams.polymarket(),
        rng=rng, risk_manager=risk_mgr,
    )
    OrderBookSimulator(engine, rng)
    ms = MarketSimulator(engine, rng)
    return engine, portfolio, risk_mgr, oms, ms


def run_basic(n_markets, n_steps, seed, vol=0.015, lag=3):
    engine, portfolio, risk_mgr, oms, ms = _build_system(seed=seed)
    for i in range(n_markets):
        path = generate_binary_path(n_steps=n_steps, vol=vol, market_lag=lag, seed=seed + i)
        ms.load_binary_market(f"binary_{i:03d}", path)
    ms.schedule_settlements(float(n_steps + 10))
    strat = EventStatArb(
        engine, oms, risk_mgr,
        ema_span=20, min_edge=0.03, cooldown_ticks=10,
        max_fraction=0.25, bankroll=10_000.0,
    )
    engine.run()
    return _extract_metrics(portfolio, strat.name, summary=strat.summary())


def run_enhanced(n_markets, n_steps, seed, vol=0.015, lag=3):
    engine, portfolio, risk_mgr, oms, ms = _build_system(seed=seed)
    for i in range(n_markets):
        path = generate_binary_path(n_steps=n_steps, vol=vol, market_lag=lag, seed=seed + i)
        ms.load_binary_market(f"binary_{i:03d}", path)
    ms.schedule_settlements(float(n_steps + 10))
    strat = EnhancedStatArb(
        engine, oms, risk_mgr,
        ema_span=20, min_edge=0.03,
        bankroll=10_000.0, max_fraction=0.25,
        cooldown_ticks=10,
    )
    engine.run()
    return _extract_metrics(portfolio, strat.name, summary=strat.summary())


def _extract_metrics(portfolio, name, summary=None):
    trades = portfolio.closed_trades_for_strategy(name)
    if not trades:
        return {"n_trades": 0, "pnl": 0.0, "win_rate": 0.0, "sharpe": 0.0,
                "max_dd": 0.0, "pf": 0.0, "summary": summary}
    pnl = np.array([t.pnl for t in trades])
    returns = np.array([t.pnl / t.notional if t.notional > 0 else 0 for t in trades])
    m = compute_metrics(returns=returns, pnl_per_trade=pnl,
                        periods_per_year=8760, capital_base=10_000.0)
    return {
        "n_trades": len(trades),
        "pnl": float(pnl.sum()),
        "win_rate": float((pnl > 0).sum() / len(trades)),
        "sharpe": m.sharpe,
        "max_dd": m.max_drawdown,
        "pf": m.profit_factor,
        "summary": summary,
    }


def _header(title):
    print(f"\n{'=' * 78}")
    print(f"  {title}")
    print(f"{'=' * 78}")


def comparison_across_seeds():
    _header("Head-to-Head: Basic vs Enhanced across 10 seeds")
    print(f"  {'Seed':>6s} {'Basic Trades':>13s} {'Basic PnL':>12s} {'Basic Win%':>11s} "
          f"{'Enh Trades':>11s} {'Enh PnL':>12s} {'Enh Win%':>11s}")
    print("  " + "-" * 78)

    basic_pnls, enh_pnls = [], []
    for i in range(10):
        seed = 42 + i * 17
        basic = run_basic(30, 500, seed)
        enh = run_enhanced(30, 500, seed)
        basic_pnls.append(basic["pnl"])
        enh_pnls.append(enh["pnl"])
        print(f"  {seed:>6d} {basic['n_trades']:>13d} ${basic['pnl']:>+11,.0f} "
              f"{basic['win_rate']:>10.1%} {enh['n_trades']:>11d} "
              f"${enh['pnl']:>+11,.0f} {enh['win_rate']:>10.1%}")

    ba, ea = np.array(basic_pnls), np.array(enh_pnls)
    print("\n  Summary:")
    print(f"    {'Metric':<18s} {'Basic':>12s} {'Enhanced':>12s} {'Δ':>10s}")
    print(f"    {'Mean PnL':<18s} ${ba.mean():>+11,.0f} ${ea.mean():>+11,.0f} "
          f"${ea.mean() - ba.mean():>+9,.0f}")
    print(f"    {'Std PnL':<18s} ${ba.std():>+11,.0f} ${ea.std():>+11,.0f} "
          f"${ea.std() - ba.std():>+9,.0f}")
    print(f"    {'Min PnL':<18s} ${ba.min():>+11,.0f} ${ea.min():>+11,.0f}")
    print(f"    {'Max PnL':<18s} ${ba.max():>+11,.0f} ${ea.max():>+11,.0f}")
    print(f"    {'Positive runs':<18s} {(ba > 0).sum():>11d}/10 {(ea > 0).sum():>11d}/10")
    t_b = ba.mean() / (ba.std() / np.sqrt(len(ba))) if ba.std() > 0 else 0
    t_e = ea.mean() / (ea.std() / np.sqrt(len(ea))) if ea.std() > 0 else 0
    print(f"    {'T-stat':<18s} {t_b:>+12.2f} {t_e:>+12.2f}")


def regime_stability():
    _header("Regime Stability: Performance across lag/vol regimes")
    print("  Lag regime test (vol=0.015 fixed):")
    print(f"    {'Lag':>4s} {'Basic PnL':>12s} {'Basic Win%':>11s} "
          f"{'Enh PnL':>12s} {'Enh Win%':>11s} {'Improvement':>12s}")
    print("  " + "-" * 72)

    for lag in [0, 3, 5, 10, 20]:
        b = run_basic(30, 500, 42, vol=0.015, lag=lag)
        e = run_enhanced(30, 500, 42, vol=0.015, lag=lag)
        imp = e["pnl"] - b["pnl"]
        print(f"    {lag:>4d} ${b['pnl']:>+11,.0f} {b['win_rate']:>10.1%} "
              f"${e['pnl']:>+11,.0f} {e['win_rate']:>10.1%} "
              f"${imp:>+11,.0f}")

    print("\n  Vol regime test (lag=3 fixed):")
    print(f"    {'Vol':>6s} {'Basic PnL':>12s} {'Basic Win%':>11s} "
          f"{'Enh PnL':>12s} {'Enh Win%':>11s} {'Improvement':>12s}")
    print("  " + "-" * 72)

    for vol in [0.005, 0.010, 0.015, 0.025, 0.040]:
        b = run_basic(30, 500, 42, vol=vol, lag=3)
        e = run_enhanced(30, 500, 42, vol=vol, lag=3)
        imp = e["pnl"] - b["pnl"]
        print(f"    {vol:>6.3f} ${b['pnl']:>+11,.0f} {b['win_rate']:>10.1%} "
              f"${e['pnl']:>+11,.0f} {e['win_rate']:>10.1%} "
              f"${imp:>+11,.0f}")


def diagnostic_enhanced():
    _header("Enhanced Strategy Diagnostics (seed=42)")
    e = run_enhanced(30, 500, 42)
    s = e["summary"]
    print(f"  Markets tracked:      {s['markets_tracked']}")
    print(f"  Fills:                {s['fills']}")
    print(f"  Rejects:              {s['rejects']}")
    print(f"  Skipped (low edge):   {s.get('skipped_low_edge', 0)}")
    print(f"  Skipped (NO side):    {s.get('skipped_no_side', 0)}")
    print(f"  Final trades:         {e['n_trades']}")
    print(f"  PnL:                  ${e['pnl']:+,.2f}")
    print(f"  Win rate:             {e['win_rate']:.1%}")
    print(f"  Sharpe:               {e['sharpe']:+.2f}")
    print(f"  Max DD:               {e['max_dd']:.2%}")


def main():
    print("=" * 78)
    print("  Basic vs Enhanced Statistical Arbitrage")
    print("=" * 78)
    diagnostic_enhanced()
    comparison_across_seeds()
    regime_stability()


if __name__ == "__main__":
    main()
