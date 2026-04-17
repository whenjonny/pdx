"""Strategy — Cross-venue arbitrage (Polymarket vs predict.fun).

Exploits price discrepancies between Polymarket (Polygon/USDC) and
predict.fun (Blast L2/USDB) on identical binary markets.  Unlike the
Polymarket-Kalshi arb which is blocked by jurisdictional walls, both
venues are globally accessible — making this strategy executable.

predict.fun exposes ``polymarketConditionIds`` enabling direct market
matching.  The main friction is cross-chain settlement risk: Polymarket
settles on Polygon, predict.fun on Blast L2.

Fee structure:
  - Polymarket: 0% maker fee
  - predict.fun: feeRateBps per market, typically 100-200 bps

We take ALL profitable opportunities (up to ``max_concurrent``) rather
than cherry-picking the single best entry per market.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from pdx_backtest.data import CrossPlatformPath
from pdx_backtest.strategies.base import Strategy, StrategyResult, Trade


def estimate_cross_venue_opportunity(
    poly_price: float,
    predict_price: float,
    poly_fee_bps: float = 0.0,
    predict_fee_bps: float = 150.0,
    settlement_risk_bps: float = 50.0,
) -> tuple[float, str]:
    """Return (net_spread, direction) for a Polymarket / predict.fun pair.

    Parameters
    ----------
    poly_price
        Polymarket YES price (0-1).
    predict_price
        predict.fun YES price (0-1).
    poly_fee_bps
        Polymarket maker fee in basis points.
    predict_fee_bps
        predict.fun fee in basis points.
    settlement_risk_bps
        Haircut for cross-chain bridge / settlement risk in basis points.

    Returns
    -------
    tuple[float, str]
        ``(net_spread, direction)`` where *direction* is ``"buy_poly"``
        (buy YES on Polymarket, sell YES on predict.fun) or
        ``"buy_predict"`` (buy YES on predict.fun, sell YES on
        Polymarket).  When the opportunity is not profitable the spread
        is returned as a negative number; the caller should filter on
        ``net_spread > 0``.
    """
    poly_fee = poly_fee_bps / 10_000.0
    predict_fee = predict_fee_bps / 10_000.0
    settlement_cost = settlement_risk_bps / 10_000.0

    # Direction 1: buy on Polymarket (cheaper), sell on predict.fun
    spread_buy_poly = predict_price - poly_price
    cost_buy_poly = (
        poly_price * poly_fee
        + predict_price * predict_fee
        + settlement_cost
    )
    net_buy_poly = spread_buy_poly - cost_buy_poly

    # Direction 2: buy on predict.fun (cheaper), sell on Polymarket
    spread_buy_predict = poly_price - predict_price
    cost_buy_predict = (
        predict_price * predict_fee
        + poly_price * poly_fee
        + settlement_cost
    )
    net_buy_predict = spread_buy_predict - cost_buy_predict

    if net_buy_poly >= net_buy_predict:
        return net_buy_poly, "buy_poly"
    return net_buy_predict, "buy_predict"


class CrossVenueArb(Strategy):
    """Cross-venue arb between Polymarket and predict.fun.

    Both platforms are globally accessible so — unlike Polymarket/Kalshi
    — this strategy is actually executable.  The main risk is
    cross-chain settlement (Polygon vs Blast L2).
    """

    name = "cross_venue_arb_poly_predict"

    def __init__(
        self,
        poly_fee_bps: float = 0.0,
        predict_fee_bps: float = 150.0,
        min_spread: float = 0.02,
        capital_per_trade: float = 1_000.0,
        max_concurrent: int = 10,
        settlement_risk_bps: float = 50.0,
    ) -> None:
        self.poly_fee = poly_fee_bps / 10_000.0
        self.predict_fee = predict_fee_bps / 10_000.0
        self.min_spread = min_spread
        self.capital_per_trade = capital_per_trade
        self.max_concurrent = max_concurrent
        self.settlement_cost = settlement_risk_bps / 10_000.0

        # Store raw bps for notes
        self._poly_fee_bps = poly_fee_bps
        self._predict_fee_bps = predict_fee_bps
        self._settlement_risk_bps = settlement_risk_bps

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _effective_spread(
        self,
        buy_price: float,
        sell_price: float,
        buy_fee: float,
        sell_fee: float,
    ) -> float:
        """Net spread after fees and settlement risk."""
        gross = sell_price - buy_price
        cost = buy_price * buy_fee + sell_price * sell_fee + self.settlement_cost
        return gross - cost

    # -----------------------------------------------------------------
    # run()
    # -----------------------------------------------------------------

    def run(
        self,
        paths: list[CrossPlatformPath],
        seed: Optional[int] = None,
    ) -> StrategyResult:
        """Execute cross-venue arb across a list of markets.

        Parameters
        ----------
        paths
            Each element represents one binary market.  ``price_a`` is
            the Polymarket price series, ``price_b`` is the predict.fun
            price series.
        seed
            Unused; present for interface compatibility.

        Returns
        -------
        StrategyResult
        """
        trades: list[Trade] = []
        pnl_list: list[float] = []
        roic_list: list[float] = []
        cum_pnl = [0.0]
        total_deployed = 0.0

        for market_idx, path in enumerate(paths):
            concurrent = 0

            for step in range(len(path.timestamps)):
                if concurrent >= self.max_concurrent:
                    break

                pa = float(path.price_a[step])  # Polymarket YES
                pb = float(path.price_b[step])  # predict.fun YES

                # --- Direction 1: buy Poly, sell predict.fun -----------
                eff_buy_poly = self._effective_spread(
                    buy_price=pa, sell_price=pb,
                    buy_fee=self.poly_fee, sell_fee=self.predict_fee,
                )

                # --- Direction 2: buy predict.fun, sell Poly -----------
                eff_buy_predict = self._effective_spread(
                    buy_price=pb, sell_price=pa,
                    buy_fee=self.predict_fee, sell_fee=self.poly_fee,
                )

                # Pick the better direction (if any)
                if eff_buy_poly >= eff_buy_predict and eff_buy_poly > self.min_spread:
                    effective = eff_buy_poly
                    direction = "buy_poly"
                    buy_price = pa
                    buy_fee = self.poly_fee
                elif eff_buy_predict > self.min_spread:
                    effective = eff_buy_predict
                    direction = "buy_predict"
                    buy_price = pb
                    buy_fee = self.predict_fee
                else:
                    continue

                notional = self.capital_per_trade
                units = notional / (buy_price * (1.0 + buy_fee)) if buy_price > 0 else 0.0
                pnl = units * effective

                trades.append(Trade(
                    step=market_idx,
                    action="cross_venue_arb",
                    notional=notional,
                    pnl=pnl,
                    meta={
                        "market_idx": market_idx,
                        "timestep": step,
                        "poly_price": pa,
                        "predict_price": pb,
                        "direction": direction,
                        "effective_spread": effective,
                        "units": units,
                        "outcome": int(path.outcome),
                        "buy_venue": "polymarket" if direction == "buy_poly" else "predict.fun",
                        "sell_venue": "predict.fun" if direction == "buy_poly" else "polymarket",
                        "settlement_chain_buy": "polygon" if direction == "buy_poly" else "blast_l2",
                        "settlement_chain_sell": "blast_l2" if direction == "buy_poly" else "polygon",
                    },
                ))
                pnl_list.append(pnl)
                roic_list.append(pnl / notional)
                cum_pnl.append(cum_pnl[-1] + pnl)
                total_deployed += notional
                concurrent += 1

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
                "poly_fee_bps": self._poly_fee_bps,
                "predict_fee_bps": self._predict_fee_bps,
                "settlement_risk_bps": self._settlement_risk_bps,
                "min_spread": self.min_spread,
                "capital_per_trade": self.capital_per_trade,
                "max_concurrent": self.max_concurrent,
                "buy_venue_a": "polymarket (Polygon / USDC)",
                "sell_venue_a": "predict.fun (Blast L2 / USDB)",
                "note": (
                    "Executable strategy — both venues are globally accessible. "
                    "Settlement risk haircut accounts for cross-chain bridge latency "
                    "between Polygon and Blast L2."
                ),
            },
        )
