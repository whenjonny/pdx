"""Backtest the cross-venue stat arb strategy on synthetic data.

Simulates two venues with correlated but offset prices (Polymarket leads,
predictX lags by a few ticks + random spread). Implements proper risk-free
cross-venue arb: buy YES on one venue + buy NO on the other = guaranteed
$1 payout at settlement.

Usage:
    python stat_arb/run_backtest.py [--markets 30] [--steps 500] [--seeds 5]
"""

from __future__ import annotations

import argparse

import numpy as np

from pdx_arb.config import ArbConfig, PolymarketConfig, PredictXConfig
from pdx_arb.execution.executor import ArbExecutor
from pdx_arb.portfolio import PortfolioTracker
from pdx_arb.risk.risk_manager import ArbRiskManager
from pdx_arb.strategy.spread import compute_cross_venue_arb
from pdx_arb.types import (
    ArbSignal,
    MarketPair,
    PricePair,
    Side,
    Venue,
    VenuePrice,
)


def generate_cross_venue_paths(
    n_markets: int = 30,
    n_steps: int = 500,
    seed: int = 42,
    vol: float = 0.015,
    lag_steps: int = 3,
    venue_noise: float = 0.025,
) -> list[dict]:
    """Generate synthetic paired price paths for two venues.

    Polymarket is the "leader" — its price moves first.
    predictX follows with a configurable lag and random noise that
    creates temporary cross-venue mispricings.

    The noise is calibrated so that poly_YES + pdx_NO sometimes < 1.0
    (or vice versa), creating genuine arb opportunities.
    """
    rng = np.random.default_rng(seed)
    markets = []

    for i in range(n_markets):
        true_prob = np.clip(
            0.5 + np.cumsum(rng.normal(0, vol, n_steps)),
            0.02, 0.98,
        )
        noise_poly = rng.normal(0, vol * 0.3, n_steps)
        poly_yes = np.clip(true_prob + noise_poly, 0.01, 0.99)

        pdx_yes = np.zeros(n_steps)
        noise_pdx = rng.normal(0, venue_noise, n_steps)
        for t in range(n_steps):
            lagged_t = max(0, t - lag_steps)
            pdx_yes[t] = np.clip(poly_yes[lagged_t] + noise_pdx[t], 0.01, 0.99)

        outcome = int(true_prob[-1] > 0.5)

        markets.append({
            "market_id": i,
            "question": f"Synthetic market {i:03d}",
            "poly_yes": poly_yes,
            "pdx_yes": pdx_yes,
            "true_prob": true_prob,
            "outcome": outcome,
        })

    return markets


