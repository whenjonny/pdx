"""Strategy 6 — Cross-platform arbitrage (Polymarket vs Kalshi).

Exploits the persistent lead-lag relationship documented by Ng et al.
(2026): Polymarket leads price discovery (higher liquidity), Kalshi
lags by minutes.  The research brief notes typical spreads of 2-5¢
on liquid markets and 5-10+¢ on volatile events.

Structural constraint: no single trader can legally access both
platforms simultaneously (Polymarket bans US users, Kalshi is US-only).
This backtest evaluates the *theoretical* opportunity set — the
numbers represent the value the jurisdictional wall leaves on the
table.

We trade when the cross-venue spread exceeds a threshold net of
both venues' fee structures:
  - Polymarket: 0% maker
  - Kalshi: ~1.2% taker
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from pdx_backtest.data import CrossPlatformPath, generate_cross_platform_path
from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


class CrossPlatformArb(Strategy):
    name = "cross_platform_arbitrage"

    def __init__(
        self,
        poly_fee_bps: float = 0.0,
        kalshi_fee_bps: float = 120.0,
        min_spread: float = 0.025,
        capital_per_trade: float = 1_000.0,
        max_concurrent: int = 5,
    ) -> None:
        self.poly_fee = poly_fee_bps / 10_000.0
        self.kalshi_fee = kalshi_fee_bps / 10_000.0
        self.min_spread = min_spread
        self.capital_per_trade = capital_per_trade
        self.max_concurrent = max_concurrent

    def run(
        self,
        paths: list[CrossPlatformPath],
        seed: Optional[int] = None,
    ) -> StrategyResult:
        trades: list[Trade] = []
        pnl_list: list[float] = []
        roic_list: list[float] = []
        cum_pnl = [0.0]
        total_deployed = 0.0

        for market_idx, path in enumerate(paths):
            best_step = -1
            best_pnl = 0.0
            best_meta: dict = {}

            notional = self.capital_per_trade
            for step in range(len(path.timestamps)):
                pa = float(path.price_a[step])  # Polymarket YES
                pb = float(path.price_b[step])  # Kalshi YES

                spread = pb - pa
                effective_spread = spread - pa * self.poly_fee - pb * self.kalshi_fee

                if effective_spread > self.min_spread:
                    # Buy YES on Poly at pa, sell YES on Kalshi at pb.
                    # If outcome = YES: both settle to $1, net = spread × units.
                    # If outcome = NO: both settle to $0, net = -spread × units.
                    # But we hedge: buy YES on cheap venue, buy NO on expensive venue.
                    # Guaranteed profit = spread per unit regardless of outcome.
                    units = notional / (pa * (1.0 + self.poly_fee))
                    pnl = units * effective_spread
                    if pnl > best_pnl:
                        best_pnl = pnl
                        best_step = step
                        best_meta = {
                            "poly_price": pa, "kalshi_price": pb,
                            "spread": spread, "effective_spread": effective_spread,
                            "units": units, "outcome": int(path.outcome),
                        }

                # Reverse: buy cheap on Kalshi, sell on Poly.
                spread_rev = pa - pb
                eff_rev = spread_rev - pb * self.kalshi_fee - pa * self.poly_fee
                if eff_rev > self.min_spread:
                    units = notional / (pb * (1.0 + self.kalshi_fee)) if pb > 0 else 0
                    pnl = units * eff_rev
                    if pnl > best_pnl:
                        best_pnl = pnl
                        best_step = step
                        best_meta = {
                            "poly_price": pa, "kalshi_price": pb,
                            "spread": -spread_rev, "effective_spread": eff_rev,
                            "direction": "reverse",
                            "units": units, "outcome": int(path.outcome),
                        }

            if best_step >= 0 and best_pnl > 0:
                trades.append(Trade(
                    step=market_idx, action="cross_platform_arb",
                    notional=self.capital_per_trade, pnl=best_pnl,
                    meta=best_meta,
                ))
                pnl_list.append(best_pnl)
                roic_list.append(best_pnl / self.capital_per_trade)
                cum_pnl.append(cum_pnl[-1] + best_pnl)
                total_deployed += self.capital_per_trade

        equity = np.asarray(cum_pnl, dtype=float) / max(self.capital_per_trade, 1e-9)
        return StrategyResult(
            name=self.name,
            trades=trades,
            equity_curve=equity,
            returns=np.asarray(roic_list, dtype=float),
            pnl_per_trade=np.asarray(pnl_list, dtype=float),
            capital_deployed=total_deployed,
            capital_lockup_period_steps=len(trades),
            notes={
                "n_markets": len(paths),
                "total_pnl": float(sum(pnl_list)),
                "poly_fee_bps": self.poly_fee * 10_000,
                "kalshi_fee_bps": self.kalshi_fee * 10_000,
                "min_spread": self.min_spread,
                "capital_per_trade": self.capital_per_trade,
                "note": "Theoretical only — jurisdictional wall prevents simultaneous access",
            },
        )
