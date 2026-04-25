"""Match a Polymarket market with a Kalshi market that resolves on the
SAME underlying event. Two strategies:

  - rule-based (default): keyword overlap + same closing date window
  - llm-based (optional): Claude semantic match (only if ANTHROPIC_API_KEY set)

The rule-based path is good enough for high-volume Trump markets where titles
share specific names/dates; LLM is better for nuanced rewordings but costs ~$0.01
per pair.
"""
from __future__ import annotations
import re
from datetime import timedelta
from typing import Iterable
from pydantic import BaseModel
from trumptrade.markets.types import MarketRef


_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "by", "or", "and",
    "with", "is", "are", "be", "will", "would", "should", "could", "may",
    "this", "that", "these", "those", "it", "as", "was", "were",
}


class MatchCandidate(BaseModel):
    polymarket: MarketRef
    kalshi: MarketRef
    similarity: float    # 0-1
    method: str          # "rules" | "llm"
    rationale: str


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return {t for t in text.split() if t and t not in _STOPWORDS and len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _close_date_compatible(a: MarketRef, b: MarketRef, window_days: int = 7) -> bool:
    if not a.closes_at or not b.closes_at:
        return True  # missing data: don't penalize
    return abs(a.closes_at - b.closes_at) <= timedelta(days=window_days)


def match_rules(
    polymarket_refs: Iterable[MarketRef],
    kalshi_refs: Iterable[MarketRef],
    min_similarity: float = 0.35,
    close_date_window_days: int = 7,
) -> list[MatchCandidate]:
    """Pair every Polymarket ref with every Kalshi ref by Jaccard token overlap +
    closing-date proximity. Returns sorted descending by similarity."""
    p_list = list(polymarket_refs)
    k_list = list(kalshi_refs)
    out: list[MatchCandidate] = []
    for p in p_list:
        p_tokens = _tokens(p.title + " " + p.description)
        if not p_tokens:
            continue
        for k in k_list:
            if not _close_date_compatible(p, k, close_date_window_days):
                continue
            k_tokens = _tokens(k.title + " " + k.description)
            sim = _jaccard(p_tokens, k_tokens)
            if sim >= min_similarity:
                shared = sorted(p_tokens & k_tokens)
                out.append(MatchCandidate(
                    polymarket=p, kalshi=k, similarity=round(sim, 3),
                    method="rules",
                    rationale=f"Shared keywords: {', '.join(shared[:8])}",
                ))
    out.sort(key=lambda c: c.similarity, reverse=True)
    return out


def match_llm(
    polymarket_refs: Iterable[MarketRef],
    kalshi_refs: Iterable[MarketRef],
    client=None,
    model: str = "claude-haiku-4-5",
    min_similarity: float = 0.7,
) -> list[MatchCandidate]:
    """LLM-assisted match. Uses Haiku for cost (binary same/different judgement
    is simple). Pre-filter with rules to avoid quadratic LLM calls."""
    import anthropic
    client = client or anthropic.Anthropic()

    # First narrow with rules at a low threshold
    candidates = match_rules(polymarket_refs, kalshi_refs, min_similarity=0.2)
    refined: list[MatchCandidate] = []
    for c in candidates:
        prompt = (
            "Two prediction-market questions; do they resolve on the SAME underlying "
            "event? Reply with JSON {\"same\": bool, \"confidence\": 0-1, \"reason\": str}.\n\n"
            f"A (Polymarket): {c.polymarket.title}\n"
            f"B (Kalshi): {c.kalshi.title}\n"
        )
        try:
            r = client.messages.create(
                model=model,
                max_tokens=256,
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "same": {"type": "boolean"},
                                "confidence": {"type": "number"},
                                "reason": {"type": "string"},
                            },
                            "required": ["same", "confidence", "reason"],
                            "additionalProperties": False,
                        },
                    },
                },
                messages=[{"role": "user", "content": prompt}],
            )
            text = next((b.text for b in r.content if b.type == "text"), None)
            if not text:
                continue
            import json
            j = json.loads(text)
            if j["same"] and j["confidence"] >= min_similarity:
                refined.append(MatchCandidate(
                    polymarket=c.polymarket, kalshi=c.kalshi,
                    similarity=float(j["confidence"]),
                    method="llm",
                    rationale=j.get("reason", "")[:200],
                ))
        except Exception:
            continue
    refined.sort(key=lambda c: c.similarity, reverse=True)
    return refined
