"""Shared types for the cross-venue arbitrage system."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto


class Venue(Enum):
    POLYMARKET = auto()
    PREDICTX = auto()


class Side(Enum):
    BUY_YES = auto()
    BUY_NO = auto()
    SELL_YES = auto()
    SELL_NO = auto()


class OrderStatus(Enum):
    PENDING = auto()
    FILLED = auto()
    PARTIAL = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class VenuePrice:
    venue: Venue
    yes_price: float
    no_price: float
    liquidity: float
    timestamp: float = field(default_factory=time.time)

    @property
    def spread(self) -> float:
        return abs(1.0 - self.yes_price - self.no_price)


@dataclass
class MarketPair:
    """A matched market existing on both venues."""
    pair_id: str
    question: str
    poly_condition_id: str
    poly_token_ids: list[str]
    pdx_market_id: int
    poly_end_date: str = ""
    pdx_deadline: int = 0
    active: bool = True

    def __hash__(self) -> int:
        return hash(self.pair_id)


@dataclass
class PricePair:
    """Simultaneous price snapshot from both venues."""
    pair: MarketPair
    poly: VenuePrice
    pdx: VenuePrice
    timestamp: float = field(default_factory=time.time)

    @property
    def yes_spread(self) -> float:
        return self.pdx.yes_price - self.poly.yes_price

    @property
    def no_spread(self) -> float:
        return self.pdx.no_price - self.poly.no_price


@dataclass
class ArbSignal:
    """A detected arbitrage opportunity."""
    pair: MarketPair
    prices: PricePair
    direction: str
    buy_venue: Venue
    sell_venue: Venue
    buy_side: Side
    gross_spread_bps: float
    net_spread_bps: float
    fee_cost_bps: float
    suggested_size_usd: float
    edge: float
    confidence: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class LegOrder:
    """One leg of an arbitrage trade."""
    venue: Venue
    market_ref: str
    side: Side
    size_usd: float
    limit_price: float
    status: OrderStatus = OrderStatus.PENDING
    fill_price: float = 0.0
    fill_size: float = 0.0
    fee_paid: float = 0.0
    tx_hash: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ArbTrade:
    """A complete arbitrage trade (two legs)."""
    trade_id: str
    signal: ArbSignal
    leg_buy: LegOrder
    leg_sell: LegOrder
    status: str = "open"
    pnl_gross: float = 0.0
    pnl_net: float = 0.0
    settled: bool = False


@dataclass
class HedgeAction:
    """Record of a hedge attempt after leg failure."""
    original_trade_id: str
    failed_venue: Venue
    filled_venue: Venue
    hedge_type: str  # "close_filled" or "retry_failed"
    success: bool
    pnl: float
    timestamp: float = field(default_factory=time.time)
