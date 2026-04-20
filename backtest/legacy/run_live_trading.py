#!/usr/bin/env python3
"""Live paper trading against Polymarket exchange for 5+ hours.

Usage:
    python3 backtest/run_live_trading.py
    python3 backtest/run_live_trading.py --hours 5 --capital 100000
    python3 backtest/run_live_trading.py --poll-interval 30 --report backtest/reports/live_trading.md

Requires network access to Polymarket CLOB API.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdx_backtest.exchange_connector import (
    ExchangeConnector,
    LiveNegRiskRebalancer,
    LiveSingleBinaryRebalancer,
    LiveStatArb,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def write_live_report(report: dict, trades_log: list, path: str) -> None:
    """Write markdown report of the live trading session."""
    lines = [
        "# Live Paper Trading Report",
        "",
        f"*Session: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        f"*Duration: {report['duration_hours']:.2f} hours*",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Duration | {report['duration_hours']:.2f} hours |",
        f"| Total Steps | {report['total_steps']} |",
        f"| Total Trades | {report['total_trades']} |",
        f"| Total PnL | ${report['total_pnl']:.2f} |",
        f"| Return | {report['return_pct']:.2f}% |",
        f"| Win Rate | {report['win_rate'] * 100:.1f}% |",
        f"| Max Drawdown | {report['max_drawdown'] * 100:.2f}% |",
        f"| Final Equity | ${report['final_equity']:.2f} |",
        f"| Open Positions | {report['open_positions']} |",
        "",
        "## Per-Strategy Breakdown",
        "",
        "| Strategy | Trades | PnL |",
        "|----------|--------|-----|",
    ]

    for strategy, pnl in report.get("strategy_pnl", {}).items():
        n = report.get("strategy_trades", {}).get(strategy, 0)
        lines.append(f"| {strategy} | {n} | ${pnl:.2f} |")

    if trades_log:
        lines.extend([
            "",
            "## Trade Log (last 50)",
            "",
            "| Time | Strategy | Market | Action | Side | Size | Price | PnL |",
            "|------|----------|--------|--------|------|------|-------|-----|",
        ])
        for t in trades_log[-50:]:
            ts = datetime.fromtimestamp(t["timestamp"]).strftime("%H:%M:%S")
            lines.append(
                f"| {ts} | {t['strategy']} | {t['market'][:30]} | "
                f"{t['action']} | {t['side']} | {t['size']:.2f} | "
                f"${t['price']:.4f} | ${t['pnl']:.2f} |"
            )

    lines.extend([
        "",
        "## Notes",
        "",
        "- Exchange: Polymarket CLOB (paper trading, no real orders)",
        "- Data: Live midpoint prices via REST polling",
        "- Strategies: NegRisk rebalancing, single-binary arb, statistical arb",
        "- Position auto-close: 30 minutes",
        "",
    ])

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines))
    logger.info("Report written to %s", path)


def write_trades_json(portfolio, path: str) -> None:
    """Save full trade log as JSON for further analysis."""
    trades_data = []
    for t in portfolio.trades:
        trades_data.append({
            "timestamp": t.timestamp,
            "market": t.market_slug,
            "token_id": t.token_id,
            "action": t.action,
            "side": t.side,
            "size": t.size,
            "price": t.price,
            "notional": t.notional,
            "pnl": t.pnl,
            "strategy": t.strategy,
            "meta": t.meta,
        })

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(trades_data, indent=2))
    logger.info("Trade log written to %s (%d trades)", path, len(trades_data))


async def run_live(args) -> None:
    strategies = [
        LiveNegRiskRebalancer(
            threshold=0.02,
            capital_per_trade=500.0,
            taker_fee_bps=0.0,
        ),
        LiveSingleBinaryRebalancer(
            threshold=0.005,
            capital_per_trade=500.0,
            taker_fee_bps=0.0,
        ),
        LiveStatArb(
            min_edge=0.03,
            capital_per_trade=500.0,
        ),
    ]

    connector = ExchangeConnector(
        strategies=strategies,
        initial_capital=args.capital,
        poll_interval_sec=args.poll_interval,
        max_markets=args.max_markets,
        min_volume=args.min_volume,
    )

    logger.info("=" * 60)
    logger.info("LIVE PAPER TRADING SESSION")
    logger.info("=" * 60)
    logger.info("Duration: %.1f hours", args.hours)
    logger.info("Capital: $%.2f", args.capital)
    logger.info("Poll interval: %.0fs", args.poll_interval)
    logger.info("Strategies: %s", ", ".join(s.name for s in strategies))
    logger.info("=" * 60)

    report = await connector.run_for(hours=args.hours)

    # Print summary
    print("\n" + "=" * 60)
    print("LIVE TRADING SESSION COMPLETE")
    print("=" * 60)
    print(f"Duration:       {report['duration_hours']:.2f} hours")
    print(f"Total Steps:    {report['total_steps']}")
    print(f"Total Trades:   {report['total_trades']}")
    print(f"Total PnL:      ${report['total_pnl']:.2f}")
    print(f"Return:         {report['return_pct']:.2f}%")
    print(f"Win Rate:       {report['win_rate'] * 100:.1f}%")
    print(f"Max Drawdown:   {report['max_drawdown'] * 100:.2f}%")
    print(f"Final Equity:   ${report['final_equity']:.2f}")

    print("\nPer-Strategy:")
    for strategy, pnl in report.get("strategy_pnl", {}).items():
        n = report.get("strategy_trades", {}).get(strategy, 0)
        print(f"  {strategy}: {n} trades, PnL ${pnl:.2f}")

    # Save reports
    if args.report:
        trades_log = [
            {"timestamp": t.timestamp, "strategy": t.strategy,
             "market": t.market_slug, "action": t.action,
             "side": t.side, "size": t.size, "price": t.price, "pnl": t.pnl}
            for t in connector.portfolio.trades
        ]
        write_live_report(report, trades_log, args.report)

    if args.trades_json:
        write_trades_json(connector.portfolio, args.trades_json)


def main():
    parser = argparse.ArgumentParser(description="Live paper trading on Polymarket")
    parser.add_argument("--hours", type=float, default=5.0,
                        help="Trading session duration in hours")
    parser.add_argument("--capital", type=float, default=100_000.0,
                        help="Initial paper trading capital")
    parser.add_argument("--poll-interval", type=float, default=30.0,
                        help="Price polling interval in seconds")
    parser.add_argument("--max-markets", type=int, default=50,
                        help="Max markets to track")
    parser.add_argument("--min-volume", type=float, default=10_000,
                        help="Minimum market volume to track")
    parser.add_argument("--report", type=str,
                        default="backtest/reports/live_trading.md",
                        help="Path for markdown report")
    parser.add_argument("--trades-json", type=str,
                        default="backtest/reports/live_trades.json",
                        help="Path for JSON trade log")
    args = parser.parse_args()

    try:
        asyncio.run(run_live(args))
    except KeyboardInterrupt:
        logger.info("Session interrupted by user")


if __name__ == "__main__":
    main()
