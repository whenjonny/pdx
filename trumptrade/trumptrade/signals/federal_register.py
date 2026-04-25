"""Federal Register API source. Tracks executive orders / presidential
documents. Slower than WH RSS (1-3 day lag) but authoritative.

Public API: https://www.federalregister.gov/developers/documentation/api/v1
No auth required.
"""
from __future__ import annotations
from datetime import datetime, timezone
from trumptrade.signals.base import SignalSource
from trumptrade.types import Signal


_BASE = "https://www.federalregister.gov/api/v1/documents.json"


class FederalRegisterSource(SignalSource):
    """Polls Federal Register documents.json for the most recent N executive
    orders (presidential_document_type=executive_order). `requests` is lazily
    imported."""

    def __init__(
        self,
        per_page: int = 20,
        document_types: tuple[str, ...] = ("presidential_document",),
        since_signing_date: str | None = None,
    ):
        self.per_page = per_page
        self.document_types = document_types
        self.since_signing_date = since_signing_date
        self._seen: set[str] = set()

    def poll(self) -> list[Signal]:
        try:
            import requests
        except ImportError as e:
            raise ImportError("FederalRegisterSource requires requests. pip install requests") from e

        params = {
            "per_page": self.per_page,
            "order": "newest",
            "conditions[type][]": list(self.document_types),
        }
        if self.since_signing_date:
            params["conditions[signing_date][gte]"] = self.since_signing_date

        try:
            resp = requests.get(_BASE, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        new: list[Signal] = []
        for doc in data.get("results", []):
            doc_id = doc.get("document_number") or doc.get("html_url")
            if not doc_id or doc_id in self._seen:
                continue
            self._seen.add(doc_id)
            ts_raw = doc.get("signing_date") or doc.get("publication_date")
            ts = self._parse_ts(ts_raw)
            text_parts = [doc.get("title", ""), doc.get("abstract", "") or ""]
            new.append(
                Signal(
                    id=str(doc_id),
                    author="federal_register",
                    timestamp=ts,
                    text="\n".join(p for p in text_parts if p),
                    url=doc.get("html_url"),
                    source="federal_register",
                    metadata={
                        "type": doc.get("type"),
                        "document_number": doc.get("document_number"),
                        "executive_order_number": doc.get("executive_order_number"),
                    },
                )
            )
        return new

    @staticmethod
    def _parse_ts(ts_raw: str | None) -> datetime:
        if not ts_raw:
            return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(ts_raw).replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)
