"""SQLite persistence for off-chain metadata.

Stores data that is NOT on the blockchain but needed across restarts:
- Market metadata (category, resolution source)
- IPFS CID registry (bytes32 hash → CID mapping)
- IPFS mock store (CID → evidence JSON, for local dev without Pinata)
- MiroFish prediction cache
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path

from app.config import settings

logger = logging.getLogger("database")

_DB_PATH = Path(settings.db_path)
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(_DB_PATH))
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.row_factory = sqlite3.Row
    return _local.conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS market_metadata (
            market_id   INTEGER PRIMARY KEY,
            category    TEXT NOT NULL DEFAULT 'general',
            resolution_source TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS cid_registry (
            bytes32_hex TEXT PRIMARY KEY,
            cid         TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mock_store (
            cid  TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prediction_cache (
            market_id       INTEGER PRIMARY KEY,
            probability_yes REAL NOT NULL,
            probability_no  REAL NOT NULL,
            confidence      REAL NOT NULL,
            reasoning       TEXT NOT NULL DEFAULT '',
            source          TEXT NOT NULL DEFAULT '',
            updated_at      INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()
    logger.info("Database initialized at %s", _DB_PATH)


# ── Market Metadata ──

def get_market_category(market_id: int) -> str:
    row = _get_conn().execute(
        "SELECT category FROM market_metadata WHERE market_id = ?", (market_id,)
    ).fetchone()
    return row["category"] if row else "general"


def get_market_resolution_source(market_id: int) -> str:
    row = _get_conn().execute(
        "SELECT resolution_source FROM market_metadata WHERE market_id = ?", (market_id,)
    ).fetchone()
    return row["resolution_source"] if row else ""


def set_market_metadata(market_id: int, category: str, resolution_source: str):
    conn = _get_conn()
    conn.execute(
        """INSERT INTO market_metadata (market_id, category, resolution_source)
           VALUES (?, ?, ?)
           ON CONFLICT(market_id) DO UPDATE SET
             category = excluded.category,
             resolution_source = excluded.resolution_source""",
        (market_id, category or "general", resolution_source or ""),
    )
    conn.commit()


# ── CID Registry ──

def get_cid(bytes32_hex: str) -> str | None:
    row = _get_conn().execute(
        "SELECT cid FROM cid_registry WHERE bytes32_hex = ?", (bytes32_hex,)
    ).fetchone()
    return row["cid"] if row else None


def set_cid(bytes32_hex: str, cid: str):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO cid_registry (bytes32_hex, cid) VALUES (?, ?)",
        (bytes32_hex, cid),
    )
    conn.commit()


# ── Mock Store ──

def get_mock_data(cid: str) -> dict | None:
    row = _get_conn().execute(
        "SELECT data FROM mock_store WHERE cid = ?", (cid,)
    ).fetchone()
    return json.loads(row["data"]) if row else None


def set_mock_data(cid: str, data: dict):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO mock_store (cid, data) VALUES (?, ?)",
        (cid, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()


# ── Prediction Cache ──

def get_prediction(market_id: int) -> dict | None:
    row = _get_conn().execute(
        "SELECT * FROM prediction_cache WHERE market_id = ?", (market_id,)
    ).fetchone()
    if not row:
        return None
    return {
        "market_id": row["market_id"],
        "probability_yes": row["probability_yes"],
        "probability_no": row["probability_no"],
        "confidence": row["confidence"],
        "reasoning": row["reasoning"],
        "source": row["source"],
        "updated_at": row["updated_at"],
    }


def set_prediction(market_id: int, probability_yes: float, probability_no: float,
                   confidence: float, reasoning: str, source: str, updated_at: int):
    conn = _get_conn()
    conn.execute(
        """INSERT INTO prediction_cache
           (market_id, probability_yes, probability_no, confidence, reasoning, source, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(market_id) DO UPDATE SET
             probability_yes = excluded.probability_yes,
             probability_no = excluded.probability_no,
             confidence = excluded.confidence,
             reasoning = excluded.reasoning,
             source = excluded.source,
             updated_at = excluded.updated_at""",
        (market_id, probability_yes, probability_no, confidence, reasoning, source, updated_at),
    )
    conn.commit()
