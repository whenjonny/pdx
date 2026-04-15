"""Strategy 1 — Multi-condition NegRisk rebalancing.

In an N-outcome market the YES prices should sum to 1.0 (and the NO
prices to N-1).  Whenever ``sum(yes) < 1 - threshold - fees`` we buy
one of every YES for a guaranteed payoff of 1.0.  Whenever
``sum(yes) > 1 + threshold + fees`` we short the basket by buying
every NO (equivalent to shorting all YES).

Research anchor: the IMDEA study (2024-2025) attributed **$29M** of
Polymarket arbitrage profit to exactly this pattern.  The effect is
strongest on the NO side (37M of the $17M profit in NO positions).
"""

from __future__ import annotations

import numpy as np

from pdx_backtest.data import MultiOutcomeSnapshot
from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


class NegRiskRebalancer(Strategy):
    name = "negrisk_rebalancer"

    def __init__(
        self,
        threshold: float = 0.01,       # minimum absolute edge before trading
        taker_fee_bps: float = 0.0,    # Polymarket CLOB = 0 maker / 0 taker on many legs
        capital_per_trade: float = 1_000.0,
    ) -> None:
        self.threshold = threshold
        self.fee = taker_fee_bps / 10_000.0
        self.capital_per_trade = capital_per_trade

    def run(self, snapshots: list[MultiOutcomeSnapshot]) -> StrategyResult:
        """Simulate a rebalancing strategy against a stream of snapshots.

        Each trade deploys exactly ``capital_per_trade`` USDC; returns
        are per-trade ROIC (= pnl / notional) — this is how arb desks
        usually quote single-event edge.  Equity curve is cumulative
        PnL expressed in units of ``capital_per_trade``.
        """
        trades: list[Trade] = []
        pnl_per_trade: list[float] = []
        per_trade_returns: list[float] = []
        cum_pnl = [0.0]
        deployed_capital = 0.0

        for step, snap in enumerate(snapshots):
            sum_yes = snap.sum_yes
            # Cost to buy-one-of-each (sum of YES prices) including fee
            cost_long = sum_yes * (1.0 + self.fee)
            # Cost to buy-one-of-each NO (sum of NO prices) including fee
            cost_short = snap.sum_no * (1.0 + self.fee)

            trade = None
            # --- Long side: buy every YES, guaranteed payoff = 1.0 ---
            if cost_long < 1.0 - self.threshold:
                units = self.capital_per_trade / cost_long
                pnl = units * (1.0 - cost_long)
                trade = Trade(
                    step=step,
                    action="buy_basket_yes",
                    notional=self.capital_per_trade,
                    pnl=pnl,
                    meta={"sum_yes": sum_yes, "units": units},
                )

            # --- Short side: buy every NO, guaranteed payoff = N-1 ---
            elif cost_short < (snap.n - 1) - self.threshold:
                units = self.capital_per_trade / cost_short
                pnl = units * ((snap.n - 1) - cost_short)
                trade = Trade(
                    step=step,
                    action="buy_basket_no",
                    notional=self.capital_per_trade,
                    pnl=pnl,
                    meta={"sum_no": snap.sum_no, "units": units},
                )

            if trade is not None:
                trades.append(trade)
                pnl_per_trade.append(trade.pnl)
                per_trade_returns.append(trade.pnl / trade.notional)
                cum_pnl.append(cum_pnl[-1] + trade.pnl)
                deployed_capital += trade.notional

        equity_curve = np.asarray(cum_pnl, dtype=float) / max(self.capital_per_trade, 1e-9)
        return StrategyResult(
            name=self.name,
            trades=trades,
            equity_curve=equity_curve,
            returns=np.asarray(per_trade_returns, dtype=float),
            pnl_per_trade=np.asarray(pnl_per_trade, dtype=float),
            capital_deployed=deployed_capital,
            capital_lockup_period_steps=len(trades),
            notes={
                "n_snapshots": len(snapshots),
                "threshold": self.threshold,
                "fee_bps": self.fee * 10_000,
                "total_pnl": float(sum(pnl_per_trade)),
                "capital_per_trade": self.capital_per_trade,
            },
        )
