"""Risk manager for cross-venue arbitrage.

Controls position sizing, exposure limits, drawdown protection,
per-market concentration limits, Kelly sizing, volume scaling,
adverse selection detection, and leg failure tracking.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from pdx_arb.config import ArbConfig
from pdx_arb.types import ArbSignal, ArbTrade, HedgeAction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Kelly sizer
# ---------------------------------------------------------------------------

class KellySizer:
    """Proper Kelly criterion sizing for structural arbitrage.

    For cross-venue arb with hedging:
    - Win (prob p): gain = guaranteed_pnl_per_unit
    - Lose (prob q): loss = cost * friction_loss_frac (NOT total loss,
      because hedge mechanism recovers most of the position)

    Kelly f* = (p/L - q/G) where G = gain, L = loss per unit invested.
    Equivalently: f* = (p*G - q*L) / (G*L)
    """

    FRICTION_LOSS_FRAC = 0.15  # avg loss on friction = 15% of cost (hedge covers rest)

    def __init__(self, config: ArbConfig) -> None:
        self.config = config

    def compute(
        self,
        cost_per_unit: float,
        guaranteed_pnl_per_unit: float,
        bankroll: float,
        leg_fail_prob: float = 0.02,
        settlement_divergence_prob: float = 0.01,
        adverse_selection_prob: float = 0.02,
    ) -> float:
        if cost_per_unit <= 0 or guaranteed_pnl_per_unit <= 0 or bankroll <= 0:
            return 0.0

        gain = guaranteed_pnl_per_unit
        loss = cost_per_unit * self.FRICTION_LOSS_FRAC

        win_prob = self.config.kelly_win_prob_base
        win_prob *= (1.0 - leg_fail_prob)
        win_prob *= (1.0 - settlement_divergence_prob)
        win_prob *= (1.0 - adverse_selection_prob)
        win_prob *= (1.0 - self.config.kelly_friction_haircut)
        win_prob = max(win_prob, 0.01)

        q = 1.0 - win_prob

        if gain <= 0 or loss <= 0:
            return 0.0

        kelly_f = (win_prob * gain - q * loss) / (gain * loss)
        kelly_f = max(kelly_f, 0.0)

        f = kelly_f * self.config.kelly_fraction
        size = f * bankroll * cost_per_unit
        return min(size, self.config.max_position_usd)


# ---------------------------------------------------------------------------
# Volume / liquidity scaler
# ---------------------------------------------------------------------------

class VolumeScaler:
    """Scale position size based on venue liquidity."""

    def __init__(self, config: ArbConfig) -> None:
        self.config = config

    def is_thin(self, poly_liquidity: float, pdx_liquidity: float) -> bool:
        return min(poly_liquidity, pdx_liquidity) < self.config.min_market_volume_usd

    def scale(
        self,
        proposed_size: float,
        poly_liquidity: float,
        pdx_liquidity: float,
    ) -> float:
        min_liq = min(poly_liquidity, pdx_liquidity)
        if min_liq <= 0:
            return 0.0

        liq_cap = min_liq * self.config.liquidity_scale_factor
        size = min(proposed_size, liq_cap)

        if self.is_thin(poly_liquidity, pdx_liquidity):
            size = min(size, self.config.thin_market_size_cap_usd)

        return size


# ---------------------------------------------------------------------------
# Adverse selection detector
# ---------------------------------------------------------------------------

@dataclass
class TradeOutcome:
    market_id: str
    timestamp: float
    adverse: bool  # True if price moved against us post-fill


class AdverseSelectionDetector:
    """Track post-trade price movements to detect toxic flow."""

    def __init__(self, config: ArbConfig) -> None:
        self.config = config
        self._history: dict[str, deque[TradeOutcome]] = defaultdict(
            lambda: deque(maxlen=config.adverse_lookback)
        )
        self._blacklist: dict[str, float] = {}  # market_id -> expiry timestamp
        self._fill_attempts: dict[str, int] = defaultdict(int)
        self._fill_failures: dict[str, int] = defaultdict(int)

    def record_price_movement(self, market_id: str, adverse: bool) -> None:
        self._history[market_id].append(
            TradeOutcome(market_id=market_id, timestamp=time.time(), adverse=adverse)
        )
        score = self._toxicity_score(market_id)
        if score >= self.config.adverse_toxicity_threshold:
            expiry = time.time() + self.config.adverse_blacklist_duration_s
            self._blacklist[market_id] = expiry
            logger.warning(
                "BLACKLIST %s: toxicity %.2f >= %.2f (expires in %.0fs)",
                market_id, score, self.config.adverse_toxicity_threshold,
                self.config.adverse_blacklist_duration_s,
            )

    def record_fill_attempt(self, market_id: str, success: bool) -> None:
        self._fill_attempts[market_id] += 1
        if not success:
            self._fill_failures[market_id] += 1

    def is_blacklisted(self, market_id: str) -> bool:
        expiry = self._blacklist.get(market_id)
        if expiry is None:
            return False
        if time.time() >= expiry:
            del self._blacklist[market_id]
            return False
        return True

    def toxicity_score(self, market_id: str) -> float:
        return self._toxicity_score(market_id)

    def _toxicity_score(self, market_id: str) -> float:
        history = self._history.get(market_id)
        if not history or len(history) < 3:
            return 0.0
        adverse_count = sum(1 for t in history if t.adverse)
        adverse_ratio = adverse_count / len(history)

        attempts = self._fill_attempts.get(market_id, 0)
        failures = self._fill_failures.get(market_id, 0)
        fail_ratio = failures / attempts if attempts > 0 else 0.0

        # Weighted: 70% adverse price moves, 30% fill failures
        return 0.7 * adverse_ratio + 0.3 * fail_ratio

    def stats(self) -> dict:
        return {
            "blacklisted_markets": [
                m for m, exp in self._blacklist.items() if time.time() < exp
            ],
            "tracked_markets": len(self._history),
        }


# ---------------------------------------------------------------------------
# Leg failure tracker
# ---------------------------------------------------------------------------

class LegFailureTracker:
    """Track naked exposure from failed legs and hedge outcomes."""

    def __init__(self, config: ArbConfig) -> None:
        self.config = config
        self._naked_exposure_usd: float = 0.0
        self._failure_count: int = 0
        self._hedge_actions: list[HedgeAction] = []

    @property
    def naked_exposure(self) -> float:
        return self._naked_exposure_usd

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def record_failure(self, size_usd: float) -> None:
        self._failure_count += 1
        self._naked_exposure_usd += size_usd
        logger.warning(
            "LEG FAILURE #%d: naked exposure now $%.0f",
            self._failure_count, self._naked_exposure_usd,
        )

    def record_hedge(self, action: HedgeAction) -> None:
        self._hedge_actions.append(action)
        if action.success:
            # Successful hedge removes the naked exposure
            self._naked_exposure_usd = max(0.0, self._naked_exposure_usd - abs(action.pnl))
            logger.info(
                "HEDGE OK (%s): pnl=$%.2f, naked exposure now $%.0f",
                action.hedge_type, action.pnl, self._naked_exposure_usd,
            )
        else:
            logger.warning("HEDGE FAILED (%s): naked exposure $%.0f", action.hedge_type, self._naked_exposure_usd)

    def should_halt(self) -> bool:
        return self._naked_exposure_usd >= self.config.max_naked_exposure_usd

    def size_penalty(self) -> float:
        """Reduce sizing as failures accumulate. 1.0 = no penalty."""
        if self._failure_count == 0:
            return 1.0
        # Each failure reduces max size by 15%, floor at 25%
        return max(0.25, 1.0 - 0.15 * self._failure_count)

    @property
    def hedge_actions(self) -> list[HedgeAction]:
        return list(self._hedge_actions)

    def stats(self) -> dict:
        successful = sum(1 for a in self._hedge_actions if a.success)
        total = len(self._hedge_actions)
        return {
            "naked_exposure_usd": self._naked_exposure_usd,
            "failure_count": self._failure_count,
            "hedge_attempts": total,
            "hedge_success_rate": successful / total if total > 0 else 0.0,
        }


# ---------------------------------------------------------------------------
# Main risk manager
# ---------------------------------------------------------------------------

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

        # New risk components
        self.kelly = KellySizer(config)
        self.volume_scaler = VolumeScaler(config)
        self.adverse = AdverseSelectionDetector(config)
        self.leg_failures = LegFailureTracker(config)

    def check(self, signal: ArbSignal) -> tuple[bool, str]:
        """Run all pre-trade checks. Returns (passed, reason)."""
        self._maybe_reset_daily()

        checks = [
            self._check_drawdown,
            self._check_daily_loss,
            self._check_naked_exposure,
            self._check_max_positions,
            self._check_per_market_exposure,
            self._check_total_exposure,
            self._check_trade_size,
            self._check_min_edge,
            self._check_volume_liquidity,
            self._check_adverse_selection,
        ]

        for check_fn in checks:
            passed, reason = check_fn(signal)
            if not passed:
                self._rejected_count += 1
                self._reject_reasons[reason] += 1
                logger.debug("Risk REJECT: %s -- %s", signal.pair.pair_id, reason)
                return False, reason

        self._passed_count += 1
        return True, "ok"

    # ---- existing checks ----

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

    # ---- new checks ----

    def _check_naked_exposure(self, signal: ArbSignal) -> tuple[bool, str]:
        if self.leg_failures.should_halt():
            return False, f"naked exposure ${self.leg_failures.naked_exposure:,.0f} >= ${self.config.max_naked_exposure_usd:,.0f} limit"
        return True, ""

    def _check_volume_liquidity(self, signal: ArbSignal) -> tuple[bool, str]:
        poly_liq = signal.prices.poly.liquidity
        pdx_liq = signal.prices.pdx.liquidity
        min_liq = min(poly_liq, pdx_liq)
        if min_liq < self.config.min_market_volume_usd:
            if signal.suggested_size_usd > self.config.thin_market_size_cap_usd:
                return False, f"thin market (liq=${min_liq:,.0f}) size ${signal.suggested_size_usd:,.0f} > cap ${self.config.thin_market_size_cap_usd:,.0f}"
        return True, ""

    def _check_adverse_selection(self, signal: ArbSignal) -> tuple[bool, str]:
        if self.adverse.is_blacklisted(signal.pair.pair_id):
            return False, f"market {signal.pair.pair_id} blacklisted (toxic flow)"
        return True, ""

    # ---- sizing ----

    def size_position(
        self,
        cost_per_unit: float,
        guaranteed_pnl_per_unit: float,
        pair_id: str = "",
        poly_liquidity: float = 0.0,
        pdx_liquidity: float = 0.0,
        signal: ArbSignal | None = None,
    ) -> float:
        """Compute final position size: Kelly * volume scaling * drawdown * failure penalty."""
        if signal is not None:
            pair_id = pair_id or signal.pair.pair_id
            poly_liquidity = poly_liquidity or signal.prices.poly.liquidity
            pdx_liquidity = pdx_liquidity or signal.prices.pdx.liquidity

        toxicity = self.adverse.toxicity_score(pair_id) if pair_id else 0.0

        kelly_size = self.kelly.compute(
            cost_per_unit=cost_per_unit,
            guaranteed_pnl_per_unit=guaranteed_pnl_per_unit,
            bankroll=self.capital,
            adverse_selection_prob=toxicity * 0.1,
        )

        if kelly_size <= 0:
            return 0.0

        sized = self.volume_scaler.scale(kelly_size, poly_liquidity, pdx_liquidity)

        sized *= self.recommended_size_multiplier()
        sized *= self.leg_failures.size_penalty()

        sized = min(sized, self.config.max_position_usd)
        return sized

    # ---- recording ----

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

    def record_leg_failure(self, size_usd: float) -> None:
        """Record a leg failure event."""
        self.leg_failures.record_failure(size_usd)

    def record_hedge(self, action: HedgeAction) -> None:
        """Record a hedge action after leg failure."""
        self.leg_failures.record_hedge(action)

    def record_price_movement(self, market_id: str, adverse: bool) -> None:
        """Record post-trade price movement for adverse selection tracking."""
        self.adverse.record_price_movement(market_id, adverse)

    def record_fill_attempt(self, market_id: str, success: bool) -> None:
        """Record a fill attempt for adverse selection tracking."""
        self.adverse.record_fill_attempt(market_id, success)

    # ---- helpers ----

    def recommended_size_multiplier(self) -> float:
        """Scale position sizes down as drawdown increases."""
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
            "leg_failures": self.leg_failures.stats(),
            "adverse_selection": self.adverse.stats(),
        }
