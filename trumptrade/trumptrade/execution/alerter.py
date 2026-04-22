from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from trumptrade.types import Signal, Classification, BasketLeg, Alert


class Alerter:
    def __init__(self, min_confidence: float = 0.55, log_path: Path | None = None):
        self.min_confidence = min_confidence
        self.log_path = log_path

    def maybe_emit(
        self,
        signal: Signal,
        classification: Classification,
        basket: list[BasketLeg],
    ) -> Alert | None:
        eff = classification.confidence * classification.follow_through
        if eff < self.min_confidence:
            print(
                f"[SKIP] {signal.id} | {classification.category}/{classification.sentiment} "
                f"| eff_conf={eff:.2f} < {self.min_confidence}"
            )
            return None

        alert = Alert(
            signal=signal,
            classification=classification,
            basket=basket,
            effective_confidence=eff,
            emitted_at=datetime.now(timezone.utc),
        )
        self._print(alert)
        if self.log_path:
            self._persist(alert)
        return alert

    def _print(self, a: Alert) -> None:
        s, c = a.signal, a.classification
        print("=" * 72)
        print(f"ALERT  {a.emitted_at.isoformat()}")
        print(f"  post   : {s.id}  by {s.author}  @ {s.timestamp.isoformat()}")
        if s.url:
            print(f"  url    : {s.url}")
        print(f"  text   : {s.text[:160]}{'...' if len(s.text) > 160 else ''}")
        print(f"  policy : {c.category} / {c.sentiment}")
        print(f"  confid : classifier={c.confidence:.2f}  follow_through={c.follow_through:.2f}  eff={a.effective_confidence:.2f}")
        print(f"  quote  : \"{c.original_excerpt}\"")
        print(f"  reason : {c.rationale}")
        if a.basket:
            print("  basket :")
            for leg in a.basket:
                print(f"    {leg.side.upper():5s}  {leg.ticker:6s}  w={leg.weight:.3f}   {leg.thesis}")
        else:
            print("  basket : (empty — category has no configured tickers for this sentiment)")
        print("=" * 72)

    def _persist(self, a: Alert) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(a.model_dump_json() + "\n")
