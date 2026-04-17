#!/usr/bin/env python3
"""Cross-venue arbitrage paper trading simulation (Polymarket ↔ predict.fun).

Runs a compressed live simulation with simulated prices from both venues.
Each tick represents ~30 seconds of real time, compressed to run quickly.

Usage:
    python3 backtest/run_cross_venue_sim.py
    python3 backtest/run_cross_venue_sim.py --ticks 1000 --capital 100000
    python3 backtest/run_cross_venue_sim.py --report backtest/reports/cross_venue_sim.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from pdx_backtest.exchange_connector import (
    LiveCrossVenueArb,
    LiveNegRiskRebalancer,
    LiveSingleBinaryRebalancer,
    PaperPortfolio,
    _SimulatedCrossVenueFeed,
    _SimulatedPriceFeed,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_cross_venue_sim(
    n_ticks: int = 600,
    capital: float = 100_000.0,
    auto_close_after: int = 60,
) -> dict:
    """Run compressed cross-venue paper trading simulation.

    Parameters
    ----------
    n_ticks : int
        Number of simulated ticks (~30s each → 600 ticks ≈ 5 hours).
    capital : float
        Starting capital in USDC.
    auto_close_after : int
        Auto-close positions after this many ticks.
    """
    portfolio = PaperPortfolio(initial_capital=capital, cash=capital)

    poly_feed = _SimulatedPriceFeed(n_binary=30, n_event_outcomes=5, n_events=4, seed=42)
    cross_feed = _SimulatedCrossVenueFeed(poly_feed, seed=99)

    cross_venue_strat = LiveCrossVenueArb(
        min_spread=0.02,
        capital_per_trade=1_000.0,
        poly_fee_bps=0.0,
        predict_fee_bps=150.0,
        settlement_risk_bps=50.0,
        max_positions=10,
    )

    negrisk_strat = LiveNegRiskRebalancer(
        threshold=0.02, capital_per_trade=500.0, max_positions=20)

    single_binary_strat = LiveSingleBinaryRebalancer(
        threshold=0.005, capital_per_trade=500.0, max_positions=10)

    strategies = [cross_venue_strat, negrisk_strat, single_binary_strat]

    logger.info("=" * 60)
    logger.info("CROSS-VENUE PAPER TRADING SIMULATION")
    logger.info("=" * 60)
    logger.info("Ticks: %d (~%.1f simulated hours)", n_ticks, n_ticks * 30 / 3600)
    logger.info("Capital: $%.0f", capital)
    logger.info("Strategies: %s", ", ".join(s.name for s in strategies))
    logger.info("Markets: %d binary + %d multi-outcome events",
                 len(poly_feed.markets), len(poly_feed.events))
    logger.info("=" * 60)

    start = time.time()

    # Track entry tick and origin strategy per position (keyed by token_id)
    pos_meta: dict[str, dict] = {}

    for tick in range(n_ticks):
        poly_prices = poly_feed.step()
        predict_prices = cross_feed.step(poly_prices)

        cross_venue_strat.update_predict_prices(predict_prices)

        n_before = len(portfolio.positions)
        for strat in strategies:
            try:
                strat.on_tick(
                    portfolio, poly_prices,
                    poly_feed.markets, poly_feed.events, tick,
                )
            except Exception as exc:
                logger.error("Strategy %s error at tick %d: %s",
                             strat.name, tick, exc)

        # Register newly opened positions
        for pos in portfolio.positions:
            if pos.token_id not in pos_meta:
                # Find the opening trade to get the strategy name
                origin = "unknown"
                for t in reversed(portfolio.trades):
                    if t.token_id == pos.token_id and t.action == "open":
                        origin = t.strategy
                        break
                pos_meta[pos.token_id] = {"entry_tick": tick, "origin": origin}

        # Auto-close old positions (iterate in reverse for safe removal)
        to_close = []
        for i, pos in enumerate(portfolio.positions):
            meta = pos_meta.get(pos.token_id, {})
            entry_tick = meta.get("entry_tick", tick)
            if tick - entry_tick > auto_close_after:
                to_close.append(i)

        for offset, idx in enumerate(to_close):
            adj = idx - offset
            if adj < len(portfolio.positions):
                pos = portfolio.positions[adj]
                p = poly_prices.get(pos.token_id, pos.entry_price)
                origin = pos_meta.get(pos.token_id, {}).get("origin", "auto_close")
                portfolio.close_position(adj, p, strategy=origin)
                pos_meta.pop(pos.token_id, None)

        portfolio.record_equity(poly_prices)

        if tick % 100 == 0 and tick > 0:
            mtm = portfolio.mark_to_market(poly_prices)
            pnl = mtm - capital
            closed = [t for t in portfolio.trades if t.action == "close"]
            cv_closed = [t for t in closed if t.strategy == "live_cross_venue"]
            logger.info(
                "[Tick %d/%d] MTM $%.0f | PnL $%.2f | "
                "Positions %d | Closed %d (CV: %d)",
                tick, n_ticks, mtm, pnl,
                len(portfolio.positions), len(closed), len(cv_closed),
            )

    # Force-close all remaining positions
    final_poly = poly_feed.step()
    n_forced = len(portfolio.positions)
    for i in range(len(portfolio.positions) - 1, -1, -1):
        pos = portfolio.positions[i]
        p = final_poly.get(pos.token_id, pos.entry_price)
        origin = pos_meta.get(pos.token_id, {}).get("origin", "session_end")
        portfolio.close_position(i, p, strategy=origin)
    portfolio.record_equity(final_poly)

    elapsed = time.time() - start
    logger.info("Simulation complete in %.1fs (%d ticks, %d forced closes)",
                 elapsed, n_ticks, n_forced)

    # Build report
    closed_trades = [t for t in portfolio.trades if t.action == "close"]
    pnl_by_strategy: dict[str, list[float]] = {}
    for t in closed_trades:
        pnl_by_strategy.setdefault(t.strategy, []).append(t.pnl)

    report = {
        "n_ticks": n_ticks,
        "simulated_hours": n_ticks * 30 / 3600,
        "elapsed_sec": elapsed,
        "initial_capital": capital,
        "final_equity": portfolio.equity_history[-1][1] if portfolio.equity_history else capital,
        "total_pnl": sum(t.pnl for t in closed_trades),
        "total_closed_trades": len(closed_trades),
        "strategies": {},
    }

    for strat_name, pnls in pnl_by_strategy.items():
        pnl_arr = np.array(pnls)
        report["strategies"][strat_name] = {
            "trades": len(pnls),
            "total_pnl": float(pnl_arr.sum()),
            "avg_pnl": float(pnl_arr.mean()) if pnls else 0,
            "win_rate": float((pnl_arr > 0).mean()) if pnls else 0,
            "max_win": float(pnl_arr.max()) if pnls else 0,
            "max_loss": float(pnl_arr.min()) if pnls else 0,
        }

    report["return_pct"] = report["total_pnl"] / capital * 100
    return report


def print_report(report: dict) -> None:
    print("\n" + "=" * 65)
    print("CROSS-VENUE SIMULATION RESULTS")
    print("=" * 65)
    print(f"Simulated:      {report['simulated_hours']:.1f} hours ({report['n_ticks']} ticks)")
    print(f"Wall time:      {report['elapsed_sec']:.1f}s")
    print(f"Capital:        ${report['initial_capital']:,.0f}")
    print(f"Final equity:   ${report['final_equity']:,.2f}")
    print(f"Total PnL:      ${report['total_pnl']:,.2f}")
    print(f"Return:         {report['return_pct']:.2f}%")
    print(f"Closed trades:  {report['total_closed_trades']}")
    print()

    header = f"{'Strategy':<25} {'Trades':>7} {'PnL':>12} {'Avg':>10} {'WinRate':>8} {'MaxWin':>10} {'MaxLoss':>10}"
    print(header)
    print("-" * len(header))

    for name, stats in sorted(report["strategies"].items()):
        print(
            f"{name:<25} {stats['trades']:>7d} ${stats['total_pnl']:>10.2f} "
            f"${stats['avg_pnl']:>8.2f} {stats['win_rate']*100:>7.1f}% "
            f"${stats['max_win']:>8.2f} ${stats['max_loss']:>8.2f}"
        )
    print()


def write_markdown_report(report: dict, path: str) -> None:
    lines = [
        "# Cross-Venue Arbitrage Simulation Report",
        "",
        f"*{datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Simulated Duration | {report['simulated_hours']:.1f} hours |",
        f"| Ticks | {report['n_ticks']} |",
        f"| Capital | ${report['initial_capital']:,.0f} |",
        f"| Final Equity | ${report['final_equity']:,.2f} |",
        f"| Total PnL | ${report['total_pnl']:,.2f} |",
        f"| Return | {report['return_pct']:.2f}% |",
        f"| Closed Trades | {report['total_closed_trades']} |",
        "",
        "## Per-Strategy Breakdown",
        "",
        "| Strategy | Trades | PnL | Avg PnL | Win Rate | Max Win | Max Loss |",
        "|----------|--------|-----|---------|----------|---------|----------|",
    ]

    for name, s in sorted(report["strategies"].items()):
        lines.append(
            f"| {name} | {s['trades']} | ${s['total_pnl']:.2f} | "
            f"${s['avg_pnl']:.2f} | {s['win_rate']*100:.1f}% | "
            f"${s['max_win']:.2f} | ${s['max_loss']:.2f} |"
        )

    lines.extend([
        "",
        "## Venues",
        "",
        "- **Polymarket** (Polygon / USDC): 0% maker fee",
        "- **predict.fun** (Blast L2 / USDB): ~150 bps fee",
        "- Settlement risk haircut: 50 bps (cross-chain bridge latency)",
        "",
        "## Notes",
        "",
        "- Simulated prices: Polymarket random walk + predict.fun lagged (1-3 ticks) with spread",
        "- Cross-venue arb: trades when spread > 2 cents after all fees + settlement risk",
        "- Other strategies (NegRisk, Single Binary) run in parallel as baseline comparison",
        "- Positions auto-close after 60 ticks (~30 min simulated time)",
        "",
    ])

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines))
    logger.info("Report written to %s", path)


def main():
    parser = argparse.ArgumentParser(
        description="Cross-venue arb paper trading simulation")
    parser.add_argument("--ticks", type=int, default=600,
                        help="Number of simulated ticks (default 600 ≈ 5h)")
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--report", type=str,
                        default="backtest/reports/cross_venue_sim.md")
    parser.add_argument("--trades-json", type=str, default=None)
    args = parser.parse_args()

    report = run_cross_venue_sim(
        n_ticks=args.ticks,
        capital=args.capital,
    )

    print_report(report)
    write_markdown_report(report, args.report)

    if args.trades_json:
        Path(args.trades_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.trades_json).write_text(json.dumps(report, indent=2))
        logger.info("JSON report written to %s", args.trades_json)


if __name__ == "__main__":
    main()
