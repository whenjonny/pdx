"""Statistical arbitrage strategy — detects and sizes cross-venue opportunities.

The core insight from backtesting: YES-side trades are systematically more
profitable than NO-side trades in prediction markets. This strategy applies
that finding to cross-venue arbitrage.

Signal generation:
1. Fetch synchronized prices from both venues
2. Compute net spread after fees, slippage, settlement risk
3. Apply EMA smoothing to detect persistent (not noise) dislocations
4. Size via fractional Kelly based on historical hit rate

The EMA filter avoids chasing transient price differences that close before
execution completes. We only trade when the spread has been persistently
above threshold for multiple observations.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from pdx_arb.config import ArbConfig
from pdx_arb.feeds.polymarket import PolymarketFeed
from pdx_arb.feeds.predictx import PredictXFeed
from pdx_arb.strategy.spread import SpreadResult, compute_no_spread, compute_spread
from pdx_arb.types import ArbSignal, MarketPair, PricePair, Side, Venue, VenuePrice

logger = logging.getLogger(__name__)


class CrossVenueStatArb:
    """Cross-venue statistical arbitrage between Polymarket and predictX.

    Scans matched market pairs, computes net spreads, applies EMA filter,
    and generates sized trading signals.
    """

    def __init__(
        self,
        poly_feed: PolymarketFeed,
        pdx_feed: PredictXFeed,
        config: ArbConfig,
        ema_span: int = 10,
        min_observations: int = 3,
        prefer_yes: bool = True,
    ) -> None:
        self.poly_feed = poly_feed
        self.pdx_feed = pdx_feed
        self.config = config
        self.prefer_yes = prefer_yes

        self._alpha = 2.0 / (ema_span + 1)
        self._min_obs = min_observations

        self._spread_ema: dict[str, float] = {}
        self._obs_count: dict[str, int] = defaultdict(int)
        self._last_signal_time: dict[str, float] = defaultdict(float)

        self._signals_generated = 0
        self._scans_performed = 0
        self._pairs_scanned = 0

    def fetch_prices(self, pair: MarketPair) -> PricePair | None:
        """Fetch synchronized prices from both venues."""
        try:
            poly_price = self.poly_feed.get_price(pair.poly_token_ids)
            pdx_price = self.pdx_feed.get_price(pair.pdx_market_id)
        except Exception as exc:
            logger.debug("Price fetch failed for %s: %s", pair.pair_id, exc)
            return None

        if poly_price.yes_price <= 0 or pdx_price.yes_price <= 0:
            return None

        return PricePair(pair=pair, poly=poly_price, pdx=pdx_price)

    def _update_ema(self, pair_id: str, net_spread_bps: float) -> float:
        """Update EMA of net spread and return current value."""
        self._obs_count[pair_id] += 1
        if pair_id not in self._spread_ema:
            self._spread_ema[pair_id] = net_spread_bps
        else:
            self._spread_ema[pair_id] = (
                self._alpha * net_spread_bps
                + (1.0 - self._alpha) * self._spread_ema[pair_id]
            )
        return self._spread_ema[pair_id]

    def _compute_size(self, spread: SpreadResult, bankroll: float) -> float:
        """Compute position size via fractional Kelly criterion.

        Kelly fraction for a binary outcome:
            f* = (p * b - q) / b
        where p = win probability, q = 1-p, b = payout odds.

        For arb, the "win probability" is the likelihood the spread closes
        in our favor (historical ~65% for persistent spreads).
        """
        est_win_prob = 0.65
        edge_pct = spread.net_spread_bps / 10_000
        if edge_pct <= 0:
            return 0.0
        payout_odds = edge_pct / spread.buy_price if spread.buy_price > 0 else 0
        if payout_odds <= 0:
            return 0.0
        kelly_f = (est_win_prob * payout_odds - (1 - est_win_prob)) / payout_odds
        kelly_f = max(kelly_f, 0.0)
        f = kelly_f * self.config.kelly_fraction
        size = f * bankroll
        return min(size, self.config.max_position_usd)

    def evaluate(self, pair: MarketPair, prices: PricePair) -> ArbSignal | None:
        """Evaluate a single market pair for arbitrage opportunity."""
        yes_spread = compute_spread(prices, self.config)
        no_spread = compute_no_spread(prices, self.config) if not self.prefer_yes else None

        candidates = []
        if yes_spread and yes_spread.profitable:
            candidates.append(("yes", yes_spread))
        if no_spread and no_spread.profitable:
            candidates.append(("no", no_spread))

        if not candidates:
            if yes_spread:
                self._update_ema(pair.pair_id, yes_spread.net_spread_bps)
            return None

        outcome_side, best = max(candidates, key=lambda x: x[1].net_spread_bps)

        ema_val = self._update_ema(pair.pair_id, best.net_spread_bps)
        obs = self._obs_count[pair.pair_id]

        if obs < self._min_obs:
            return None
        if ema_val < self.config.min_net_spread_bps:
            return None

        now = time.time()
        if now - self._last_signal_time[pair.pair_id] < self.config.cooldown_s:
            return None

        size = self._compute_size(best, self.config.max_position_usd)
        if size < 10.0:
            return None

        if outcome_side == "yes":
            buy_side = Side.BUY_YES
        else:
            buy_side = Side.BUY_NO

        confidence = min(ema_val / self.config.min_net_spread_bps, 3.0) / 3.0

        signal = ArbSignal(
            pair=pair,
            prices=prices,
            direction=best.direction,
            buy_venue=best.buy_venue,
            sell_venue=best.sell_venue,
            buy_side=buy_side,
            gross_spread_bps=best.gross_spread_bps,
            net_spread_bps=best.net_spread_bps,
            fee_cost_bps=best.fee_cost_bps,
            suggested_size_usd=size,
            edge=best.net_spread_bps / 10_000,
            confidence=confidence,
        )

        self._last_signal_time[pair.pair_id] = now
        self._signals_generated += 1
        return signal

    def scan(self, pairs: list[MarketPair]) -> list[ArbSignal]:
        """Scan all matched pairs and return actionable signals."""
        self._scans_performed += 1
        signals: list[ArbSignal] = []

        for pair in pairs:
            if not pair.active:
                continue
            self._pairs_scanned += 1

            prices = self.fetch_prices(pair)
            if prices is None:
                continue

            signal = self.evaluate(pair, prices)
            if signal is not None:
                signals.append(signal)
                logger.info(
                    "SIGNAL: %s | %s → %s | net=%.0f bps | size=$%.0f | conf=%.0f%%",
                    pair.question[:40],
                    signal.buy_venue.name,
                    signal.sell_venue.name,
                    signal.net_spread_bps,
                    signal.suggested_size_usd,
                    signal.confidence * 100,
                )

        return signals

    def summary(self) -> dict:
        return {
            "scans": self._scans_performed,
            "pairs_scanned": self._pairs_scanned,
            "signals_generated": self._signals_generated,
            "tracked_pairs": len(self._spread_ema),
            "pairs_above_threshold": sum(
                1 for v in self._spread_ema.values()
                if v >= self.config.min_net_spread_bps
            ),
        }
