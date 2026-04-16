"""Strategy 5 — Single-binary rebalancing (YES + NO ≠ $1.00).

In a PDX CPMM, priceYes + priceNo always equals 1.0 by construction.
But on CLOB-based venues (Polymarket), YES and NO are independently
priced orderbooks.  When the best-ask of YES plus the best-ask of NO
sums to less than $1.00, buying both locks in a guaranteed profit.
When both bids sum to more than $1.00, selling both does the same.

IMDEA 2024-25: $10.6M profit from this pattern alone ($5.9M long +
$4.7M short).  Time windows are typically < 200ms — pure bot territory.

We simulate a CLOB-style binary market where YES and NO prices are
independently noisy observations of the same underlying.
"""

from __future__ import annotations

import numpy as np

from pdx_backtest.data import MarketPath
from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


class SingleBinaryRebalancer(Strategy):
    name = "single_binary_rebalancer"

    def __init__(
        self,
        threshold: float = 0.005,
        taker_fee_bps: float = 0.0,
        capital_per_trade: float = 1_000.0,
        no_noise_std: float = 0.012,
    ) -> None:
        self.threshold = threshold
        self.fee = taker_fee_bps / 10_000.0
        self.capital_per_trade = capital_per_trade
        self.no_noise_std = no_noise_std

    def run(self, path: MarketPath, seed: int | None = 42) -> StrategyResult:
        rng = np.random.default_rng(seed)
        trades: list[Trade] = []
        pnl_list: list[float] = []
        roic_list: list[float] = []
        cum_pnl = [0.0]

        for step in range(len(path)):
            yes_price = float(path.market_price[step])
            # NO is independently priced with its own noise.
            no_price = float(np.clip(
                1.0 - path.true_prob[step] + rng.normal(0, self.no_noise_std),
                0.001, 0.999,
            ))
            pair_cost = (yes_price + no_price) * (1.0 + self.fee)

            if pair_cost < 1.0 - self.threshold:
                # Long arb: buy both, guaranteed payout = $1.
                units = self.capital_per_trade / pair_cost
                pnl = units * (1.0 - pair_cost)
                trades.append(Trade(
                    step=step, action="buy_pair",
                    notional=self.capital_per_trade, pnl=pnl,
                    meta={"yes_price": yes_price, "no_price": no_price,
                           "pair_cost": pair_cost, "units": units},
                ))
                pnl_list.append(pnl)
                roic_list.append(pnl / self.capital_per_trade)
                cum_pnl.append(cum_pnl[-1] + pnl)

            elif pair_cost > 1.0 + self.threshold + 2 * self.fee:
                # Short arb: sell both (if you hold inventory or can short).
                # Payoff = pair_cost - 1.0 per unit.
                units = self.capital_per_trade / 1.0  # need $1 collateral per pair
                pnl = units * (pair_cost / (1.0 + self.fee) - 1.0)
                trades.append(Trade(
                    step=step, action="sell_pair",
                    notional=self.capital_per_trade, pnl=pnl,
                    meta={"yes_price": yes_price, "no_price": no_price,
                           "pair_cost": pair_cost, "units": units},
                ))
                pnl_list.append(pnl)
                roic_list.append(pnl / self.capital_per_trade)
                cum_pnl.append(cum_pnl[-1] + pnl)

        equity = np.asarray(cum_pnl, dtype=float) / max(self.capital_per_trade, 1e-9)
        return StrategyResult(
            name=self.name,
            trades=trades,
            equity_curve=equity,
            returns=np.asarray(roic_list, dtype=float),
            pnl_per_trade=np.asarray(pnl_list, dtype=float),
            capital_deployed=self.capital_per_trade * len(trades) if trades else 0.0,
            capital_lockup_period_steps=len(trades),
            notes={
                "n_steps": len(path),
                "threshold": self.threshold,
                "total_pnl": float(sum(pnl_list)),
                "capital_per_trade": self.capital_per_trade,
            },
        )
