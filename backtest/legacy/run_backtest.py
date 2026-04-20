"""Entry point — runs every strategy on a shared synthetic universe
and prints a comparison table + a detailed per-strategy breakdown.

Usage:
    python3 backtest/run_backtest.py
    python3 backtest/run_backtest.py --n-markets 200 --seed 99
    python3 backtest/run_backtest.py --report reports/run_001.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

# Ensure package is importable when invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from pdx_backtest.data import (
    generate_binary_path,
    generate_multi_outcome_paths,
    generate_negrisk_scenario,
)
from pdx_backtest.engine import BacktestEngine
from pdx_backtest.strategies import (
    BayesianMarketMaker,
    NegRiskRebalancer,
    StatisticalArb,
    TimeArb,
)


def run(n_markets: int, seed: int, n_steps_mm: int, report_path: str | None) -> int:
    engine = BacktestEngine(periods_per_year=252, risk_free=0.04)

    # ---------------------------------------------------------------
    # Shared synthetic universe
    # ---------------------------------------------------------------
    print(f"\n[data] seed={seed}  n_markets={n_markets}  mm_path_len={n_steps_mm}")

    binary_paths = [
        generate_binary_path(
            n_steps=n_steps_mm,
            initial_prob=float(np.random.default_rng(seed + i).uniform(0.1, 0.9)),
            seed=seed + i,
        )
        for i in range(n_markets)
    ]
    # One long-dated universe where most outcomes are high-probability.
    long_dated_paths = [
        generate_binary_path(
            n_steps=60,
            initial_prob=float(np.random.default_rng(seed * 2 + i).uniform(0.7, 0.95)),
            vol=0.005,
            market_noise=0.015,
            longshot_bias=0.04,
            seed=seed * 2 + i,
        )
        for i in range(n_markets)
    ]

    neg_risk_universe = generate_multi_outcome_paths(
        n_markets=n_markets, n_outcomes=5, n_snapshots=80, seed=seed
    )
    flat_snapshots = [snap for run_ in neg_risk_universe for snap in run_]

    # ---------------------------------------------------------------
    # 1. NegRisk rebalancing
    # ---------------------------------------------------------------
    negrisk = NegRiskRebalancer(threshold=0.01, taker_fee_bps=0.0, capital_per_trade=1_000.0)
    neg_result = negrisk.run(flat_snapshots)
    r1 = engine.evaluate(
        neg_result,
        periods_per_year=8760,  # Polymarket data updates ~ hourly cadence.
        initial_capital=1.0,
        # Fair comparison: capital_base = capital_per_trade (recycled each
        # trade).  Gives total_return = total_pnl / capital_per_trade.
        capital_base=negrisk.capital_per_trade,
    )

    # ---------------------------------------------------------------
    # 2. Bayesian market-making on PDX CPMM
    # ---------------------------------------------------------------
    mm = BayesianMarketMaker(
        initial_liquidity=10_000.0,
        prior_yes=0.55,
        trader_intensity=8.0,
        informed_fraction=0.25,
    )
    from pdx_backtest.strategies.base import StrategyResult

    mm_results = [mm.run(p, seed=seed + i) for i, p in enumerate(binary_paths[:20])]
    combined_returns = np.concatenate([r.returns for r in mm_results])
    combined_pnl = np.concatenate([r.pnl_per_trade for r in mm_results])
    total_initial = sum(float(r.notes["initial_liquidity"]) for r in mm_results)
    total_fees = sum(float(r.notes["fees_collected"]) for r in mm_results)
    total_rebates = sum(float(r.notes["rebates"]) for r in mm_results)
    total_final_pnl = sum(float(r.notes["final_pnl"]) for r in mm_results)
    mm_combined = StrategyResult(
        name=mm.name,
        trades=[t for r in mm_results for t in r.trades],
        equity_curve=np.cumsum(combined_returns),
        returns=combined_returns,
        pnl_per_trade=combined_pnl,
        capital_deployed=total_initial,
        capital_lockup_period_steps=sum(r.capital_lockup_period_steps for r in mm_results),
        notes={
            "n_markets": len(mm_results),
            "total_initial": total_initial,
            "total_fees_collected": total_fees,
            "total_rebates": total_rebates,
            "total_mm_pnl": total_final_pnl,
            "roi_pct": total_final_pnl / total_initial * 100.0 if total_initial > 0 else 0.0,
        },
    )
    r2 = engine.evaluate(
        mm_combined,
        periods_per_year=8760,
        initial_capital=1.0,
        capital_base=total_initial,
    )

    # ---------------------------------------------------------------
    # 3. Statistical arbitrage
    # ---------------------------------------------------------------
    sa = StatisticalArb(taker_fee_bps=120.0, min_edge=0.03, max_position_fraction=0.25)
    sa_result = sa.run(binary_paths, seed=seed)
    r3 = engine.evaluate(
        sa_result,
        periods_per_year=52,   # event-scale (~weekly)
        initial_capital=1.0,
        capital_base=sa.bankroll,
    )

    # ---------------------------------------------------------------
    # 4. Time arbitrage on long-dated high-probability outcomes
    # ---------------------------------------------------------------
    ta = TimeArb(settlement_days=180, min_edge=0.04, fair_prob_floor=0.75,
                 taker_fee_bps=120.0, risk_free=0.04, capital_per_market=1_000.0)
    ta_result = ta.run(long_dated_paths, seed=seed)
    ta_capital_base = ta.capital_per_market * len(long_dated_paths)
    r4 = engine.evaluate(
        ta_result,
        periods_per_year=2,  # semi-annual settlement cadence
        initial_capital=1.0,
        capital_base=ta_capital_base,
    )

    # ---------------------------------------------------------------
    # Report
    # ---------------------------------------------------------------
    print("\n============ BACKTEST SUMMARY ============\n")
    print(engine.comparison_table())
    print()

    _print_details("NegRisk Rebalancer", r1)
    _print_details("Bayesian Market Maker", r2)
    _print_details("Statistical Arbitrage", r3)
    _print_details("Time Arbitrage", r4)

    if report_path:
        _write_markdown_report(report_path, [r1, r2, r3, r4], seed=seed,
                               n_markets=n_markets)
        print(f"\nreport: {report_path}")

    return 0


def _print_details(label: str, result) -> None:
    m = result.metrics
    print(f"\n-- {label} --")
    print(f"  Trades executed     : {m.n_trades}")
    print(f"  Total return        : {m.total_return:+.4%}")
    print(f"  CAGR                : {m.cagr:+.2%}")
    print(f"  Annualised vol      : {m.volatility:.2%}")
    print(f"  Sharpe              : {m.sharpe:+.2f}")
    print(f"  Sortino             : {m.sortino:+.2f}")
    print(f"  Calmar              : {m.calmar:+.2f}")
    print(f"  Max drawdown        : {m.max_drawdown:+.2%}")
    print(f"  Win rate            : {m.win_rate:.2%}")
    print(f"  Profit factor       : {m.profit_factor:.2f}")
    print(f"  Gross profit / loss : ${m.gross_profit:,.2f} / ${m.gross_loss:,.2f}")
    notes = result.strategy_result.notes
    if notes:
        print(f"  Notes               : {json.dumps(notes, default=_json_safe)}")


def _write_markdown_report(path: str, results, seed: int, n_markets: int) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lines: list[str] = []
    lines.append("# PDX Backtest Report")
    lines.append("")
    lines.append(f"- seed: `{seed}`")
    lines.append(f"- n_markets: `{n_markets}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Strategy | Trades | Total | CAGR | Sharpe | Sortino | MDD | Win | PF |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        m = r.metrics
        lines.append(
            f"| {r.strategy_name} | {m.n_trades} | {m.total_return:+.2%} | "
            f"{m.cagr:+.2%} | {m.sharpe:+.2f} | {m.sortino:+.2f} | "
            f"{m.max_drawdown:+.2%} | {m.win_rate:.1%} | {m.profit_factor:.2f} |"
        )
    lines.append("")
    for r in results:
        lines.append(f"### {r.strategy_name}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps({
            "metrics": asdict(r.metrics),
            "notes": r.strategy_result.notes,
        }, indent=2, default=_json_safe))
        lines.append("```")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))


def _json_safe(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return float(o)
    raise TypeError(f"{type(o)} is not JSON serialisable")


def sweep(n_seeds: int, n_markets: int, mm_steps: int, base_seed: int) -> int:
    """Run each strategy across N seeds and report distribution of outcomes.

    This is the robustness check — confirms that the strategy edge is
    stable across different synthetic-data draws rather than an artifact
    of a single lucky seed.
    """
    print(f"\n[sweep] n_seeds={n_seeds} base_seed={base_seed} n_markets={n_markets}")
    rows: dict[str, list[dict]] = {
        "negrisk_rebalancer": [],
        "bayesian_market_maker": [],
        "statistical_arbitrage": [],
        "time_arbitrage": [],
    }
    import io, contextlib

    for i in range(n_seeds):
        s = base_seed + i * 1000
        engine = BacktestEngine(periods_per_year=252, risk_free=0.04)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run(n_markets, s, mm_steps, None)
        # engine's results aren't accessible — rerun directly to harvest metrics.
        for r in _collect_results(n_markets, s, mm_steps):
            rows[r.strategy_name].append({
                "seed": s,
                "total_return": r.metrics.total_return,
                "sharpe": r.metrics.sharpe,
                "sortino": r.metrics.sortino,
                "max_drawdown": r.metrics.max_drawdown,
                "win_rate": r.metrics.win_rate,
                "n_trades": r.metrics.n_trades,
                "total_pnl": r.metrics.total_pnl,
            })

    print("\n============ ROBUSTNESS SWEEP ============\n")
    print(f"{'Strategy':28s}  {'mean_ret':>10s}  {'std_ret':>10s}  "
          f"{'mean_sharpe':>12s}  {'worst_case':>12s}  {'best_case':>12s}")
    print("-" * 92)
    for name, data in rows.items():
        if not data:
            continue
        rets = np.array([d["total_return"] for d in data])
        sharpes = np.array([d["sharpe"] for d in data])
        print(
            f"{name:28s}  "
            f"{rets.mean():+10.2%}  "
            f"{rets.std():10.2%}  "
            f"{sharpes.mean():+12.2f}  "
            f"{rets.min():+12.2%}  "
            f"{rets.max():+12.2%}"
        )
    return 0


def _collect_results(n_markets: int, seed: int, mm_steps: int):
    """Re-run and harvest individual BacktestResult objects."""
    engine = BacktestEngine(periods_per_year=252, risk_free=0.04)

    binary_paths = [
        generate_binary_path(
            n_steps=mm_steps,
            initial_prob=float(np.random.default_rng(seed + i).uniform(0.1, 0.9)),
            seed=seed + i,
        ) for i in range(n_markets)
    ]
    long_dated_paths = [
        generate_binary_path(
            n_steps=60,
            initial_prob=float(np.random.default_rng(seed * 2 + i).uniform(0.7, 0.95)),
            vol=0.005, market_noise=0.015, longshot_bias=0.04,
            seed=seed * 2 + i,
        ) for i in range(n_markets)
    ]
    neg_risk_universe = generate_multi_outcome_paths(
        n_markets=n_markets, n_outcomes=5, n_snapshots=80, seed=seed
    )
    flat_snapshots = [snap for run_ in neg_risk_universe for snap in run_]

    negrisk = NegRiskRebalancer(threshold=0.01, capital_per_trade=1_000.0)
    r1 = engine.evaluate(negrisk.run(flat_snapshots), periods_per_year=8760,
                         capital_base=negrisk.capital_per_trade)

    mm = BayesianMarketMaker(initial_liquidity=10_000.0, prior_yes=0.55,
                             trader_intensity=8.0, informed_fraction=0.25)
    from pdx_backtest.strategies.base import StrategyResult
    mm_results = [mm.run(p, seed=seed + i) for i, p in enumerate(binary_paths[:20])]
    combined_returns = np.concatenate([r.returns for r in mm_results])
    combined_pnl = np.concatenate([r.pnl_per_trade for r in mm_results])
    total_initial = sum(float(r.notes["initial_liquidity"]) for r in mm_results)
    mm_combined = StrategyResult(
        name=mm.name, trades=[t for r in mm_results for t in r.trades],
        equity_curve=np.cumsum(combined_returns), returns=combined_returns,
        pnl_per_trade=combined_pnl, capital_deployed=total_initial,
        capital_lockup_period_steps=sum(r.capital_lockup_period_steps for r in mm_results),
        notes={"n_markets": len(mm_results)},
    )
    r2 = engine.evaluate(mm_combined, periods_per_year=8760, capital_base=total_initial)

    sa = StatisticalArb(taker_fee_bps=120.0, min_edge=0.03, max_position_fraction=0.25)
    r3 = engine.evaluate(sa.run(binary_paths, seed=seed), periods_per_year=52,
                         capital_base=sa.bankroll)

    ta = TimeArb(settlement_days=180, min_edge=0.04, fair_prob_floor=0.75,
                 taker_fee_bps=120.0, risk_free=0.04, capital_per_market=1_000.0)
    r4 = engine.evaluate(ta.run(long_dated_paths, seed=seed), periods_per_year=2,
                         capital_base=ta.capital_per_market * len(long_dated_paths))

    return [r1, r2, r3, r4]


def main() -> int:
    p = argparse.ArgumentParser(description="PDX prediction-market backtester")
    p.add_argument("--n-markets", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--mm-steps", type=int, default=200,
                   help="number of steps in each market-making path")
    p.add_argument("--report", type=str, default=None,
                   help="optional markdown report path, e.g. reports/run_001.md")
    p.add_argument("--sweep", type=int, default=0,
                   help="run robustness sweep across N seeds")
    args = p.parse_args()
    if args.sweep > 0:
        return sweep(args.sweep, args.n_markets, args.mm_steps, args.seed)
    return run(args.n_markets, args.seed, args.mm_steps, args.report)


if __name__ == "__main__":
    sys.exit(main())
