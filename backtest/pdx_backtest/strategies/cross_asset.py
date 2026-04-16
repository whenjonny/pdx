"""Strategy 9 — Cross-asset statistical arbitrage.

Uses the Breeden-Litzenberger (1978) method to extract risk-neutral
probability distributions from option prices and compare them to
prediction-market binary event prices.

Stevens Institute (2024) demonstrated persistent mispricings between
Kalshi economic-indicator contracts and options-implied distributions
on SPX, CPI, and Fed Funds futures.

We simulate this by generating:
1. An "options-implied" probability (higher precision, lower noise
   — representing the deep-liquidity options market).
2. A "prediction market" price (noisier, lagging — representing
   Kalshi-style binary contracts).

When they diverge, we trade the prediction market toward the
options-implied fair value.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from pdx_backtest.data import MarketPath
from pdx_backtest.metrics import half_kelly
from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


class CrossAssetArb(Strategy):
    name = "cross_asset_arb"

    def __init__(
        self,
        options_noise: float = 0.01,
        min_edge: float = 0.03,
        taker_fee_bps: float = 120.0,
        capital_per_trade: float = 1_000.0,
        kelly_mult: float = 0.25,
    ) -> None:
        self.options_noise = options_noise
        self.min_edge = min_edge
        self.fee = taker_fee_bps / 10_000.0
        self.capital_per_trade = capital_per_trade
        self.kelly_mult = kelly_mult

    def run(self, paths: list[MarketPath], seed: Optional[int] = 42) -> StrategyResult:
        rng = np.random.default_rng(seed)
        trades: list[Trade] = []
        pnl_list: list[float] = []
        roic_list: list[float] = []
        cum_pnl = [0.0]
        deployed = 0.0

        for idx, path in enumerate(paths):
            # Options-implied probability = true_prob + small noise.
            options_prob = np.clip(
                path.true_prob + rng.normal(0, self.options_noise, size=len(path)),
                0.005, 0.995,
            )

            # Find the step with the largest options-vs-market divergence.
            edges = options_prob - path.market_price
            best_step = int(np.argmax(np.abs(edges)))
            edge = float(edges[best_step])
            opt_p = float(options_prob[best_step])
            mkt_p = float(path.market_price[best_step])

            if abs(edge) < self.min_edge:
                continue

            # Size with fractional Kelly.
            side_yes = edge > 0
            entry_price = mkt_p if side_yes else (1.0 - mkt_p)
            f = half_kelly(opt_p if side_yes else (1.0 - opt_p), entry_price) * self.kelly_mult
            f = np.clip(f, 0.01, 0.5)
            notional = f * self.capital_per_trade

            tokens = notional * (1.0 - self.fee) / max(entry_price, 1e-6)
            if (side_yes and path.outcome == 1) or (not side_yes and path.outcome == 0):
                payoff = tokens
            else:
                payoff = 0.0
            pnl = payoff - notional

            trades.append(Trade(
                step=idx, action="cross_asset_yes" if side_yes else "cross_asset_no",
                notional=notional, pnl=pnl,
                meta={
                    "options_prob": opt_p, "market_price": mkt_p,
                    "edge": edge, "fraction": float(f),
                    "outcome": int(path.outcome),
                },
            ))
            pnl_list.append(pnl)
            roic_list.append(pnl / notional if notional > 0 else 0.0)
            cum_pnl.append(cum_pnl[-1] + pnl)
            deployed += notional

        equity = np.asarray(cum_pnl, dtype=float) / max(self.capital_per_trade, 1e-9)
        return StrategyResult(
            name=self.name,
            trades=trades,
            equity_curve=equity,
            returns=np.asarray(roic_list, dtype=float),
            pnl_per_trade=np.asarray(pnl_list, dtype=float),
            capital_deployed=deployed,
            capital_lockup_period_steps=len(trades),
            notes={
                "n_markets": len(paths),
                "total_pnl": float(sum(pnl_list)),
                "fee_bps": self.fee * 10_000,
                "options_noise": self.options_noise,
                "min_edge": self.min_edge,
            },
        )
