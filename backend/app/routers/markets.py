import time

from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    MarketResponse,
    MarketTrade,
    PlatformStats,
    CreateMarketRequest, CreateMarketResponse,
    MintUSDCRequest, MintUSDCResponse,
    SettleMarketRequest, SettleMarketResponse,
    SetMarketMetadataRequest,
)
from app.services.blockchain import blockchain_service

router = APIRouter(prefix="/api", tags=["markets"])


@router.get("/markets", response_model=list[MarketResponse])
def list_markets(
    category: str | None = None,
    sort: str = "newest",
    search: str | None = None,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
):
    """List markets with optional filtering, sorting, and pagination."""
    try:
        markets = blockchain_service.list_markets()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch markets: {e}")

    now = int(time.time())

    # Apply filters
    if category:
        markets = [m for m in markets if m.category.lower() == category.lower()]

    if search:
        search_lower = search.lower()
        markets = [m for m in markets if search_lower in m.question.lower()]

    if status:
        if status == "active":
            markets = [m for m in markets if not m.resolved and m.deadline > now]
        elif status == "resolved":
            markets = [m for m in markets if m.resolved]
        elif status == "locked":
            # Locked = in lockdown period (past lockTime but not resolved and not expired)
            markets = [
                m for m in markets
                if not m.resolved and m.lockTime <= now < m.deadline
            ]

    # Apply sort
    if sort == "newest":
        markets.sort(key=lambda m: m.id, reverse=True)
    elif sort == "volume":
        markets.sort(key=lambda m: m.totalDeposited, reverse=True)
    elif sort == "ending_soon":
        # Only include non-expired markets, sort by deadline ascending
        markets = [m for m in markets if m.deadline > now]
        markets.sort(key=lambda m: m.deadline)

    # Apply pagination
    page = max(1, page)
    limit = max(1, min(limit, 100))
    skip = (page - 1) * limit
    markets = markets[skip:skip + limit]

    return markets


@router.get("/markets/{market_id}", response_model=MarketResponse)
def get_market(market_id: int):
    market = blockchain_service.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return market


@router.get("/markets/{market_id}/trades", response_model=list[MarketTrade])
def get_market_trades(market_id: int, limit: int = 50):
    """Get trade history for a specific market."""
    # Verify market exists
    market = blockchain_service.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    try:
        limit = max(1, min(limit, 500))
        trades = blockchain_service.get_market_trades(market_id)
        return trades[:limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch trades: {e}")


@router.post("/markets", response_model=CreateMarketResponse)
def create_market(req: CreateMarketRequest):
    """Create a new prediction market."""
    try:
        result = blockchain_service.create_market(
            question=req.question,
            deadline_days=req.deadline_days,
            initial_liquidity_usdc=req.initial_liquidity,
        )
        # Store off-chain metadata (category, resolution source)
        blockchain_service.set_market_metadata(
            market_id=result["market_id"],
            category=req.category,
            resolution_source=req.resolution_source,
        )
        return CreateMarketResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/markets/{market_id}/metadata")
def set_market_metadata(market_id: int, req: SetMarketMetadataRequest):
    """Set off-chain metadata (category, resolution source) for a market."""
    market = blockchain_service.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    blockchain_service.set_market_metadata(
        market_id=market_id,
        category=req.category,
        resolution_source=req.resolution_source,
    )
    return {"ok": True}


@router.post("/markets/settle", response_model=SettleMarketResponse)
def settle_market(req: SettleMarketRequest):
    """Settle a market (oracle only)."""
    try:
        result = blockchain_service.settle_market(req.market_id, req.outcome)
        return SettleMarketResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/markets/mint-usdc", response_model=MintUSDCResponse)
def mint_usdc(req: MintUSDCRequest):
    """Mint MockUSDC to an address."""
    try:
        result = blockchain_service.mint_usdc(req.to, req.amount)
        return MintUSDCResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=PlatformStats)
def get_platform_stats():
    """Get platform-wide statistics."""
    try:
        markets = blockchain_service.list_markets()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {e}")

    now = int(time.time())
    active_markets = [m for m in markets if not m.resolved and m.deadline > now]
    total_volume = sum(m.totalDeposited for m in markets)
    total_evidence = sum(m.evidenceCount for m in markets)

    return PlatformStats(
        total_markets=len(markets),
        active_markets=len(active_markets),
        total_volume=str(total_volume),
        total_evidence=total_evidence,
    )