def run_single_backtest(
    n_markets: int = 30,
    n_steps: int = 500,
    seed: int = 42,
    config: ArbConfig | None = None,
    verbose: bool = False,
) -> dict:
    """Run one backtest with proper cross-venue arb (both legs)."""
    if config is None:
        config = ArbConfig(
            min_net_spread_bps=80.0,
            max_position_usd=2_000.0,
            max_total_exposure_usd=30_000.0,
            max_positions=50,
            kelly_fraction=0.5,
            cooldown_s=0.0,
            slippage_bps=15.0,
            settlement_risk_bps=0.0,
            polymarket=PolymarketConfig(fee_bps_taker=80.0),
            predictx=PredictXConfig(fee_bps_normal=30.0),
        )

    markets = generate_cross_venue_paths(n_markets, n_steps, seed)
    pairs = [
        MarketPair(
            pair_id=f"bt_{m['market_id']:03d}",
            question=m["question"],
            poly_condition_id=f"cond_{m['market_id']:03d}",
            poly_token_ids=[f"tok_yes_{m['market_id']}", f"tok_no_{m['market_id']}"],
            pdx_market_id=m["market_id"],
        )
        for m in markets
    ]

    initial_capital = 50_000.0
    risk_mgr = ArbRiskManager(config, initial_capital=initial_capital)
    portfolio = PortfolioTracker(initial_capital=initial_capital)
    executor = ArbExecutor(config, dry_run=True)

    alpha = 2.0 / 11
    spread_ema: dict[str, float] = {}
    obs_count: dict[str, int] = {}
    last_trade_step: dict[str, int] = {}
    cooldown_steps = 5

    total_arb_profit = 0.0
    n_arb_trades = 0
    n_winning = 0

    for step in range(n_steps):
        for idx, m in enumerate(markets):
            pair = pairs[idx]
            poly_yes = float(m["poly_yes"][step])
            pdx_yes = float(m["pdx_yes"][step])

            prices = PricePair(
                pair=pair,
                poly=VenuePrice(Venue.POLYMARKET, poly_yes, 1 - poly_yes, 10000),
                pdx=VenuePrice(Venue.PREDICTX, pdx_yes, 1 - pdx_yes, 5000),
            )

            spread = compute_cross_venue_arb(prices, config)
            if spread is None:
                continue

            pid = pair.pair_id
            obs_count[pid] = obs_count.get(pid, 0) + 1
            if pid not in spread_ema:
                spread_ema[pid] = spread.net_spread_bps
            else:
                spread_ema[pid] = alpha * spread.net_spread_bps + (1 - alpha) * spread_ema[pid]

            if obs_count[pid] < 3:
                continue
            if spread_ema[pid] < config.min_net_spread_bps:
                continue
            if step - last_trade_step.get(pid, -999) < cooldown_steps:
                continue
            if not spread.profitable:
                continue

            size = min(
                spread.guaranteed_pnl_per_unit * 10 * config.kelly_fraction * initial_capital,
                config.max_position_usd,
            )
            size *= risk_mgr.recommended_size_multiplier()
            if size < 10:
                continue

            signal = ArbSignal(
                pair=pair,
                prices=prices,
                direction=spread.direction,
                buy_venue=spread.buy_venue_yes,
                sell_venue=spread.buy_venue_no,
                buy_side=Side.BUY_YES,
                gross_spread_bps=spread.gross_spread_bps,
                net_spread_bps=spread.net_spread_bps,
                fee_cost_bps=spread.fee_cost_bps,
                suggested_size_usd=size,
                edge=spread.guaranteed_pnl_per_unit,
                confidence=min(spread_ema[pid] / max(config.min_net_spread_bps, 1.0), 3) / 3,
            )

            passed, reason = risk_mgr.check(signal)
            if not passed:
                continue

            cost_yes = spread.yes_price
            cost_no = spread.no_price
            total_cost = cost_yes + cost_no
            units = size / total_cost if total_cost > 0 else 0
            if units <= 0:
                continue

            fee_yes = (config.polymarket.fee_bps_taker if spread.buy_venue_yes == Venue.POLYMARKET
                       else config.predictx.fee_bps_normal) / 10_000 * cost_yes * units
            fee_no = (config.predictx.fee_bps_normal if spread.buy_venue_no == Venue.PREDICTX
                      else config.polymarket.fee_bps_taker) / 10_000 * cost_no * units
            slippage_cost = config.slippage_bps / 10_000 * total_cost * units * 2

            guaranteed_pnl = units * 1.0 - units * total_cost - fee_yes - fee_no - slippage_cost

            n_arb_trades += 1
            total_arb_profit += guaranteed_pnl
            if guaranteed_pnl > 0:
                n_winning += 1

            from pdx_arb.types import ArbTrade, LegOrder, OrderStatus
            trade = ArbTrade(
                trade_id=f"arb_{n_arb_trades:04d}",
                signal=signal,
                leg_buy=LegOrder(
                    venue=spread.buy_venue_yes,
                    market_ref=str(pair.pdx_market_id),
                    side=Side.BUY_YES,
                    size_usd=units * cost_yes,
                    limit_price=cost_yes,
                    status=OrderStatus.FILLED,
                    fill_price=cost_yes,
                    fill_size=units,
                    fee_paid=fee_yes,
                ),
                leg_sell=LegOrder(
                    venue=spread.buy_venue_no,
                    market_ref=str(pair.pdx_market_id),
                    side=Side.BUY_NO,
                    size_usd=units * cost_no,
                    limit_price=cost_no,
                    status=OrderStatus.FILLED,
                    fill_price=cost_no,
                    fill_size=units,
                    fee_paid=fee_no,
                ),
                status="filled",
                pnl_gross=units * (1.0 - total_cost),
                pnl_net=guaranteed_pnl,
            )

            risk_mgr.record_trade(trade)
            portfolio.record_open(trade)
            risk_mgr.record_settlement(trade)
            portfolio.record_close(trade)
            last_trade_step[pid] = step

    snap = portfolio.snapshot()

    if verbose:
        portfolio.print_summary()

    return {
        "seed": seed,
        "n_trades": n_arb_trades,
        "pnl": total_arb_profit,
        "win_rate": n_winning / n_arb_trades if n_arb_trades > 0 else 0,
        "sharpe": snap.sharpe,
        "max_dd": snap.max_drawdown_pct,
        "avg_pnl": total_arb_profit / n_arb_trades if n_arb_trades > 0 else 0,
    }


