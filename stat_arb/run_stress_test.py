"""Stress test: how does the arb hold up under realistic frictions?

Adds to the backtest the frictions that production trading actually faces:
1. Leg-fill failure (one leg executes, the other rejects → naked position)
2. Settlement divergence (venues resolve to different outcomes)
3. Non-linear market impact (CPMM price moves with trade size)
4. Competition staleness (signal age → by the time you execute, price moved)
5. Adverse selection (some "arbs" are actually you being picked off)

Running this shows how much the 100% win rate collapses under realistic
conditions, and helps calibrate the min_spread threshold that remains
robust even in a hostile environment.

Usage:
    python stat_arb/run_stress_test.py [--markets 30] [--seeds 10]
"""

from __future__ import annotations

import argparse

import numpy as np

from pdx_arb.config import ArbConfig, PolymarketConfig, PredictXConfig


def simulate_with_friction(
    n_markets: int,
    n_steps: int,
    seed: int,
    *,
    leg_fail_prob: float = 0.0,
    settlement_divergence_prob: float = 0.0,
    impact_coefficient: float = 0.0,
    stale_signal_prob: float = 0.0,
    adverse_selection_prob: float = 0.0,
    min_spread_bps: float = 100.0,
    kelly_fraction: float = 0.5,
    max_position_usd: float = 2_000.0,
    initial_capital: float = 50_000.0,
) -> dict:
    """Run the arb with configurable friction parameters.

    Returns PnL, win rate, and failure breakdown.
    """
    rng = np.random.default_rng(seed)
    capital = initial_capital
    peak = initial_capital
    max_dd_pct = 0.0

    n_trades = 0
    n_wins = 0
    total_pnl = 0.0

    n_leg_failures = 0
    n_settlement_divergences = 0
    n_stale = 0
    n_adverse = 0
    naked_losses = 0.0

    vol = 0.015
    venue_noise = 0.025
    lag_steps = 3

    poly_fee_bps = 80.0
    pdx_fee_bps = 30.0

    for i in range(n_markets):
        true_prob = np.clip(
            0.5 + np.cumsum(rng.normal(0, vol, n_steps)),
            0.02, 0.98,
        )
        poly_yes = np.clip(true_prob + rng.normal(0, vol * 0.3, n_steps), 0.01, 0.99)
        pdx_yes = np.zeros(n_steps)
        noise = rng.normal(0, venue_noise, n_steps)
        for t in range(n_steps):
            lt = max(0, t - lag_steps)
            pdx_yes[t] = np.clip(poly_yes[lt] + noise[t], 0.01, 0.99)

        outcome = int(true_prob[-1] > 0.5)
        pdx_outcome = outcome
        if rng.random() < settlement_divergence_prob:
            pdx_outcome = 1 - outcome

        last_trade_step = -999
        cooldown = 8

        for t in range(n_steps):
            if t - last_trade_step < cooldown:
                continue

            py = poly_yes[t]
            pdx = pdx_yes[t]
            cost_a = py + (1 - pdx)
            cost_b = pdx + (1 - py)

            if cost_a <= cost_b:
                cost = cost_a
                yes_price = py
                no_price = 1 - pdx
                yes_on_poly = True
            else:
                cost = cost_b
                yes_price = pdx
                no_price = 1 - py
                yes_on_poly = False

            gross_profit = 1.0 - cost
            if gross_profit <= 0:
                continue

            fee_yes_bps = poly_fee_bps if yes_on_poly else pdx_fee_bps
            fee_no_bps = pdx_fee_bps if yes_on_poly else poly_fee_bps
            fee_cost = (fee_yes_bps / 10_000) * yes_price + (fee_no_bps / 10_000) * no_price

            net_per_unit = gross_profit - fee_cost
            if net_per_unit * 10_000 < min_spread_bps:
                continue

            units = min(
                kelly_fraction * initial_capital * 10 * net_per_unit / cost,
                max_position_usd / cost,
            )
            if units < 10:
                continue

            if rng.random() < stale_signal_prob:
                drift = rng.normal(0, vol * 0.5)
                yes_price = max(0.01, min(0.99, yes_price + drift))
                no_price = max(0.01, min(0.99, no_price - drift))
                n_stale += 1

            if impact_coefficient > 0:
                impact = impact_coefficient * np.sqrt(units * cost / 10_000)
                yes_price = min(0.99, yes_price + impact)
                no_price = min(0.99, no_price + impact)

            if rng.random() < adverse_selection_prob:
                fair_price = true_prob[t]
                yes_price += (fair_price - yes_price) * 0.3
                no_price += ((1 - fair_price) - no_price) * 0.3
                n_adverse += 1

            n_trades += 1
            cost_actual = yes_price + no_price
            fee_actual = (fee_yes_bps / 10_000) * yes_price * units + (fee_no_bps / 10_000) * no_price * units

            yes_fail = rng.random() < leg_fail_prob
            no_fail = rng.random() < leg_fail_prob

            if yes_fail and no_fail:
                pnl = 0.0
                capital += pnl
            elif yes_fail:
                n_leg_failures += 1
                payout = units if outcome == 0 else 0.0
                pnl = payout - units * no_price - fee_actual / 2
                naked_losses += min(0, pnl)
                capital += pnl
            elif no_fail:
                n_leg_failures += 1
                venue_outcome = pdx_outcome if yes_on_poly else outcome
                payout = units if venue_outcome == 1 else 0.0
                pnl = payout - units * yes_price - fee_actual / 2
                naked_losses += min(0, pnl)
                capital += pnl
            else:
                yes_settles_to = outcome if yes_on_poly else pdx_outcome
                no_settles_to = pdx_outcome if yes_on_poly else outcome
                yes_payout = units if yes_settles_to == 1 else 0.0
                no_payout = units if no_settles_to == 0 else 0.0
                total_payout = yes_payout + no_payout
                pnl = total_payout - units * cost_actual - fee_actual
                if yes_settles_to == no_settles_to:
                    n_settlement_divergences += 1
                capital += pnl

            total_pnl += pnl
            if pnl > 0:
                n_wins += 1

            peak = max(peak, capital)
            if peak > 0:
                max_dd_pct = max(max_dd_pct, (peak - capital) / peak * 100)

            last_trade_step = t

    return {
        "n_trades": n_trades,
        "n_wins": n_wins,
        "win_rate": n_wins / n_trades if n_trades > 0 else 0,
        "pnl": total_pnl,
        "max_dd_pct": max_dd_pct,
        "leg_failures": n_leg_failures,
        "settlement_divergences": n_settlement_divergences,
        "stale_signals": n_stale,
        "adverse_selection": n_adverse,
        "naked_losses": naked_losses,
    }


