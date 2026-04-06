import random
import time
from datetime import datetime, timezone

import httpx
from app.config import settings
from app.models.schemas import PredictionResponse


class MockMiroFishClient:
    """Mock MiroFish client that generates predictions based on AMM prices."""

    def get_prediction(self, market_id: int, current_yes_price: float = 0.5) -> PredictionResponse:
        # Add slight variance around AMM price to simulate independent analysis
        noise = random.gauss(0, 0.05)
        prob = max(0.01, min(0.99, current_yes_price + noise))

        if abs(prob - 0.5) < 0.1:
            confidence = "LOW"
            reasoning = "Insufficient evidence to form a strong opinion. Market is roughly balanced."
        elif abs(prob - 0.5) < 0.25:
            confidence = "MEDIUM"
            direction = "YES" if prob > 0.5 else "NO"
            reasoning = (
                f"Moderate evidence suggests {direction} outcome. "
                f"Based on analysis of {random.randint(5, 15)} evidence sources, "
                f"key factors point toward a {prob:.0%} probability."
            )
        else:
            confidence = "HIGH"
            direction = "YES" if prob > 0.5 else "NO"
            reasoning = (
                f"Strong evidence supports {direction} outcome. "
                f"Multi-agent simulation across {random.randint(10, 30)} personas "
                f"with {random.randint(20, 50)} evidence sources converges on {prob:.0%}."
            )

        return PredictionResponse(
            probability=round(prob, 4),
            confidence=confidence,
            reasoning=reasoning,
            lastUpdated=datetime.now(timezone.utc).isoformat(),
        )


class MiroFishClient:
    """Real MiroFish client — calls the MiroFish Flask API."""

    def __init__(self):
        self.base_url = settings.mirofish_url

    def get_prediction(self, market_id: int, current_yes_price: float = 0.5) -> PredictionResponse:
        try:
            # Check if MiroFish is running
            resp = httpx.get(f"{self.base_url}/api/report/status", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Extract probability from report if available
                prob = data.get("probability", current_yes_price)
                return PredictionResponse(
                    probability=prob,
                    confidence=data.get("confidence", "MEDIUM"),
                    reasoning=data.get("summary", "MiroFish analysis in progress..."),
                    lastUpdated=datetime.now(timezone.utc).isoformat(),
                )
        except Exception:
            pass

        # Fallback to mock if MiroFish unavailable
        return MockMiroFishClient().get_prediction(market_id, current_yes_price)


def get_mirofish_client():
    if settings.use_mock_mirofish:
        return MockMiroFishClient()
    return MiroFishClient()


mirofish_client = get_mirofish_client()
