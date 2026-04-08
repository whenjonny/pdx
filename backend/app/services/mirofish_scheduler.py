"""MiroFish background scheduler — periodically analyzes all active markets.

Supports incremental V2 aggregation: when new evidence has preprocessed
embedding / Monte Carlo data, the aggregator updates mathematically without
calling an LLM.  V1 evidence still falls through to the LLM / heuristic path.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger("mirofish")


@dataclass
class CachedPrediction:
    market_id: int
    probability_yes: float
    probability_no: float
    confidence: float
    reasoning: str
    source: str
    updated_at: int  # unix timestamp


class MiroFishScheduler:
    def __init__(self):
        self._cache: dict[int, CachedPrediction] = {}
        self._evidence_counts: dict[int, int] = {}  # track processed evidence count per market
        self._task: asyncio.Task | None = None

    def get_cached_prediction(self, market_id: int) -> CachedPrediction | None:
        pred = self._cache.get(market_id)
        if pred:
            return pred
        # Fallback: load from SQLite
        from app.services import database as db
        row = db.get_prediction(market_id)
        if row:
            cached = CachedPrediction(**row)
            self._cache[market_id] = cached
            return cached
        return None

    def is_stale(self, market_id: int, max_age: int = 600) -> bool:
        """Check if prediction is stale (older than max_age seconds)."""
        pred = self.get_cached_prediction(market_id)
        if pred is None:
            return True
        return (int(time.time()) - pred.updated_at) > max_age

    async def analyze_single_market(self, market_id: int) -> CachedPrediction | None:
        """Analyze a single market, using incremental V2 aggregation when possible."""
        from app.services.blockchain import blockchain_service
        from app.services.ipfs import ipfs_service
        from app.services.mirofish_aggregator import aggregator
        from app.services.anticheat import evaluate_evidence

        market = blockchain_service.get_market(market_id)
        if not market:
            return None

        evidence = blockchain_service.get_evidence_list(market_id)
        total_count = len(evidence)
        prev_count = self._evidence_counts.get(market_id, 0)

        # Nothing new — return cached prediction
        if total_count == prev_count and market_id in self._cache:
            return self._cache[market_id]

        # Build submitter counts for per-address cap
        submitter_counts: dict[str, int] = {}
        for e in evidence:
            submitter_counts[e.submitter] = submitter_counts.get(e.submitter, 0) + 1

        # Fetch IPFS data for new evidence items only (incremental)
        new_start = prev_count
        v1_items: list[dict] = []
        v2_count = 0
        trust_scores: dict[int, float] = {}

        for i in range(new_start, total_count):
            e = evidence[i]
            ipfs_data = ipfs_service.fetch_by_hash(e.ipfsHash)
            if ipfs_data and ipfs_data.get("version") == "2.0":
                # Get existing embeddings before adding this one (for novelty check)
                existing_embs = aggregator.get_all_embeddings(market_id)

                # V2 evidence → feed to incremental aggregator with submitter
                aggregator.add_evidence(market_id, ipfs_data, i, submitter=e.submitter)
                v2_count += 1

                # Anti-cheat evaluation
                result = evaluate_evidence(
                    evidence_index=i,
                    submitter=e.submitter,
                    ipfs_data=ipfs_data,
                    submitter_counts=submitter_counts,
                    total_evidence=total_count,
                    existing_embeddings=existing_embs,
                )
                trust_scores[i] = result.trust_score
            else:
                # V1 evidence → collect for LLM/heuristic analysis
                ev_dict = {"summary": e.summary, "timestamp": e.timestamp}
                if ipfs_data:
                    ev_dict["title"] = ipfs_data.get("title", "")
                    ev_dict["content"] = ipfs_data.get("content", "")
                    ev_dict["direction"] = ipfs_data.get("direction", "")
                    ev_dict["source_url"] = ipfs_data.get("sourceUrl", "")
                v1_items.append(ev_dict)

        # Apply anti-cheat trust scores to aggregator
        if trust_scores:
            aggregator.apply_trust_scores(market_id, trust_scores)

        self._evidence_counts[market_id] = total_count

        # Determine final prediction via best available path
        agg_state = aggregator.get_state(market_id)
        has_v2 = agg_state is not None and len(agg_state.digests) > 0

        if has_v2 and not v1_items:
            # Pure V2 path: use aggregator result directly (no LLM)
            cached = CachedPrediction(
                market_id=market_id,
                probability_yes=agg_state.probability_yes,
                probability_no=round(1 - agg_state.probability_yes, 4),
                confidence=agg_state.confidence,
                reasoning=agg_state.reasoning,
                source="MiroFish V2 Aggregator",
                updated_at=agg_state.updated_at,
            )
        elif has_v2 and v1_items:
            # Hybrid: blend V2 aggregation with V1 LLM/heuristic
            from app.services.mirofish_predictor import analyze_market

            # Collect ALL v1 evidence (not just new) for LLM context
            all_v1 = []
            for i, e in enumerate(evidence):
                ipfs_data = ipfs_service.fetch_by_hash(e.ipfsHash)
                if not ipfs_data or ipfs_data.get("version") != "2.0":
                    ev_dict = {"summary": e.summary, "timestamp": e.timestamp}
                    if ipfs_data:
                        ev_dict["title"] = ipfs_data.get("title", "")
                        ev_dict["content"] = ipfs_data.get("content", "")
                        ev_dict["direction"] = ipfs_data.get("direction", "")
                        ev_dict["source_url"] = ipfs_data.get("sourceUrl", "")
                    all_v1.append(ev_dict)

            v1_result = await analyze_market(market_id, market.question, all_v1)
            v1_prob = v1_result["probability_yes"]
            v1_conf = v1_result["confidence"]

            # Weighted blend: V2 gets higher weight due to preprocessed data
            v2_w = agg_state.confidence * len(agg_state.digests)
            v1_w = v1_conf * len(all_v1)
            total_w = v2_w + v1_w
            if total_w > 0:
                blended_prob = (agg_state.probability_yes * v2_w + v1_prob * v1_w) / total_w
            else:
                blended_prob = 0.5
            blended_prob = max(0.05, min(0.95, blended_prob))
            blended_conf = max(agg_state.confidence, v1_conf)

            cached = CachedPrediction(
                market_id=market_id,
                probability_yes=round(blended_prob, 4),
                probability_no=round(1 - blended_prob, 4),
                confidence=round(blended_conf, 2),
                reasoning=(
                    f"Hybrid analysis: {len(agg_state.digests)} V2 items (aggregated) "
                    f"+ {len(all_v1)} V1 items (LLM/heuristic). "
                    f"{v1_result['reasoning']}"
                ),
                source="MiroFish Hybrid",
                updated_at=int(time.time()),
            )
        else:
            # Pure V1 path: fall through to existing LLM/heuristic
            from app.services.mirofish_predictor import analyze_market

            all_evidence_dicts = []
            for e in evidence:
                ev_dict = {"summary": e.summary, "timestamp": e.timestamp}
                ipfs_data = ipfs_service.fetch_by_hash(e.ipfsHash)
                if ipfs_data:
                    ev_dict["title"] = ipfs_data.get("title", "")
                    ev_dict["content"] = ipfs_data.get("content", "")
                    ev_dict["direction"] = ipfs_data.get("direction", "")
                    ev_dict["source_url"] = ipfs_data.get("sourceUrl", "")
                all_evidence_dicts.append(ev_dict)

            result = await analyze_market(market_id, market.question, all_evidence_dicts)
            cached = CachedPrediction(
                market_id=market_id,
                probability_yes=result["probability_yes"],
                probability_no=round(1 - result["probability_yes"], 4),
                confidence=result["confidence"],
                reasoning=result["reasoning"],
                source=result["source"],
                updated_at=int(time.time()),
            )

        self._cache[market_id] = cached
        # Persist to SQLite
        from app.services import database as db
        db.set_prediction(
            market_id=cached.market_id,
            probability_yes=cached.probability_yes,
            probability_no=cached.probability_no,
            confidence=cached.confidence,
            reasoning=cached.reasoning,
            source=cached.source,
            updated_at=cached.updated_at,
        )
        logger.info(
            "Market %d: prob=%.2f conf=%.2f source=%s (v2=%d new_v1=%d)",
            market_id, cached.probability_yes, cached.confidence,
            cached.source, v2_count, len(v1_items),
        )
        return cached

    async def _run_cycle(self):
        """Analyze all active markets."""
        from app.services.blockchain import blockchain_service

        try:
            markets = blockchain_service.list_markets()
            active = [m for m in markets if not m.resolved]
            logger.info("MiroFish analyzing %d active markets", len(active))

            for market in active:
                try:
                    await self.analyze_single_market(market.id)
                except Exception as e:
                    logger.error("MiroFish failed for market %d: %s", market.id, e)

        except Exception as e:
            logger.error("MiroFish cycle failed: %s", e)

    async def _loop(self):
        """Background loop that runs every interval."""
        # Initial run after short delay to let app start
        await asyncio.sleep(5)
        logger.info("MiroFish scheduler started (interval=%ds)", settings.mirofish_interval_seconds)

        while True:
            await self._run_cycle()
            await asyncio.sleep(settings.mirofish_interval_seconds)

    def start(self):
        """Start the background scheduler task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("MiroFish background task created")

    def stop(self):
        """Stop the background scheduler task."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("MiroFish background task cancelled")


# Singleton
mirofish_scheduler = MiroFishScheduler()
