"""Evidence formatting and IPFS upload helpers.

Supports both V1 (raw text) and V2 (preprocessed embedding + Monte Carlo)
evidence formats.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict
from typing import Optional

import requests

from pdx_sdk.config import DEFAULT_BACKEND_URL

logger = logging.getLogger(__name__)


# ─── V1 Format ───────────────────────────────────────────────────────

def format_evidence(
    market_id: int,
    direction: str,
    confidence: float,
    sources: list[str],
    analysis: str,
    generated_by: str = "pdx-agent",
) -> dict:
    """Build a V1 evidence JSON payload matching the PDX spec.

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


# ─── V2 Format (with preprocessed data) ──────────────────────────────

def format_evidence_v2(
    market_id: int,
    direction: str,
    text: str,
    sources: list[dict],
    analysis: str,
    prior_yes: float = 0.5,
    evidence_score: float = 0.0,
    generated_by: str = "pdx-agent",
) -> dict:
    """Build a V2 evidence payload with auto-computed embedding and Monte Carlo.

    This is the recommended way for agents to submit evidence.  It runs
    local compute (embedding + Monte Carlo simulation) and packages the
    results into a single payload that the MiroFish aggregator can
    consume without calling an LLM.

    Parameters
    ----------
    market_id : int
        The on-chain market ID.
    direction : str
        ``"YES"`` or ``"NO"``.
    text : str
        The evidence text to embed and analyze.
    sources : list[dict]
        Source metadata: ``[{"url": "...", "title": "...", "credibility": 8.5}]``.
    analysis : str
        Structured analysis text.
    prior_yes : float
        Prior probability of YES (e.g. current AMM price).
    evidence_score : float
        Evidence direction score in ``[-1, 1]``.  Positive = supports YES.
    generated_by : str
        Agent identifier.

    Returns
    -------
    dict
        V2 evidence payload ready for IPFS upload via :func:`upload_to_ipfs_v2`.
    """
    from pdx_sdk.compute import compute_embedding, run_monte_carlo

    embedding = compute_embedding(text)

    scores = [evidence_score] if evidence_score != 0.0 else None
    mc = run_monte_carlo(prior_yes, evidence_scores=scores)

    return {
        "version": "2.0",
        "marketId": market_id,
        "direction": direction.upper(),
        "confidence": round(abs(evidence_score) if evidence_score != 0.0 else 0.5, 4),
        "embedding": embedding,
        "monteCarlo": {
            "mean": round(mc.mean, 4),
            "std": round(mc.std, 4),
            "ci_95_lower": round(mc.ci_95_lower, 4),
            "ci_95_upper": round(mc.ci_95_upper, 4),
            "n_simulations": mc.n_simulations,
        },
        "sources": sources,
        "structuredAnalysis": {
            "claim": analysis,
            "supporting_points": [],
            "counter_points": [],
            "net_sentiment": evidence_score,
        },
        "generatedBy": generated_by,
        "timestamp": int(time.time()),
    }


# ─── Upload Helpers ───────────────────────────────────────────────────

def upload_to_ipfs(
    evidence_data: dict,
    backend_url: str = DEFAULT_BACKEND_URL,
) -> str:
    """Upload V1 evidence JSON to the PDX backend which pins it to IPFS.

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


def upload_to_ipfs_v2(
    evidence_data: dict,
    backend_url: str = DEFAULT_BACKEND_URL,
) -> str:
    """Upload V2 evidence (with embedding/MC) to the PDX backend.

    Parameters
    ----------
    evidence_data : dict
        The V2 evidence payload from :func:`format_evidence_v2`.
    backend_url : str
        Base URL of the PDX backend API.

    Returns
    -------
    str
        The IPFS CID returned by the backend.
    """
    url = f"{backend_url.rstrip('/')}/api/evidence/upload/v2"
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
