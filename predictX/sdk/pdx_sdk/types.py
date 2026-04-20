"""Data types for PDX SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Market:
    """On-chain prediction market state."""

    id: int
    question: str
    reserveYes: int
    reserveNo: int
    k: int
    deadline: int
    lockTime: int
    totalDeposited: int
    feesAccrued: int
    resolved: bool
    outcome: bool
    creator: str
    yesToken: str
    noToken: str
    priceYes: int
    priceNo: int


@dataclass
class Evidence:
    """Evidence record attached to a market."""

    submitter: str
    ipfsHash: str
    summary: str
    timestamp: int


@dataclass
class TradeResult:
    """Result of a write transaction (trade, evidence, redeem)."""

    tx_hash: str
    tokens_amount: int = 0
    fee: int = 0
    gas_used: int = 0


@dataclass
class Prediction:
    """Agent prediction for a market outcome."""

    probability: float
    confidence: float
    reasoning: str
    lastUpdated: Optional[str] = None


@dataclass
class MonteCarloResult:
    """Result of a Monte Carlo simulation."""

    mean: float
    std: float
    ci_95_lower: float
    ci_95_upper: float
    n_simulations: int
