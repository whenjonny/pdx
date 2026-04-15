"""Strategy 3 — Statistical arbitrage via a superior probability model.

Adapts Ludescher (2024)'s half-Kelly sizing rule:

    f* = (p - p_m) / (1 - p_m)

where ``p`` is our model's probability and ``p_m`` is the market
price.  Positive ``f*`` means buy YES; negative means buy NO.

Anchors from the research note:

- FiveThirtyEight beats PredictIt net-of-fees on presidential markets.
- Long-shot / favourite bias is measurable on traditional exchanges
  (Snowberg-Wolfers 2010); less so on Polymarket (Reichenbach-Walther
  2025).
- Kalshi's ~1.2% taker fee is the relevant friction, along with
  bid-ask spread.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from pdx_backtest.data import MarketPath
from pdx_backtest.metrics import half_kelly
from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


class StatisticalArb(Strategy):
    name = "statistical_arbitrage"

    def __init__(
        self,
        taker_fee_bps: float = 120.0,     # Kalshi-like
        min_edge: float = 0.02,           # only trade when |p − p_m| > 2¢
        max_position_fraction: float = 0.25,  # half-Kelly × 0.5 cap (quarter-Kelly)
        bankroll: float = 10_000.0,
    ) -> None:
        self.fee = taker_fee_bps / 10_000.0
        self.min_edge = min_edge
        self.cap = max_position_fraction
        self.bankroll = bankroll

    def run(self, paths: list[MarketPath], seed: Optional[int] = None) -> StrategyResult:
        trades: list[Trade] = []
        pnl_per_trade: list[float] = []
        equity = [self.bankroll]
        deployed_total = 0.0

        rng = np.random.default_rng(seed)

        for market_idx, path in enumerate(paths):
            # Our "model" probability = the *true* probability with
            # a modest Gaussian estimation error.  Calibrated so the
            # model beats the market-implied probability (which itself
            # has a lag + long-shot bias baked in).
            model_noise = rng.normal(0, 0.03, size=len(path))
            model_p = np.clip(path.true_prob + model_noise, 0.005, 0.995)

            # Trade once per market — at the step with the largest edge.
            edges = model_p - path.market_price
            i = int(np.argmax(np.abs(edges)))
            edge = edges[i]
            p = float(model_p[i])
            price = float(path.market_price[i])

            if abs(edge) < self.min_edge:
                continue

            f_kelly = half_kelly(p, price if edge > 0 else 1.0 - price) * 0.5  # quarter-kelly
            f = np.clip(f_kelly, -self.cap, self.cap)
            if abs(f) < 1e-4:
                continue

            notional = abs(f) * equity[-1]
            deployed_total += notional
            side_yes = edge > 0  # buy YES if undervalued, NO if overvalued

            entry_price = price if side_yes else (1.0 - price)
            # Realise PnL at settlement: winning tokens pay 1, else 0.
            # Tokens received = notional * (1 - fee) / entry_price
            tokens = notional * (1.0 - self.fee) / max(entry_price, 1e-6)
            payoff = tokens if (side_yes and path.outcome == 1) or (not side_yes and path.outcome == 0) else 0.0
            pnl = payoff - notional

            trades.append(Trade(
                step=market_idx,
                action="stat_arb_yes" if side_yes else "stat_arb_no",
                notional=notional,
                pnl=pnl,
                meta={
                    "edge": edge,
                    "model_p": p,
                    "market_price": price,
                    "entry_price": entry_price,
                    "outcome": int(path.outcome),
                    "fraction": f,
                },
            ))
            pnl_per_trade.append(pnl)
            equity.append(equity[-1] + pnl)

        # Per-trade ROIC returns for Sharpe/Sortino.
        roic = (
            np.asarray(pnl_per_trade, dtype=float)
            / np.asarray([t.notional for t in trades], dtype=float)
            if trades else np.array([], dtype=float)
        )
        equity_curve = (
            np.cumsum([0.0] + pnl_per_trade) / self.bankroll
            if trades else np.array([0.0])
        )
        return StrategyResult(
            name=self.name,
            trades=trades,
            equity_curve=np.asarray(equity_curve, dtype=float),
            returns=roic,
            pnl_per_trade=np.asarray(pnl_per_trade, dtype=float),
            capital_deployed=deployed_total,
            capital_lockup_period_steps=sum(len(p) for p in paths),
            notes={
                "n_markets": len(paths),
                "fee_bps": self.fee * 10_000,
                "min_edge": self.min_edge,
                "bankroll": self.bankroll,
                "total_pnl": float(sum(pnl_per_trade)),
            },
        )
