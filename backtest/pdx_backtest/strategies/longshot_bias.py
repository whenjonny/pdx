"""Strategy 7 — Favourite-longshot bias exploitation.

Snowberg & Wolfers (2010, JPE): using 5M+ horse-race observations,
long-shots are systematically over-bet (expected return ~55% at 50:1)
while favourites are under-bet (return ~85% at even money).

On prediction markets this translates to:
- Sell contracts priced $0.02-$0.10 (long-shots, over-priced)
- Buy contracts priced $0.90-$0.98 (near-certainties, under-priced)

Caveat: Reichenbach & Walther (2025) found that Polymarket does NOT
exhibit a general favourite-longshot bias, unlike traditional betting.
This strategy therefore evaluates whether the bias is present in our
synthetic data generator (which does bake it in via ``longshot_bias``).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from pdx_backtest.data import MarketPath
from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


class LongshotBiasExploiter(Strategy):
    name = "longshot_bias_exploiter"

    def __init__(
        self,
        sell_zone: tuple[float, float] = (0.02, 0.10),
        buy_zone: tuple[float, float] = (0.90, 0.98),
        taker_fee_bps: float = 120.0,
        capital_per_trade: float = 500.0,
    ) -> None:
        self.sell_lo, self.sell_hi = sell_zone
        self.buy_lo, self.buy_hi = buy_zone
        self.fee = taker_fee_bps / 10_000.0
        self.capital_per_trade = capital_per_trade

    def run(self, paths: list[MarketPath], seed: Optional[int] = None) -> StrategyResult:
        trades: list[Trade] = []
        pnl_list: list[float] = []
        roic_list: list[float] = []
        cum_pnl = [0.0]
        deployed = 0.0

        for idx, path in enumerate(paths):
            # Use the initial market price as the entry point.
            price = float(path.market_price[0])
            true_p = float(path.true_prob[0])
            outcome = int(path.outcome)

            # Zone 1: sell overpriced long-shots (price in $0.02-$0.10).
            if self.sell_lo <= price <= self.sell_hi:
                # Sell YES at ``price`` → collect ``price`` per unit.
                # If YES wins (outcome=1), pay $1 per unit → lose.
                # If NO wins (outcome=0), keep the premium → win.
                notional = self.capital_per_trade
                units = notional / max(1.0 - price, 1e-6)  # collateral = $1-price per short
                revenue = units * price * (1.0 - self.fee)
                if outcome == 0:
                    pnl = revenue  # keep premium
                else:
                    pnl = revenue - units * 1.0  # pay out $1 per unit
                trades.append(Trade(
                    step=idx, action="sell_longshot_yes",
                    notional=notional, pnl=pnl,
                    meta={"price": price, "true_p": true_p, "outcome": outcome,
                           "units": units, "zone": "sell_longshot"},
                ))
                pnl_list.append(pnl)
                roic_list.append(pnl / notional)
                cum_pnl.append(cum_pnl[-1] + pnl)
                deployed += notional

            # Zone 2: buy under-priced near-certainties (price in $0.90-$0.98).
            elif self.buy_lo <= price <= self.buy_hi:
                notional = self.capital_per_trade
                units = notional * (1.0 - self.fee) / max(price, 1e-6)
                if outcome == 1:
                    pnl = units * 1.0 - notional  # redeem at $1
                else:
                    pnl = -notional  # tokens worthless
                trades.append(Trade(
                    step=idx, action="buy_favourite_yes",
                    notional=notional, pnl=pnl,
                    meta={"price": price, "true_p": true_p, "outcome": outcome,
                           "units": units, "zone": "buy_favourite"},
                ))
                pnl_list.append(pnl)
                roic_list.append(pnl / notional)
                cum_pnl.append(cum_pnl[-1] + pnl)
                deployed += notional

            # Also check the NO side: if market_price is high (0.90-0.98),
            # the NO side is a long-shot (0.02-0.10).
            no_price = 1.0 - price
            if self.sell_lo <= no_price <= self.sell_hi:
                notional = self.capital_per_trade
                units = notional / max(1.0 - no_price, 1e-6)
                revenue = units * no_price * (1.0 - self.fee)
                if outcome == 1:  # YES wins → NO loses → we keep premium
                    pnl = revenue
                else:
                    pnl = revenue - units * 1.0
                trades.append(Trade(
                    step=idx, action="sell_longshot_no",
                    notional=notional, pnl=pnl,
                    meta={"no_price": no_price, "true_p": true_p, "outcome": outcome,
                           "units": units, "zone": "sell_longshot_no"},
                ))
                pnl_list.append(pnl)
                roic_list.append(pnl / notional)
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
                "sell_zone": f"${self.sell_lo:.2f}-${self.sell_hi:.2f}",
                "buy_zone": f"${self.buy_lo:.2f}-${self.buy_hi:.2f}",
                "fee_bps": self.fee * 10_000,
            },
        )
