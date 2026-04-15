"""Strategy 4 — Time arbitrage on long-dated near-certain contracts.

Thesis (from the research note):

    Long-dated high-probability outcomes are systematically
    *under-priced* because rational traders require a capital-lockup
    premium.  If you can buy a contract for $0.85 that is truly worth
    $0.95 and it settles in 6 months, your realised annual return is
    ~18% — which beats the risk-free rate but only marginally.

Implementation:

- Markets are binary and each takes ``settlement_days`` to resolve.
- We scan every market, find those trading below our fair-value
  estimate by at least ``min_edge`` cents.
- Enter a long YES position sized so that all capital is deployed
  across the universe.
- Compute **annualised** returns and compare to the risk-free rate.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from pdx_backtest.data import MarketPath
from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


class TimeArb(Strategy):
    name = "time_arbitrage"

    def __init__(
        self,
        settlement_days: int = 180,
        min_edge: float = 0.05,            # 5¢ minimum under-pricing
        fair_prob_floor: float = 0.80,     # only "near-certain" outcomes
        taker_fee_bps: float = 120.0,      # Kalshi-like
        risk_free: float = 0.04,
        capital_per_market: float = 1_000.0,
    ) -> None:
        self.settlement_days = settlement_days
        self.min_edge = min_edge
        self.fair_floor = fair_prob_floor
        self.fee = taker_fee_bps / 10_000.0
        self.risk_free = risk_free
        self.capital_per_market = capital_per_market

    def run(self, paths: list[MarketPath], seed: Optional[int] = None) -> StrategyResult:
        rng = np.random.default_rng(seed)
        trades: list[Trade] = []
        pnl_per_trade: list[float] = []
        equity = [self.capital_per_market * len(paths)]
        deployed = 0.0

        for idx, path in enumerate(paths):
            # Entry = first timestep; fair probability estimate has
            # small Gaussian error.
            fair_p = float(np.clip(path.true_prob[0] + rng.normal(0, 0.02), 0.005, 0.995))
            entry_price = float(path.market_price[0])

            if fair_p < self.fair_floor:
                continue
            if fair_p - entry_price < self.min_edge:
                continue

            notional = self.capital_per_market
            tokens = notional * (1.0 - self.fee) / max(entry_price, 1e-6)
            payoff = tokens if path.outcome == 1 else 0.0
            pnl = payoff - notional

            # Annualise return for reporting.
            holding_years = self.settlement_days / 365.25
            period_ret = pnl / notional
            annualised = (1.0 + period_ret) ** (1.0 / holding_years) - 1.0 if holding_years > 0 else 0.0
            excess_vs_rf = annualised - self.risk_free

            trades.append(Trade(
                step=idx,
                action="buy_yes_long_dated",
                notional=notional,
                pnl=pnl,
                meta={
                    "entry_price": entry_price,
                    "fair_p": fair_p,
                    "edge": fair_p - entry_price,
                    "holding_years": holding_years,
                    "annualised_return": annualised,
                    "excess_vs_rf": excess_vs_rf,
                    "outcome": int(path.outcome),
                },
            ))
            pnl_per_trade.append(pnl)
            equity.append(equity[-1] + pnl)
            deployed += notional

        # Per-trade ROIC (absolute, not annualised — metrics handle annualisation).
        roic = (
            np.asarray(pnl_per_trade, dtype=float)
            / np.asarray([t.notional for t in trades], dtype=float)
            if trades else np.array([], dtype=float)
        )
        capital_base = self.capital_per_market * len(paths)
        equity_curve = (
            np.cumsum([0.0] + pnl_per_trade) / capital_base
            if trades else np.array([0.0])
        )
        avg_annualised = (
            float(np.mean([t.meta["annualised_return"] for t in trades]))
            if trades else 0.0
        )
        return StrategyResult(
            name=self.name,
            trades=trades,
            equity_curve=np.asarray(equity_curve, dtype=float),
            returns=roic,
            pnl_per_trade=np.asarray(pnl_per_trade, dtype=float),
            capital_deployed=deployed,
            capital_lockup_period_steps=self.settlement_days * len(trades),
            notes={
                "settlement_days": self.settlement_days,
                "fee_bps": self.fee * 10_000,
                "risk_free": self.risk_free,
                "min_edge": self.min_edge,
                "fair_floor": self.fair_floor,
                "avg_annualised_return": avg_annualised,
                "total_pnl": float(sum(pnl_per_trade)),
                "capital_base": capital_base,
            },
        )
