#!/usr/bin/env python3
"""Backtest with realistic execution friction.

Applies slippage, market impact, execution failure, partial fills,
and latency to all strategy PnLs.  Compares frictionless (ideal)
vs realistic results.

Usage:
    python3 backtest/run_realistic_backtest.py
    python3 backtest/run_realistic_backtest.py --report backtest/reports/realistic.md
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from pdx_backtest.cross_venue_data import fetch_cross_venue_paths
from pdx_backtest.engine import BacktestEngine
from pdx_backtest.friction import FrictionParams, apply_friction_to_arb_pnl
from pdx_backtest.historical_data import (
    fetch_binary_market_paths,
    fetch_cross_platform_proxy_paths,
    fetch_negrisk_snapshots,
)
from pdx_backtest.strategies import (
    CrossVenueArb,
    NegRiskRebalancer,
    SingleBinaryRebalancer,
)
from pdx_backtest.strategies.base import StrategyResult, Trade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def apply_friction_to_result(
    sr: StrategyResult,
    params: FrictionParams,
    n_legs: int = 2,
    seed: int = 42,
) -> StrategyResult:
    """Apply execution friction to every trade in a StrategyResult."""
    rng = np.random.default_rng(seed)
    new_trades = []
    new_pnl = []
    new_returns = []

    for trade in sr.trades:
        adj_pnl, succeeded, fill_rate = apply_friction_to_arb_pnl(
            gross_pnl=trade.pnl,
            notional=trade.notional,
            rng=rng,
            params=params,
            n_legs=n_legs,
        )
        if not succeeded:
            new_trades.append(Trade(
                step=trade.step,
                action=trade.action + "_FAILED",
                notional=0.0,
                pnl=0.0,
                meta={**trade.meta, "failed": True, "fill_rate": 0.0},
            ))
            new_pnl.append(0.0)
            new_returns.append(0.0)
        else:
            new_trades.append(Trade(
                step=trade.step,
                action=trade.action,
                notional=trade.notional * fill_rate,
                pnl=adj_pnl,
                meta={**trade.meta, "fill_rate": fill_rate,
                      "gross_pnl": trade.pnl, "friction_cost": trade.pnl * fill_rate - adj_pnl},
            ))
            new_pnl.append(adj_pnl)
            new_returns.append(adj_pnl / max(trade.notional * fill_rate, 1e-9))

    pnl_arr = np.array(new_pnl)
    cum_pnl = np.cumsum(np.concatenate([[0.0], pnl_arr]))

    return StrategyResult(
        name=sr.name,
        trades=new_trades,
        equity_curve=cum_pnl / max(1e-9, abs(cum_pnl).max() or 1.0),
        returns=np.array(new_returns),
        pnl_per_trade=pnl_arr,
        capital_deployed=sum(t.notional for t in new_trades),
        capital_lockup_period_steps=sr.capital_lockup_period_steps,
        notes={**sr.notes, "friction": "applied"},
    )


def run_realistic_backtest(
    n_markets: int = 50,
    capital_base: float = 100_000.0,
) -> dict:
    engine = BacktestEngine()
    start = time.time()

    logger.info("=" * 60)
    logger.info("REALISTIC BACKTEST (with execution friction)")
    logger.info("=" * 60)

    # Fetch data
    binary_paths = fetch_binary_market_paths(
        n_markets=n_markets, min_volume=10_000, interval="max", fidelity=60)
    negrisk_sequences = fetch_negrisk_snapshots(min_outcomes=3, max_events=20)
    cross_venue_paths = fetch_cross_venue_paths(n_markets=min(20, n_markets), fidelity=5)

    logger.info("Data: %d binary, %d NegRisk, %d cross-venue",
                 len(binary_paths), len(negrisk_sequences), len(cross_venue_paths))

    poly_friction = FrictionParams.polymarket()
    predict_friction = FrictionParams.predict_fun()
    no_friction = FrictionParams.none()

    results = {"ideal": {}, "realistic": {}}

    # --- NegRisk ---
    logger.info("Running NegRisk Rebalancer...")
    nr = NegRiskRebalancer(threshold=0.01, taker_fee_bps=0.0, capital_per_trade=1000.0)
    all_trades, all_pnl, all_roic = [], [], []
    for seq in negrisk_sequences:
        sr = nr.run(seq)
        all_trades.extend(sr.trades)
        all_pnl.extend(sr.pnl_per_trade.tolist())
        all_roic.extend(sr.returns.tolist())

    if all_trades:
        ideal_sr = StrategyResult(
            name="negrisk", trades=all_trades,
            equity_curve=np.cumsum([0.0] + all_pnl) / capital_base,
            returns=np.array(all_roic),
            pnl_per_trade=np.array(all_pnl),
            capital_deployed=sum(t.notional for t in all_trades),
            capital_lockup_period_steps=len(all_trades),
            notes={"n_events": len(negrisk_sequences)},
        )
        # NegRisk has N legs (one per outcome, typically 3-5)
        realistic_sr = apply_friction_to_result(ideal_sr, poly_friction, n_legs=4, seed=1)
        results["ideal"]["negrisk"] = engine.evaluate(ideal_sr, capital_base=capital_base)
        results["realistic"]["negrisk"] = engine.evaluate(realistic_sr, capital_base=capital_base)

    # --- Single Binary ---
    logger.info("Running Single Binary Rebalancer...")
    sb = SingleBinaryRebalancer(threshold=0.02, taker_fee_bps=0.0,
                                 capital_per_trade=500.0, no_noise_std=0.001)
    all_trades, all_pnl, all_roic = [], [], []
    for path in binary_paths:
        sr = sb.run(path, seed=42)
        all_trades.extend(sr.trades)
        all_pnl.extend(sr.pnl_per_trade.tolist())
        all_roic.extend(sr.returns.tolist())

    if all_trades:
        ideal_sr = StrategyResult(
            name="single_binary", trades=all_trades,
            equity_curve=np.cumsum([0.0] + all_pnl) / capital_base,
            returns=np.array(all_roic),
            pnl_per_trade=np.array(all_pnl),
            capital_deployed=sum(t.notional for t in all_trades),
            capital_lockup_period_steps=len(all_trades),
            notes={"n_markets": len(binary_paths)},
        )
        realistic_sr = apply_friction_to_result(ideal_sr, poly_friction, n_legs=2, seed=2)
        results["ideal"]["single_binary"] = engine.evaluate(ideal_sr, capital_base=capital_base)
        results["realistic"]["single_binary"] = engine.evaluate(realistic_sr, capital_base=capital_base)

    # --- Cross-Venue Arb ---
    if cross_venue_paths:
        logger.info("Running Cross-Venue Arb...")
        cv = CrossVenueArb(
            poly_fee_bps=0.0, predict_fee_bps=150.0,
            min_spread=0.02, capital_per_trade=1000.0,
            settlement_risk_bps=50.0,
        )
        ideal_sr = cv.run(cross_venue_paths, seed=42)
        if ideal_sr.n_trades > 0:
            # Cross-venue has 2 legs across 2 venues with different friction
            # Use the worse (predict.fun) params as conservative estimate
            realistic_sr = apply_friction_to_result(
                ideal_sr, predict_friction, n_legs=2, seed=3)
            results["ideal"]["cross_venue"] = engine.evaluate(ideal_sr, capital_base=capital_base)
            results["realistic"]["cross_venue"] = engine.evaluate(realistic_sr, capital_base=capital_base)

    elapsed = time.time() - start
    logger.info("Realistic backtest complete in %.1fs", elapsed)
    return results


def print_comparison(results: dict) -> str:
    lines = []
    lines.append("")
    lines.append("=" * 90)
    lines.append("IDEAL vs REALISTIC COMPARISON")
    lines.append("=" * 90)
    lines.append("")

    header = (
        f"{'Strategy':<20} {'':>3} {'Trades':>7} {'PnL':>12} {'Return':>9} "
        f"{'Sharpe':>8} {'WinRate':>8} {'MDD':>8}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    all_strategies = sorted(
        set(list(results["ideal"].keys()) + list(results["realistic"].keys()))
    )

    for name in all_strategies:
        if name in results["ideal"]:
            m = results["ideal"][name].metrics
            lines.append(
                f"{name:<20} {'IDL':>3} {m.n_trades:>7d} ${m.total_pnl:>10.2f} "
                f"{m.total_return*100:>8.2f}% {m.sharpe:>8.2f} "
                f"{m.win_rate*100:>7.1f}% {m.max_drawdown*100:>7.2f}%"
            )
        if name in results["realistic"]:
            m = results["realistic"][name].metrics
            lines.append(
                f"{'':20} {'RLT':>3} {m.n_trades:>7d} ${m.total_pnl:>10.2f} "
                f"{m.total_return*100:>8.2f}% {m.sharpe:>8.2f} "
                f"{m.win_rate*100:>7.1f}% {m.max_drawdown*100:>7.2f}%"
            )
        lines.append("")

    # Summary
    ideal_total = sum(
        results["ideal"][n].metrics.total_pnl for n in results["ideal"])
    real_total = sum(
        results["realistic"][n].metrics.total_pnl for n in results["realistic"])
    pnl_reduction = (1 - real_total / ideal_total) * 100 if ideal_total != 0 else 0

    lines.append(f"Total Ideal PnL:     ${ideal_total:>12.2f}")
    lines.append(f"Total Realistic PnL: ${real_total:>12.2f}")
    lines.append(f"PnL reduction:       {pnl_reduction:>12.1f}%")
    lines.append("")
    lines.append("Friction applied: slippage (bid-ask spread), market impact,")
    lines.append("execution failure (~15-20%), partial fills, latency adverse move")
    lines.append("")

    output = "\n".join(lines)
    print(output)
    return output


def write_report(results: dict, path: str) -> None:
    lines = [
        "# Realistic Backtest Report (with Execution Friction)",
        "",
        "## Friction Model",
        "",
        "| Parameter | Polymarket | predict.fun |",
        "|-----------|-----------|-------------|",
        "| Half-spread | 60 bps (1.2% round-trip) | 100 bps (2% round-trip) |",
        "| Market impact | 0.08 × sqrt(size/liquidity) | 0.15 × sqrt(size/liquidity) |",
        "| Execution failure rate | 15% | 20% |",
        "| Partial fill (mean) | ~77% | ~60% |",
        "| Latency adverse move | σ=0.3% | σ=0.5% |",
        "",
        "## Ideal vs Realistic",
        "",
        "| Strategy | Mode | Trades | PnL | Return | Sharpe | Win Rate | Max DD |",
        "|----------|------|--------|-----|--------|--------|----------|--------|",
    ]

    for mode in ["ideal", "realistic"]:
        mode_label = "Ideal" if mode == "ideal" else "Realistic"
        for name in sorted(results[mode].keys()):
            m = results[mode][name].metrics
            lines.append(
                f"| {name} | {mode_label} | {m.n_trades} | "
                f"${m.total_pnl:.2f} | {m.total_return*100:.2f}% | "
                f"{m.sharpe:.2f} | {m.win_rate*100:.1f}% | "
                f"{m.max_drawdown*100:.2f}% |"
            )

    ideal_total = sum(results["ideal"][n].metrics.total_pnl for n in results["ideal"])
    real_total = sum(results["realistic"][n].metrics.total_pnl for n in results["realistic"])

    lines.extend([
        "",
        "## Summary",
        "",
        f"- **Ideal total PnL**: ${ideal_total:,.2f}",
        f"- **Realistic total PnL**: ${real_total:,.2f}",
        f"- **PnL reduction from friction**: {(1-real_total/ideal_total)*100:.1f}%" if ideal_total else "",
        "",
        "## Why Win Rates Drop",
        "",
        "1. **Slippage**: buying at ask (not mid) reduces effective edge per trade",
        "2. **Execution failure**: ~15-20% of arb attempts fail (window closes)",
        "3. **Partial fills**: only ~60-77% of order fills on average",
        "4. **Market impact**: $1000 orders move price on thin books",
        "5. **Latency**: price moves adversely during detection→execution gap",
        "",
    ])

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines))
    logger.info("Report written to %s", path)


def main():
    parser = argparse.ArgumentParser(description="Realistic backtest with friction")
    parser.add_argument("--n-markets", type=int, default=50)
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--report", type=str, default="backtest/reports/realistic.md")
    args = parser.parse_args()

    results = run_realistic_backtest(n_markets=args.n_markets, capital_base=args.capital)
    print_comparison(results)
    write_report(results, args.report)


if __name__ == "__main__":
    main()