def run_seed_sweep(n_markets, n_steps, n_seeds, config=None):
    """Run backtest across multiple seeds for robustness."""
    print(f"\n{'=' * 78}")
    print(f"  Cross-Venue Risk-Free Arb Backtest: {n_markets} mkts × {n_steps} steps × {n_seeds} seeds")
    print(f"{'=' * 78}")
    print(f"\n  {'Seed':>6s} {'Trades':>8s} {'PnL':>12s} {'Win%':>8s} "
          f"{'Sharpe':>8s} {'MaxDD':>8s} {'Avg PnL':>10s}")
    print(f"  {'-' * 66}")

    results = []
    for i in range(n_seeds):
        seed = 42 + i * 17
        r = run_single_backtest(n_markets, n_steps, seed, config)
        results.append(r)
        print(f"  {seed:>6d} {r['n_trades']:>8d} ${r['pnl']:>+11,.2f} "
              f"{r['win_rate']:>7.1%} {r['sharpe']:>+8.2f} "
              f"{r['max_dd']:>7.2f}% ${r['avg_pnl']:>+9,.2f}")

    pnls = np.array([r["pnl"] for r in results])
    wrs = np.array([r["win_rate"] for r in results])
    trades = np.array([r["n_trades"] for r in results])

    print(f"\n  Summary ({n_seeds} seeds):")
    print(f"    Mean PnL:       ${pnls.mean():>+11,.2f}")
    print(f"    Std PnL:        ${pnls.std():>+11,.2f}")
    print(f"    Min/Max PnL:    ${pnls.min():>+11,.2f} / ${pnls.max():>+11,.2f}")
    print(f"    Mean Win Rate:  {wrs.mean():>10.1%}")
    print(f"    Mean Trades:    {trades.mean():>10.0f}")
    print(f"    Positive runs:  {(pnls > 0).sum():>10d}/{n_seeds}")

    if pnls.std() > 0:
        t_stat = pnls.mean() / (pnls.std() / np.sqrt(len(pnls)))
        print(f"    T-stat:         {t_stat:>+10.2f}")


def run_parameter_sweep(n_markets, n_steps, n_seeds):
    """Sweep over key parameters to find optimal configuration."""
    print(f"\n{'=' * 78}")
    print(f"  Parameter Sweep: venue noise × min spread threshold")
    print(f"{'=' * 78}")

    base_config = ArbConfig(
        min_net_spread_bps=80.0,
        max_position_usd=2_000.0,
        max_total_exposure_usd=30_000.0,
        max_positions=50,
        kelly_fraction=0.5,
        cooldown_s=0.0,
        slippage_bps=15.0,
        settlement_risk_bps=0.0,
        polymarket=PolymarketConfig(fee_bps_taker=80.0),
        predictx=PredictXConfig(fee_bps_normal=30.0),
    )

    print(f"\n  Min spread sweep (venue_noise=0.025):")
    print(f"  {'MinSpread':>10s} {'AvgTrades':>10s} {'AvgPnL':>12s} {'AvgWin%':>10s}")
    print(f"  {'-' * 46}")

    for min_sp in [40, 60, 80, 100, 120, 150, 200]:
        cfg = ArbConfig(**{**base_config.__dict__, "min_net_spread_bps": float(min_sp)})
        pnls, trades_arr, wrs = [], [], []
        for i in range(n_seeds):
            r = run_single_backtest(n_markets, n_steps, 42 + i * 17, cfg)
            pnls.append(r["pnl"])
            trades_arr.append(r["n_trades"])
            wrs.append(r["win_rate"])
        print(f"  {min_sp:>10d} {np.mean(trades_arr):>10.0f} "
              f"${np.mean(pnls):>+11,.2f} {np.mean(wrs):>9.1%}")


def main():
    parser = argparse.ArgumentParser(description="Cross-venue stat arb backtest")
    parser.add_argument("--markets", type=int, default=30, help="Markets per seed")
    parser.add_argument("--steps", type=int, default=500, help="Steps per market")
    parser.add_argument("--seeds", type=int, default=5, help="Number of seeds")
    parser.add_argument("--min-spread", type=float, default=80.0, help="Min net spread bps")
    parser.add_argument("--sweep", action="store_true", help="Run parameter sweep")
    parser.add_argument("--verbose", action="store_true", help="Verbose output per seed")
    args = parser.parse_args()

    config = ArbConfig(
        min_net_spread_bps=args.min_spread,
        max_position_usd=2_000.0,
        max_total_exposure_usd=30_000.0,
        max_positions=50,
        kelly_fraction=0.5,
        cooldown_s=0.0,
        slippage_bps=15.0,
        settlement_risk_bps=0.0,
        polymarket=PolymarketConfig(fee_bps_taker=80.0),
        predictx=PredictXConfig(fee_bps_normal=30.0),
    )

    run_seed_sweep(args.markets, args.steps, args.seeds, config)

    if args.sweep:
        run_parameter_sweep(args.markets, args.steps, args.seeds)


if __name__ == "__main__":
    main()
