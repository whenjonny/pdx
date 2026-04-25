"""Exit rules. Each rule is a pure function (position, context) -> ExitDecision."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from trumptrade.monitor.position import OpenPosition, ExitReason


@dataclass
class ExitDecision:
    should_close: bool
    reason: Optional[ExitReason] = None
    detail: str = ""


@dataclass
class MarketContext:
    """What the monitor loop hands every rule on each tick."""
    current_yes_bid: Optional[float] = None
    current_yes_ask: Optional[float] = None
    current_no_bid: Optional[float] = None
    current_no_ask: Optional[float] = None
    last_trade: Optional[float] = None
    volume_24h: Optional[float] = None
    closes_at: Optional[datetime] = None
    # External signals from the trumptrade pipeline
    walkback_triggered: bool = False
    walkback_category: Optional[str] = None


class ExitRule(ABC):
    name: str = "rule"

    @abstractmethod
    def evaluate(self, position: OpenPosition, ctx: MarketContext) -> ExitDecision:
        ...


# ---- 1. arb convergence -----------------------------------------------------

class ArbConvergenceRule(ExitRule):
    """When the locked spread closes (yes_bid + no_bid >= threshold), peel
    both legs to realize profit early. Requires `target_arb_close_cost` set."""
    name = "arb_convergence"

    def __init__(self, close_at_total: float = 0.99):
        self.close_at_total = close_at_total

    def evaluate(self, p: OpenPosition, ctx: MarketContext) -> ExitDecision:
        if p.target_arb_close_cost is None:
            return ExitDecision(False)
        # Use the side we're holding to compute the bid we'd hit on close
        my_bid = ctx.current_yes_bid if p.side == "BUY_YES" else ctx.current_no_bid
        if my_bid is None:
            return ExitDecision(False)
        # If this leg's bid is high enough that pair-total >= threshold, close
        # `target_arb_close_cost` represents the original entry cost (e.g. 0.927)
        # We close when we can recover near 1.0 by selling at bid
        if my_bid >= (1.0 - p.target_arb_close_cost) + (self.close_at_total - 1.0) + p.entry_price:
            return ExitDecision(
                True, reason="arb_convergence",
                detail=f"my_bid={my_bid:.3f} >= profit-take threshold",
            )
        return ExitDecision(False)


# ---- 2. stop loss -----------------------------------------------------------

class StopLossRule(ExitRule):
    name = "stop_loss"

    def evaluate(self, p: OpenPosition, ctx: MarketContext) -> ExitDecision:
        if p.stop_loss_price is None:
            return ExitDecision(False)
        mark = ctx.current_yes_bid if p.side == "BUY_YES" else ctx.current_no_bid
        if mark is None:
            return ExitDecision(False)
        if mark <= p.stop_loss_price:
            return ExitDecision(
                True, reason="stop_loss",
                detail=f"mark={mark:.3f} <= stop={p.stop_loss_price:.3f}",
            )
        return ExitDecision(False)


# ---- 3. take profit ---------------------------------------------------------

class TakeProfitRule(ExitRule):
    name = "take_profit"

    def evaluate(self, p: OpenPosition, ctx: MarketContext) -> ExitDecision:
        if p.take_profit_price is None:
            return ExitDecision(False)
        mark = ctx.current_yes_bid if p.side == "BUY_YES" else ctx.current_no_bid
        if mark is None:
            return ExitDecision(False)
        if mark >= p.take_profit_price:
            return ExitDecision(
                True, reason="take_profit",
                detail=f"mark={mark:.3f} >= take_profit={p.take_profit_price:.3f}",
            )
        return ExitDecision(False)


# ---- 4. time decay ----------------------------------------------------------

class TimeDecayRule(ExitRule):
    """Close before the market resolves. Avoids the last-N-hour liquidity cliff."""
    name = "time_decay"

    def __init__(self, hours_before_close: int = 24):
        self.hours_before_close = hours_before_close

    def evaluate(self, p: OpenPosition, ctx: MarketContext) -> ExitDecision:
        # Prefer market's own close time (if streamed by the venue) to the
        # position's max_hold_until — so we don't ride a contract into resolution.
        cutoff_dt = ctx.closes_at or p.max_hold_until
        if cutoff_dt is None:
            return ExitDecision(False)
        now = datetime.now(timezone.utc)
        if cutoff_dt - now <= timedelta(hours=self.hours_before_close):
            return ExitDecision(
                True, reason="time_decay",
                detail=f"closes in {(cutoff_dt - now).total_seconds()/3600:.1f}h",
            )
        return ExitDecision(False)


# ---- 5. liquidity drop ------------------------------------------------------

class LiquidityDropRule(ExitRule):
    name = "liquidity_drop"

    def __init__(self, min_volume_24h: float = 1000.0):
        self.min_volume_24h = min_volume_24h

    def evaluate(self, p: OpenPosition, ctx: MarketContext) -> ExitDecision:
        if ctx.volume_24h is None:
            return ExitDecision(False)
        if ctx.volume_24h < self.min_volume_24h:
            return ExitDecision(
                True, reason="liquidity_drop",
                detail=f"24h volume {ctx.volume_24h:.0f} < {self.min_volume_24h:.0f}",
            )
        return ExitDecision(False)


# ---- 6. walkback ------------------------------------------------------------

class WalkbackRule(ExitRule):
    """Closes the position when the trumptrade pipeline detects a Trump
    reversal in the same category that originated this position."""
    name = "walkback"

    def evaluate(self, p: OpenPosition, ctx: MarketContext) -> ExitDecision:
        if not ctx.walkback_triggered:
            return ExitDecision(False)
        return ExitDecision(
            True, reason="walkback",
            detail=f"walk-back detected in category {ctx.walkback_category!r}",
        )


def build_default_rules() -> list[ExitRule]:
    return [
        WalkbackRule(),               # most urgent: news reversed
        ArbConvergenceRule(0.99),
        StopLossRule(),
        TakeProfitRule(),
        TimeDecayRule(24),
        LiquidityDropRule(1000.0),
    ]
