import random
import time

from app.config import settings
from app.models.schemas import PredictionResponse


class MockMiroFishClient:
    """Mock MiroFish client that generates predictions based on AMM prices."""

    def get_prediction(self, market_id: int, current_yes_price: float = 0.5) -> PredictionResponse:
        # Add slight variance around AMM price to simulate independent analysis
        noise = random.gauss(0, 0.05)
        prob = max(0.01, min(0.99, current_yes_price + noise))

        if abs(prob - 0.5) < 0.1:
            confidence = 0.35
            reasoning = "Insufficient evidence to form a strong opinion. Market is roughly balanced."
        elif abs(prob - 0.5) < 0.25:
            confidence = 0.60
            direction = "YES" if prob > 0.5 else "NO"
            reasoning = (
                f"Moderate evidence suggests {direction} outcome. "
                f"Based on analysis of {random.randint(5, 15)} evidence sources, "
                f"key factors point toward a {prob:.0%} probability."
            )
        else:
            confidence = 0.85
            direction = "YES" if prob > 0.5 else "NO"
            reasoning = (
                f"Strong evidence supports {direction} outcome. "
                f"Multi-agent simulation across {random.randint(10, 30)} personas "
                f"with {random.randint(20, 50)} evidence sources converges on {prob:.0%}."
            )

        return PredictionResponse(
            market_id=market_id,
            probability_yes=round(prob, 4),
            probability_no=round(1 - prob, 4),
            confidence=confidence,
            reasoning=reasoning,
            source="MiroFish Mock",
            updated_at=int(time.time()),
        )


class ScheduledMiroFishClient:
    """Reads predictions from the MiroFish scheduler's in-memory cache."""

    async def get_prediction_async(self, market_id: int, current_yes_price: float = 0.5) -> PredictionResponse:
        from app.services.mirofish_scheduler import mirofish_scheduler

        # If cache is stale or missing, trigger on-demand analysis
        if mirofish_scheduler.is_stale(market_id):
            await mirofish_scheduler.analyze_single_market(market_id)

        cached = mirofish_scheduler.get_cached_prediction(market_id)
        if cached:
            return PredictionResponse(
                market_id=cached.market_id,
                probability_yes=cached.probability_yes,
                probability_no=cached.probability_no,
                confidence=cached.confidence,
                reasoning=cached.reasoning,
                source=cached.source,
                amm_price_yes=current_yes_price,
                updated_at=cached.updated_at,
            )

        # Fallback if analysis failed
        return PredictionResponse(
            market_id=market_id,
            probability_yes=0.5,
            probability_no=0.5,
            confidence=0.0,
            reasoning="MiroFish analysis pending...",
            source="MiroFish",
            amm_price_yes=current_yes_price,
            updated_at=int(time.time()),
        )

    def get_prediction(self, market_id: int, current_yes_price: float = 0.5) -> PredictionResponse:
        """Sync wrapper — reads from cache only (no on-demand)."""
        from app.services.mirofish_scheduler import mirofish_scheduler

        cached = mirofish_scheduler.get_cached_prediction(market_id)
        if cached:
            return PredictionResponse(
                market_id=cached.market_id,
                probability_yes=cached.probability_yes,
                probability_no=cached.probability_no,
                confidence=cached.confidence,
                reasoning=cached.reasoning,
                source=cached.source,
                amm_price_yes=current_yes_price,
                updated_at=cached.updated_at,
            )

        return PredictionResponse(
            market_id=market_id,
            probability_yes=0.5,
            probability_no=0.5,
            confidence=0.0,
            reasoning="MiroFish analysis pending...",
            source="MiroFish",
            amm_price_yes=current_yes_price,
            updated_at=int(time.time()),
        )


def get_mirofish_client():
    if settings.use_mock_mirofish:
        return MockMiroFishClient()
    return ScheduledMiroFishClient()


mirofish_client = get_mirofish_client()
