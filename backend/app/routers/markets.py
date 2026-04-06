from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    MarketResponse,
    CreateMarketRequest, CreateMarketResponse,
    MintUSDCRequest, MintUSDCResponse,
    SettleMarketRequest, SettleMarketResponse,
)
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


@router.post("", response_model=CreateMarketResponse)
def create_market(req: CreateMarketRequest):
    """Create a new prediction market."""
    try:
        result = blockchain_service.create_market(
            question=req.question,
            deadline_days=req.deadline_days,
            initial_liquidity_usdc=req.initial_liquidity,
        )
        return CreateMarketResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settle", response_model=SettleMarketResponse)
def settle_market(req: SettleMarketRequest):
    """Settle a market (oracle only)."""
    try:
        result = blockchain_service.settle_market(req.market_id, req.outcome)
        return SettleMarketResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mint-usdc", response_model=MintUSDCResponse)
def mint_usdc(req: MintUSDCRequest):
    """Mint MockUSDC to an address."""
    try:
        result = blockchain_service.mint_usdc(req.to, req.amount)
        return MintUSDCResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
