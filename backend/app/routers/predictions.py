from fastapi import APIRouter, HTTPException
from app.models.schemas import PredictionResponse
from app.services.blockchain import blockchain_service
from app.services.mirofish_client import mirofish_client

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("/{market_id}", response_model=PredictionResponse)
def get_prediction(market_id: int):
    """Get MiroFish probability prediction for a market."""
    market = blockchain_service.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    current_yes_price = market.priceYes
    return mirofish_client.get_prediction(market_id, current_yes_price)
