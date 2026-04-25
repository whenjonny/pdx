"""Append-only log of every signal observed. Used for replay and post-hoc
attribution (which signal triggered which decision/order/position)."""
from __future__ import annotations
import json
from pathlib import Path
from trumptrade.types import Signal


class SignalLog:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, source_name: str, signal: Signal) -> None:
        entry = {
            "source": source_name,
            "signal": signal.model_dump(mode="json"),
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def record_many(self, source_name: str, signals: list[Signal]) -> None:
        for s in signals:
            self.record(source_name, s)

    def tail(self, n: int = 50) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()
        out = []
        for line in lines[-n:]:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
