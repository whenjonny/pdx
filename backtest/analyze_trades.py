"""Analyze winning vs losing trades in basic stat arb to find hidden signal."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from pdx_backtest.data import generate_binary_path
from pdx_backtest.event_engine import (
    EventEngine, MarketSimulator, OrderBookSimulator,
)
from pdx_backtest.friction import FrictionParams
from pdx_backtest.oms import OrderManagementSystem
from pdx_backtest.portfolio import Portfolio
from pdx_backtest.risk_manager import RiskLimits, RiskManager
from pdx_backtest.strategies.event_strategies import EventStatArb


def collect_trades_with_context(n_markets: int = 50, n_steps: int = 500,
                                 seeds: list[int] | None = None) -> list[dict]:
    """Run stat arb and capture per-trade context."""
    if seeds is None:
        seeds = [42 + i * 17 for i in range(5)]

    all_trades = []

    for seed in seeds:
        engine = EventEngine(seed=seed)
        rng = np.random.default_rng(seed)
        portfolio = Portfolio(engine, initial_capital=100_000.0)
        risk_mgr = RiskManager(engine, portfolio, RiskLimits(
            max_open_positions=500, max_strategy_positions=200,
            max_strategy_loss=50_000.0, max_single_trade_notional=10_000.0,
        ))
        oms = OrderManagementSystem(
            engine, default_friction=FrictionParams.polymarket(),
            rng=rng, risk_manager=risk_mgr,
        )
        OrderBookSimulator(engine, rng)
        ms = MarketSimulator(engine, rng)

        paths = {}
        for i in range(n_markets):
            path = generate_binary_path(n_steps=n_steps, seed=seed + i)
            mid = f"binary_{i:03d}"
            ms.load_binary_market(mid, path)
            paths[mid] = path
        ms.schedule_settlements(float(n_steps + 10))

        strat = EventStatArb(
            engine, oms, risk_mgr,
            ema_span=20, min_edge=0.03, cooldown_ticks=10,
            max_fraction=0.25, bankroll=10_000.0,
        )

        fills_by_market = defaultdict(list)
        from pdx_backtest.event_engine import OrderFill
        engine.register(OrderFill, lambda f: fills_by_market[f.market_id].append(f)
                         if f.strategy_name == strat.name else None)

        engine.run()

        for trade in portfolio.closed_trades_for_strategy(strat.name):
            mid = trade.market_id
            path = paths.get(mid)
            if path is None:
                continue

            fills = fills_by_market.get(mid, [])
            fill = next((f for f in fills if f.fill_price == trade.entry_price), None)
            entry_step = int(fill.timestamp) if fill else 0

            all_trades.append({
                "seed": seed,
                "market": mid,
                "entry_step": entry_step,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "side": trade.side,
                "size": trade.size,
                "notional": trade.notional,
                "pnl": trade.pnl,
                "roi": trade.pnl / trade.notional if trade.notional > 0 else 0,
                "outcome": path.outcome,
                "true_prob_at_entry": float(path.true_prob[min(entry_step, len(path) - 1)]),
                "market_price_at_entry": float(path.market_price[min(entry_step, len(path) - 1)]),
                "true_prob_final": float(path.true_prob[-1]),
                "price_range": float(path.market_price.max() - path.market_price.min()),
                "price_vol": float(path.market_price.std()),
            })

    return all_trades


def analyze_winning_vs_losing(trades: list[dict]) -> None:
    if not trades:
        print("  No trades collected.")
        return

    winners = [t for t in trades if t["pnl"] > 0]
    losers = [t for t in trades if t["pnl"] <= 0]

    print(f"\n  Total trades: {len(trades)}")
    print(f"  Winners: {len(winners)} ({len(winners)/len(trades):.1%})")
    print(f"  Losers: {len(losers)} ({len(losers)/len(trades):.1%})")
    print(f"  Avg winner PnL: ${np.mean([t['pnl'] for t in winners]):+,.2f}")
    print(f"  Avg loser PnL: ${np.mean([t['pnl'] for t in losers]):+,.2f}")

    print("\n  Feature comparison (winners vs losers):")
    features = [
        "entry_step", "entry_price", "true_prob_at_entry",
        "market_price_at_entry", "price_range", "price_vol", "notional",
    ]
    print(f"    {'Feature':<26s} {'Winners':>12s} {'Losers':>12s} {'Delta':>10s}")
    print("    " + "-" * 62)
    for feat in features:
        w = np.mean([t[feat] for t in winners])
        l = np.mean([t[feat] for t in losers])
        delta = w - l
        print(f"    {feat:<26s} {w:>12.4f} {l:>12.4f} {delta:>+10.4f}")


def analyze_by_entry_price(trades: list[dict]) -> None:
    print("\n  PnL by entry price zone:")
    zones = [(0.0, 0.15), (0.15, 0.30), (0.30, 0.50),
             (0.50, 0.70), (0.70, 0.85), (0.85, 1.0)]
    print(f"    {'Zone':<18s} {'Trades':>7s} {'WinRate':>9s} "
          f"{'AvgPnL':>10s} {'TotalPnL':>12s}")
    print("    " + "-" * 58)
    for lo, hi in zones:
        zone_trades = [t for t in trades if lo <= t["entry_price"] < hi]
        if not zone_trades:
            continue
        pnls = [t["pnl"] for t in zone_trades]
        wr = sum(1 for p in pnls if p > 0) / len(pnls)
        print(f"    [{lo:.2f}, {hi:.2f})       {len(zone_trades):>7d} "
              f"{wr:>8.1%} ${np.mean(pnls):>+9,.1f} ${sum(pnls):>+11,.1f}")


def analyze_by_entry_timing(trades: list[dict]) -> None:
    print("\n  PnL by entry step (time within market):")
    zones = [(0, 50), (50, 150), (150, 300), (300, 450), (450, 500)]
    print(f"    {'Step range':<14s} {'Trades':>7s} {'WinRate':>9s} "
          f"{'AvgPnL':>10s} {'TotalPnL':>12s}")
    print("    " + "-" * 58)
    for lo, hi in zones:
        zone = [t for t in trades if lo <= t["entry_step"] < hi]
        if not zone:
            continue
        pnls = [t["pnl"] for t in zone]
        wr = sum(1 for p in pnls if p > 0) / len(pnls)
        print(f"    [{lo:>3d}, {hi:>3d})     {len(zone):>7d} "
              f"{wr:>8.1%} ${np.mean(pnls):>+9,.1f} ${sum(pnls):>+11,.1f}")


def analyze_side_performance(trades: list[dict]) -> None:
    print("\n  PnL by side:")
    for side in ["yes", "no"]:
        side_trades = [t for t in trades if t["side"] == side]
        if not side_trades:
            continue
        pnls = [t["pnl"] for t in side_trades]
        wr = sum(1 for p in pnls if p > 0) / len(pnls)
        print(f"    {side:>4s}: {len(side_trades):>4d} trades, "
              f"win={wr:.1%}, avg=${np.mean(pnls):+,.2f}, "
              f"total=${sum(pnls):+,.2f}")


def analyze_by_market_characteristics(trades: list[dict]) -> None:
    print("\n  PnL by market vol quintile:")
    trades_sorted = sorted(trades, key=lambda t: t["price_vol"])
    n = len(trades_sorted)
    for i, name in enumerate(["Q1 (low vol)", "Q2", "Q3", "Q4", "Q5 (high vol)"]):
        lo = i * n // 5
        hi = (i + 1) * n // 5
        zone = trades_sorted[lo:hi]
        if not zone:
            continue
        pnls = [t["pnl"] for t in zone]
        wr = sum(1 for p in pnls if p > 0) / len(pnls)
        vol_range = (zone[0]["price_vol"], zone[-1]["price_vol"])
        print(f"    {name:<20s} vol∈[{vol_range[0]:.3f},{vol_range[1]:.3f}] "
              f"win={wr:.1%} avg=${np.mean(pnls):+,.0f} total=${sum(pnls):+,.0f}")


def analyze_hold_duration(trades: list[dict]) -> None:
    print("\n  PnL by 'distance to settlement' (500 - entry_step):")
    zones = [(0, 50), (50, 150), (150, 300), (300, 500)]
    for lo, hi in zones:
        zone = [t for t in trades if lo <= (500 - t["entry_step"]) < hi]
        if not zone:
            continue
        pnls = [t["pnl"] for t in zone]
        wr = sum(1 for p in pnls if p > 0) / len(pnls)
        print(f"    Settlement in [{lo:>3d},{hi:>3d}) steps: "
              f"{len(zone):>4d} trades, "
              f"win={wr:.1%}, avg=${np.mean(pnls):+,.2f}")


def main() -> None:
    print("=" * 72)
    print("  Trade-level Analysis: What makes winners differ from losers?")
    print("=" * 72)
    print("\n  Collecting trades from 5 seeds x 50 markets = ~500 trades each...")

    trades = collect_trades_with_context(n_markets=50)
    print(f"  Collected {len(trades)} trades")

    analyze_winning_vs_losing(trades)
    analyze_by_entry_price(trades)
    analyze_by_entry_timing(trades)
    analyze_side_performance(trades)
    analyze_by_market_characteristics(trades)
    analyze_hold_duration(trades)


if __name__ == "__main__":
    main()
