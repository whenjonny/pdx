from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    EvidenceResponse,
    EvidenceUploadRequest,
    EvidenceUploadRequestV2,
    EvidenceUploadResponse,
)
from app.services.blockchain import blockchain_service
from app.services.ipfs import ipfs_service
from app.services.anticheat import validate_monte_carlo

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

EMBEDDING_DIM = 384
MC_REQUIRED_KEYS = {"mean", "std", "ci_95_lower", "ci_95_upper"}


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


@router.post("/upload/v2", response_model=EvidenceUploadResponse)
def upload_evidence_v2(req: EvidenceUploadRequestV2):
    """Upload V2 evidence (with preprocessed embedding/MC data) to IPFS."""
    # Validate embedding dimension
    if req.embedding is not None and len(req.embedding) != EMBEDDING_DIM:
        raise HTTPException(
            status_code=422,
            detail=f"embedding must be {EMBEDDING_DIM}-dimensional, got {len(req.embedding)}",
        )
    # Validate monte_carlo keys
    if req.monte_carlo is not None:
        missing = MC_REQUIRED_KEYS - set(req.monte_carlo.keys())
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"monte_carlo missing required keys: {missing}",
            )
    # Validate direction
    if req.direction.upper() not in ("YES", "NO"):
        raise HTTPException(status_code=422, detail="direction must be YES or NO")

    # Anti-cheat: validate Monte Carlo data at upload time
    if req.monte_carlo is not None:
        mc_valid, mc_violations = validate_monte_carlo(req.monte_carlo)
        if not mc_valid:
            raise HTTPException(
                status_code=422,
                detail=f"Monte Carlo validation failed: {'; '.join(mc_violations)}",
            )

    evidence_data = {
        "version": "2.0",
        "marketId": req.market_id,
        "title": req.title,
        "content": req.content,
        "sourceUrl": req.source_url,
        "direction": req.direction.upper(),
        "confidence": req.confidence,
        "generatedBy": req.generated_by,
    }
    if req.embedding is not None:
        evidence_data["embedding"] = req.embedding
    if req.monte_carlo is not None:
        evidence_data["monteCarlo"] = req.monte_carlo
    if req.sources is not None:
        # Strip client-provided credibility; server will compute its own
        sanitized_sources = []
        for s in req.sources:
            sanitized = {k: v for k, v in s.items() if k != "credibility"}
            sanitized["credibility_source"] = "server"  # marker
            sanitized_sources.append(sanitized)
        evidence_data["sources"] = sanitized_sources
    if req.structured_analysis is not None:
        evidence_data["structuredAnalysis"] = req.structured_analysis

    try:
        cid = ipfs_service.pin_json(evidence_data)
        evidence_hash = "0x" + ipfs_service.data_to_bytes32(cid).hex()
        return EvidenceUploadResponse(cid=cid, evidenceHash=evidence_hash)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"IPFS upload failed: {e}")


@router.get("/{market_id}/{evidence_index}/content")
def get_evidence_content(market_id: int, evidence_index: int):
    """Fetch full evidence content from IPFS."""
    evidence_list = blockchain_service.get_evidence_list(market_id)
    if evidence_index < 0 or evidence_index >= len(evidence_list):
        raise HTTPException(status_code=404, detail="Evidence not found")

    ev = evidence_list[evidence_index]
    content = ipfs_service.fetch_by_hash(ev.ipfsHash)
    if content is None:
        raise HTTPException(status_code=404, detail="IPFS content not available")

    return content
