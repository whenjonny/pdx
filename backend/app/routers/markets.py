from fastapi import APIRouter, HTTPException
from app.models.schemas import MarketResponse
from app.services.blockchain import blockchain_service

router = APIRouter(prefix="/api/markets", tags=["markets"])


@router.get("", response_model=list[MarketResponse])
def list_markets():
    return blockchain_service.list_markets()


@router.get("/{market_id}", response_model=MarketResponse)
def get_market(market_id: int):
    market = blockchain_service.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return market
