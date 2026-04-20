"""Spread calculator — computes net arbitrage spread after all costs.

The key insight: proper cross-venue arb is RISK-FREE when executed correctly.
Buy YES on venue A + Buy NO on venue B = guaranteed $1 payout regardless
of outcome. Profit = $1 - cost_of_YES_A - cost_of_NO_B - fees.

This only works when the cross-venue price sum < 1.0:
  - If poly_YES + pdx_NO < 1.0 → buy YES on Poly, buy NO on PDX
  - If pdx_YES + poly_NO < 1.0 → buy YES on PDX, buy NO on Poly

The guaranteed profit per dollar is: (1 - sum) / sum, minus fees.
"""

from __future__ import annotations

from dataclasses import dataclass

from pdx_arb.config import ArbConfig
from pdx_arb.types import PricePair, Venue


@dataclass
class SpreadResult:
    """Result of spread analysis for one price pair."""
    direction: str
    buy_venue_yes: Venue
    buy_venue_no: Venue
    gross_spread_bps: float
    fee_cost_bps: float
    slippage_bps: float
    net_spread_bps: float
    profitable: bool
    yes_price: float
    no_price: float
    cost_per_unit: float
    guaranteed_pnl_per_unit: float

    @property
    def buy_venue(self) -> Venue:
        return self.buy_venue_yes

    @property
    def sell_venue(self) -> Venue:
        return self.buy_venue_no

    @property
    def buy_price(self) -> float:
        return self.yes_price


def compute_cross_venue_arb(prices: PricePair, config: ArbConfig) -> SpreadResult | None:
    """Compute cross-venue risk-free arbitrage spread.

    Buy YES on the venue where it's cheaper, buy NO on the other.
    If their sum < 1.0, the difference is guaranteed profit at settlement.
    """
    poly_yes = prices.poly.yes_price
    poly_no = prices.poly.no_price
    pdx_yes = prices.pdx.yes_price
    pdx_no = prices.pdx.no_price

    if min(poly_yes, poly_no, pdx_yes, pdx_no) <= 0:
        return None

    cost_a = poly_yes + pdx_no
    cost_b = pdx_yes + poly_no

    if cost_a <= cost_b:
        direction = "yes_poly_no_pdx"
        buy_venue_yes = Venue.POLYMARKET
        buy_venue_no = Venue.PREDICTX
        yes_price = poly_yes
        no_price = pdx_no
        cost = cost_a
    else:
        direction = "yes_pdx_no_poly"
        buy_venue_yes = Venue.PREDICTX
        buy_venue_no = Venue.POLYMARKET
        yes_price = pdx_yes
        no_price = poly_no
        cost = cost_b

    gross_profit = 1.0 - cost
    gross_bps = gross_profit * 10_000

    poly_fee_bps = config.polymarket.fee_bps_taker
    pdx_fee_bps = config.predictx.fee_bps_normal

    if buy_venue_yes == Venue.POLYMARKET:
        fee_bps = poly_fee_bps * yes_price + pdx_fee_bps * no_price
    else:
        fee_bps = pdx_fee_bps * yes_price + poly_fee_bps * no_price

    slippage_bps = config.slippage_bps * 2
    net_bps = gross_bps - fee_bps - slippage_bps

    return SpreadResult(
        direction=direction,
        buy_venue_yes=buy_venue_yes,
        buy_venue_no=buy_venue_no,
        gross_spread_bps=gross_bps,
        fee_cost_bps=fee_bps,
        slippage_bps=slippage_bps,
        net_spread_bps=net_bps,
        profitable=net_bps >= config.min_net_spread_bps,
        yes_price=yes_price,
        no_price=no_price,
        cost_per_unit=cost,
        guaranteed_pnl_per_unit=max(0, 1.0 - cost),
    )


def compute_spread(prices: PricePair, config: ArbConfig) -> SpreadResult | None:
    """Backward-compatible wrapper — delegates to compute_cross_venue_arb."""
    return compute_cross_venue_arb(prices, config)


def compute_directional_spread(prices: PricePair, config: ArbConfig) -> SpreadResult | None:
    """Directional spread: buy the cheaper YES, hold to settlement.

    NOT risk-free — depends on the outcome. Use compute_cross_venue_arb for
    the guaranteed-profit approach. This is kept for comparison purposes.
    """
    poly_yes = prices.poly.yes_price
    pdx_yes = prices.pdx.yes_price

    if poly_yes <= 0 or pdx_yes <= 0:
        return None

    poly_fee_bps = config.polymarket.fee_bps_taker
    pdx_fee_bps = config.predictx.fee_bps_normal

    if poly_yes < pdx_yes:
        direction = "directional_buy_poly"
        buy_venue = Venue.POLYMARKET
        other_venue = Venue.PREDICTX
        buy_price = poly_yes
        other_price = 1.0 - poly_yes
        gross_bps = (pdx_yes - poly_yes) * 10_000
        fee_bps = poly_fee_bps * buy_price
    else:
        direction = "directional_buy_pdx"
        buy_venue = Venue.PREDICTX
        other_venue = Venue.POLYMARKET
        buy_price = pdx_yes
        other_price = 1.0 - pdx_yes
        gross_bps = (poly_yes - pdx_yes) * 10_000
        fee_bps = pdx_fee_bps * buy_price

    net_bps = gross_bps - fee_bps - config.slippage_bps - config.settlement_risk_bps

    return SpreadResult(
        direction=direction,
        buy_venue_yes=buy_venue,
        buy_venue_no=other_venue,
        gross_spread_bps=gross_bps,
        fee_cost_bps=fee_bps,
        slippage_bps=config.slippage_bps,
        net_spread_bps=net_bps,
        profitable=net_bps >= config.min_net_spread_bps,
        yes_price=buy_price,
        no_price=other_price,
        cost_per_unit=buy_price,
        guaranteed_pnl_per_unit=0.0,
    )


def compute_no_spread(prices: PricePair, config: ArbConfig) -> SpreadResult | None:
    """Backward-compat: same as compute_cross_venue_arb (arb is symmetric)."""
    return compute_cross_venue_arb(prices, config)
