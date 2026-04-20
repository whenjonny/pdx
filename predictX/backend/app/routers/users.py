from fastapi import APIRouter, HTTPException
from app.models.schemas import UserPosition, UserTransaction, UserSummary
from app.services.blockchain import blockchain_service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/{address}/positions", response_model=list[UserPosition])
def get_user_positions(address: str):
    """Get all markets where the user holds YES or NO tokens."""
    try:
        return blockchain_service.get_user_positions(address)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{address}/transactions", response_model=list[UserTransaction])
def get_user_transactions(address: str):
    """Get all blockchain transactions for the user, sorted by block number descending."""
    try:
        return blockchain_service.get_user_transactions(address)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{address}/summary", response_model=UserSummary)
def get_user_summary(address: str):
    """Get aggregated summary of user activity."""
    try:
        positions = blockchain_service.get_user_positions(address)
        transactions = blockchain_service.get_user_transactions(address)

        markets_created = sum(1 for t in transactions if t.type == "create_market")
        evidence_submitted = sum(1 for t in transactions if t.type == "submit_evidence")

        # Sum estimated USDC value across all positions
        total_value = sum(int(p.current_value_usdc) for p in positions)

        return UserSummary(
            address=address,
            active_positions=len(positions),
            markets_created=markets_created,
            evidence_submitted=evidence_submitted,
            total_value_usdc=str(total_value),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
