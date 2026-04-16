#!/usr/bin/env python3
"""Backtest strategies on real Polymarket historical data.

Usage:
    python3 backtest/run_real_backtest.py
    python3 backtest/run_real_backtest.py --n-markets 100 --report backtest/reports/real_backtest.md
    python3 backtest/run_real_backtest.py --strategies negrisk,single_binary

Requires network access to Polymarket APIs.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from pdx_backtest.engine import BacktestEngine
from pdx_backtest.historical_data import (
    fetch_binary_market_paths,
    fetch_cross_platform_proxy_paths,
    fetch_negrisk_snapshots,
)
from pdx_backtest.strategies import (
    CrossAssetArb,
    CrossPlatformArb,
    LongshotBiasExploiter,
    NegRiskRebalancer,
    SingleBinaryRebalancer,
    StatisticalArb,
    TimeArb,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_real_backtest(
    n_markets: int = 50,
    capital_base: float = 100_000.0,
    strategies_filter: set[str] | None = None,
) -> dict:
    """Fetch real data and backtest all applicable strategies."""
    engine = BacktestEngine()
    results = {}
    start = time.time()

    # ------------------------------------------------------------------
    # Phase 1: Fetch real historical data
    # ------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("PHASE 1: Fetching real Polymarket data")
    logger.info("=" * 60)

    binary_paths = fetch_binary_market_paths(
        n_markets=n_markets, min_volume=10_000,
        interval="max", fidelity=60,
    )
    logger.info("Fetched %d binary market paths", len(binary_paths))

    negrisk_sequences = fetch_negrisk_snapshots(min_outcomes=3, max_events=20)
    logger.info("Fetched %d NegRisk event sequences", len(negrisk_sequences))

    cross_plat_paths = fetch_cross_platform_proxy_paths(
        n_markets=min(20, n_markets), fidelity=5,
    )
    logger.info("Fetched %d cross-platform paths", len(cross_plat_paths))

    # ------------------------------------------------------------------
    # Phase 2: Backtest strategies on real data
    # ------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("PHASE 2: Backtesting on real data")
    logger.info("=" * 60)

    def should_run(name: str) -> bool:
        if strategies_filter is None:
            return True
        return name in strategies_filter

    # --- Strategy 1: NegRisk Rebalancer ---
    if should_run("negrisk") and negrisk_sequences:
        logger.info("Running NegRisk Rebalancer on %d events…", len(negrisk_sequences))
        nr = NegRiskRebalancer(threshold=0.01, taker_fee_bps=0.0, capital_per_trade=1000.0)
        all_trades = []
        all_pnl = []
        all_roic = []
        for seq in negrisk_sequences:
            sr = nr.run(seq)
            all_trades.extend(sr.trades)
            all_pnl.extend(sr.pnl_per_trade.tolist())
            all_roic.extend(sr.returns.tolist())

        if all_trades:
            from pdx_backtest.strategies.base import StrategyResult
            combined = StrategyResult(
                name="negrisk_rebalancer",
                trades=all_trades,
                equity_curve=np.cumsum([0.0] + all_pnl) / capital_base,
                returns=np.array(all_roic),
                pnl_per_trade=np.array(all_pnl),
                capital_deployed=sum(t.notional for t in all_trades),
                capital_lockup_period_steps=len(all_trades),
                notes={"n_events": len(negrisk_sequences), "data_source": "polymarket_real"},
            )
            br = engine.evaluate(combined, capital_base=capital_base)
            results["negrisk"] = br
            logger.info("  NegRisk: %d trades, total PnL $%.2f, return %.2f%%",
                         len(all_trades), sum(all_pnl), sum(all_pnl) / capital_base * 100)

    # --- Strategy 2: Single Binary Rebalancer ---
    if should_run("single_binary") and binary_paths:
        logger.info("Running Single Binary Rebalancer on %d markets…", len(binary_paths))
        sb = SingleBinaryRebalancer(threshold=0.005, taker_fee_bps=0.0,
                                    capital_per_trade=500.0, no_noise_std=0.005)
        all_trades = []
        all_pnl = []
        all_roic = []
        for path in binary_paths:
            sr = sb.run(path, seed=42)
            all_trades.extend(sr.trades)
            all_pnl.extend(sr.pnl_per_trade.tolist())
            all_roic.extend(sr.returns.tolist())

        if all_trades:
            from pdx_backtest.strategies.base import StrategyResult
            combined = StrategyResult(
                name="single_binary_rebalancer",
                trades=all_trades,
                equity_curve=np.cumsum([0.0] + all_pnl) / capital_base,
                returns=np.array(all_roic),
                pnl_per_trade=np.array(all_pnl),
                capital_deployed=sum(t.notional for t in all_trades),
                capital_lockup_period_steps=len(all_trades),
                notes={"n_markets": len(binary_paths), "data_source": "polymarket_real"},
            )
            br = engine.evaluate(combined, capital_base=capital_base)
            results["single_binary"] = br
            logger.info("  Single Binary: %d trades, total PnL $%.2f, return %.2f%%",
                         len(all_trades), sum(all_pnl), sum(all_pnl) / capital_base * 100)

    # --- Strategy 3: Statistical Arbitrage ---
    if should_run("stat_arb") and binary_paths:
        logger.info("Running Statistical Arb on %d markets…", len(binary_paths))
        sa = StatisticalArb(lookback=20, entry_z=1.5, exit_z=0.5,
                            capital_per_trade=500.0, half_kelly_mult=0.5)
        all_trades = []
        all_pnl = []
        all_roic = []
        for path in binary_paths:
            sr = sa.run(path, seed=42)
            all_trades.extend(sr.trades)
            all_pnl.extend(sr.pnl_per_trade.tolist())
            all_roic.extend(sr.returns.tolist())

        if all_trades:
            from pdx_backtest.strategies.base import StrategyResult
            combined = StrategyResult(
                name="stat_arb",
                trades=all_trades,
                equity_curve=np.cumsum([0.0] + all_pnl) / capital_base,
                returns=np.array(all_roic),
                pnl_per_trade=np.array(all_pnl),
                capital_deployed=sum(t.notional for t in all_trades),
                capital_lockup_period_steps=len(all_trades),
                notes={"n_markets": len(binary_paths), "data_source": "polymarket_real"},
            )
            br = engine.evaluate(combined, capital_base=capital_base)
            results["stat_arb"] = br
            logger.info("  Stat Arb: %d trades, total PnL $%.2f",
                         len(all_trades), sum(all_pnl))

    # --- Strategy 4: Time Arbitrage ---
    if should_run("time_arb") and binary_paths:
        logger.info("Running Time Arb on %d markets…", len(binary_paths))
        long_dated = [p for p in binary_paths if len(p) >= 200]
        if long_dated:
            ta = TimeArb(fair_prob_floor=0.75, discount_rate=0.04,
                         capital_per_trade=2000.0)
            all_trades = []
            all_pnl = []
            all_roic = []
            for path in long_dated:
                sr = ta.run(path)
                all_trades.extend(sr.trades)
                all_pnl.extend(sr.pnl_per_trade.tolist())
                all_roic.extend(sr.returns.tolist())

            if all_trades:
                from pdx_backtest.strategies.base import StrategyResult
                combined = StrategyResult(
                    name="time_arb",
                    trades=all_trades,
                    equity_curve=np.cumsum([0.0] + all_pnl) / capital_base,
                    returns=np.array(all_roic),
                    pnl_per_trade=np.array(all_pnl),
                    capital_deployed=sum(t.notional for t in all_trades),
                    capital_lockup_period_steps=len(all_trades),
                    notes={"n_markets": len(long_dated), "data_source": "polymarket_real"},
                )
                br = engine.evaluate(combined, capital_base=capital_base)
                results["time_arb"] = br
                logger.info("  Time Arb: %d trades, total PnL $%.2f",
                             len(all_trades), sum(all_pnl))

    # --- Strategy 5: Cross-Platform Arb ---
    if should_run("cross_platform") and cross_plat_paths:
        logger.info("Running Cross-Platform Arb on %d paths…", len(cross_plat_paths))
        cp = CrossPlatformArb(min_spread=0.02, capital_per_trade=1000.0)
        sr = cp.run(cross_plat_paths, seed=42)
        if sr.n_trades > 0:
            br = engine.evaluate(sr, capital_base=capital_base)
            results["cross_platform"] = br
            logger.info("  Cross-Platform: %d trades, total PnL $%.2f",
                         sr.n_trades, float(sr.pnl_per_trade.sum()))

    # --- Strategy 6: Longshot Bias ---
    if should_run("longshot") and binary_paths:
        logger.info("Running Longshot Bias Exploiter on %d markets…", len(binary_paths))
        lb = LongshotBiasExploiter(
            sell_zone=(0.02, 0.10),
            buy_zone=(0.90, 0.98),
            taker_fee_bps=0.0,
        )
        sr = lb.run(binary_paths)
        if sr.n_trades > 0:
            br = engine.evaluate(sr, capital_base=capital_base)
            results["longshot"] = br
            logger.info("  Longshot: %d trades, total PnL $%.2f",
                         sr.n_trades, float(sr.pnl_per_trade.sum()))

    # --- Strategy 7: Cross-Asset Arb ---
    if should_run("cross_asset") and binary_paths:
        logger.info("Running Cross-Asset Arb on %d markets…", len(binary_paths))
        ca = CrossAssetArb(min_edge=0.02, taker_fee_bps=120.0)
        sr = ca.run(binary_paths, seed=42)
        if sr.n_trades > 0:
            br = engine.evaluate(sr, capital_base=capital_base)
            results["cross_asset"] = br
            logger.info("  Cross-Asset: %d trades, total PnL $%.2f",
                         sr.n_trades, float(sr.pnl_per_trade.sum()))

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info("Backtest complete in %.1fs", elapsed)
    logger.info("=" * 60)

    return results


def print_results_table(results: dict) -> str:
    """Format results as a comparison table."""
    lines = []
    header = (
        f"{'Strategy':<25} {'Trades':>7} {'Total PnL':>12} {'Return%':>10} "
        f"{'Sharpe':>8} {'MDD%':>8} {'WinRate':>8}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for name, br in sorted(results.items()):
        m = br.metrics
        lines.append(
            f"{name:<25} {m.n_trades:>7d} ${m.total_pnl:>10.2f} "
            f"{m.total_return * 100:>9.2f}% {m.sharpe:>8.2f} "
            f"{m.max_drawdown * 100:>7.2f}% {m.win_rate * 100:>7.1f}%"
        )

    return "\n".join(lines)


def write_markdown_report(results: dict, path: str) -> None:
    """Write a markdown report of the real-data backtest."""
    lines = [
        "# Real-Data Backtest Report",
        "",
        f"*Generated from Polymarket historical data*",
        "",
        "## Strategy Performance",
        "",
        "| Strategy | Trades | Total PnL | Return | Sharpe | Max DD | Win Rate |",
        "|----------|--------|-----------|--------|--------|--------|----------|",
    ]

    for name, br in sorted(results.items()):
        m = br.metrics
        lines.append(
            f"| {name} | {m.n_trades} | ${m.total_pnl:.2f} | "
            f"{m.total_return * 100:.2f}% | {m.sharpe:.2f} | "
            f"{m.max_drawdown * 100:.2f}% | {m.win_rate * 100:.1f}% |"
        )

    lines.extend([
        "",
        "## Notes",
        "",
        "- Data source: Polymarket CLOB API (real historical prices)",
        "- NegRisk data from multi-outcome events (3+ outcomes)",
        "- Cross-platform uses real Polymarket prices with simulated Kalshi lag",
        "- Capital base: $100,000",
        "- No transaction costs on Polymarket (0% maker fee)",
        "",
    ])

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines))
    logger.info("Report written to %s", path)


def main():
    parser = argparse.ArgumentParser(description="Backtest on real Polymarket data")
    parser.add_argument("--n-markets", type=int, default=50)
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--strategies", type=str, default=None,
                        help="Comma-separated list of strategies to run")
    parser.add_argument("--report", type=str, default=None,
                        help="Path to write markdown report")
    args = parser.parse_args()

    strategies_filter = None
    if args.strategies:
        strategies_filter = set(args.strategies.split(","))

    results = run_real_backtest(
        n_markets=args.n_markets,
        capital_base=args.capital,
        strategies_filter=strategies_filter,
    )

    if results:
        table = print_results_table(results)
        print("\n" + table + "\n")

        if args.report:
            write_markdown_report(results, args.report)
    else:
        print("No results — check that Polymarket APIs are accessible.")
        print("Run from a machine with direct internet access (not cloud/sandbox).")


if __name__ == "__main__":
    main()
