from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    EvidenceResponse,
    EvidenceUploadRequest,
    EvidenceUploadResponse,
)
from app.services.blockchain import blockchain_service
from app.services.ipfs import ipfs_service

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


@router.get("/{market_id}", response_model=list[EvidenceResponse])
def list_evidence(market_id: int):
    return blockchain_service.get_evidence_list(market_id)


@router.post("/upload", response_model=EvidenceUploadResponse)
def upload_evidence(req: EvidenceUploadRequest):
    """Upload evidence to IPFS and return the CID + bytes32 hash."""
    evidence_data = {
        "version": "1.0",
        "marketId": req.market_id,
        "title": req.title,
        "content": req.content,
        "sourceUrl": req.source_url,
        "direction": req.direction,
    }

    try:
        cid = ipfs_service.pin_json(evidence_data)
        evidence_hash = "0x" + ipfs_service.data_to_bytes32(cid).hex()
        return EvidenceUploadResponse(cid=cid, evidenceHash=evidence_hash)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"IPFS upload failed: {e}")
