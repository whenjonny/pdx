"""Append-only jsonl persistence for positions. Idempotent open() / close().

The store keeps an in-memory index AND writes every state change to disk so
crashes don't lose state. On load, the LATEST entry per position id wins.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from trumptrade.monitor.position import OpenPosition


class PositionStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._by_id: dict[str, OpenPosition] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    p = OpenPosition(**data)
                    self._by_id[p.id] = p
                except Exception:
                    continue

    def _append(self, position: OpenPosition) -> None:
        with open(self.path, "a") as f:
            f.write(position.model_dump_json() + "\n")

    # --- public API ---------------------------------------------------------

    def open(self, position: OpenPosition) -> OpenPosition:
        if position.id in self._by_id:
            raise ValueError(f"position {position.id} already exists")
        self._by_id[position.id] = position
        self._append(position)
        return position

    def update(self, position: OpenPosition) -> None:
        self._by_id[position.id] = position
        self._append(position)

    def get(self, position_id: str) -> OpenPosition | None:
        return self._by_id.get(position_id)

    def all(self) -> list[OpenPosition]:
        return list(self._by_id.values())

    def open_positions(self) -> list[OpenPosition]:
        return [p for p in self._by_id.values() if p.status == "open"]

    def closed_positions(self) -> list[OpenPosition]:
        return [p for p in self._by_id.values() if p.status == "closed"]

    def close(self, position_id: str, exit_price: float, reason, at: datetime | None = None) -> OpenPosition:
        from datetime import timezone
        p = self._by_id.get(position_id)
        if p is None:
            raise KeyError(position_id)
        if p.status == "closed":
            return p
        p.mark_closed(exit_price=exit_price, reason=reason, at=at or datetime.now(timezone.utc))
        self._append(p)
        return p
