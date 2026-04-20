"""Anti-cheat service for MiroFish evidence evaluation.

Computes a composite trust score for each evidence item based on:
  a) Server-side domain credibility (replaces client-provided values)
  b) Per-address weight cap (dampens single-submitter dominance)
  c) Embedding spot-check (server recomputes a sample to verify honesty)
  d) Monte Carlo statistical validation (rejects impossible distributions)
  e) Novelty penalty (reduces credit for redundant/duplicate evidence)
"""

import logging
import math
import random
from dataclasses import dataclass

from app.config import settings
from app.services.domain_whitelist import score_domain

logger = logging.getLogger("anticheat")


# ─── Data Structures ─────────────────────────────────────────────────

@dataclass
class TrustResult:
    """Result of anti-cheat evaluation for a single evidence item."""
    evidence_index: int
    trust_score: float           # composite score (0.0 - 1.0)
    credibility: float           # server-computed domain credibility (0.0 - 1.0)
    address_cap_factor: float    # per-address damping (0.0 - 1.0)
    novelty_factor: float        # originality score (0.05 - 1.0)
    mc_valid: bool
    embedding_verified: bool | None  # None = not spot-checked
    mc_violations: list[str] | None = None


# ─── Monte Carlo Validation ──────────────────────────────────────────

def validate_monte_carlo(mc: dict | None) -> tuple[bool, list[str]]:
    """Run 7 statistical sanity checks on Monte Carlo results.

    Returns (is_valid, list_of_violations).
    """
    if mc is None:
        return True, []

    violations: list[str] = []
    mean = mc.get("mean")
    std = mc.get("std")
    ci_lo = mc.get("ci_95_lower")
    ci_hi = mc.get("ci_95_upper")

    if mean is None or std is None or ci_lo is None or ci_hi is None:
        return False, ["missing required MC fields"]

    mean, std, ci_lo, ci_hi = float(mean), float(std), float(ci_lo), float(ci_hi)

    # 1. Non-degenerate std
    if std <= 0:
        violations.append("std must be positive")

    # 2. Valid CI order
    if ci_lo >= ci_hi:
        violations.append("ci_95_lower must be < ci_95_upper")

    # 3. Valid range
    if ci_lo < 0 or ci_hi > 1:
        violations.append("CI bounds must be in [0, 1]")

    # 4. Valid probability
    if mean <= 0 or mean >= 1:
        violations.append("mean must be in (0, 1)")

    # 5. Plausible spread
    if std > 0.5:
        violations.append("std too large (>0.5)")
    elif std < 0.001 and std > 0:
        violations.append("std suspiciously small (<0.001)")

    # 6. Non-trivial interval
    if ci_hi - ci_lo <= 0.01:
        violations.append("CI interval too narrow (<=0.01)")

    # 7. Mean near CI center
    ci_center = (ci_lo + ci_hi) / 2
    if abs(mean - ci_center) > 0.3:
        violations.append("mean too far from CI center (>0.3)")

    return len(violations) == 0, violations


# ─── Server-side Credibility ─────────────────────────────────────────

def compute_server_credibility(sources: list[dict] | None) -> float:
    """Compute domain-based credibility, normalized to [0, 1].

    Ignores client-provided credibility scores entirely.
    """
    if not sources:
        return 0.3  # no sources = low credibility

    scores: list[float] = []
    for s in sources:
        url = s.get("url") or s.get("sourceUrl") or ""
        if url:
            scores.append(score_domain(url))
        else:
            scores.append(1.0)  # no URL = very low

    avg = sum(scores) / len(scores)
    return min(1.0, avg / 10.0)  # normalize from 1-10 scale to 0-1


# ─── Per-Address Weight Cap ──────────────────────────────────────────

def compute_address_cap(
    submitter: str,
    submitter_counts: dict[str, int],
    total_evidence: int,
) -> float:
    """Compute damping factor for a submitter's evidence.

    If this address has submitted more than max_fraction of total evidence,
    dampen proportionally.
    """
    if total_evidence <= 1:
        return 1.0

    max_frac = settings.anticheat_max_address_fraction
    count = submitter_counts.get(submitter, 0)
    actual_frac = count / total_evidence

    if actual_frac <= max_frac:
        return 1.0

    # Dampen: if you have 50% but cap is 25%, factor = 0.25/0.50 = 0.5
    return max_frac / actual_frac


