from __future__ import annotations
from trumptrade.types import Classification, BasketLeg


def expand_basket(classification: Classification, playbook: dict) -> list[BasketLeg]:
    if classification.category == "unknown":
        return []
    cat = playbook.get("categories", {}).get(classification.category)
    if not cat:
        return []

    sent = classification.sentiment
    long_key = f"{sent}_long"
    short_key = f"{sent}_short"

    scale = classification.confidence * classification.follow_through

    legs: list[BasketLeg] = []
    for leg in cat.get(long_key, []) or []:
        legs.append(
            BasketLeg(
                ticker=leg["ticker"],
                side="long",
                weight=round(leg["weight"] * scale, 4),
                thesis=leg.get("thesis", ""),
            )
        )
    for leg in cat.get(short_key, []) or []:
        legs.append(
            BasketLeg(
                ticker=leg["ticker"],
                side="short",
                weight=round(leg["weight"] * scale, 4),
                thesis=leg.get("thesis", ""),
            )
        )
    return legs
