"""Incremental evidence aggregator for V2 preprocessed data.

When agents submit V2 evidence (with embeddings and Monte Carlo results),
this module aggregates them using pure math — no LLM calls needed.
Supports incremental updates: adding one evidence item at a time without
reprocessing the entire set.
"""

import logging
import math
import time
from dataclasses import dataclass, field

logger = logging.getLogger("mirofish.aggregator")


# ─── Data Structures ─────────────────────────────────────────────────

@dataclass
class EvidenceDigest:
    """Preprocessed summary of a single V2 evidence item."""
    index: int                          # on-chain evidence index
    direction: str                      # "YES" or "NO"
    confidence: float                   # agent's self-assessed confidence
    mc_mean: float                      # Monte Carlo mean probability
    mc_std: float                       # Monte Carlo std deviation
    ci_95_lower: float = 0.0
    ci_95_upper: float = 1.0
    embedding: list[float] | None = None
    credibility: float = 5.0            # source credibility (1-10), legacy field
    submitter: str = ""                 # on-chain submitter address
    trust_score: float = 1.0            # anti-cheat composite score (replaces credibility in weight calc)
    timestamp: int = 0
    cluster_id: int = -1                # assigned after clustering


@dataclass
class MarketAggregation:
    """Aggregated state for a single market (incrementally maintained)."""
    market_id: int
    digests: list[EvidenceDigest] = field(default_factory=list)
    probability_yes: float = 0.5
    confidence: float = 0.1
    reasoning: str = ""
    cluster_count: int = 0
    agreement_score: float = 0.0        # 0-1, how much evidence agrees
    updated_at: int = 0


# ─── Aggregator ───────────────────────────────────────────────────────

