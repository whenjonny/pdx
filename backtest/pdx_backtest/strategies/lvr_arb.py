"""Strategy 8 — Loss-vs-Rebalancing (LVR) informed trading against AMM.

Milionis et al. (2022) formalised LVR: when an AMM's price is stale
relative to new information, informed traders extract value by trading
against the pool at the outdated price.

The LVR trader profits from the *immediate price correction*, not
settlement.  Buy cheap YES → sell it back a few steps later once the
pool price catches up → pocket the difference minus fees and slippage.

This is the mirror image of the MM strategy: the MM loses LVR.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from pdx_backtest.amm import CPMM, FeeSchedule
from pdx_backtest.data import MarketPath
from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


class LVRArb(Strategy):
    name = "lvr_informed_arb"

    def __init__(
        self,
        pool_liquidity: float = 50_000.0,
        trade_size: float = 500.0,
        min_edge: float = 0.03,
        hold_steps: int = 3,
        fees: Optional[FeeSchedule] = None,
    ) -> None:
        self.pool_liquidity = pool_liquidity
        self.trade_size = trade_size
        self.min_edge = min_edge
        self.hold_steps = hold_steps
        self.fees = fees or FeeSchedule()

    def run(self, path: MarketPath, seed: Optional[int] = 42) -> StrategyResult:
        pool = CPMM(self.pool_liquidity, self.fees)
        trades: list[Trade] = []
        pnl_list: list[float] = []
        roic_list: list[float] = []
        cum_pnl = [0.0]

        # Pending positions: (exit_step, is_yes, tokens, cost).
        pending: list[tuple[int, bool, float, float]] = []

        for step, true_p in enumerate(path.true_prob):
            # Close any matured positions first.
            still_pending = []
            for (exit_step, is_yes, tokens, cost) in pending:
                if step >= exit_step:
                    try:
                        usdc_out = pool.sell(tokens, is_yes=is_yes)
                    except ValueError:
                        usdc_out = 0.0
                    pnl = usdc_out - cost
                    pnl_list.append(pnl)
                    roic_list.append(pnl / cost if cost > 0 else 0.0)
                    cum_pnl.append(cum_pnl[-1] + pnl)
                    trades.append(Trade(
                        step=step, action=f"close_{'yes' if is_yes else 'no'}_lvr",
                        notional=cost, pnl=pnl,
                        meta={"usdc_out": usdc_out, "tokens_sold": tokens},
                    ))
                else:
                    still_pending.append((exit_step, is_yes, tokens, cost))
            pending = still_pending

            amm_price = pool.price_yes
            edge = float(true_p) - amm_price

            if abs(edge) < self.min_edge:
                continue

            # Open new position.
            is_yes = edge > 0
            try:
                tokens = pool.buy(self.trade_size, is_yes=is_yes, has_evidence=False)
            except ValueError:
                continue
            pending.append((step + self.hold_steps, is_yes, tokens, self.trade_size))
            trades.append(Trade(
                step=step, action=f"open_{'yes' if is_yes else 'no'}_lvr",
                notional=self.trade_size, pnl=0.0,
                meta={"edge": edge, "amm_price": amm_price,
                       "true_p": float(true_p), "tokens": tokens},
            ))

        # Force-close anything still pending at the end.
        for (_, is_yes, tokens, cost) in pending:
            try:
                usdc_out = pool.sell(tokens, is_yes=is_yes)
            except ValueError:
                usdc_out = 0.0
            pnl = usdc_out - cost
            pnl_list.append(pnl)
            roic_list.append(pnl / cost if cost > 0 else 0.0)
            cum_pnl.append(cum_pnl[-1] + pnl)

        cash_spent = sum(abs(t.notional) for t in trades if "open" in t.action)
        equity = np.asarray(cum_pnl, dtype=float) / max(self.trade_size, 1e-9)
        return StrategyResult(
            name=self.name,
            trades=trades,
            equity_curve=equity,
            returns=np.asarray(roic_list, dtype=float),
            pnl_per_trade=np.asarray(pnl_list, dtype=float),
            capital_deployed=cash_spent,
            capital_lockup_period_steps=len(path),
            notes={
                "cash_spent": cash_spent,
                "total_pnl": float(sum(pnl_list)),
                "outcome": int(path.outcome),
                "pool_liquidity": self.pool_liquidity,
                "final_amm_price": pool.price_yes,
                "hold_steps": self.hold_steps,
            },
        )
