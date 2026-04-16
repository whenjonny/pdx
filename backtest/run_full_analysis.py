"""Comprehensive backtest + 5-hour live simulation + robustness sweep.

Covers all 10 prediction-market arbitrage strategies and produces
a unified comparison report.

Usage:
    python3 backtest/run_full_analysis.py
    python3 backtest/run_full_analysis.py --seed 99 --n-markets 200
    python3 backtest/run_full_analysis.py --report backtest/reports/full_analysis.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from pdx_backtest.data import (
    generate_binary_path,
    generate_cross_platform_path,
    generate_multi_outcome_paths,
    generate_negrisk_scenario,
)
from pdx_backtest.engine import BacktestEngine, BacktestResult
from pdx_backtest.live_sim import run_live_sim
from pdx_backtest.strategies import (
    BayesianMarketMaker,
    CrossAssetArb,
    CrossPlatformArb,
    LongshotBiasExploiter,
    LVRArb,
    NegRiskRebalancer,
    SingleBinaryRebalancer,
    StatisticalArb,
    TimeArb,
    VolatilityEventStrategy,
)
from pdx_backtest.strategies.base import StrategyResult


def run_all_backtests(n_markets: int, seed: int) -> list[BacktestResult]:
    """Run all 10 strategies and return results."""
    engine = BacktestEngine(periods_per_year=252, risk_free=0.04)
    rng = np.random.default_rng(seed)

    # --- Shared data ---
    binary_paths = [
        generate_binary_path(
            n_steps=200,
            initial_prob=float(rng.uniform(0.1, 0.9)),
            seed=seed + i,
        ) for i in range(n_markets)
    ]
    long_dated = [
        generate_binary_path(
            n_steps=60,
            initial_prob=float(rng.uniform(0.7, 0.95)),
            vol=0.005, market_noise=0.015, longshot_bias=0.04,
            seed=seed * 2 + i,
        ) for i in range(n_markets)
    ]
    # Diverse initial_prob set for longshot bias detection.
    diverse_paths = [
        generate_binary_path(
            n_steps=100,
            initial_prob=float(rng.uniform(0.02, 0.98)),
            vol=0.01, market_noise=0.008, longshot_bias=0.05,
            seed=seed * 3 + i,
        ) for i in range(n_markets)
    ]
    neg_risk = generate_multi_outcome_paths(
        n_markets=n_markets, n_outcomes=5, n_snapshots=80, seed=seed
    )
    flat_neg = [snap for run_ in neg_risk for snap in run_]
    cross_paths = [
        generate_cross_platform_path(
            n_steps=200,
            initial_prob=float(rng.uniform(0.3, 0.7)),
            seed=seed * 4 + i,
        ) for i in range(n_markets)
    ]

    results: list[BacktestResult] = []

    # 1. Single-binary rebalancing.
    sb = SingleBinaryRebalancer(threshold=0.005, capital_per_trade=1000.0)
    # Run across multiple paths and aggregate.
    sb_trades, sb_pnl, sb_roic = [], [], []
    for i, p in enumerate(binary_paths[:30]):
        r = sb.run(p, seed=seed + i)
        sb_trades.extend(r.trades)
        sb_pnl.extend(r.pnl_per_trade.tolist())
        sb_roic.extend(r.returns.tolist())
    sb_combined = StrategyResult(
        name="single_binary_rebalancer",
        trades=sb_trades,
        equity_curve=np.cumsum([0.0] + sb_pnl) / 1000.0,
        returns=np.asarray(sb_roic, dtype=float),
        pnl_per_trade=np.asarray(sb_pnl, dtype=float),
        capital_deployed=1000.0 * len(sb_trades),
        capital_lockup_period_steps=len(sb_trades),
        notes={"total_pnl": float(sum(sb_pnl)), "n_paths": 30},
    )
    results.append(engine.evaluate(sb_combined, periods_per_year=8760, capital_base=1000.0))

    # 2. NegRisk rebalancing.
    nr = NegRiskRebalancer(threshold=0.01, capital_per_trade=1000.0)
    results.append(engine.evaluate(
        nr.run(flat_neg), periods_per_year=8760, capital_base=1000.0))

    # 3. Bayesian market maker.
    mm = BayesianMarketMaker(initial_liquidity=10_000.0, prior_yes=0.55,
                             trader_intensity=8.0, informed_fraction=0.25)
    mm_runs = [mm.run(p, seed=seed + i) for i, p in enumerate(binary_paths[:20])]
    mm_rets = np.concatenate([r.returns for r in mm_runs])
    mm_pnl = np.concatenate([r.pnl_per_trade for r in mm_runs])
    total_init = sum(float(r.notes["initial_liquidity"]) for r in mm_runs)
    mm_combined = StrategyResult(
        name="bayesian_market_maker", trades=[t for r in mm_runs for t in r.trades],
        equity_curve=np.cumsum(mm_rets), returns=mm_rets, pnl_per_trade=mm_pnl,
        capital_deployed=total_init,
        capital_lockup_period_steps=sum(r.capital_lockup_period_steps for r in mm_runs),
        notes={"n_markets": len(mm_runs), "total_pnl": float(mm_pnl.sum()),
               "total_initial": total_init},
    )
    results.append(engine.evaluate(mm_combined, periods_per_year=8760, capital_base=total_init))

    # 4. Statistical arbitrage.
    sa = StatisticalArb(taker_fee_bps=120.0, min_edge=0.03)
    results.append(engine.evaluate(
        sa.run(binary_paths, seed=seed), periods_per_year=52, capital_base=sa.bankroll))

    # 5. Time arbitrage.
    ta = TimeArb(settlement_days=180, min_edge=0.04, fair_prob_floor=0.75,
                 taker_fee_bps=120.0)
    results.append(engine.evaluate(
        ta.run(long_dated, seed=seed), periods_per_year=2,
        capital_base=1000.0 * len(long_dated)))

    # 6. Cross-platform arbitrage.
    cp = CrossPlatformArb(min_spread=0.02, capital_per_trade=1000.0)
    results.append(engine.evaluate(
        cp.run(cross_paths, seed=seed), periods_per_year=52, capital_base=1000.0))

    # 7. Favourite-longshot bias.
    lb = LongshotBiasExploiter(taker_fee_bps=120.0, capital_per_trade=500.0)
    results.append(engine.evaluate(
        lb.run(diverse_paths, seed=seed), periods_per_year=52, capital_base=500.0))

    # 8. LVR informed arb.
    lvr = LVRArb(pool_liquidity=50_000.0, trade_size=500.0, min_edge=0.03)
    lvr_trades, lvr_pnl, lvr_roic = [], [], []
    for i, p in enumerate(binary_paths[:20]):
        r = lvr.run(p, seed=seed + i)
        lvr_trades.extend(r.trades)
        lvr_pnl.extend(r.pnl_per_trade.tolist())
        lvr_roic.extend(r.returns.tolist())
    lvr_combined = StrategyResult(
        name="lvr_informed_arb", trades=lvr_trades,
        equity_curve=np.cumsum([0.0] + lvr_pnl) / 500.0,
        returns=np.asarray(lvr_roic, dtype=float),
        pnl_per_trade=np.asarray(lvr_pnl, dtype=float),
        capital_deployed=500.0 * len(lvr_trades),
        capital_lockup_period_steps=len(lvr_trades),
        notes={"total_pnl": float(sum(lvr_pnl)), "n_paths": 20},
    )
    results.append(engine.evaluate(lvr_combined, periods_per_year=52, capital_base=500.0))

    # 9. Cross-asset arb.
    ca = CrossAssetArb(options_noise=0.01, min_edge=0.03, taker_fee_bps=120.0)
    results.append(engine.evaluate(
        ca.run(binary_paths, seed=seed), periods_per_year=52, capital_base=1000.0))

    # 10. Volatility event positioning.
    ve = VolatilityEventStrategy(capital_per_event=2000.0, taker_fee_bps=30.0)
    results.append(engine.evaluate(
        ve.run(n_events=50, seed=seed), periods_per_year=52, capital_base=2000.0))

    return results


def robustness_sweep(n_seeds: int, n_markets: int, base_seed: int) -> dict[str, dict]:
    """Run each strategy across N seeds and collect distribution stats."""
    all_data: dict[str, list[dict]] = {}

    for i in range(n_seeds):
        s = base_seed + i * 1000
        results = run_all_backtests(n_markets, s)
        for r in results:
            name = r.strategy_name
            if name not in all_data:
                all_data[name] = []
            all_data[name].append({
                "seed": s,
                "total_return": r.metrics.total_return,
                "total_pnl": r.metrics.total_pnl,
                "sharpe": r.metrics.sharpe,
                "max_drawdown": r.metrics.max_drawdown,
                "win_rate": r.metrics.win_rate,
                "n_trades": r.metrics.n_trades,
            })

    summary: dict[str, dict] = {}
    for name, data in all_data.items():
        rets = np.array([d["total_return"] for d in data])
        pnls = np.array([d["total_pnl"] for d in data])
        sharpes = np.array([d["sharpe"] for d in data])
        mdds = np.array([d["max_drawdown"] for d in data])
        wins = np.array([d["win_rate"] for d in data])
        summary[name] = {
            "mean_return": float(rets.mean()),
            "std_return": float(rets.std()),
            "mean_pnl": float(pnls.mean()),
            "mean_sharpe": float(sharpes.mean()),
            "worst_return": float(rets.min()),
            "best_return": float(rets.max()),
            "mean_mdd": float(mdds.mean()),
            "mean_win_rate": float(wins.mean()),
        }
    return summary


def write_report(
    path: str,
    bt_results: list[BacktestResult],
    sweep: dict[str, dict],
    live_result,
    seed: int,
    n_markets: int,
) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lines: list[str] = []
    lines.append("# PDX 全策略回测分析报告")
    lines.append("")
    lines.append(f"- Seed: `{seed}` | Markets: `{n_markets}` | Date: 2026-04-16")
    lines.append("")

    # Section 1: backtest table.
    lines.append("## 一、单次回测结果（10 策略）")
    lines.append("")
    lines.append("| # | Strategy | Trades | Total Return | Sharpe | Sortino | MDD | Win% | PF | Total PnL |")
    lines.append("|---|----------|--------|-------------|--------|---------|-----|------|----|----|")
    for i, r in enumerate(bt_results, 1):
        m = r.metrics
        pf = f"{m.profit_factor:.2f}" if m.profit_factor < 1e6 else "∞"
        lines.append(
            f"| {i} | {r.strategy_name} | {m.n_trades} | {m.total_return:+.2%} | "
            f"{m.sharpe:+.2f} | {m.sortino:+.2f} | {m.max_drawdown:+.2%} | "
            f"{m.win_rate:.1%} | {pf} | ${m.total_pnl:,.0f} |"
        )
    lines.append("")

    # Section 2: robustness sweep.
    lines.append("## 二、多种子稳健性扫描")
    lines.append("")
    lines.append("| Strategy | Mean Return | Std | Mean Sharpe | Worst | Best | Mean MDD | Mean Win% |")
    lines.append("|----------|-----------|------|------------|-------|------|----------|-----------|")
    for name, s in sweep.items():
        lines.append(
            f"| {name} | {s['mean_return']:+.2%} | {s['std_return']:.2%} | "
            f"{s['mean_sharpe']:+.2f} | {s['worst_return']:+.2%} | "
            f"{s['best_return']:+.2%} | {s['mean_mdd']:+.2%} | {s['mean_win_rate']:.1%} |"
        )
    lines.append("")

    # Section 3: live sim summary.
    lines.append("## 三、5小时实盘模拟")
    lines.append("")
    lines.append(f"- Duration: {live_result.duration_minutes} minutes")
    lines.append(f"- Events at: {live_result.events}")
    lines.append(f"- Total trades: {live_result.aggregate_trades}")
    lines.append(f"- Total PnL: ${live_result.aggregate_pnl:,.2f}")
    lines.append("")
    lines.append("| Strategy | Trades | PnL | ROI | Sharpe | MDD | Win% |")
    lines.append("|----------|--------|-----|-----|--------|-----|------|")
    for name, state in sorted(live_result.strategies.items()):
        m = live_result.metrics.get(name)
        roi = state.total_pnl / max(state.capital_deployed, 1e-6)
        lines.append(
            f"| {name} | {state.n_trades} | ${state.total_pnl:,.2f} | "
            f"{roi:+.2%} | {m.sharpe:+.2f} | {m.max_drawdown:+.2%} | {m.win_rate:.1%} |"
        )
    lines.append("")

    # Section 4: strategy ranking.
    lines.append("## 四、风险调整后策略排名")
    lines.append("")
    ranked = sorted(sweep.items(), key=lambda x: x[1]["mean_sharpe"], reverse=True)
    for rank, (name, s) in enumerate(ranked, 1):
        lines.append(f"{rank}. **{name}** — Sharpe {s['mean_sharpe']:+.2f}, "
                      f"Return {s['mean_return']:+.2%} ± {s['std_return']:.2%}, "
                      f"MDD {s['mean_mdd']:+.2%}")
    lines.append("")

    # Section 5: conclusions.
    lines.append("## 五、结论与实操建议")
    lines.append("")
    lines.append("详见 backtest/README.md 中的策略描述和风险提示。")
    lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))


def main() -> int:
    p = argparse.ArgumentParser(description="Full PDX backtest analysis")
    p.add_argument("--n-markets", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n-seeds", type=int, default=5, help="robustness sweep seeds")
    p.add_argument("--report", type=str, default="backtest/reports/full_analysis.md")
    args = p.parse_args()

    print("=" * 70)
    print(" PHASE 1: SINGLE-SEED BACKTEST (10 strategies)")
    print("=" * 70)
    bt_results = run_all_backtests(args.n_markets, args.seed)
    print("\nBacktest Results:")
    for r in bt_results:
        m = r.metrics
        print(f"  {r.strategy_name:32s}  trades={m.n_trades:5d}  "
              f"ret={m.total_return:+10.2%}  Sharpe={m.sharpe:+7.2f}  "
              f"MDD={m.max_drawdown:+7.2%}  win={m.win_rate:5.1%}  "
              f"PnL=${m.total_pnl:,.0f}")

    print("\n" + "=" * 70)
    print(f" PHASE 2: ROBUSTNESS SWEEP ({args.n_seeds} seeds)")
    print("=" * 70)
    sweep = robustness_sweep(args.n_seeds, args.n_markets, args.seed)
    print(f"\n{'Strategy':32s}  {'Mean Ret':>10s}  {'Std':>8s}  "
          f"{'Mean Sharpe':>12s}  {'Worst':>10s}  {'Best':>10s}")
    print("-" * 90)
    for name, s in sweep.items():
        print(f"{name:32s}  {s['mean_return']:+10.2%}  {s['std_return']:8.2%}  "
              f"{s['mean_sharpe']:+12.2f}  {s['worst_return']:+10.2%}  "
              f"{s['best_return']:+10.2%}")

    print("\n" + "=" * 70)
    print(" PHASE 3: 5-HOUR LIVE SIMULATION")
    print("=" * 70)
    live_result = run_live_sim(seed=args.seed, verbose=True)

    print("\n" + "=" * 70)
    print(" WRITING REPORT")
    print("=" * 70)
    write_report(args.report, bt_results, sweep, live_result, args.seed, args.n_markets)
    print(f"\nReport: {args.report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