class IncrementalAggregator:
    """Aggregates V2 evidence using cosine-similarity clustering
    and weighted averaging.  Maintains per-market state for incremental
    updates."""

    SIMILARITY_THRESHOLD = 0.85  # cosine similarity above this → same cluster

    def __init__(self) -> None:
        self._states: dict[int, MarketAggregation] = {}

    def get_state(self, market_id: int) -> MarketAggregation | None:
        return self._states.get(market_id)

    def processed_count(self, market_id: int) -> int:
        state = self._states.get(market_id)
        return len(state.digests) if state else 0

    # ─── Public API ───────────────────────────────────────────────

    def add_evidence(self, market_id: int, ipfs_data: dict, index: int, submitter: str = "") -> MarketAggregation:
        """Incrementally add one V2 evidence item and re-aggregate."""
        digest = self._parse_digest(ipfs_data, index, submitter=submitter)
        if digest is None:
            # Not a valid V2 item; return current state unchanged
            state = self._states.get(market_id)
            if state is None:
                state = MarketAggregation(market_id=market_id)
                self._states[market_id] = state
            return state

        state = self._states.get(market_id)
        if state is None:
            state = MarketAggregation(market_id=market_id)
            self._states[market_id] = state

        state.digests.append(digest)
        self._assign_cluster_incremental(state, digest)
        self._recompute(state)
        return state

    def apply_trust_scores(self, market_id: int, scores: dict[int, float]) -> None:
        """Update trust scores on existing digests by evidence index, then recompute."""
        state = self._states.get(market_id)
        if not state:
            return
        changed = False
        for d in state.digests:
            if d.index in scores:
                d.trust_score = scores[d.index]
                changed = True
        if changed:
            self._recompute(state)

    def get_all_embeddings(self, market_id: int) -> list[list[float]]:
        """Return all non-None embeddings for a market (for novelty checks)."""
        state = self._states.get(market_id)
        if not state:
            return []
        return [d.embedding for d in state.digests if d.embedding is not None]

    def rebuild(self, market_id: int, all_ipfs_items: list[dict]) -> MarketAggregation:
        """Full rebuild from scratch (cold start or repair)."""
        state = MarketAggregation(market_id=market_id)

        for i, item in enumerate(all_ipfs_items):
            digest = self._parse_digest(item, i)
            if digest is not None:
                state.digests.append(digest)

        if state.digests:
            self._assign_clusters_full(state)
            self._recompute(state)

        self._states[market_id] = state
        return state

    # ─── Parsing ──────────────────────────────────────────────────

    def _parse_digest(self, ipfs_data: dict, index: int, submitter: str = "") -> EvidenceDigest | None:
        """Parse an IPFS JSON blob into an EvidenceDigest, or None if not V2."""
        version = ipfs_data.get("version", "1.0")
        if version != "2.0":
            return None

        mc = ipfs_data.get("monteCarlo") or {}
        sources = ipfs_data.get("sources") or []
        avg_cred = _avg_credibility(sources)

        return EvidenceDigest(
            index=index,
            direction=ipfs_data.get("direction", "YES").upper(),
            confidence=float(ipfs_data.get("confidence", 0.5)),
            mc_mean=float(mc.get("mean", 0.5)),
            mc_std=float(mc.get("std", 0.15)),
            ci_95_lower=float(mc.get("ci_95_lower", 0.0)),
            ci_95_upper=float(mc.get("ci_95_upper", 1.0)),
            embedding=ipfs_data.get("embedding"),
            credibility=avg_cred,
            submitter=submitter,
            timestamp=int(ipfs_data.get("timestamp", 0)),
        )

    # ─── Clustering ───────────────────────────────────────────────

    def _assign_cluster_incremental(self, state: MarketAggregation, new: EvidenceDigest) -> None:
        """Assign *new* to the nearest existing cluster, or create a new one."""
        if new.embedding is None:
            new.cluster_id = _next_cluster_id(state.digests)
            return

        best_sim = -1.0
        best_cluster = -1
        for d in state.digests:
            if d is new or d.embedding is None:
                continue
            sim = _cosine_similarity(new.embedding, d.embedding)
            if sim > best_sim:
                best_sim = sim
                best_cluster = d.cluster_id

        if best_sim >= self.SIMILARITY_THRESHOLD and best_cluster >= 0:
            new.cluster_id = best_cluster
        else:
            new.cluster_id = _next_cluster_id(state.digests)

    def _assign_clusters_full(self, state: MarketAggregation) -> None:
        """Assign clusters for all digests from scratch (greedy single-link)."""
        next_id = 0
        for i, d in enumerate(state.digests):
            if d.embedding is None:
                d.cluster_id = next_id
                next_id += 1
                continue

            assigned = False
            for j in range(i):
                prev = state.digests[j]
                if prev.embedding is None:
                    continue
                if _cosine_similarity(d.embedding, prev.embedding) >= self.SIMILARITY_THRESHOLD:
                    d.cluster_id = prev.cluster_id
                    assigned = True
                    break

            if not assigned:
                d.cluster_id = next_id
                next_id += 1

    # ─── Aggregation ──────────────────────────────────────────────

    def _recompute(self, state: MarketAggregation) -> None:
        """Recompute probability, confidence, reasoning from digests."""
        if not state.digests:
            state.probability_yes = 0.5
            state.confidence = 0.1
            state.reasoning = "No V2 evidence yet."
            state.cluster_count = 0
            state.agreement_score = 0.0
            state.updated_at = int(time.time())
            return

        # Pick cluster representatives (highest confidence per cluster)
        reps = _cluster_representatives(state.digests)
        state.cluster_count = len(reps)

        now = time.time()
        weighted_sum = 0.0
        total_weight = 0.0

        for d in reps:
            age_days = max(0, (now - d.timestamp) / 86400) if d.timestamp > 0 else 30
            recency = 1.0 / (1.0 + age_days * 0.1)
            w = d.confidence * d.trust_score * recency
            weighted_sum += d.mc_mean * w
            total_weight += w

        if total_weight > 0:
            prob = weighted_sum / total_weight
        else:
            prob = 0.5

        prob = max(0.05, min(0.95, prob))

        # Agreement score: how much cluster reps agree with each other
        agreement = _compute_agreement(reps)
        state.agreement_score = agreement

        # Confidence: f(count, agreement, avg CI spread)
        n = len(reps)
        avg_ci_spread = sum(d.ci_95_upper - d.ci_95_lower for d in reps) / n
        count_factor = min(1.0, n / 10.0)                   # more evidence → higher
        agreement_factor = agreement                          # more agreement → higher
        precision_factor = max(0, 1.0 - avg_ci_spread)       # tighter CIs → higher
        conf = 0.3 * count_factor + 0.4 * agreement_factor + 0.3 * precision_factor
        conf = max(0.1, min(0.95, conf))

        direction = "YES" if prob > 0.5 else "NO" if prob < 0.5 else "neutral"
        state.probability_yes = round(prob, 4)
        state.confidence = round(conf, 2)
        state.reasoning = (
            f"Aggregated {len(state.digests)} V2 evidence items "
            f"({state.cluster_count} unique clusters, agreement={agreement:.0%}). "
            f"Weighted consensus: {direction} at {prob:.0%}."
        )
        state.updated_at = int(time.time())


# ─── Helpers ──────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _avg_credibility(sources: list[dict]) -> float:
    """Average credibility score from sources list, default 5.0."""
    if not sources:
        return 5.0
    scores = [s.get("credibility", 5.0) for s in sources]
    return sum(scores) / len(scores)


def _next_cluster_id(digests: list[EvidenceDigest]) -> int:
    """Return the next unused cluster ID."""
    if not digests:
        return 0
    return max(d.cluster_id for d in digests) + 1


def _cluster_representatives(digests: list[EvidenceDigest]) -> list[EvidenceDigest]:
    """Pick the highest-confidence digest from each cluster."""
    clusters: dict[int, EvidenceDigest] = {}
    for d in digests:
        if d.cluster_id not in clusters or d.confidence > clusters[d.cluster_id].confidence:
            clusters[d.cluster_id] = d
    return list(clusters.values())


def _compute_agreement(reps: list[EvidenceDigest]) -> float:
    """Compute agreement score (0-1) among cluster representatives.

    1.0 = all agree on the same direction.
    0.0 = perfectly split.
    """
    if len(reps) <= 1:
        return 1.0

    yes_count = sum(1 for d in reps if d.direction == "YES")
    no_count = len(reps) - yes_count
    majority = max(yes_count, no_count)
    return majority / len(reps)


# ─── Singleton ────────────────────────────────────────────────────────

aggregator = IncrementalAggregator()
