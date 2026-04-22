"""Walk-back detector.

Trump frequently announces bold policy then softens within 48h. If a new signal
hits the same category with OPPOSITE sentiment, emit close instructions for the
earlier basket.
"""
from __future__ import annotations
from datetime import timedelta
from pathlib import Path
import json
from trumptrade.types import Alert, BasketLeg


_OPPOSITE = {"hawkish": "dovish", "dovish": "hawkish"}


class WalkbackDetector:
    def __init__(self, window_hours: int = 48):
        self.window = timedelta(hours=window_hours)
        self._recent: list[Alert] = []

    def feed(self, alert: Alert) -> list[tuple[Alert, list[BasketLeg]]]:
        """Add a new alert. If it walks back any recent alert, return the list of
        (original_alert, close_legs) pairs. close_legs are the reverse of the
        original basket (long -> short close, short -> long close) — i.e. orders
        that flatten the prior position."""
        closures: list[tuple[Alert, list[BasketLeg]]] = []
        now = alert.emitted_at
        opp = _OPPOSITE.get(alert.classification.sentiment)
        cat = alert.classification.category

        # prune old
        self._recent = [a for a in self._recent if now - a.emitted_at <= self.window]

        if opp and cat != "unknown":
            for prior in self._recent:
                pc = prior.classification
                if pc.category == cat and pc.sentiment == opp:
                    closures.append((prior, self._invert(prior.basket)))

        self._recent.append(alert)
        return closures

    @staticmethod
    def _invert(basket: list[BasketLeg]) -> list[BasketLeg]:
        return [
            BasketLeg(
                ticker=leg.ticker,
                side="short" if leg.side == "long" else "long",
                weight=leg.weight,
                thesis=f"walk-back close of prior {leg.side} {leg.ticker}",
            )
            for leg in basket
        ]

    @classmethod
    def load_recent(cls, jsonl_path: Path, window_hours: int = 48) -> "WalkbackDetector":
        """Bootstrap state from existing alerts.jsonl."""
        det = cls(window_hours=window_hours)
        if not jsonl_path.exists():
            return det
        with open(jsonl_path) as f:
            for line in f:
                if line.strip():
                    det._recent.append(Alert(**json.loads(line)))
        return det
