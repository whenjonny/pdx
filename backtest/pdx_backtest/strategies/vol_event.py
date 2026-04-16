"""Strategy 10 — Volatility-event positioning.

Pre-event buildup: debates, CPI releases, FOMC meetings, election
nights all cause temporary spread widening on prediction markets.

Research brief: Polymarket-Kalshi spreads were widest during the
2024 debate nights and key poll releases; post-event, spreads
compressed as uncertainty resolved.

On a single-venue CPMM, the analog is:
- Before the event: volatility premium — market price drifts away
  from true value as noise traders panic-buy/sell, creating a
  mean-reversion opportunity.
- We enter a position toward fair value before the event resolves,
  betting on the spread compressing after the information shock.

We model events as discrete jumps in true probability that occur at
a known ``event_step``.  Pre-event, the market overreacts; post-event,
it snaps back.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


class VolatilityEventStrategy(Strategy):
    name = "volatility_event"

    def __init__(
        self,
        capital_per_event: float = 2_000.0,
        taker_fee_bps: float = 30.0,
        panic_threshold: float = 0.06,
    ) -> None:
        self.capital_per_event = capital_per_event
        self.fee = taker_fee_bps / 10_000.0
        self.panic_threshold = panic_threshold

    def run(
        self,
        n_events: int = 50,
        n_steps: int = 100,
        event_step: int = 60,
        seed: int | None = 42,
    ) -> StrategyResult:
        rng = np.random.default_rng(seed)
        trades: list[Trade] = []
        pnl_list: list[float] = []
        roic_list: list[float] = []
        cum_pnl = [0.0]
        deployed = 0.0

        for event_idx in range(n_events):
            # True prob evolution: stable → event jump → new level.
            base_prob = float(rng.uniform(0.3, 0.7))
            event_shock = float(rng.normal(0, 0.15))
            post_event_prob = np.clip(base_prob + event_shock, 0.05, 0.95)

            true_probs = np.full(n_steps, base_prob)
            true_probs[event_step:] = post_event_prob

            # Market price: tracks true_prob but with pre-event panic.
            market_prices = np.zeros(n_steps)
            for t in range(n_steps):
                if t < event_step - 10:
                    # Quiet period — market tracks base reasonably.
                    market_prices[t] = base_prob + rng.normal(0, 0.01)
                elif t < event_step:
                    # Panic zone: 10 steps before event.
                    # Market *overreacts* — moves away from base in a
                    # random direction (noise traders' speculative panic).
                    panic_dir = 1.0 if rng.random() > 0.5 else -1.0
                    panic_magnitude = abs(rng.normal(0.08, 0.04))
                    market_prices[t] = base_prob + panic_dir * panic_magnitude + rng.normal(0, 0.02)
                else:
                    # Post-event: snaps toward the true new level.
                    decay = 0.7 ** (t - event_step)
                    market_prices[t] = post_event_prob + (market_prices[event_step - 1] - post_event_prob) * decay
                    market_prices[t] += rng.normal(0, 0.005)
            market_prices = np.clip(market_prices, 0.01, 0.99)

            # Entry: at the peak of panic (step = event_step - 1).
            entry_step = event_step - 1
            entry_price = float(market_prices[entry_step])
            fair_price = float(true_probs[entry_step])
            panic_gap = entry_price - fair_price

            if abs(panic_gap) < self.panic_threshold:
                continue

            side_yes = panic_gap < 0  # market too low → buy YES
            entry = entry_price if side_yes else (1.0 - entry_price)
            notional = self.capital_per_event

            # Exit: a few steps after the event when market has corrected.
            exit_step = min(event_step + 5, n_steps - 1)
            exit_price = float(market_prices[exit_step])
            exit_val = exit_price if side_yes else (1.0 - exit_price)

            # P&L from mean-reversion (sell back at corrected price).
            tokens = notional * (1.0 - self.fee) / max(entry, 1e-6)
            revenue = tokens * exit_val * (1.0 - self.fee)
            pnl = revenue - notional

            outcome = int(rng.random() < post_event_prob)
            trades.append(Trade(
                step=event_idx, action="vol_event_yes" if side_yes else "vol_event_no",
                notional=notional, pnl=pnl,
                meta={
                    "entry_price": entry, "exit_price": exit_val,
                    "fair_price": fair_price, "panic_gap": panic_gap,
                    "base_prob": base_prob, "post_event_prob": post_event_prob,
                    "outcome": outcome,
                },
            ))
            pnl_list.append(pnl)
            roic_list.append(pnl / notional)
            cum_pnl.append(cum_pnl[-1] + pnl)
            deployed += notional

        equity = np.asarray(cum_pnl, dtype=float) / max(self.capital_per_event, 1e-9)
        return StrategyResult(
            name=self.name,
            trades=trades,
            equity_curve=equity,
            returns=np.asarray(roic_list, dtype=float),
            pnl_per_trade=np.asarray(pnl_list, dtype=float),
            capital_deployed=deployed,
            capital_lockup_period_steps=len(trades),
            notes={
                "n_events": n_events,
                "total_pnl": float(sum(pnl_list)),
                "fee_bps": self.fee * 10_000,
                "panic_threshold": self.panic_threshold,
                "capital_per_event": self.capital_per_event,
            },
        )
