"""Market matcher — finds equivalent markets across Polymarket and predictX."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from pdx_arb.feeds.polymarket import PolymarketFeed
from pdx_arb.feeds.predictx import PredictXFeed
from pdx_arb.types import MarketPair

logger = logging.getLogger(__name__)

MIN_SIMILARITY = 0.70


def _normalize_question(q: str) -> str:
    """Normalize a question string for comparison."""
    q = q.lower().strip()
    q = re.sub(r"[^\w\s]", "", q)
    q = re.sub(r"\s+", " ", q)
    return q


def _similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two normalized question strings."""
    na, nb = _normalize_question(a), _normalize_question(b)
    return SequenceMatcher(None, na, nb).ratio()


class MarketMatcher:
    """Matches predictX markets with Polymarket equivalents.

    Strategy:
    1. If predictX stores a polymarketConditionId, use that for exact match.
    2. Otherwise, fuzzy-match by question string similarity.
    """

    def __init__(
        self,
        poly_feed: PolymarketFeed,
        pdx_feed: PredictXFeed,
        min_similarity: float = MIN_SIMILARITY,
        manual_pairs: list[dict] | None = None,
    ) -> None:
        self.poly_feed = poly_feed
        self.pdx_feed = pdx_feed
        self.min_similarity = min_similarity
        self._manual_pairs = manual_pairs or []
        self._cached_pairs: list[MarketPair] = []

    def add_manual_pair(
        self,
        pdx_market_id: int,
        poly_condition_id: str,
        poly_token_ids: list[str],
        question: str = "",
    ) -> MarketPair:
        """Register a manually matched market pair."""
        pair = MarketPair(
            pair_id=f"manual_{pdx_market_id}_{poly_condition_id[:8]}",
            question=question,
            poly_condition_id=poly_condition_id,
            poly_token_ids=poly_token_ids,
            pdx_market_id=pdx_market_id,
        )
        self._cached_pairs.append(pair)
        return pair

    def scan(self) -> list[MarketPair]:
        """Scan both venues and return all matched market pairs."""
        poly_markets = self.poly_feed.fetch_active_markets()
        pdx_markets = self.pdx_feed.fetch_active_markets()

        if not poly_markets or not pdx_markets:
            logger.info(
                "Scan found poly=%d, pdx=%d markets",
                len(poly_markets), len(pdx_markets),
            )
            return list(self._cached_pairs)

        pairs: list[MarketPair] = list(self._cached_pairs)
        matched_poly_ids: set[str] = {p.poly_condition_id for p in pairs}
        matched_pdx_ids: set[int] = {p.pdx_market_id for p in pairs}

        poly_by_cid = {m["condition_id"]: m for m in poly_markets}

        for pdx_m in pdx_markets:
            pdx_id = pdx_m["market_id"]
            if pdx_id in matched_pdx_ids:
                continue

            best_match = None
            best_score = 0.0

            for poly_m in poly_markets:
                cid = poly_m["condition_id"]
                if cid in matched_poly_ids:
                    continue
                score = _similarity(pdx_m["question"], poly_m["question"])
                if score > best_score:
                    best_score = score
                    best_match = poly_m

            if best_match and best_score >= self.min_similarity:
                pair = MarketPair(
                    pair_id=f"auto_{pdx_id}_{best_match['condition_id'][:8]}",
                    question=pdx_m["question"],
                    poly_condition_id=best_match["condition_id"],
                    poly_token_ids=best_match["token_ids"],
                    pdx_market_id=pdx_id,
                    poly_end_date=best_match.get("end_date", ""),
                    pdx_deadline=pdx_m.get("deadline", 0),
                )
                pairs.append(pair)
                matched_poly_ids.add(best_match["condition_id"])
                matched_pdx_ids.add(pdx_id)
                logger.info(
                    "Matched: pdx#%d <-> poly/%s (%.0f%%) '%s'",
                    pdx_id, best_match["condition_id"][:8],
                    best_score * 100, pdx_m["question"][:60],
                )
            else:
                logger.debug(
                    "No match for pdx#%d (best=%.0f%%): '%s'",
                    pdx_id, best_score * 100, pdx_m["question"][:60],
                )

        self._cached_pairs = pairs
        return pairs

    @property
    def pairs(self) -> list[MarketPair]:
        return list(self._cached_pairs)
