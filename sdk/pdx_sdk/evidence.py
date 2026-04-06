"""Evidence formatting and IPFS upload helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

import requests

from pdx_sdk.config import DEFAULT_BACKEND_URL

logger = logging.getLogger(__name__)


def format_evidence(
    market_id: int,
    direction: str,
    confidence: float,
    sources: list[str],
    analysis: str,
    generated_by: str = "pdx-agent",
) -> dict:
    """Build a structured evidence JSON payload matching the PDX spec.

    Parameters
    ----------
    market_id : int
        The on-chain market ID this evidence relates to.
    direction : str
        ``"YES"`` or ``"NO"`` -- the direction the evidence supports.
    confidence : float
        Confidence score in ``[0, 1]``.
    sources : list[str]
        List of source URLs or references.
    analysis : str
        Free-text analysis / reasoning.
    generated_by : str
        Identifier for the agent that produced this evidence.

    Returns
    -------
    dict
        Structured evidence payload ready for IPFS upload.
    """
    return {
        "version": "1.0",
        "marketId": market_id,
        "direction": direction.upper(),
        "confidence": round(confidence, 4),
        "sources": sources,
        "analysis": analysis,
        "generatedBy": generated_by,
        "timestamp": int(time.time()),
    }


def upload_to_ipfs(
    evidence_data: dict,
    backend_url: str = DEFAULT_BACKEND_URL,
) -> str:
    """Upload evidence JSON to the PDX backend which pins it to IPFS.

    Parameters
    ----------
    evidence_data : dict
        The evidence payload (typically from :func:`format_evidence`).
    backend_url : str
        Base URL of the PDX backend API.

    Returns
    -------
    str
        The IPFS CID (content identifier) returned by the backend.

    Raises
    ------
    requests.HTTPError
        If the backend returns a non-2xx status.
    """
    url = f"{backend_url.rstrip('/')}/api/evidence/upload"
    response = requests.post(
        url,
        json=evidence_data,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("cid") or data.get("ipfsHash") or data.get("hash", "")


def mock_upload(evidence_data: dict) -> str:
    """Return a deterministic fake CID derived from the evidence content.

    Useful for local testing without a running backend / IPFS node.
    """
    raw = json.dumps(evidence_data, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()
    # Return a hex string that fits in bytes32 (64 hex chars).
    return digest[:64]
