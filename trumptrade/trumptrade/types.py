from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Signal(BaseModel):
    id: str
    author: str
    timestamp: datetime
    text: str
    url: Optional[str] = None
    source: str = "unknown"
    metadata: dict = Field(default_factory=dict)


class Classification(BaseModel):
    category: str
    sentiment: Literal["hawkish", "dovish", "neutral"]
    follow_through: float = Field(ge=0.0, le=1.0)
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    original_excerpt: str


class BasketLeg(BaseModel):
    ticker: str
    side: Literal["long", "short"]
    weight: float
    thesis: str


class Alert(BaseModel):
    signal: Signal
    classification: Classification
    basket: list[BasketLeg]
    effective_confidence: float
    emitted_at: datetime
