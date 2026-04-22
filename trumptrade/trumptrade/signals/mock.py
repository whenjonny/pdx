from __future__ import annotations
import json
from pathlib import Path
from trumptrade.signals.base import SignalSource
from trumptrade.types import Signal


class MockFileSource(SignalSource):
    """Reads signals from a JSON file. Each call to poll() returns all signals
    that haven't been returned before (tracked by id)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._seen: set[str] = set()

    def poll(self) -> list[Signal]:
        if not self.path.exists():
            return []
        with open(self.path) as f:
            raw = json.load(f)
        new: list[Signal] = []
        for item in raw:
            sig = Signal(**item)
            if sig.id in self._seen:
                continue
            self._seen.add(sig.id)
            new.append(sig)
        return new
