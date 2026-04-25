"""Portfolio-wide risk limits. Layered above per-trade `playbook.risk_gates`.

Defaults are conservative — tune in `config/risk_limits.yaml` once you've
walked through alert mode.
"""
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
import yaml


class RiskLimits(BaseModel):
    # Account-level
    account_value_usd: float = 10_000.0           # for now, manual; later hook to broker
    max_total_exposure_pct: float = Field(default=0.30, ge=0.0, le=1.0)

    # Per-venue caps
    max_per_venue_pct: float = Field(default=0.15, ge=0.0, le=1.0)

    # Per-policy-category caps (from playbook)
    max_per_category_pct: float = Field(default=0.10, ge=0.0, le=1.0)

    # Per-event caps (in case category has many sub-events)
    max_per_event_pct: float = Field(default=0.05, ge=0.0, le=1.0)

    # Per-position caps
    max_per_position_pct: float = Field(default=0.03, ge=0.0, le=1.0)

    # Daily P&L throttle: stop new opens after N% drawdown today
    daily_loss_circuit_breaker_pct: float = Field(default=0.05, ge=0.0, le=1.0)

    # Open-position counters
    max_open_positions: int = 50
    max_open_per_venue: int = 25

    # Concentration: max consecutive same-direction signals in same category
    max_directional_streak_per_category: int = 5

    # Min remaining liquidity (24h volume) before opening new
    min_market_volume_24h: float = 1000.0

    # Min cushion for arb edge (after fees) to size into
    arb_min_edge: float = 0.005


def load_risk_limits(path: Path | str | None) -> RiskLimits:
    if path is None:
        return RiskLimits()
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return RiskLimits(**data)
