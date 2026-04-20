#!/usr/bin/env python3
"""Risk-enhanced backtest + 5-hour live simulation.

Uses Kelly criterion, volatility scaling, and dynamic capital allocation
to optimize PnL across all strategies.

Usage:
    python3 backtest/run_risk_enhanced.py
    python3 backtest/run_risk_enhanced.py --n-markets 100 --hours 5
    python3 backtest/run_risk_enhanced.py --report backtest/reports/risk_enhanced.md
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from pdx_backtest.engine import BacktestEngine
from pdx_backtest.historical_data import (
    fetch_binary_market_paths,
    fetch_cross_platform_proxy_paths,
    fetch_negrisk_snapshots,
)
from pdx_backtest.metrics import half_kelly, kelly_fraction
from pdx_backtest.strategies import (
    CrossAssetArb,
    CrossPlatformArb,
    LongshotBiasExploiter,
    NegRiskRebalancer,
    SingleBinaryRebalancer,
    StatisticalArb,
    TimeArb,
    VolatilityEventStrategy,
)
from pdx_backtest.strategies.base import StrategyResult, Trade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Risk parameter estimation
# ---------------------------------------------------------------------------


@dataclass
class RiskProfile:
    name: str
    win_rate: float
    avg_win: float
    avg_loss: float
    kelly_frac: float
    half_kelly_frac: float
    vol: float
    sharpe: float
    n_trades: int
    total_pnl: float
    allocated_capital: float = 0.0


def estimate_risk_profile(name: str, result: StrategyResult) -> RiskProfile:
    """Estimate risk parameters from a calibration run."""
    pnl = result.pnl_per_trade
    if len(pnl) == 0:
        return RiskProfile(name=name, win_rate=0, avg_win=0, avg_loss=0,
                           kelly_frac=0, half_kelly_frac=0, vol=0, sharpe=0,
                           n_trades=0, total_pnl=0)

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    wr = len(wins) / len(pnl) if len(pnl) > 0 else 0
    avg_w = float(wins.mean()) if len(wins) > 0 else 0
    avg_l = float(np.abs(losses).mean()) if len(losses) > 0 else 0.01

    # Kelly from win rate and payoff ratio
    if avg_l > 0 and wr > 0:
        b = avg_w / avg_l  # payoff ratio
        kf = (b * wr - (1 - wr)) / b
        kf = max(0.0, min(1.0, kf))
    else:
        kf = 0.0

    hk = kf * 0.5
    vol = float(np.std(result.returns, ddof=1)) if len(result.returns) > 1 else 1.0
    mean_r = float(np.mean(result.returns)) if len(result.returns) > 0 else 0.0
    sharpe = mean_r / vol if vol > 0 else 0.0

    return RiskProfile(
        name=name, win_rate=wr, avg_win=avg_w, avg_loss=avg_l,
        kelly_frac=kf, half_kelly_frac=hk, vol=vol, sharpe=sharpe,
        n_trades=len(pnl), total_pnl=float(pnl.sum()),
    )


def allocate_capital(profiles: list[RiskProfile], total_capital: float,
                     min_alloc: float = 0.05, max_alloc: float = 0.40) -> dict[str, float]:
    """Allocate capital across strategies proportional to Sharpe, capped."""
    positive = [p for p in profiles if p.sharpe > 0 and p.n_trades >= 3]
    if not positive:
        even = total_capital / max(len(profiles), 1)
        return {p.name: even for p in profiles}

    total_sharpe = sum(p.sharpe for p in positive)
    alloc = {}
    for p in profiles:
        if p.sharpe > 0 and p.n_trades >= 3:
            raw = (p.sharpe / total_sharpe) if total_sharpe > 0 else 0
            capped = max(min_alloc, min(max_alloc, raw))
            alloc[p.name] = capped * total_capital
        else:
            alloc[p.name] = min_alloc * total_capital

    # Normalize to total_capital
    s = sum(alloc.values())
    if s > 0:
        for k in alloc:
            alloc[k] = alloc[k] / s * total_capital
    return alloc


# ---------------------------------------------------------------------------
# Strategy runners (single-path strategies need aggregation)
# ---------------------------------------------------------------------------


def _run_negrisk(negrisk_seqs, capital_per_trade, threshold=0.01):
    nr = NegRiskRebalancer(threshold=threshold, taker_fee_bps=0.0,
                           capital_per_trade=capital_per_trade)
    all_t, all_p, all_r = [], [], []
    for seq in negrisk_seqs:
        sr = nr.run(seq)
        all_t.extend(sr.trades)
        all_p.extend(sr.pnl_per_trade.tolist())
        all_r.extend(sr.returns.tolist())
    if not all_t:
        return StrategyResult(name="negrisk_rebalancer", trades=[], equity_curve=np.array([0.0]),
                              returns=np.array([]), pnl_per_trade=np.array([]),
                              capital_deployed=0, capital_lockup_period_steps=0, notes={})
    return StrategyResult(
        name="negrisk_rebalancer", trades=all_t,
        equity_curve=np.cumsum([0.0] + all_p),
        returns=np.array(all_r), pnl_per_trade=np.array(all_p),
        capital_deployed=sum(t.notional for t in all_t),
        capital_lockup_period_steps=len(all_t), notes={"data_source": "realistic"},
    )


def _run_single_binary(binary_paths, capital_per_trade, threshold=0.02, no_noise=0.001):
    sb = SingleBinaryRebalancer(threshold=threshold, taker_fee_bps=0.0,
                                capital_per_trade=capital_per_trade, no_noise_std=no_noise)
    all_t, all_p, all_r = [], [], []
    for i, path in enumerate(binary_paths):
        sr = sb.run(path, seed=i)
        all_t.extend(sr.trades)
        all_p.extend(sr.pnl_per_trade.tolist())
        all_r.extend(sr.returns.tolist())
    if not all_t:
        return StrategyResult(name="single_binary_rebalancer", trades=[], equity_curve=np.array([0.0]),
                              returns=np.array([]), pnl_per_trade=np.array([]),
                              capital_deployed=0, capital_lockup_period_steps=0, notes={})
    return StrategyResult(
        name="single_binary_rebalancer", trades=all_t,
        equity_curve=np.cumsum([0.0] + all_p),
        returns=np.array(all_r), pnl_per_trade=np.array(all_p),
        capital_deployed=sum(t.notional for t in all_t),
        capital_lockup_period_steps=len(all_t), notes={"data_source": "realistic"},
    )


def _run_stat_arb(binary_paths, bankroll=10_000, min_edge=0.02):
    sa = StatisticalArb(min_edge=min_edge, taker_fee_bps=120.0, bankroll=bankroll)
    return sa.run(binary_paths, seed=42)


def _run_time_arb(binary_paths, capital_per_market=2000):
    long_dated = [p for p in binary_paths if len(p) >= 200]
    if not long_dated:
        return StrategyResult(name="time_arb", trades=[], equity_curve=np.array([0.0]),
                              returns=np.array([]), pnl_per_trade=np.array([]),
                              capital_deployed=0, capital_lockup_period_steps=0, notes={})
    ta = TimeArb(fair_prob_floor=0.80, risk_free=0.04, capital_per_market=capital_per_market)
    return ta.run(long_dated, seed=42)


def _run_cross_platform(xplat_paths, capital_per_trade=1000, min_spread=0.03):
    cp = CrossPlatformArb(min_spread=min_spread, capital_per_trade=capital_per_trade,
                          kalshi_fee_bps=120.0)
    return cp.run(xplat_paths, seed=42)


def _run_longshot(binary_paths):
    lb = LongshotBiasExploiter(sell_zone=(0.02, 0.10), buy_zone=(0.90, 0.98), taker_fee_bps=0.0)
    return lb.run(binary_paths)


def _run_cross_asset(binary_paths, min_edge=0.02):
    ca = CrossAssetArb(min_edge=min_edge, taker_fee_bps=120.0)
    return ca.run(binary_paths, seed=42)


def _run_vol_event(capital_per_event=1000):
    ve = VolatilityEventStrategy(capital_per_event=capital_per_event, panic_threshold=0.03)
    return ve.run(n_events=30, seed=42)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_risk_enhanced(n_markets: int = 50, capital_base: float = 100_000.0) -> dict:
    engine = BacktestEngine()
    start = time.time()

    # ---- Fetch data ----
    logger.info("=" * 60)
    logger.info("PHASE 1: Fetching data")
    logger.info("=" * 60)
    binary_paths = fetch_binary_market_paths(n_markets=n_markets)
    negrisk_seqs = fetch_negrisk_snapshots(min_outcomes=3, max_events=20)
    xplat_paths = fetch_cross_platform_proxy_paths(n_markets=min(20, n_markets))
    logger.info("Data: %d binary, %d negrisk, %d cross-platform",
                len(binary_paths), len(negrisk_seqs), len(xplat_paths))

    # Split data: 30% calibration, 70% test
    cal_split = 0.3
    n_cal_bin = max(5, int(len(binary_paths) * cal_split))
    n_cal_neg = max(3, int(len(negrisk_seqs) * cal_split))
    n_cal_xp = max(3, int(len(xplat_paths) * cal_split))

    cal_binary = binary_paths[:n_cal_bin]
    test_binary = binary_paths[n_cal_bin:]
    cal_negrisk = negrisk_seqs[:n_cal_neg]
    test_negrisk = negrisk_seqs[n_cal_neg:]
    cal_xplat = xplat_paths[:n_cal_xp]
    test_xplat = xplat_paths[n_cal_xp:]

    # ---- Phase 2: Calibration run (fixed sizing) ----
    logger.info("=" * 60)
    logger.info("PHASE 2: Calibration (fixed sizing on 30%% data)")
    logger.info("=" * 60)

    fixed_cap = 500.0
    cal_results = {
        "negrisk": _run_negrisk(cal_negrisk, fixed_cap),
        "single_binary": _run_single_binary(cal_binary, fixed_cap),
        "stat_arb": _run_stat_arb(cal_binary, bankroll=10_000),
        "time_arb": _run_time_arb(cal_binary, capital_per_market=2000),
        "cross_platform": _run_cross_platform(cal_xplat, capital_per_trade=1000),
        "longshot": _run_longshot(cal_binary),
        "cross_asset": _run_cross_asset(cal_binary),
        "vol_event": _run_vol_event(capital_per_event=1000),
    }

    profiles = {}
    for name, sr in cal_results.items():
        p = estimate_risk_profile(name, sr)
        profiles[name] = p
        logger.info("  %s: %d trades, WR %.1f%%, Kelly %.3f, Sharpe %.2f, PnL $%.2f",
                     name, p.n_trades, p.win_rate * 100, p.kelly_frac, p.sharpe, p.total_pnl)

    # ---- Phase 3: Risk-sized allocation ----
    logger.info("=" * 60)
    logger.info("PHASE 3: Risk-enhanced backtest (Kelly + vol scaling on 70%% data)")
    logger.info("=" * 60)

    alloc = allocate_capital(list(profiles.values()), capital_base)
    for name, cap in sorted(alloc.items()):
        logger.info("  Allocated $%.0f to %s (%.1f%%)", cap, name, cap / capital_base * 100)

    # Compute risk-sized capital_per_trade for each strategy
    def risk_cap(name: str) -> float:
        p = profiles[name]
        base = alloc.get(name, capital_base * 0.1)
        # Half-Kelly fraction of allocated capital
        hk = max(p.half_kelly_frac, 0.02)  # minimum 2% per trade
        # Volatility inverse scaling: lower vol → more capital
        vol_scale = 1.0 / max(p.vol, 0.001)
        vol_scale = min(vol_scale, 10.0)  # cap at 10x
        # Normalize vol_scale relative to median
        median_vol = np.median([pr.vol for pr in profiles.values() if pr.vol > 0] or [1.0])
        vol_factor = median_vol / max(p.vol, 0.001)
        vol_factor = max(0.2, min(3.0, vol_factor))
        sized = base * hk * vol_factor
        return max(100.0, min(sized, base * 0.5))

    # Run risk-enhanced strategies on test set
    risk_results = {}

    rc = risk_cap("negrisk")
    logger.info("  negrisk: risk-sized cap_per_trade=$%.0f", rc)
    sr = _run_negrisk(test_negrisk, capital_per_trade=rc)
    if sr.n_trades > 0:
        risk_results["negrisk"] = engine.evaluate(sr, capital_base=alloc.get("negrisk", capital_base))

    rc = risk_cap("single_binary")
    logger.info("  single_binary: risk-sized cap_per_trade=$%.0f", rc)
    sr = _run_single_binary(test_binary, capital_per_trade=rc)
    if sr.n_trades > 0:
        risk_results["single_binary"] = engine.evaluate(sr, capital_base=alloc.get("single_binary", capital_base))

    rc = risk_cap("stat_arb")
    logger.info("  stat_arb: risk-sized bankroll=$%.0f", rc * 20)
    sr = _run_stat_arb(test_binary, bankroll=rc * 20, min_edge=0.02)
    if sr.n_trades > 0:
        risk_results["stat_arb"] = engine.evaluate(sr, capital_base=alloc.get("stat_arb", capital_base))

    rc = risk_cap("time_arb")
    logger.info("  time_arb: risk-sized cap_per_market=$%.0f", rc * 4)
    sr = _run_time_arb(test_binary, capital_per_market=rc * 4)
    if sr.n_trades > 0:
        risk_results["time_arb"] = engine.evaluate(sr, capital_base=alloc.get("time_arb", capital_base))

    rc = risk_cap("cross_platform")
    logger.info("  cross_platform: risk-sized cap_per_trade=$%.0f", rc * 2)
    sr = _run_cross_platform(test_xplat, capital_per_trade=rc * 2, min_spread=0.03)
    if sr.n_trades > 0:
        risk_results["cross_platform"] = engine.evaluate(sr, capital_base=alloc.get("cross_platform", capital_base))

    sr = _run_longshot(test_binary)
    if sr.n_trades > 0:
        risk_results["longshot"] = engine.evaluate(sr, capital_base=alloc.get("longshot", capital_base))

    rc = risk_cap("cross_asset")
    sr = _run_cross_asset(test_binary, min_edge=0.015)
    if sr.n_trades > 0:
        risk_results["cross_asset"] = engine.evaluate(sr, capital_base=alloc.get("cross_asset", capital_base))

    rc = risk_cap("vol_event")
    sr = _run_vol_event(capital_per_event=rc * 2)
    if sr.n_trades > 0:
        risk_results["vol_event"] = engine.evaluate(sr, capital_base=alloc.get("vol_event", capital_base))

    # ---- Phase 4: Baseline comparison (fixed sizing on same test set) ----
    logger.info("=" * 60)
    logger.info("PHASE 4: Baseline comparison (fixed sizing on same 70%% data)")
    logger.info("=" * 60)

    baseline_results = {}
    for name, runner, args in [
        ("negrisk", _run_negrisk, (test_negrisk, 500.0)),
        ("single_binary", _run_single_binary, (test_binary, 500.0)),
        ("stat_arb", _run_stat_arb, (test_binary,)),
        ("time_arb", _run_time_arb, (test_binary,)),
        ("cross_platform", _run_cross_platform, (test_xplat,)),
        ("longshot", _run_longshot, (test_binary,)),
        ("cross_asset", _run_cross_asset, (test_binary,)),
        ("vol_event", _run_vol_event, ()),
    ]:
        sr = runner(*args)
        if sr.n_trades > 0:
            baseline_results[name] = engine.evaluate(sr, capital_base=capital_base / 8)

    elapsed = time.time() - start
    logger.info("All phases complete in %.1fs", elapsed)

    return {
        "profiles": profiles,
        "allocation": alloc,
        "risk_enhanced": risk_results,
        "baseline": baseline_results,
    }


# ---------------------------------------------------------------------------
# Live simulation with risk parameters
# ---------------------------------------------------------------------------


async def run_live_risk_enhanced(hours: float, capital: float, profiles: dict) -> dict:
    from pdx_backtest.exchange_connector import (
        ExchangeConnector,
        LiveNegRiskRebalancer,
        LiveSingleBinaryRebalancer,
        LiveStatArb,
    )

    # Use Kelly-derived capital per trade for live strategies
    nr_cap = 500.0
    sb_cap = 500.0
    sa_cap = 500.0
    if "negrisk" in profiles and profiles["negrisk"].half_kelly_frac > 0:
        nr_cap = capital * profiles["negrisk"].half_kelly_frac * 0.1
        nr_cap = max(200, min(nr_cap, 5000))
    if "single_binary" in profiles and profiles["single_binary"].half_kelly_frac > 0:
        sb_cap = capital * profiles["single_binary"].half_kelly_frac * 0.1
        sb_cap = max(200, min(sb_cap, 5000))
    if "stat_arb" in profiles and profiles["stat_arb"].half_kelly_frac > 0:
        sa_cap = capital * profiles["stat_arb"].half_kelly_frac * 0.1
        sa_cap = max(200, min(sa_cap, 5000))

    logger.info("Live Kelly-sized: NegRisk=$%.0f, Binary=$%.0f, StatArb=$%.0f",
                nr_cap, sb_cap, sa_cap)

    strategies = [
        LiveNegRiskRebalancer(threshold=0.02, capital_per_trade=nr_cap, max_positions=20),
        LiveSingleBinaryRebalancer(threshold=0.005, capital_per_trade=sb_cap, max_positions=10),
        LiveStatArb(min_edge=0.03, capital_per_trade=sa_cap),
    ]

    connector = ExchangeConnector(
        strategies=strategies,
        initial_capital=capital,
        poll_interval_sec=1.0,
        max_markets=30,
    )

    report = await connector.run_for(hours=hours)
    return report


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_comparison(baseline: dict, risk_enhanced: dict) -> str:
    lines = []
    lines.append(f"{'Strategy':<20} {'Mode':<12} {'Trades':>7} {'PnL':>12} {'Return%':>10} "
                 f"{'Sharpe':>8} {'MDD%':>8} {'WR%':>7}")
    lines.append("-" * 90)

    all_names = sorted(set(list(baseline.keys()) + list(risk_enhanced.keys())))
    for name in all_names:
        if name in baseline:
            m = baseline[name].metrics
            lines.append(f"{name:<20} {'baseline':<12} {m.n_trades:>7} ${m.total_pnl:>10.2f} "
                         f"{m.total_return * 100:>9.2f}% {m.sharpe:>8.2f} "
                         f"{m.max_drawdown * 100:>7.2f}% {m.win_rate * 100:>6.1f}%")
        if name in risk_enhanced:
            m = risk_enhanced[name].metrics
            lines.append(f"{'':<20} {'risk-sized':<12} {m.n_trades:>7} ${m.total_pnl:>10.2f} "
                         f"{m.total_return * 100:>9.2f}% {m.sharpe:>8.2f} "
                         f"{m.max_drawdown * 100:>7.2f}% {m.win_rate * 100:>6.1f}%")
        lines.append("")

    # Totals
    base_pnl = sum(br.metrics.total_pnl for br in baseline.values())
    risk_pnl = sum(br.metrics.total_pnl for br in risk_enhanced.values())
    lines.append(f"{'TOTAL':<20} {'baseline':<12} {'':>7} ${base_pnl:>10.2f}")
    lines.append(f"{'TOTAL':<20} {'risk-sized':<12} {'':>7} ${risk_pnl:>10.2f}")
    if base_pnl != 0:
        improvement = (risk_pnl - base_pnl) / abs(base_pnl) * 100
        lines.append(f"\nRisk-enhanced PnL improvement: {improvement:+.1f}%")

    return "\n".join(lines)


def write_report(results: dict, live_report: dict | None, path: str) -> None:
    profiles = results["profiles"]
    alloc = results["allocation"]
    risk_enhanced = results["risk_enhanced"]
    baseline = results["baseline"]

    lines = [
        "# Risk-Enhanced Backtest Report",
        "",
        "## Calibration — Risk Profiles",
        "",
        "| Strategy | Win Rate | Avg Win | Avg Loss | Kelly | Half-Kelly | Vol | Sharpe |",
        "|----------|----------|---------|----------|-------|------------|-----|--------|",
    ]
    for name, p in sorted(profiles.items()):
        lines.append(f"| {name} | {p.win_rate * 100:.1f}% | ${p.avg_win:.2f} | "
                     f"${p.avg_loss:.2f} | {p.kelly_frac:.3f} | {p.half_kelly_frac:.3f} | "
                     f"{p.vol:.4f} | {p.sharpe:.2f} |")

    lines.extend([
        "",
        "## Capital Allocation",
        "",
        "| Strategy | Allocated | % of Total |",
        "|----------|-----------|------------|",
    ])
    total_cap = sum(alloc.values())
    for name, cap in sorted(alloc.items()):
        lines.append(f"| {name} | ${cap:,.0f} | {cap / total_cap * 100:.1f}% |")

    lines.extend([
        "",
        "## Baseline vs Risk-Enhanced Comparison",
        "",
        "| Strategy | Mode | Trades | PnL | Return | Sharpe | MDD | Win Rate |",
        "|----------|------|--------|-----|--------|--------|-----|----------|",
    ])
    all_names = sorted(set(list(baseline.keys()) + list(risk_enhanced.keys())))
    for name in all_names:
        if name in baseline:
            m = baseline[name].metrics
            lines.append(f"| {name} | baseline | {m.n_trades} | ${m.total_pnl:.2f} | "
                         f"{m.total_return * 100:.2f}% | {m.sharpe:.2f} | "
                         f"{m.max_drawdown * 100:.2f}% | {m.win_rate * 100:.1f}% |")
        if name in risk_enhanced:
            m = risk_enhanced[name].metrics
            lines.append(f"| {name} | **risk-sized** | {m.n_trades} | ${m.total_pnl:.2f} | "
                         f"{m.total_return * 100:.2f}% | {m.sharpe:.2f} | "
                         f"{m.max_drawdown * 100:.2f}% | {m.win_rate * 100:.1f}% |")

    base_pnl = sum(br.metrics.total_pnl for br in baseline.values())
    risk_pnl = sum(br.metrics.total_pnl for br in risk_enhanced.values())
    lines.extend([
        "",
        f"**Baseline Total PnL**: ${base_pnl:,.2f}",
        f"**Risk-Enhanced Total PnL**: ${risk_pnl:,.2f}",
    ])
    if base_pnl != 0:
        lines.append(f"**Improvement**: {(risk_pnl - base_pnl) / abs(base_pnl) * 100:+.1f}%")

    if live_report:
        lines.extend([
            "",
            "## Live Simulation (Risk-Enhanced)",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Duration | {live_report.get('duration_hours', 0):.2f} hours |",
            f"| Steps | {live_report.get('total_steps', 0)} |",
            f"| Trades | {live_report.get('total_trades', 0)} |",
            f"| PnL | ${live_report.get('total_pnl', 0):.2f} |",
            f"| Return | {live_report.get('return_pct', 0):.4f}% |",
            f"| Win Rate | {live_report.get('win_rate', 0) * 100:.1f}% |",
            f"| Max Drawdown | {live_report.get('max_drawdown', 0) * 100:.2f}% |",
            "",
            "### Per-Strategy",
            "",
            "| Strategy | Trades | PnL |",
            "|----------|--------|-----|",
        ])
        for s, pnl in live_report.get("strategy_pnl", {}).items():
            n = live_report.get("strategy_trades", {}).get(s, 0)
            lines.append(f"| {s} | {n} | ${pnl:.2f} |")

    lines.extend(["", "---", f"*Generated {time.strftime('%Y-%m-%d %H:%M')}*", ""])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines))
    logger.info("Report written to %s", path)


def main():
    parser = argparse.ArgumentParser(description="Risk-enhanced backtest + live sim")
    parser.add_argument("--n-markets", type=int, default=50)
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--hours", type=float, default=5.0,
                        help="Live simulation duration in hours")
    parser.add_argument("--report", type=str,
                        default="backtest/reports/risk_enhanced.md")
    parser.add_argument("--skip-live", action="store_true",
                        help="Skip the live simulation phase")
    args = parser.parse_args()

    results = run_risk_enhanced(n_markets=args.n_markets, capital_base=args.capital)

    # Print comparison table
    comparison = print_comparison(results["baseline"], results["risk_enhanced"])
    print("\n" + comparison + "\n")

    # Live simulation with risk parameters
    live_report = None
    if not args.skip_live:
        logger.info("=" * 60)
        logger.info("PHASE 5: Live simulation (%.1f hours, risk-enhanced)", args.hours)
        logger.info("=" * 60)
        live_report = asyncio.run(
            run_live_risk_enhanced(args.hours, args.capital, results["profiles"])
        )
        print("\nLive Simulation Results:")
        print(f"  Steps: {live_report['total_steps']}")
        print(f"  Trades: {live_report['total_trades']}")
        print(f"  PnL: ${live_report['total_pnl']:.2f}")
        print(f"  Return: {live_report['return_pct']:.4f}%")
        print(f"  Win Rate: {live_report['win_rate'] * 100:.1f}%")

    write_report(results, live_report, args.report)


if __name__ == "__main__":
    main()
