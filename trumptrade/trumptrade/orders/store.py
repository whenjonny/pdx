"""Append-only audit log for orders. Same idiom as PositionStore."""
from __future__ import annotations
import json
from pathlib import Path
from trumptrade.orders.order import Order


class OrderStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._by_id: dict[str, Order] = {}
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
                    o = Order(**json.loads(line))
                    self._by_id[o.id] = o
                except Exception:
                    continue

    def _append(self, order: Order) -> None:
        with open(self.path, "a") as f:
            f.write(order.model_dump_json() + "\n")

    def add(self, order: Order) -> Order:
        if order.id in self._by_id:
            raise ValueError(f"order {order.id} already in store")
        self._by_id[order.id] = order
        self._append(order)
        return order

    def update(self, order: Order) -> None:
        self._by_id[order.id] = order
        self._append(order)

    def get(self, order_id: str) -> Order | None:
        return self._by_id.get(order_id)

    def all(self) -> list[Order]:
        return list(self._by_id.values())

    def by_status(self, status: str) -> list[Order]:
        return [o for o in self._by_id.values() if o.status == status]

    def by_decision(self, decision_id: str) -> list[Order]:
        return [o for o in self._by_id.values() if o.decision_id == decision_id]
