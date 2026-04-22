"""Deterministic, LLM-free classifier. Uses playbook keywords + simple sentiment
heuristics. Useful for:
- Demo without ANTHROPIC_API_KEY
- CI tests (fast, no network)
- Baseline to compare LLM output against
"""
from __future__ import annotations
from trumptrade.types import Signal, Classification


_HAWKISH_TRIGGERS = {
    "tariff", "impose", "ban", "sanction", "executive order", "eo ",
    "signed", "effective", "crack down", "drill", "open up", "repeal",
    "breakup", "investigate", "penalty", "strategic reserve",
    "most favored nation", "mfn", "price cut", "deportation", "border",
    "aid package", "defense budget", "rolling back", "deregulation",
    "antitrust", "monopol", "section 230", "breakup", "breakup",
    "expanding", "increasing", "strengthening", "approved", "approving",
    "ice", "expedite", "clear the regulatory", "drill baby",
}

_DOVISH_TRIGGERS = {
    "pause", "delay", "reverse", "walk back", "deal", "agreement",
    "cooperation", "lift", "ease", "restart negotiations", "compromise",
    "suspending", "suspend", "revocation review", "more careful",
    "productive talks", "may pause", "fair deal",
}


def _score_category(text: str, category_cfg: dict) -> float:
    """Score 0-1. Reward raw hits, but cap at 1.0. A single keyword hit = 0.35;
    two = 0.60; three = 0.80; four+ = 0.95."""
    text_lower = text.lower()
    keywords = category_cfg.get("keywords") or []
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    if hits == 0:
        return 0.0
    scale = {1: 0.35, 2: 0.60, 3: 0.80}
    return scale.get(hits, 0.95)


def _detect_sentiment(text: str) -> str:
    t = text.lower()
    hawk = sum(1 for k in _HAWKISH_TRIGGERS if k in t)
    dove = sum(1 for k in _DOVISH_TRIGGERS if k in t)
    if hawk > dove and hawk >= 1:
        return "hawkish"
    if dove > hawk and dove >= 1:
        return "dovish"
    return "neutral"


def _estimate_follow_through(text: str, priors: dict) -> float:
    t = text.lower()
    # High: explicit action in progress or done
    if any(k in t for k in [
        "signed", "executive order", "effective ", "today i have",
        "rolling back", "approving", "approved", "opening up",
        "expanding", "strengthening", "increasing", "expedite",
        "suspending", "repeal ", "ending the",
    ]):
        return priors.get("executive_order_promise_to_signature_30d", 0.70)
    # Medium: tariff/sanction threat
    if any(k in t for k in ["tariff", "impose", "investigate", "antitrust", "ban "]):
        return priors.get("tariff_threat_to_imposition_90d", 0.45)
    # Low: rhetoric / promise without channel
    return priors.get("tweet_only_no_official_channel_30d", 0.20)


def fake_classify(signal: Signal, playbook: dict) -> Classification:
    categories = playbook.get("categories", {})
    priors = playbook.get("follow_through_priors", {})

    scored = [(name, _score_category(signal.text, cfg)) for name, cfg in categories.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    best_name, best_score = scored[0] if scored else ("unknown", 0.0)

    if best_score == 0.0:
        return Classification(
            category="unknown",
            sentiment="neutral",
            follow_through=0.0,
            rationale="fake-classifier: no playbook keywords matched",
            confidence=0.0,
            original_excerpt=signal.text[:200],
        )

    sentiment = _detect_sentiment(signal.text)
    if sentiment == "neutral":
        classifier_confidence = min(0.40, best_score)
    else:
        # hawkish/dovish signal + keyword match -> high confidence
        classifier_confidence = min(0.90, 0.40 + best_score)

    ft = _estimate_follow_through(signal.text, priors)

    first_sentence = signal.text.split(".")[0][:200]

    return Classification(
        category=best_name,
        sentiment=sentiment,
        follow_through=ft,
        rationale=(
            f"fake-classifier: matched category '{best_name}' (keyword density {best_score:.2f}), "
            f"sentiment '{sentiment}' by trigger words"
        ),
        confidence=round(classifier_confidence, 2),
        original_excerpt=first_sentence,
    )
