"""Decision audit log: every TradeDecision an agent ever produced."""
from __future__ import annotations
import json
from pathlib import Path
from trumptrade.agents.base import TradeDecision


class DecisionStore:
    """Append-only jsonl log of every TradeDecision. Independent from the
    OrderStore — a decision may be rejected by risk and never become an order,
    but we still want it logged for post-hoc analysis."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, decision: TradeDecision) -> None:
        with open(self.path, "a") as f:
            f.write(decision.model_dump_json() + "\n")

    def record_many(self, decisions: list[TradeDecision]) -> None:
        for d in decisions:
            self.record(d)

    def all(self) -> list[TradeDecision]:
        if not self.path.exists():
            return []
        out: list[TradeDecision] = []
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                out.append(TradeDecision(**json.loads(line)))
            except Exception:
                continue
        return out


__all__ = ["DecisionStore"]