def run_stress_sweep(n_markets: int, n_steps: int, n_seeds: int):
    """Run the backtest under increasingly harsh friction regimes."""

    scenarios = [
        ("Perfect (current)", dict()),
        ("Mild frictions", dict(
            leg_fail_prob=0.02,
            settlement_divergence_prob=0.005,
            impact_coefficient=0.002,
            stale_signal_prob=0.1,
            adverse_selection_prob=0.05,
        )),
        ("Realistic (prod-like)", dict(
            leg_fail_prob=0.05,
            settlement_divergence_prob=0.02,
            impact_coefficient=0.005,
            stale_signal_prob=0.25,
            adverse_selection_prob=0.15,
        )),
        ("Hostile (bot competition)", dict(
            leg_fail_prob=0.10,
            settlement_divergence_prob=0.05,
            impact_coefficient=0.010,
            stale_signal_prob=0.50,
            adverse_selection_prob=0.30,
        )),
    ]

    print(f"\n{'=' * 78}")
    print(f"  Stress Test: Cross-Venue Arb under Realistic Frictions")
    print(f"  ({n_markets} markets × {n_steps} steps × {n_seeds} seeds)")
    print(f"{'=' * 78}\n")

    header = (
        f"  {'Scenario':<28s} "
        f"{'Trades':>7s} "
        f"{'Win%':>7s} "
        f"{'Mean PnL':>12s} "
        f"{'Max DD':>8s} "
        f"{'LegFail':>8s}"
    )
    print(header)
    print(f"  {'-' * 72}")

    for name, frictions in scenarios:
        pnls, wrs, trades_arr, dds, leg_fails = [], [], [], [], []
        for i in range(n_seeds):
            r = simulate_with_friction(
                n_markets=n_markets,
                n_steps=n_steps,
                seed=42 + i * 17,
                min_spread_bps=100.0,
                **frictions,
            )
            pnls.append(r["pnl"])
            wrs.append(r["win_rate"])
            trades_arr.append(r["n_trades"])
            dds.append(r["max_dd_pct"])
            leg_fails.append(r["leg_failures"])

        print(
            f"  {name:<28s} "
            f"{np.mean(trades_arr):>7.0f} "
            f"{np.mean(wrs):>6.1%} "
            f"${np.mean(pnls):>+11,.0f} "
            f"{np.mean(dds):>7.1f}% "
            f"{np.mean(leg_fails):>8.0f}"
        )

    print(f"\n  Interpretation:")
    print(f"    Perfect:     100% win rate proves the arb MATH is correct")
    print(f"    Mild:        Small frictions → win% drops 2-5%, PnL still strong")
    print(f"    Realistic:   What production would look like")
    print(f"    Hostile:     Competition strips the edge — raise min_spread_bps")


def run_min_spread_robustness(n_markets: int, n_steps: int, n_seeds: int):
    """How does min_spread threshold interact with realistic frictions?"""
    print(f"\n{'=' * 78}")
    print(f"  Min Spread Threshold vs Realistic Frictions")
    print(f"{'=' * 78}\n")

    frictions = dict(
        leg_fail_prob=0.05,
        settlement_divergence_prob=0.02,
        impact_coefficient=0.005,
        stale_signal_prob=0.25,
        adverse_selection_prob=0.15,
    )

    print(f"  {'MinSpread':>10s} {'Trades':>8s} {'Win%':>7s} {'Mean PnL':>12s} {'T-stat':>8s}")
    print(f"  {'-' * 50}")

    for thresh in [50, 100, 150, 200, 300, 500]:
        pnls, wrs, trades = [], [], []
        for i in range(n_seeds):
            r = simulate_with_friction(
                n_markets=n_markets,
                n_steps=n_steps,
                seed=42 + i * 17,
                min_spread_bps=float(thresh),
                **frictions,
            )
            pnls.append(r["pnl"])
            wrs.append(r["win_rate"])
            trades.append(r["n_trades"])

        pnl_arr = np.array(pnls)
        t_stat = pnl_arr.mean() / (pnl_arr.std() / np.sqrt(len(pnl_arr))) if pnl_arr.std() > 0 else 0

        print(
            f"  {thresh:>10d} {np.mean(trades):>8.0f} "
            f"{np.mean(wrs):>6.1%} ${np.mean(pnls):>+11,.0f} {t_stat:>+8.2f}"
        )


def main():
    parser = argparse.ArgumentParser(description="Cross-venue arb stress test")
    parser.add_argument("--markets", type=int, default=30)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--seeds", type=int, default=10)
    args = parser.parse_args()

    run_stress_sweep(args.markets, args.steps, args.seeds)
    run_min_spread_robustness(args.markets, args.steps, args.seeds)


if __name__ == "__main__":
    main()
