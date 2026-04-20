"""Risk manager for cross-venue arbitrage.

Controls position sizing, exposure limits, drawdown protection, and
per-market concentration limits. Mirrors the production risk manager
from the event-driven backtest but adapted for cross-venue trading.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from pdx_arb.config import ArbConfig
from pdx_arb.types import ArbSignal, ArbTrade

logger = logging.getLogger(__name__)


class ArbRiskManager:
    """Pre-trade risk checks for cross-venue arbitrage."""

    def __init__(self, config: ArbConfig, initial_capital: float = 100_000.0) -> None:
        self.config = config
        self.initial_capital = initial_capital
        self.capital = initial_capital

        self._open_positions: dict[str, float] = {}
        self._daily_pnl = 0.0
        self._daily_reset_time = time.time()
        self._peak_capital = initial_capital
        self._total_pnl = 0.0
        self._rejected_count = 0
        self._passed_count = 0
        self._reject_reasons: dict[str, int] = defaultdict(int)

    def check(self, signal: ArbSignal) -> tuple[bool, str]:
        """Run all pre-trade checks. Returns (passed, reason)."""
        self._maybe_reset_daily()

        checks = [
            self._check_drawdown,
            self._check_daily_loss,
            self._check_max_positions,
            self._check_per_market_exposure,
            self._check_total_exposure,
            self._check_trade_size,
            self._check_min_edge,
        ]

        for check_fn in checks:
            passed, reason = check_fn(signal)
            if not passed:
                self._rejected_count += 1
                self._reject_reasons[reason] += 1
                logger.debug("Risk REJECT: %s — %s", signal.pair.pair_id, reason)
                return False, reason

        self._passed_count += 1
        return True, "ok"

    def _check_drawdown(self, signal: ArbSignal) -> tuple[bool, str]:
        dd_pct = (self._peak_capital - self.capital) / self._peak_capital * 100
        if dd_pct >= self.config.max_drawdown_pct:
            return False, f"drawdown {dd_pct:.1f}% >= {self.config.max_drawdown_pct}%"
        return True, ""

    def _check_daily_loss(self, signal: ArbSignal) -> tuple[bool, str]:
        if self._daily_pnl <= -self.config.daily_loss_limit_usd:
            return False, f"daily loss ${self._daily_pnl:+,.0f} hit limit"
        return True, ""

    def _check_max_positions(self, signal: ArbSignal) -> tuple[bool, str]:
        if len(self._open_positions) >= self.config.max_positions:
            return False, f"max positions {self.config.max_positions} reached"
        return True, ""

    def _check_per_market_exposure(self, signal: ArbSignal) -> tuple[bool, str]:
        current = self._open_positions.get(signal.pair.pair_id, 0.0)
        if current + signal.suggested_size_usd > self.config.max_per_market_usd:
            return False, f"per-market exposure ${current + signal.suggested_size_usd:,.0f} > ${self.config.max_per_market_usd:,.0f}"
        return True, ""

    def _check_total_exposure(self, signal: ArbSignal) -> tuple[bool, str]:
        total = sum(self._open_positions.values()) + signal.suggested_size_usd
        if total > self.config.max_total_exposure_usd:
            return False, f"total exposure ${total:,.0f} > ${self.config.max_total_exposure_usd:,.0f}"
        return True, ""

    def _check_trade_size(self, signal: ArbSignal) -> tuple[bool, str]:
        if signal.suggested_size_usd > self.config.max_position_usd:
            return False, f"trade size ${signal.suggested_size_usd:,.0f} > ${self.config.max_position_usd:,.0f}"
        return True, ""

    def _check_min_edge(self, signal: ArbSignal) -> tuple[bool, str]:
        if signal.net_spread_bps < self.config.min_net_spread_bps:
            return False, f"edge {signal.net_spread_bps:.0f} bps < {self.config.min_net_spread_bps:.0f} bps min"
        return True, ""

    def record_trade(self, trade: ArbTrade) -> None:
        """Update risk state after a trade executes."""
        if trade.status == "filled":
            self._open_positions[trade.signal.pair.pair_id] = (
                self._open_positions.get(trade.signal.pair.pair_id, 0.0)
                + trade.leg_buy.size_usd
            )

    def record_settlement(self, trade: ArbTrade) -> None:
        """Update risk state after a trade settles."""
        pair_id = trade.signal.pair.pair_id
        if pair_id in self._open_positions:
            self._open_positions[pair_id] -= trade.leg_buy.size_usd
            if self._open_positions[pair_id] <= 0:
                del self._open_positions[pair_id]
        self._total_pnl += trade.pnl_net
        self._daily_pnl += trade.pnl_net
        self.capital += trade.pnl_net
        self._peak_capital = max(self._peak_capital, self.capital)

    def recommended_size_multiplier(self) -> float:
        """Scale position sizes down as drawdown increases.

        Returns 1.0 at 0% drawdown, linearly decreasing to 0.25 at
        max_drawdown_pct/2, and 0.0 at max_drawdown_pct.
        """
        if self._peak_capital <= 0:
            return 0.0
        dd_pct = (self._peak_capital - self.capital) / self._peak_capital * 100
        half_max = self.config.max_drawdown_pct / 2
        if dd_pct <= half_max * 0.5:
            return 1.0
        if dd_pct >= self.config.max_drawdown_pct:
            return 0.0
        return max(0.0, 1.0 - dd_pct / self.config.max_drawdown_pct)

    def _maybe_reset_daily(self) -> None:
        """Reset daily P&L counter every 24 hours."""
        now = time.time()
        if now - self._daily_reset_time >= 86400:
            self._daily_pnl = 0.0
            self._daily_reset_time = now

    def summary(self) -> dict:
        dd = (self._peak_capital - self.capital) / self._peak_capital * 100 if self._peak_capital > 0 else 0
        return {
            "capital": self.capital,
            "total_pnl": self._total_pnl,
            "daily_pnl": self._daily_pnl,
            "drawdown_pct": dd,
            "open_positions": len(self._open_positions),
            "total_exposure": sum(self._open_positions.values()),
            "passed": self._passed_count,
            "rejected": self._rejected_count,
            "reject_reasons": dict(self._reject_reasons),
            "size_multiplier": self.recommended_size_multiplier(),
        }
