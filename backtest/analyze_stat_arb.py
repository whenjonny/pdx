"""Deep-dive analysis of statistical arbitrage strategy.

Profiles the EMA-based stat arb across parameter sweeps to identify:
  1. Which parameters drive profitability (ema_span, min_edge, cooldown)
  2. Which market conditions favor the strategy (drift, volatility)
  3. Entry timing: is max-edge trade better than first-crossing trade?
  4. Exit strategy: hold to settlement vs close when edge evaporates
  5. Comparison to alternative signals (z-score, momentum, Bollinger)
"""

from __future__ import annotations

import numpy as np

from pdx_backtest.data import generate_binary_path
from pdx_backtest.event_engine import (
    EventEngine, MarketSimulator, OrderBookSimulator,
    MarketTick, OrderFill, OrderReject,
)
from pdx_backtest.friction import FrictionParams
from pdx_backtest.metrics import compute_metrics
from pdx_backtest.oms import OrderManagementSystem
from pdx_backtest.portfolio import Portfolio
from pdx_backtest.risk_manager import RiskLimits, RiskManager
from pdx_backtest.strategies.event_strategies import EventStatArb


def _build_system(seed: int = 42, initial_capital: float = 100_000.0):
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


def run_stat_arb(
    n_markets: int,
    n_steps: int,
    seed: int,
    ema_span: int,
    min_edge: float,
    cooldown_ticks: int,
    max_fraction: float,
    bankroll: float,
) -> dict:
    """Run a single stat arb config and return metrics."""
    engine, portfolio, risk_mgr, oms, ms = _build_system(seed=seed)

    for i in range(n_markets):
        path = generate_binary_path(n_steps=n_steps, seed=seed + i)
        ms.load_binary_market(f"binary_{i:03d}", path)
    ms.schedule_settlements(float(n_steps + 10))

    strat = EventStatArb(
        engine, oms, risk_mgr,
        ema_span=ema_span,
        min_edge=min_edge,
        bankroll=bankroll,
        max_fraction=max_fraction,
        cooldown_ticks=cooldown_ticks,
    )
    engine.run()

    trades = portfolio.closed_trades_for_strategy(strat.name)
    if not trades:
        return {
            "n_trades": 0, "total_pnl": 0.0, "win_rate": 0.0,
            "avg_pnl": 0.0, "sharpe": 0.0, "max_dd": 0.0,
        }

    pnl = np.array([t.pnl for t in trades])
    returns = np.array([t.pnl / t.notional if t.notional > 0 else 0.0 for t in trades])
    wins = (pnl > 0).sum()
    metrics = compute_metrics(
        returns=returns, pnl_per_trade=pnl,
        periods_per_year=8760, capital_base=bankroll,
    )

    return {
        "n_trades": len(trades),
        "total_pnl": float(pnl.sum()),
        "win_rate": wins / len(trades),
        "avg_pnl": float(pnl.mean()),
        "sharpe": metrics.sharpe,
        "max_dd": metrics.max_drawdown,
        "gross_profit": float(pnl[pnl > 0].sum()),
        "gross_loss": float(pnl[pnl < 0].sum()),
        "profit_factor": metrics.profit_factor,
    }


