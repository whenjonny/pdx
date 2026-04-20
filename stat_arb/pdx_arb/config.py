"""Configuration for the cross-venue arbitrage system."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class PolymarketConfig:
    gamma_url: str = "https://gamma-api.polymarket.com"
    clob_url: str = "https://clob.polymarket.com"
    fee_bps_maker: float = 0.0
    fee_bps_taker: float = 100.0
    poll_interval_s: float = 5.0

    @classmethod
    def from_env(cls) -> PolymarketConfig:
        return cls(
            gamma_url=os.getenv("POLY_GAMMA_URL", cls.gamma_url),
            clob_url=os.getenv("POLY_CLOB_URL", cls.clob_url),
        )


@dataclass
class PredictXConfig:
    rpc_url: str = "http://localhost:8545"
    backend_url: str = "http://localhost:8000"
    market_address: str = ""
    usdc_address: str = ""
    private_key: str = ""
    fee_bps_normal: float = 30.0
    fee_bps_evidence: float = 10.0
    poll_interval_s: float = 2.0

    @classmethod
    def from_env(cls) -> PredictXConfig:
        return cls(
            rpc_url=os.getenv("PDX_RPC_URL", cls.rpc_url),
            backend_url=os.getenv("PDX_BACKEND_URL", cls.backend_url),
            market_address=os.getenv("PDX_MARKET_ADDRESS", ""),
            usdc_address=os.getenv("PDX_USDC_ADDRESS", ""),
            private_key=os.getenv("PDX_PRIVATE_KEY", ""),
        )


@dataclass
class ArbConfig:
    min_net_spread_bps: float = 150.0
    max_position_usd: float = 5_000.0
    max_total_exposure_usd: float = 50_000.0
    max_positions: int = 20
    max_per_market_usd: float = 10_000.0
    kelly_fraction: float = 0.25
    cooldown_s: float = 30.0
    settlement_risk_bps: float = 50.0
    slippage_bps: float = 30.0
    max_drawdown_pct: float = 15.0
    daily_loss_limit_usd: float = 5_000.0
    scan_interval_s: float = 10.0

    # Leg failure hedging
    hedge_retry_slippage_bps: float = 100.0
    max_naked_exposure_usd: float = 5_000.0

    # Volume / liquidity sizing
    min_market_volume_usd: float = 10_000.0
    liquidity_scale_factor: float = 0.1
    thin_market_size_cap_usd: float = 500.0

    # Kelly criterion
    kelly_win_prob_base: float = 0.95
    kelly_friction_haircut: float = 0.10

    # Adverse selection
    adverse_lookback: int = 20
    adverse_toxicity_threshold: float = 0.4
    adverse_blacklist_duration_s: float = 3600.0

    polymarket: PolymarketConfig = None  # type: ignore[assignment]
    predictx: PredictXConfig = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.polymarket is None:
            self.polymarket = PolymarketConfig()
        if self.predictx is None:
            self.predictx = PredictXConfig()

    @classmethod
    def from_env(cls) -> ArbConfig:
        return cls(
            min_net_spread_bps=float(os.getenv("ARB_MIN_SPREAD_BPS", "150")),
            max_position_usd=float(os.getenv("ARB_MAX_POSITION_USD", "5000")),
            max_total_exposure_usd=float(os.getenv("ARB_MAX_EXPOSURE_USD", "50000")),
            kelly_fraction=float(os.getenv("ARB_KELLY_FRACTION", "0.25")),
            polymarket=PolymarketConfig.from_env(),
            predictx=PredictXConfig.from_env(),
        )
