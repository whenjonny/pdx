"""Scan for cross-venue arbitrage opportunities between Polymarket and predictX.

This is the read-only scanner — it finds and reports opportunities without
executing any trades. Use run_bot.py for live/paper trading.

Usage:
    python stat_arb/run_scanner.py [--interval 10] [--min-spread 150]
"""

from __future__ import annotations

import argparse
import logging
import time

from pdx_arb.config import ArbConfig
from pdx_arb.feeds.matcher import MarketMatcher
from pdx_arb.feeds.polymarket import PolymarketFeed
from pdx_arb.feeds.predictx import PredictXFeed
from pdx_arb.strategy.stat_arb import CrossVenueStatArb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def scan_once(
    matcher: MarketMatcher,
    strategy: CrossVenueStatArb,
    verbose: bool = True,
) -> list:
    """Run one scan cycle."""
    pairs = matcher.scan()
    if not pairs:
        logger.info("No matched market pairs found")
        return []

    logger.info("Scanning %d matched pairs...", len(pairs))
    signals = strategy.scan(pairs)

    if verbose and signals:
        print(f"\n{'=' * 80}")
        print(f"  Found {len(signals)} arbitrage opportunities")
        print(f"{'=' * 80}")
        print(f"  {'Market':<40s} {'Direction':<24s} {'Net bps':>8s} {'Size':>8s} {'Conf':>6s}")
        print(f"  {'-' * 78}")
        for sig in sorted(signals, key=lambda s: -s.net_spread_bps):
            print(
                f"  {sig.pair.question[:38]:<40s} "
                f"{sig.buy_venue.name[:4]}→{sig.sell_venue.name[:4]} "
                f"({sig.buy_side.name:<8s})  "
                f"{sig.net_spread_bps:>+7.0f} "
                f"${sig.suggested_size_usd:>6,.0f} "
                f"{sig.confidence:>5.0%}"
            )
    elif verbose:
        logger.info("No profitable opportunities found this scan")

    return signals


def run_continuous(
    matcher: MarketMatcher,
    strategy: CrossVenueStatArb,
    interval_s: float = 10.0,
    max_scans: int = 0,
):
    """Run scanner in a loop."""
    scan_count = 0
    total_signals = 0

    print(f"\nStarting continuous scan (interval={interval_s}s)")
    print(f"Min net spread: {strategy.config.min_net_spread_bps:.0f} bps")
    print(f"Press Ctrl+C to stop\n")

    try:
        while True:
            scan_count += 1
            signals = scan_once(matcher, strategy, verbose=True)
            total_signals += len(signals)

            if scan_count % 10 == 0:
                s = strategy.summary()
                print(f"\n  --- Scan #{scan_count} stats: "
                      f"pairs={s['tracked_pairs']}, "
                      f"signals={total_signals}, "
                      f"above_threshold={s['pairs_above_threshold']} ---\n")

            if 0 < max_scans <= scan_count:
                break

            time.sleep(interval_s)
    except KeyboardInterrupt:
        print(f"\n\nStopped after {scan_count} scans, {total_signals} signals found")


def main():
    parser = argparse.ArgumentParser(description="Cross-venue arb scanner")
    parser.add_argument("--interval", type=float, default=10.0, help="Scan interval (seconds)")
    parser.add_argument("--min-spread", type=float, default=150.0, help="Min net spread (bps)")
    parser.add_argument("--max-scans", type=int, default=0, help="Max scans (0=unlimited)")
    parser.add_argument("--once", action="store_true", help="Single scan then exit")
    args = parser.parse_args()

    config = ArbConfig.from_env()
    config.min_net_spread_bps = args.min_spread

    poly_feed = PolymarketFeed(config.polymarket)
    pdx_feed = PredictXFeed(config.predictx)
    matcher = MarketMatcher(poly_feed, pdx_feed)
    strategy = CrossVenueStatArb(poly_feed, pdx_feed, config, prefer_yes=True)

    if args.once:
        scan_once(matcher, strategy)
    else:
        run_continuous(matcher, strategy, interval_s=args.interval, max_scans=args.max_scans)


if __name__ == "__main__":
    main()
