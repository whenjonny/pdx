"""5-hour simulated live session.

Simulates a single 5-hour trading window where all 10 strategies
run concurrently against a shared synthetic market environment.

Time is discretised at 1-minute resolution (300 steps = 5 hours).
At each minute:
  - Markets tick (new prices arrive for binary, NegRisk, cross-platform).
  - Each strategy evaluates the new state and may execute trades.
  - P&L is marked-to-market.
  - Risk metrics are updated.

Output: a ``LiveSimResult`` with per-minute equity snapshots,
per-strategy P&L curves, trade logs, and a final summary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np

from pdx_backtest.amm import CPMM, FeeSchedule
from pdx_backtest.data import (
    MarketPath,
    MultiOutcomeSnapshot,
    CrossPlatformPath,
    generate_binary_path,
    generate_cross_platform_path,
    generate_negrisk_scenario,
)
from pdx_backtest.metrics import compute_metrics, PerformanceMetrics, half_kelly


# ---------------------------------------------------------------------------
# Market environment
# ---------------------------------------------------------------------------

SIM_MINUTES = 300  # 5 hours


@dataclass
class MarketEnvironment:
    """The shared universe of instruments available in the live sim."""

    binary_paths: list[MarketPath]
    negrisk_snapshots: list[list[MultiOutcomeSnapshot]]
    cross_paths: list[CrossPlatformPath]
    cpmm_pool: CPMM
    event_schedule: list[int]  # minute indices when "events" happen


def build_environment(
    n_binary: int = 20,
    n_negrisk: int = 10,
    n_cross: int = 10,
    pool_liq: float = 100_000.0,
    seed: int = 42,
) -> MarketEnvironment:
    rng = np.random.default_rng(seed)

    binary_paths = [
        generate_binary_path(
            n_steps=SIM_MINUTES,
            initial_prob=float(rng.uniform(0.15, 0.85)),
            vol=0.008,
            market_lag=2,
            market_noise=0.006,
            longshot_bias=0.03,
            seed=seed + i,
        )
        for i in range(n_binary)
    ]
    negrisk = [
        generate_negrisk_scenario(
            n_outcomes=5,
            n_snapshots=SIM_MINUTES,
            yes_mispricing=0.02,
            opportunity_rate=0.12,
            seed=seed * 3 + i,
        )
        for i in range(n_negrisk)
    ]
    cross_paths = [
        generate_cross_platform_path(
            n_steps=SIM_MINUTES,
            initial_prob=float(rng.uniform(0.3, 0.7)),
            seed=seed * 5 + i,
        )
        for i in range(n_cross)
    ]
    pool = CPMM(pool_liq, FeeSchedule())

    # Schedule 3-5 random "event" minutes where volatility spikes.
    n_events = int(rng.integers(3, 6))
    events = sorted(rng.choice(range(60, SIM_MINUTES - 30), size=n_events, replace=False).tolist())

    return MarketEnvironment(
        binary_paths=binary_paths,
        negrisk_snapshots=negrisk,
        cross_paths=cross_paths,
        cpmm_pool=pool,
        event_schedule=events,
    )


# ---------------------------------------------------------------------------
# Live simulation result
# ---------------------------------------------------------------------------


@dataclass
class StrategyLiveState:
    name: str
    equity_curve: list[float] = field(default_factory=lambda: [0.0])
    trades: list[dict] = field(default_factory=list)
    total_pnl: float = 0.0
    n_trades: int = 0
    capital_deployed: float = 0.0


@dataclass
class LiveSimResult:
    duration_minutes: int
    strategies: dict[str, StrategyLiveState]
    aggregate_equity: np.ndarray
    aggregate_pnl: float
    aggregate_trades: int
    per_minute_log: list[dict]
    metrics: dict[str, PerformanceMetrics]
    events: list[int]

    def summary_table(self) -> str:
        header = (
            f"{'Strategy':30s}  {'Trades':>7s}  {'PnL':>12s}  {'ROI':>8s}  "
            f"{'Sharpe':>7s}  {'MDD':>8s}  {'Win':>6s}"
        )
        lines = [header, "-" * len(header)]
        for name, state in sorted(self.strategies.items()):
            m = self.metrics.get(name)
            roi = state.total_pnl / max(state.capital_deployed, 1e-6)
            sharpe = m.sharpe if m else 0.0
            mdd = m.max_drawdown if m else 0.0
            win = m.win_rate if m else 0.0
            lines.append(
                f"{name:30s}  {state.n_trades:7d}  "
                f"${state.total_pnl:11,.2f}  "
                f"{roi:+7.2%}  {sharpe:+7.2f}  {mdd:+7.2%}  {win:5.1%}"
            )
        lines.append("-" * len(header))
        lines.append(
            f"{'AGGREGATE':30s}  {self.aggregate_trades:7d}  "
            f"${self.aggregate_pnl:11,.2f}"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------


def run_live_sim(seed: int = 42, verbose: bool = True) -> LiveSimResult:
    """Run the full 5-hour live simulation."""
    env = build_environment(seed=seed)

    # Initialise per-strategy state.
    strat_names = [
        "single_binary_rebal",
        "negrisk_rebal",
        "market_maker",
        "stat_arb",
        "time_arb",
        "cross_platform",
        "longshot_bias",
        "lvr_arb",
        "cross_asset",
        "vol_event",
    ]
    states: dict[str, StrategyLiveState] = {
        n: StrategyLiveState(name=n) for n in strat_names
    }
    per_minute_log: list[dict] = []
    rng = np.random.default_rng(seed * 7)

    CAPITAL_PER_TRADE = 1_000.0

    for minute in range(SIM_MINUTES):
        minute_trades: dict[str, int] = {}
        minute_pnl: dict[str, float] = {}

        is_event = minute in env.event_schedule

        # --- 1. Single-binary rebalancing (CLOB-style YES+NO mispricing) ---
        for path in env.binary_paths:
            if minute >= len(path):
                continue
            yes_p = float(path.market_price[minute])
            no_p = float(np.clip(
                1.0 - path.true_prob[minute] + rng.normal(0, 0.012),
                0.001, 0.999,
            ))
            pair_cost = yes_p + no_p
            if pair_cost < 0.99:
                pnl = (1.0 - pair_cost) * CAPITAL_PER_TRADE / pair_cost
                _record(states["single_binary_rebal"], minute, pnl, CAPITAL_PER_TRADE)

        # --- 2. NegRisk rebalancing ---
        for neg_market in env.negrisk_snapshots:
            if minute >= len(neg_market):
                continue
            snap = neg_market[minute]
            if snap.sum_yes < 0.99:
                units = CAPITAL_PER_TRADE / snap.sum_yes
                pnl = units * (1.0 - snap.sum_yes)
                _record(states["negrisk_rebal"], minute, pnl, CAPITAL_PER_TRADE)
            elif snap.sum_no < (snap.n - 1) - 0.01:
                units = CAPITAL_PER_TRADE / snap.sum_no
                pnl = units * ((snap.n - 1) - snap.sum_no)
                _record(states["negrisk_rebal"], minute, pnl, CAPITAL_PER_TRADE)

        # --- 3. Market making (fee income on the CPMM) ---
        # Taker flow arrives; pool earns fees.
        flow = max(0.0, rng.normal(50.0 if not is_event else 200.0, 20.0))
        if flow > 0.1:
            side = rng.random() > 0.5
            fee = flow * 0.003
            try:
                env.cpmm_pool.buy(flow, is_yes=side, has_evidence=False)
                _record(states["market_maker"], minute, fee, flow)
            except ValueError:
                pass

        # --- 4. Statistical arbitrage ---
        for path in env.binary_paths[:5]:
            if minute >= len(path):
                continue
            model_p = float(np.clip(path.true_prob[minute] + rng.normal(0, 0.02), 0.01, 0.99))
            mkt_p = float(path.market_price[minute])
            edge = model_p - mkt_p
            if abs(edge) > 0.04:
                f = half_kelly(model_p if edge > 0 else (1.0 - model_p),
                               mkt_p if edge > 0 else (1.0 - mkt_p)) * 0.25
                notional = abs(f) * CAPITAL_PER_TRADE
                if notional > 10:
                    # Estimate PnL from edge (not settlement — live sim is intraday).
                    est_pnl = notional * edge * 0.5  # conservative: capture half the edge
                    _record(states["stat_arb"], minute, est_pnl, notional)

        # --- 5. Time arbitrage (check weekly — only fire at minute 0) ---
        if minute == 0:
            for path in env.binary_paths:
                fair = float(path.true_prob[0])
                mkt = float(path.market_price[0])
                if fair > 0.80 and fair - mkt > 0.05:
                    tokens = CAPITAL_PER_TRADE * 0.988 / max(mkt, 1e-6)
                    pnl = tokens * (1.0 if path.outcome == 1 else 0.0) - CAPITAL_PER_TRADE
                    _record(states["time_arb"], minute, pnl, CAPITAL_PER_TRADE)

        # --- 6. Cross-platform arbitrage ---
        for cp in env.cross_paths:
            if minute >= len(cp.timestamps):
                continue
            pa, pb = float(cp.price_a[minute]), float(cp.price_b[minute])
            spread = abs(pa - pb) - 0.012 * max(pa, pb)  # net of Kalshi fee
            if spread > 0.025:
                pnl = spread * CAPITAL_PER_TRADE / max(min(pa, pb), 1e-6)
                _record(states["cross_platform"], minute, pnl, CAPITAL_PER_TRADE)

        # --- 7. Longshot bias ---
        for path in env.binary_paths:
            if minute >= len(path):
                continue
            p = float(path.market_price[minute])
            if 0.02 <= p <= 0.08:
                # Sell overpriced longshot.  Realised at settlement.
                # For live sim, assume ~90% of these win (true prob < 5%).
                wins = float(path.true_prob[minute]) < 0.10
                pnl = p * CAPITAL_PER_TRADE * 0.988 if wins else -(1.0 - p) * CAPITAL_PER_TRADE
                _record(states["longshot_bias"], minute, pnl, CAPITAL_PER_TRADE)
            elif 0.92 <= p <= 0.98:
                # NO side is a longshot — sell it.
                no_p = 1.0 - p
                wins = float(path.true_prob[minute]) > 0.90
                pnl = no_p * CAPITAL_PER_TRADE * 0.988 if wins else -(1.0 - no_p) * CAPITAL_PER_TRADE
                _record(states["longshot_bias"], minute, pnl, CAPITAL_PER_TRADE)

        # --- 8. LVR arb against the CPMM ---
        for path in env.binary_paths[:3]:
            if minute >= len(path):
                continue
            true_p = float(path.true_prob[minute])
            amm_p = env.cpmm_pool.price_yes
            edge = true_p - amm_p
            if abs(edge) > 0.04:
                # Trade toward true value.
                trade_size = 200.0
                try:
                    tokens = env.cpmm_pool.buy(trade_size, is_yes=(edge > 0), has_evidence=False)
                    # Immediate MTM gain ≈ edge * tokens.
                    mtm_gain = abs(edge) * tokens * 0.3
                    _record(states["lvr_arb"], minute, mtm_gain, trade_size)
                except ValueError:
                    pass

        # --- 9. Cross-asset arb ---
        for path in env.binary_paths[:5]:
            if minute >= len(path):
                continue
            opt_p = float(np.clip(path.true_prob[minute] + rng.normal(0, 0.008), 0.01, 0.99))
            mkt_p = float(path.market_price[minute])
            edge = opt_p - mkt_p
            if abs(edge) > 0.035:
                f = 0.15
                notional = f * CAPITAL_PER_TRADE
                est_pnl = notional * edge * 0.4
                _record(states["cross_asset"], minute, est_pnl, notional)

        # --- 10. Volatility event positioning ---
        if is_event:
            for path in env.binary_paths[:5]:
                if minute >= len(path) - 5:
                    continue
                pre = float(path.market_price[minute])
                post = float(path.market_price[min(minute + 5, len(path) - 1)])
                panic = abs(pre - float(path.true_prob[minute]))
                if panic > 0.05:
                    side_yes = pre < float(path.true_prob[minute])
                    entry = pre if side_yes else (1.0 - pre)
                    exit_val = post if side_yes else (1.0 - post)
                    tokens = CAPITAL_PER_TRADE * 0.997 / max(entry, 1e-6)
                    pnl = tokens * exit_val * 0.997 - CAPITAL_PER_TRADE
                    _record(states["vol_event"], minute, pnl, CAPITAL_PER_TRADE)

        # Snapshot for logging.
        per_minute_log.append({
            "minute": minute,
            "is_event": is_event,
            "aggregate_pnl": sum(s.total_pnl for s in states.values()),
            "aggregate_trades": sum(s.n_trades for s in states.values()),
        })

    # Compute per-strategy metrics.
    metrics: dict[str, PerformanceMetrics] = {}
    for name, state in states.items():
        rets = np.diff(state.equity_curve) if len(state.equity_curve) > 1 else np.array([])
        if len(rets) == 0:
            rets = np.array([0.0])
        pnl_arr = np.asarray([t.get("pnl", 0) for t in state.trades], dtype=float) if state.trades else np.array([0.0])
        metrics[name] = compute_metrics(
            returns=rets,
            pnl_per_trade=pnl_arr,
            periods_per_year=8760 * 12,  # minutes → annualised
            risk_free=0.04,
            capital_base=max(state.capital_deployed, CAPITAL_PER_TRADE),
        )

    # Build aggregate equity at minute resolution (not trade resolution).
    agg_equity = np.zeros(SIM_MINUTES + 1)
    for entry in per_minute_log:
        agg_equity[entry["minute"] + 1] = entry["aggregate_pnl"]

    result = LiveSimResult(
        duration_minutes=SIM_MINUTES,
        strategies=states,
        aggregate_equity=agg_equity,
        aggregate_pnl=sum(s.total_pnl for s in states.values()),
        aggregate_trades=sum(s.n_trades for s in states.values()),
        per_minute_log=per_minute_log,
        metrics=metrics,
        events=env.event_schedule,
    )

    if verbose:
        print(f"\n{'='*70}")
        print(f" 5-HOUR LIVE SIMULATION REPORT  ({SIM_MINUTES} minutes, seed={seed})")
        print(f"{'='*70}")
        print(f"  Events at minutes: {env.event_schedule}")
        print()
        print(result.summary_table())
        print()
        _print_timeline(per_minute_log, env.event_schedule)

    return result


def _record(state: StrategyLiveState, minute: int, pnl: float, notional: float) -> None:
    state.trades.append({"minute": minute, "pnl": pnl, "notional": notional})
    state.total_pnl += pnl
    state.n_trades += 1
    state.capital_deployed += notional
    state.equity_curve.append(state.equity_curve[-1] + pnl)


def _print_timeline(log: list[dict], events: list[int]) -> None:
    """Print a compact timeline at 30-min intervals."""
    print("  Timeline (30-min snapshots):")
    print(f"  {'Min':>5s}  {'Cum PnL':>12s}  {'Cum Trades':>10s}  {'Event':>6s}")
    for entry in log:
        m = entry["minute"]
        if m % 30 == 0 or m == len(log) - 1:
            ev = " *" if entry["is_event"] else ""
            print(
                f"  {m:5d}  ${entry['aggregate_pnl']:11,.2f}  "
                f"{entry['aggregate_trades']:10d}  {ev}"
            )
    print()
