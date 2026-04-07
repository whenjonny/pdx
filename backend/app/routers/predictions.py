from fastapi import APIRouter, HTTPException
from app.models.schemas import PredictionResponse
from app.services.blockchain import blockchain_service
from app.services.mirofish_client import mirofish_client, ScheduledMiroFishClient

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("/{market_id}", response_model=PredictionResponse)
async def get_prediction(market_id: int):
    """Get MiroFish probability prediction for a market."""
    market = blockchain_service.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    current_yes_price = market.priceYes

    # Use async method if available (ScheduledMiroFishClient)
    if isinstance(mirofish_client, ScheduledMiroFishClient):
        prediction = await mirofish_client.get_prediction_async(market_id, current_yes_price)
    else:
        prediction = mirofish_client.get_prediction(market_id, current_yes_price)

    # Always include current AMM price
    prediction.amm_price_yes = current_yes_price
    return prediction