def _header(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


def _print_results(results: list[tuple], labels: list[str]) -> None:
    hdr = "  " + "  ".join(f"{lbl:>10s}" for lbl in labels)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for row in results:
        print("  " + "  ".join(
            f"{v:>10.4f}" if isinstance(v, float) else f"{str(v):>10s}"
            for v in row
        ))


def analysis_1_ema_span_sweep():
    """How does EMA window size affect performance?"""
    _header("Analysis 1: EMA Span Sweep (holding other params constant)")
    print("  n_markets=30, n_steps=500, min_edge=3%, cooldown=10, max_frac=25%")

    results = []
    for span in [5, 10, 15, 20, 30, 50, 75, 100]:
        m = run_stat_arb(
            n_markets=30, n_steps=500, seed=42,
            ema_span=span, min_edge=0.03, cooldown_ticks=10,
            max_fraction=0.25, bankroll=10_000.0,
        )
        results.append((
            span, m["n_trades"], m["total_pnl"], m["win_rate"],
            m["avg_pnl"], m["sharpe"], m["profit_factor"],
        ))

    _print_results(results, [
        "EMA", "Trades", "TotalPnL", "WinRate", "AvgPnL", "Sharpe", "PF",
    ])


def analysis_2_min_edge_sweep():
    """How does the minimum edge threshold affect profitability?"""
    _header("Analysis 2: Min Edge Sweep")
    print("  n_markets=30, n_steps=500, ema_span=20, cooldown=10, max_frac=25%")

    results = []
    for edge in [0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10]:
        m = run_stat_arb(
            n_markets=30, n_steps=500, seed=42,
            ema_span=20, min_edge=edge, cooldown_ticks=10,
            max_fraction=0.25, bankroll=10_000.0,
        )
        results.append((
            edge, m["n_trades"], m["total_pnl"], m["win_rate"],
            m["avg_pnl"], m["sharpe"], m["profit_factor"],
        ))

    _print_results(results, [
        "MinEdge", "Trades", "TotalPnL", "WinRate", "AvgPnL", "Sharpe", "PF",
    ])


def analysis_3_cooldown_sweep():
    """How does cooldown affect overtrading vs missed opportunities?"""
    _header("Analysis 3: Cooldown Ticks Sweep")
    print("  n_markets=30, n_steps=500, ema_span=20, min_edge=3%, max_frac=25%")

    results = []
    for cd in [1, 3, 5, 10, 20, 50]:
        m = run_stat_arb(
            n_markets=30, n_steps=500, seed=42,
            ema_span=20, min_edge=0.03, cooldown_ticks=cd,
            max_fraction=0.25, bankroll=10_000.0,
        )
        results.append((
            cd, m["n_trades"], m["total_pnl"], m["win_rate"],
            m["avg_pnl"], m["sharpe"], m["profit_factor"],
        ))

    _print_results(results, [
        "Cooldown", "Trades", "TotalPnL", "WinRate", "AvgPnL", "Sharpe", "PF",
    ])


def analysis_4_position_size_sweep():
    """How does max position fraction affect risk-adjusted returns?"""
    _header("Analysis 4: Max Kelly Fraction Sweep")
    print("  n_markets=30, n_steps=500, ema_span=20, min_edge=3%, cooldown=10")

    results = []
    for f in [0.05, 0.10, 0.15, 0.25, 0.40, 0.60]:
        m = run_stat_arb(
            n_markets=30, n_steps=500, seed=42,
            ema_span=20, min_edge=0.03, cooldown_ticks=10,
            max_fraction=f, bankroll=10_000.0,
        )
        results.append((
            f, m["n_trades"], m["total_pnl"], m["win_rate"],
            m["avg_pnl"], m["sharpe"], m["max_dd"],
        ))

    _print_results(results, [
        "MaxFrac", "Trades", "TotalPnL", "WinRate", "AvgPnL", "Sharpe", "MaxDD",
    ])


def analysis_5_seed_robustness():
    """Is the edge real or just luck on seed=42?"""
    _header("Analysis 5: Seed Robustness (is it real edge or luck?)")
    print("  Best config: ema_span=20, min_edge=3%, cooldown=10, max_frac=25%")

    results = []
    pnls = []
    for seed in range(10):
        m = run_stat_arb(
            n_markets=30, n_steps=500, seed=42 + seed * 17,
            ema_span=20, min_edge=0.03, cooldown_ticks=10,
            max_fraction=0.25, bankroll=10_000.0,
        )
        results.append((
            42 + seed * 17, m["n_trades"], m["total_pnl"],
            m["win_rate"], m["sharpe"], m["profit_factor"],
        ))
        pnls.append(m["total_pnl"])

    _print_results(results, [
        "Seed", "Trades", "TotalPnL", "WinRate", "Sharpe", "PF",
    ])

    pnls_arr = np.array(pnls)
    print(f"\n  Mean PnL:    ${pnls_arr.mean():>+10,.2f}")
    print(f"  Std PnL:     ${pnls_arr.std():>+10,.2f}")
    print(f"  Min PnL:     ${pnls_arr.min():>+10,.2f}")
    print(f"  Max PnL:     ${pnls_arr.max():>+10,.2f}")
    print(f"  Positive:    {(pnls_arr > 0).sum()}/{len(pnls_arr)} runs")
    t_stat = pnls_arr.mean() / (pnls_arr.std() / np.sqrt(len(pnls_arr))) if pnls_arr.std() > 0 else 0
    print(f"  T-stat:      {t_stat:>+10.2f}  (>2 = significant)")


def analysis_6_entry_signal_comparison():
    """Compare different entry signals: EMA, Z-score, Bollinger."""
    _header("Analysis 6: Alternative Entry Signals")
    print("  Note: current implementation uses EMA only.")
    print("  This analysis would require signal_type parameter in EventStatArb.")
    print("  [Placeholder — see event_strategies.py for extension]")


def analysis_7_price_regime():
    """Does stat arb work better in high-vol or low-vol markets?"""
    _header("Analysis 7: Market Volatility Regime Analysis")
    print("  Varying vol parameter of synthetic data generator...")

    results = []
    for vol in [0.005, 0.010, 0.015, 0.025, 0.040]:
        engine, portfolio, risk_mgr, oms, ms = _build_system(seed=42)
        for i in range(30):
            # vol is hardcoded in generate_binary_path default — need custom
            from pdx_backtest.data import generate_binary_path as gbp
            path = gbp(n_steps=500, vol=vol, seed=42 + i)
            ms.load_binary_market(f"binary_{i:03d}", path)
        ms.schedule_settlements(510.0)

        strat = EventStatArb(
            engine, oms, risk_mgr,
            ema_span=20, min_edge=0.03, cooldown_ticks=10,
            max_fraction=0.25, bankroll=10_000.0,
        )
        engine.run()

        trades = portfolio.closed_trades_for_strategy(strat.name)
        if not trades:
            results.append((vol, 0, 0.0, 0.0, 0.0))
            continue
        pnl = np.array([t.pnl for t in trades])
        results.append((
            vol, len(trades), float(pnl.sum()),
            float((pnl > 0).sum() / len(pnl)),
            float(pnl.mean()),
        ))

    _print_results(results, [
        "Vol", "Trades", "TotalPnL", "WinRate", "AvgPnL",
    ])


def analysis_8_lag_regime():
    """Does stat arb work better on markets with more lag?"""
    _header("Analysis 8: Market Lag Regime Analysis")
    print("  EMA-based mean reversion should profit more from higher lag...")

    results = []
    for lag in [0, 1, 3, 5, 10, 20]:
        engine, portfolio, risk_mgr, oms, ms = _build_system(seed=42)
        from pdx_backtest.data import generate_binary_path as gbp
        for i in range(30):
            path = gbp(n_steps=500, market_lag=lag, seed=42 + i)
            ms.load_binary_market(f"binary_{i:03d}", path)
        ms.schedule_settlements(510.0)

        strat = EventStatArb(
            engine, oms, risk_mgr,
            ema_span=20, min_edge=0.03, cooldown_ticks=10,
            max_fraction=0.25, bankroll=10_000.0,
        )
        engine.run()

        trades = portfolio.closed_trades_for_strategy(strat.name)
        if not trades:
            results.append((lag, 0, 0.0, 0.0, 0.0))
            continue
        pnl = np.array([t.pnl for t in trades])
        results.append((
            lag, len(trades), float(pnl.sum()),
            float((pnl > 0).sum() / len(pnl)),
            float(pnl.mean()),
        ))

    _print_results(results, [
        "Lag", "Trades", "TotalPnL", "WinRate", "AvgPnL",
    ])


def analysis_9_joint_optimization():
    """Find the best (ema_span, min_edge) combination."""
    _header("Analysis 9: Joint Optimization (EMA x Edge)")
    print("  Grid search on ema_span × min_edge, avg across 5 seeds.")

    best = None
    best_sharpe = -999.0
    print(f"  {'EMA':>4s} {'Edge':>6s} {'Trades':>7s} {'AvgPnL':>10s} "
          f"{'WinRate':>8s} {'Sharpe':>8s}  Rating")
    print("  " + "-" * 60)

    for span in [10, 20, 30]:
        for edge in [0.02, 0.03, 0.05]:
            trade_counts = []
            pnls = []
            wins = []
            for seed_offset in range(5):
                m = run_stat_arb(
                    n_markets=20, n_steps=500, seed=42 + seed_offset * 100,
                    ema_span=span, min_edge=edge, cooldown_ticks=10,
                    max_fraction=0.25, bankroll=10_000.0,
                )
                trade_counts.append(m["n_trades"])
                pnls.append(m["total_pnl"])
                wins.append(m["win_rate"] if m["n_trades"] > 0 else 0.0)

            avg_trades = np.mean(trade_counts)
            avg_pnl = np.mean(pnls) if pnls else 0.0
            pnl_std = np.std(pnls) if len(pnls) > 1 else 1.0
            sharpe = avg_pnl / pnl_std if pnl_std > 0 else 0.0
            avg_win = np.mean(wins)

            rating = "★★★" if avg_pnl > 500 and sharpe > 1 else "★★" if avg_pnl > 0 else " "
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best = (span, edge, avg_pnl, avg_win, sharpe)

            print(f"  {span:>4d} {edge:>6.3f} {avg_trades:>7.1f} "
                  f"${avg_pnl:>+9,.0f} {avg_win:>7.1%} {sharpe:>+8.2f}  {rating}")

    if best:
        print(f"\n  Best config: EMA={best[0]}, Edge={best[1]:.3f}")
        print(f"    Avg PnL: ${best[2]:+,.2f}")
        print(f"    Win rate: {best[3]:.1%}")
        print(f"    Sharpe: {best[4]:+.2f}")


def main():
    print("=" * 72)
    print("  Statistical Arbitrage Deep-Dive Analysis")
    print("=" * 72)

    analysis_1_ema_span_sweep()
    analysis_2_min_edge_sweep()
    analysis_3_cooldown_sweep()
    analysis_4_position_size_sweep()
    analysis_5_seed_robustness()
    analysis_7_price_regime()
    analysis_8_lag_regime()
    analysis_9_joint_optimization()


if __name__ == "__main__":
    main()