# ─── Embedding Spot-Check ────────────────────────────────────────────

_embedding_model = None


def _load_embedding_model():
    """Lazily load the sentence-transformer model for spot-checking."""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded embedding model for anti-cheat spot-checking")
        return _embedding_model
    except ImportError:
        logger.warning("sentence-transformers not installed; spot-check disabled")
        return None


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def check_embedding(client_embedding: list[float] | None, content: str) -> bool | None:
    """Spot-check: recompute embedding server-side and compare.

    Returns True (pass), False (fail), or None (not checked).
    """
    if client_embedding is None or not content:
        return None

    # Probabilistic sampling
    if random.random() > settings.anticheat_spot_check_rate:
        return None  # not selected for spot-check

    model = _load_embedding_model()
    if model is None:
        return None  # can't check without model

    try:
        server_emb = model.encode(content).tolist()
        sim = _cosine_sim(client_embedding, server_emb)
        passed = sim >= settings.anticheat_embedding_tolerance
        if not passed:
            logger.warning(
                "Embedding spot-check FAILED: sim=%.3f (threshold=%.2f)",
                sim, settings.anticheat_embedding_tolerance,
            )
        return passed
    except Exception as e:
        logger.error("Embedding spot-check error: %s", e)
        return None


# ─── Novelty Penalty ─────────────────────────────────────────────────

def compute_novelty(
    new_embedding: list[float] | None,
    existing_embeddings: list[list[float]],
) -> float:
    """Compute novelty factor based on similarity to existing evidence.

    First submitter of a fact gets full credit; latecomers get diminished.
    Returns a factor in [0.05, 1.0].
    """
    if new_embedding is None or not existing_embeddings:
        return 1.0  # can't compare = assume novel

    max_sim = 0.0
    for existing in existing_embeddings:
        if existing is None:
            continue
        sim = _cosine_sim(new_embedding, existing)
        if sim > max_sim:
            max_sim = sim

    if max_sim > 0.95:
        return 0.05  # near-duplicate
    elif max_sim > 0.85:
        return 0.2   # mostly redundant
    elif max_sim > 0.70:
        return 0.5   # partial overlap
    else:
        return 1.0   # novel


# ─── Composite Evaluation ────────────────────────────────────────────

def evaluate_evidence(
    evidence_index: int,
    submitter: str,
    ipfs_data: dict,
    submitter_counts: dict[str, int],
    total_evidence: int,
    existing_embeddings: list[list[float]],
) -> TrustResult:
    """Run all anti-cheat checks and produce a composite trust score.

    The trust score completely replaces client-provided credibility in the
    aggregator's weight calculation.
    """
    if not settings.anticheat_enabled:
        return TrustResult(
            evidence_index=evidence_index,
            trust_score=1.0,
            credibility=1.0,
            address_cap_factor=1.0,
            novelty_factor=1.0,
            mc_valid=True,
            embedding_verified=None,
        )

    # a) Server-side credibility
    sources = ipfs_data.get("sources") or []
    credibility = compute_server_credibility(sources)

    # b) Per-address cap
    cap_factor = compute_address_cap(submitter, submitter_counts, total_evidence)

    # c) Embedding spot-check
    content = ipfs_data.get("content", "")
    client_embedding = ipfs_data.get("embedding")
    emb_check = check_embedding(client_embedding, content)
    emb_factor = 0.1 if emb_check is False else 1.0

    # d) Monte Carlo validation
    mc_data = ipfs_data.get("monteCarlo")
    mc_valid, mc_violations = validate_monte_carlo(mc_data)
    mc_factor = 1.0 if mc_valid else 0.3

    # e) Novelty penalty
    novelty = compute_novelty(client_embedding, existing_embeddings)

    # Composite
    trust = credibility * cap_factor * mc_factor * emb_factor * novelty
    trust = max(0.01, min(1.0, trust))

    logger.debug(
        "Evidence #%d trust=%.3f (cred=%.2f cap=%.2f mc=%s emb=%s novelty=%.2f)",
        evidence_index, trust, credibility, cap_factor,
        mc_valid, emb_check, novelty,
    )

    return TrustResult(
        evidence_index=evidence_index,
        trust_score=trust,
        credibility=credibility,
        address_cap_factor=cap_factor,
        novelty_factor=novelty,
        mc_valid=mc_valid,
        embedding_verified=emb_check,
        mc_violations=mc_violations if mc_violations else None,
    )
