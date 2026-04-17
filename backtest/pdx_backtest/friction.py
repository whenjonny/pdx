"""Execution friction model for realistic backtesting.

Real prediction market trading faces several frictions that synthetic
backtests tend to ignore.  This module injects them consistently across
all strategies:

  1. **Slippage** — you pay bid/ask spread, not midpoint.
     Polymarket avg spread ~1.2% (2025).  predict.fun wider (~2%).
  2. **Market impact** — large orders move the price.
     Modelled as sqrt(order_size / liquidity) × impact_coefficient.
  3. **Execution failure** — arb windows close before fill.
     Modelled as a Bernoulli draw per trade (failure rate ~15-30%).
  4. **Partial fills** — only part of the order is filled.
     Modelled as a Beta distribution of fill rate.
  5. **Latency** — time to detect + execute. During this time the
     price can move adversely.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FrictionParams:
    """Configurable execution friction parameters."""

    half_spread_bps: float = 60.0
    impact_coeff: float = 0.1
    default_liquidity: float = 50_000.0
    execution_failure_rate: float = 0.15
    partial_fill_alpha: float = 5.0
    partial_fill_beta: float = 1.5
    latency_adverse_move_std: float = 0.003

    @classmethod
    def polymarket(cls) -> "FrictionParams":
        return cls(
            half_spread_bps=60.0,
            impact_coeff=0.08,
            default_liquidity=50_000.0,
            execution_failure_rate=0.15,
            partial_fill_alpha=5.0,
            partial_fill_beta=1.5,
            latency_adverse_move_std=0.003,
        )

    @classmethod
    def predict_fun(cls) -> "FrictionParams":
        return cls(
            half_spread_bps=100.0,
            impact_coeff=0.15,
            default_liquidity=20_000.0,
            execution_failure_rate=0.20,
            partial_fill_alpha=3.0,
            partial_fill_beta=2.0,
            latency_adverse_move_std=0.005,
        )

    @classmethod
    def none(cls) -> "FrictionParams":
        return cls(
            half_spread_bps=0.0,
            impact_coeff=0.0,
            default_liquidity=1e12,
            execution_failure_rate=0.0,
            partial_fill_alpha=100.0,
            partial_fill_beta=0.01,
            latency_adverse_move_std=0.0,
        )


def apply_slippage(mid_price: float, side: str, params: FrictionParams) -> float:
    """Return the execution price after bid-ask spread."""
    half_spread = params.half_spread_bps / 10_000.0
    if side == "buy":
        return mid_price * (1.0 + half_spread)
    else:
        return mid_price * (1.0 - half_spread)


def apply_market_impact(
    price: float,
    order_notional: float,
    side: str,
    params: FrictionParams,
) -> float:
    """Return the execution price after market impact."""
    impact_frac = params.impact_coeff * np.sqrt(
        order_notional / params.default_liquidity
    )
    if side == "buy":
        return price * (1.0 + impact_frac)
    else:
        return price * (1.0 - impact_frac)


def execution_succeeds(rng: np.random.Generator, params: FrictionParams) -> bool:
    """Return whether this trade attempt successfully fills."""
    return rng.random() > params.execution_failure_rate


def fill_fraction(rng: np.random.Generator, params: FrictionParams) -> float:
    """Return the fraction of the order that fills (0-1)."""
    return float(np.clip(
        rng.beta(params.partial_fill_alpha, params.partial_fill_beta),
        0.0, 1.0,
    ))


def latency_price_move(rng: np.random.Generator, params: FrictionParams) -> float:
    """Return an adverse price move due to execution latency."""
    return rng.normal(0, params.latency_adverse_move_std)


def realistic_execution_price(
    mid_price: float,
    order_notional: float,
    side: str,
    rng: np.random.Generator,
    params: FrictionParams,
) -> float:
    """Full execution price: slippage + impact + latency move."""
    price = apply_slippage(mid_price, side, params)
    price = apply_market_impact(price, order_notional, side, params)
    move = latency_price_move(rng, params)
    if side == "buy":
        price += abs(move)
    else:
        price -= abs(move)
    return max(price, 0.001)


def apply_friction_to_arb_pnl(
    gross_pnl: float,
    notional: float,
    rng: np.random.Generator,
    params: FrictionParams,
    n_legs: int = 2,
) -> tuple[float, bool, float]:
    """Apply execution friction to an arbitrage trade.

    Returns (adjusted_pnl, succeeded, fill_rate).
    """
    if not execution_succeeds(rng, params):
        return 0.0, False, 0.0

    fr = fill_fraction(rng, params)

    slippage_cost = n_legs * (params.half_spread_bps / 10_000.0) * notional * fr
    impact_cost = n_legs * params.impact_coeff * np.sqrt(
        notional * fr / params.default_liquidity
    ) * notional * fr
    latency_cost = abs(rng.normal(0, params.latency_adverse_move_std)) * notional * fr

    total_cost = slippage_cost + impact_cost + latency_cost
    adjusted_pnl = gross_pnl * fr - total_cost

    return float(adjusted_pnl), True, float(fr)
