"""MiroFish background scheduler — periodically analyzes all active markets."""

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
        """Analyze a single market on demand."""
        from app.services.blockchain import blockchain_service
        from app.services.mirofish_predictor import analyze_market

        market = blockchain_service.get_market(market_id)
        if not market:
            return None

        from app.services.ipfs import ipfs_service

        evidence = blockchain_service.get_evidence_list(market_id)
        evidence_dicts = []
        for e in evidence:
            ev_dict = {"summary": e.summary, "timestamp": e.timestamp}
            # Try to fetch full content from IPFS
            ipfs_data = ipfs_service.fetch_by_hash(e.ipfsHash)
            if ipfs_data:
                ev_dict["title"] = ipfs_data.get("title", "")
                ev_dict["content"] = ipfs_data.get("content", "")
                ev_dict["direction"] = ipfs_data.get("direction", "")
                ev_dict["source_url"] = ipfs_data.get("sourceUrl", "")
            evidence_dicts.append(ev_dict)

        result = await analyze_market(market_id, market.question, evidence_dicts)

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
