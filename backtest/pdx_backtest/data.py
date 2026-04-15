"""Synthetic market-data generators.

We don't ship historical Polymarket/Kalshi tick data in the repo,
so backtests run against synthetic paths that are calibrated to
the stylised facts in the research note:

- Polymarket mean bid/ask spread ~1.2% in 2025 (down from 4.5% in 2023)
- YES+NO sum deviates from 1.00 by a few cents on binary markets
- Multi-outcome NegRisk markets routinely misprice by 5-10% aggregate
- Long-tail prices (0.05/0.95) are the most frequently mispriced

Each generator returns a deterministic ``numpy`` array seeded by the
``rng`` argument so tests can assert exact outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Binary market path (single YES token over time)
# ---------------------------------------------------------------------------


@dataclass
class MarketPath:
    """A single binary market sampled at discrete time steps.

    ``true_prob`` is the latent fair probability of YES.  ``market_price``
    is what the exchange quotes — it drifts around ``true_prob`` with
    noise, lag, and the long-shot / favourite bias baked in.
    """

    timestamps: np.ndarray
    true_prob: np.ndarray
    market_price: np.ndarray
    outcome: int  # 1 for YES, 0 for NO
    settlement_delay_steps: int = 0

    def __len__(self) -> int:
        return len(self.timestamps)


def generate_binary_path(
    n_steps: int = 500,
    initial_prob: float = 0.5,
    drift: float = 0.0,
    vol: float = 0.015,
    market_lag: int = 3,
    market_noise: float = 0.01,
    longshot_bias: float = 0.03,
    seed: int | None = 42,
) -> MarketPath:
    """Generate a synthetic binary-market trajectory.

    The **true** probability follows a bounded Brownian motion; the
    **market** price lags by ``market_lag`` steps and is biased towards
    0.5 by ``longshot_bias`` (i.e. long-shots over-priced, favourites
    under-priced — the Snowberg-Wolfers effect).
    """
    rng = np.random.default_rng(seed)
    shocks = rng.normal(drift, vol, size=n_steps)
    true_prob = np.clip(initial_prob + np.cumsum(shocks), 0.001, 0.999)

    # Market price lags the true prob by ``market_lag`` steps
    if market_lag > 0:
        lagged = np.concatenate([np.full(market_lag, initial_prob), true_prob[:-market_lag]])
    else:
        lagged = true_prob.copy()

    # Long-shot bias: pull prices towards 0.5
    biased = lagged + longshot_bias * (0.5 - lagged)
    observation_noise = rng.normal(0.0, market_noise, size=n_steps)
    market_price = np.clip(biased + observation_noise, 0.001, 0.999)

    # Resolve outcome by sampling with final true probability
    outcome = int(rng.random() < true_prob[-1])

    return MarketPath(
        timestamps=np.arange(n_steps),
        true_prob=true_prob,
        market_price=market_price,
        outcome=outcome,
    )


# ---------------------------------------------------------------------------
# Multi-outcome NegRisk market snapshot
# ---------------------------------------------------------------------------


@dataclass
class MultiOutcomeSnapshot:
    """One time-step of an N-outcome market (e.g. 5-way election).

    ``yes_prices`` sums to ``sum_yes`` which should approach 1.0 at
    fair value; ``no_prices`` should sum to ``N - 1``.  Deviations
    create the NegRisk arbitrage opportunity documented in the
    IMDEA paper ($29M realised in 2024-2025).
    """

    yes_prices: np.ndarray
    no_prices: np.ndarray
    winner_index: int

    @property
    def n(self) -> int:
        return len(self.yes_prices)

    @property
    def sum_yes(self) -> float:
        return float(self.yes_prices.sum())

    @property
    def sum_no(self) -> float:
        return float(self.no_prices.sum())


def generate_negrisk_scenario(
    n_outcomes: int = 5,
    n_snapshots: int = 200,
    yes_mispricing: float = 0.02,
    opportunity_rate: float = 0.15,
    seed: int | None = 7,
) -> list[MultiOutcomeSnapshot]:
    """Generate a sequence of NegRisk snapshots with realistic mispricings.

    Parameters
    ----------
    yes_mispricing
        Typical magnitude of aggregate YES-sum deviation from 1.0
        *when* an opportunity exists.  IMDEA: 2-4¢ on mature markets.
    opportunity_rate
        Fraction of snapshots that actually exhibit an arbitrageable
        deviation.  The rest are priced within noise of fair value —
        this matches the real Polymarket order book, where mispricings
        are punctuated rather than continuous.
    """
    rng = np.random.default_rng(seed)
    snapshots: list[MultiOutcomeSnapshot] = []

    alpha = rng.uniform(0.5, 3.0, size=n_outcomes)
    true_probs = rng.dirichlet(alpha)
    winner = int(rng.choice(n_outcomes, p=true_probs))

    for _ in range(n_snapshots):
        noisy = true_probs + rng.normal(0, 0.008, size=n_outcomes)
        noisy = np.clip(noisy, 0.005, 0.995)

        has_opportunity = rng.random() < opportunity_rate
        if has_opportunity:
            bias_sign = rng.choice([-1.0, 1.0])
            bias = bias_sign * abs(rng.normal(yes_mispricing, yes_mispricing / 2))
        else:
            # Fair-value noise only.
            bias = rng.normal(0, 0.003)

        scale = (1.0 + bias) / noisy.sum()
        yes_prices = np.clip(noisy * scale, 0.005, 0.995)

        no_prices = 1.0 - yes_prices + rng.normal(0, 0.005, size=n_outcomes)
        no_prices = np.clip(no_prices, 0.005, 0.995)

        snapshots.append(MultiOutcomeSnapshot(
            yes_prices=yes_prices,
            no_prices=no_prices,
            winner_index=winner,
        ))

    return snapshots


def generate_multi_outcome_paths(
    n_markets: int = 10,
    **kwargs,
) -> list[list[MultiOutcomeSnapshot]]:
    """Convenience: multiple independent NegRisk scenarios."""
    base_seed = kwargs.pop("seed", 1)
    return [
        generate_negrisk_scenario(seed=base_seed + i, **kwargs)
        for i in range(n_markets)
    ]


# ---------------------------------------------------------------------------
# Cross-platform spread generator (Polymarket vs Kalshi)
# ---------------------------------------------------------------------------


@dataclass
class CrossPlatformPath:
    """Synthetic two-venue price series for the same binary event."""

    timestamps: np.ndarray
    price_a: np.ndarray   # Polymarket-style (no maker fee)
    price_b: np.ndarray   # Kalshi-style (~1.2% taker fee)
    true_prob: np.ndarray
    outcome: int


def generate_cross_platform_path(
    n_steps: int = 500,
    initial_prob: float = 0.5,
    vol: float = 0.012,
    lead_lag: int = 4,
    mean_spread: float = 0.025,  # 2.5 cents — matches 2024-2025 typical spread
    seed: int | None = 11,
) -> CrossPlatformPath:
    """Generate correlated price series for Polymarket-like and Kalshi-like venues.

    Polymarket leads (more informed, higher liquidity) and Kalshi lags
    by ``lead_lag`` steps — matches Ng et al. 2026 finding.
    """
    rng = np.random.default_rng(seed)
    shocks = rng.normal(0, vol, size=n_steps)
    true_prob = np.clip(initial_prob + np.cumsum(shocks), 0.001, 0.999)

    price_a = true_prob + rng.normal(0, 0.003, size=n_steps)
    # Kalshi lags + persistent spread
    if lead_lag > 0:
        lagged = np.concatenate([np.full(lead_lag, initial_prob), true_prob[:-lead_lag]])
    else:
        lagged = true_prob.copy()
    price_b = lagged + rng.normal(mean_spread, 0.006, size=n_steps)
    price_a = np.clip(price_a, 0.001, 0.999)
    price_b = np.clip(price_b, 0.001, 0.999)

    outcome = int(rng.random() < true_prob[-1])
    return CrossPlatformPath(
        timestamps=np.arange(n_steps),
        price_a=price_a,
        price_b=price_b,
        true_prob=true_prob,
        outcome=outcome,
    )
