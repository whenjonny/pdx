"""Strategy 2 — Bayesian market making on a PDX CPMM pool.

Accounting model (matches PDXMarket.sol cash flows):

- LP deposits ``initial_liquidity`` USDC to seed the pool.
- Each step, one or more taker trades arrive, each bringing USDC in
  and minting fresh outcome tokens to the taker.
- The pool retains the entire USDC inflow (minus fees which are
  tracked separately, they're added to the pool's cash too).
- At settlement, the pool must pay $1 per outstanding *external*
  token on the winning side.  Whatever is left is withdrawn by
  the LP.

  Final LP wealth = initial_liquidity + Σ buy_usdc − external_winning_tokens

  → MM PnL = Σ buy_usdc − external_winning_tokens + rebates

The ``informed_fraction`` parameter lets us study adverse selection:
higher values make the MM a net loser (standard LVR result).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from pdx_backtest.amm import CPMM, FeeSchedule
from pdx_backtest.data import MarketPath
from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


class BayesianMarketMaker(Strategy):
    name = "bayesian_market_maker"

    def __init__(
        self,
        initial_liquidity: float = 10_000.0,
        fees: Optional[FeeSchedule] = None,
        prior_yes: float = 0.5,
        trader_intensity: float = 5.0,
        trader_noise: float = 0.02,
        informed_fraction: float = 0.3,
        rebate_bps: float = 5.0,
    ) -> None:
        self.initial_liquidity = initial_liquidity
        self.fees = fees or FeeSchedule()
        self.prior_yes = prior_yes
        self.trader_intensity = trader_intensity
        self.trader_noise = trader_noise
        self.informed_fraction = informed_fraction
        self.rebate = rebate_bps / 10_000.0

    def _seed_pool(self) -> CPMM:
        pool = CPMM(self.initial_liquidity, self.fees)
        s = pool.reserve_yes + pool.reserve_no
        pool.reserve_no = self.prior_yes * s
        pool.reserve_yes = (1.0 - self.prior_yes) * s
        pool.k = pool.reserve_yes * pool.reserve_no
        return pool

    def run(self, path: MarketPath, seed: Optional[int] = 123) -> StrategyResult:
        rng = np.random.default_rng(seed)
        pool = self._seed_pool()

        external_yes = 0.0        # outstanding YES tokens held by users
        external_no = 0.0
        cash_inflow = 0.0         # user USDC → pool (inclusive of fee)
        fees_collected = 0.0
        rebates = 0.0

        trades: list[Trade] = []
        step_pnl: list[float] = []     # MTM change per step
        prev_mtm = 0.0  # MM's mark-to-market PnL at step 0 = 0

        def mtm_pnl(true_p: float) -> float:
            """Expected MM PnL at current pool state and true probability."""
            # At settlement, pool owes external tokens their $1 payout.
            # Expected outflow = external_yes * P(YES) + external_no * P(NO)
            expected_payout = external_yes * true_p + external_no * (1.0 - true_p)
            return cash_inflow + rebates - expected_payout

        for step, true_p in enumerate(path.true_prob):
            flow = max(0.0, rng.normal(self.trader_intensity, self.trader_intensity * 0.3))
            if flow < 1e-3:
                cur_mtm = mtm_pnl(float(true_p))
                step_pnl.append(cur_mtm - prev_mtm)
                prev_mtm = cur_mtm
                continue

            informed = rng.random() < self.informed_fraction
            if informed:
                side_yes = true_p > pool.price_yes
            else:
                side_yes = rng.random() < pool.price_yes + rng.normal(0, self.trader_noise)

            fee = flow * self.fees.rate(False)
            rebate = flow * self.rebate
            tokens_out = pool.buy(flow, is_yes=side_yes, has_evidence=False)

            # Accounting.
            cash_inflow += flow          # entire user USDC (incl fee) goes to pool
            fees_collected += fee
            rebates += rebate
            if side_yes:
                external_yes += tokens_out
            else:
                external_no += tokens_out

            cur_mtm = mtm_pnl(float(true_p))
            step_pnl.append(cur_mtm - prev_mtm)
            prev_mtm = cur_mtm

            trades.append(Trade(
                step=step,
                action="provide_liq_yes" if side_yes else "provide_liq_no",
                notional=flow,
                pnl=fee + rebate,   # locally, the "safe" MM revenue per trade
                meta={
                    "price_after": pool.price_yes,
                    "tokens_minted": tokens_out,
                    "side_yes": side_yes,
                    "informed": informed,
                },
            ))

        # Terminal settlement PnL (exact, not MTM).
        outcome = int(path.outcome)
        realised_payout = external_yes if outcome == 1 else external_no
        final_pnl = cash_inflow + rebates - realised_payout
        # Adjust last step to reflect realised settlement.
        if step_pnl:
            step_pnl[-1] = final_pnl - sum(step_pnl[:-1])

        # Per-step returns (ROIC on initial_liquidity).
        step_pnl_arr = np.asarray(step_pnl, dtype=float)
        returns = step_pnl_arr / self.initial_liquidity
        equity = np.cumsum(step_pnl_arr) / self.initial_liquidity

        return StrategyResult(
            name=self.name,
            trades=trades,
            equity_curve=equity,
            returns=returns,
            # Step-level PnL is the MM's "trade" PnL — includes every
            # MTM change including terminal settlement.  Per-user-trade
            # fees are still in ``trades`` for inspection.
            pnl_per_trade=step_pnl_arr,
            capital_deployed=self.initial_liquidity,
            capital_lockup_period_steps=len(path),
            notes={
                "fees_collected": fees_collected,
                "rebates": rebates,
                "cash_inflow": cash_inflow,
                "external_yes_at_settle": external_yes,
                "external_no_at_settle": external_no,
                "outcome": outcome,
                "realised_payout": realised_payout,
                "final_pnl": final_pnl,
                "final_price_yes": pool.price_yes,
                "initial_liquidity": self.initial_liquidity,
            },
        )
