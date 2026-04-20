"""Statistical arbitrage strategy — detects and sizes cross-venue opportunities.

Signal generation:
1. Fetch synchronized prices from both venues
2. Compute net spread after fees, slippage, settlement risk
3. Apply EMA smoothing to detect persistent (not noise) dislocations
4. Size via Kelly criterion from risk manager
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from pdx_arb.config import ArbConfig
from pdx_arb.feeds.polymarket import PolymarketFeed
from pdx_arb.feeds.predictx import PredictXFeed
from pdx_arb.strategy.spread import compute_cross_venue_arb
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
        risk_manager=None,
        ema_span: int = 10,
        min_observations: int = 3,
    ) -> None:
        self.poly_feed = poly_feed
        self.pdx_feed = pdx_feed
        self.config = config
        self._risk = risk_manager

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
        self._obs_count[pair_id] += 1
        if pair_id not in self._spread_ema:
            self._spread_ema[pair_id] = net_spread_bps
        else:
            self._spread_ema[pair_id] = (
                self._alpha * net_spread_bps
                + (1.0 - self._alpha) * self._spread_ema[pair_id]
            )
        return self._spread_ema[pair_id]

    def evaluate(self, pair: MarketPair, prices: PricePair) -> ArbSignal | None:
        """Evaluate a single market pair for arbitrage opportunity."""
        spread = compute_cross_venue_arb(prices, self.config)
        if spread is None:
            return None

        self._update_ema(pair.pair_id, spread.net_spread_bps)

        if not spread.profitable:
            return None

        ema_val = self._spread_ema[pair.pair_id]
        obs = self._obs_count[pair.pair_id]

        if obs < self._min_obs:
            return None
        if ema_val < self.config.min_net_spread_bps:
            return None

        now = time.time()
        if now - self._last_signal_time[pair.pair_id] < self.config.cooldown_s:
            return None

        if self._risk is not None:
            size = self._risk.size_position(
                cost_per_unit=spread.cost_per_unit,
                guaranteed_pnl_per_unit=spread.guaranteed_pnl_per_unit,
                pair_id=pair.pair_id,
                poly_liquidity=prices.poly.liquidity,
                pdx_liquidity=prices.pdx.liquidity,
            )
        else:
            size = self._fallback_size(spread)

        if size < 10.0:
            return None

        buy_side = Side.BUY_YES if "yes" in spread.direction[:10] else Side.BUY_NO
        confidence = min(ema_val / self.config.min_net_spread_bps, 3.0) / 3.0

        signal = ArbSignal(
            pair=pair,
            prices=prices,
            direction=spread.direction,
            buy_venue=spread.buy_venue_yes,
            sell_venue=spread.buy_venue_no,
            buy_side=buy_side,
            gross_spread_bps=spread.gross_spread_bps,
            net_spread_bps=spread.net_spread_bps,
            fee_cost_bps=spread.fee_cost_bps,
            suggested_size_usd=size,
            edge=spread.net_spread_bps / 10_000,
            confidence=confidence,
        )

        self._last_signal_time[pair.pair_id] = now
        self._signals_generated += 1
        return signal

    def _fallback_size(self, spread) -> float:
        """Simple sizing when no risk manager is attached."""
        edge_pct = spread.net_spread_bps / 10_000
        if edge_pct <= 0:
            return 0.0
        size = self.config.kelly_fraction * self.config.max_position_usd * edge_pct * 10
        return min(size, self.config.max_position_usd)

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
                    "SIGNAL: %s | %s+%s | net=%.0f bps | size=$%.0f | conf=%.0f%%",
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
