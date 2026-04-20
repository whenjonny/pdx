"""Cross-venue arbitrage bot — scans, evaluates, and executes trades.

Modes:
  --dry-run (default): Paper trading with simulated fills
  --live:              Real execution on predictX (requires PDX_PRIVATE_KEY)

Usage:
    python stat_arb/run_bot.py --dry-run --interval 10
    python stat_arb/run_bot.py --live --capital 10000
"""

from __future__ import annotations

import argparse
import logging
import time

from pdx_arb.config import ArbConfig
from pdx_arb.execution.executor import ArbExecutor
from pdx_arb.feeds.matcher import MarketMatcher
from pdx_arb.feeds.polymarket import PolymarketFeed
from pdx_arb.feeds.predictx import PredictXFeed
from pdx_arb.portfolio import PortfolioTracker
from pdx_arb.risk.risk_manager import ArbRiskManager
from pdx_arb.strategy.stat_arb import CrossVenueStatArb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_bot(
    config: ArbConfig,
    initial_capital: float = 100_000.0,
    interval_s: float = 10.0,
    max_cycles: int = 0,
    dry_run: bool = True,
):
    poly_feed = PolymarketFeed(config.polymarket)
    pdx_feed = PredictXFeed(config.predictx)
    matcher = MarketMatcher(poly_feed, pdx_feed)
    strategy = CrossVenueStatArb(poly_feed, pdx_feed, config, prefer_yes=True)
    risk_mgr = ArbRiskManager(config, initial_capital=initial_capital)
    portfolio = PortfolioTracker(initial_capital=initial_capital)

    pdx_client = None
    if not dry_run:
        pdx_client = pdx_feed._get_sdk_client()
        if pdx_client is None:
            logger.error("Cannot init PDX client — check PDX_PRIVATE_KEY, PDX_MARKET_ADDRESS")
            return

    executor = ArbExecutor(config, pdx_client=pdx_client, dry_run=dry_run)

    mode = "PAPER" if dry_run else "LIVE"
    print(f"\n{'=' * 60}")
    print(f"  Cross-Venue Arbitrage Bot [{mode}]")
    print(f"  Capital: ${initial_capital:,.0f}")
    print(f"  Min spread: {config.min_net_spread_bps:.0f} bps")
    print(f"  Max position: ${config.max_position_usd:,.0f}")
    print(f"  Kelly fraction: {config.kelly_fraction:.0%}")
    print(f"  Scan interval: {interval_s}s")
    print(f"{'=' * 60}\n")

    cycle = 0
    try:
        while True:
            cycle += 1
            pairs = matcher.scan()
            if not pairs:
                if cycle == 1:
                    logger.info("No matched pairs found — waiting for markets...")
                time.sleep(interval_s)
                if 0 < max_cycles <= cycle:
                    break
                continue

            signals = strategy.scan(pairs)

            for signal in signals:
                mult = risk_mgr.recommended_size_multiplier()
                signal = signal.__class__(
                    **{**signal.__dict__, "suggested_size_usd": signal.suggested_size_usd * mult}
                )

                passed, reason = risk_mgr.check(signal)
                if not passed:
                    logger.debug("Risk blocked: %s — %s", signal.pair.question[:30], reason)
                    continue

                trade = executor.execute(signal)
                risk_mgr.record_trade(trade)
                portfolio.record_open(trade)

                if trade.status == "filled":
                    risk_mgr.record_settlement(trade)
                    portfolio.record_close(trade)

            if cycle % 10 == 0:
                _print_status(cycle, strategy, risk_mgr, executor, portfolio)

            if 0 < max_cycles <= cycle:
                break

            time.sleep(interval_s)

    except KeyboardInterrupt:
        print("\n\nShutting down...")

    _print_final_report(strategy, risk_mgr, executor, portfolio)


def _print_status(cycle, strategy, risk_mgr, executor, portfolio):
    s = strategy.summary()
    r = risk_mgr.summary()
    e = executor.summary()
    print(f"\n  --- Cycle {cycle} ---")
    print(f"  Pairs tracked: {s['tracked_pairs']} | Signals: {s['signals_generated']}")
    print(f"  Trades: {e['filled']} filled, {e['failed']} failed")
    print(f"  P&L: ${e['total_pnl']:+,.2f} | Capital: ${r['capital']:,.0f} | DD: {r['drawdown_pct']:.1f}%")


def _print_final_report(strategy, risk_mgr, executor, portfolio):
    portfolio.print_summary()

    s = strategy.summary()
    r = risk_mgr.summary()
    e = executor.summary()

    print(f"\n  Strategy: {s['scans']} scans, {s['signals_generated']} signals")
    print(f"  Risk: {r['passed']} passed, {r['rejected']} rejected")
    if r["reject_reasons"]:
        print(f"  Reject breakdown:")
        for reason, count in sorted(r["reject_reasons"].items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count}")
    print(f"  Execution: {e['filled']} filled, {e['failed']} failed, vol=${e['total_volume']:,.0f}")


def main():
    parser = argparse.ArgumentParser(description="Cross-venue arbitrage bot")
    parser.add_argument("--live", action="store_true", help="Enable live trading")
    parser.add_argument("--capital", type=float, default=100_000.0, help="Initial capital")
    parser.add_argument("--interval", type=float, default=10.0, help="Scan interval (s)")
    parser.add_argument("--min-spread", type=float, default=150.0, help="Min net spread (bps)")
    parser.add_argument("--max-position", type=float, default=5000.0, help="Max position USD")
    parser.add_argument("--max-cycles", type=int, default=0, help="Max cycles (0=unlimited)")
    args = parser.parse_args()

    config = ArbConfig.from_env()
    config.min_net_spread_bps = args.min_spread
    config.max_position_usd = args.max_position

    run_bot(
        config=config,
        initial_capital=args.capital,
        interval_s=args.interval,
        max_cycles=args.max_cycles,
        dry_run=not args.live,
    )


if __name__ == "__main__":
    main()
