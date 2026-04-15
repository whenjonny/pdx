"""Constant-product market-maker simulator.

Mirrors the pricing math of ``contracts/src/PDXMarket.sol``:

    reserveYes * reserveNo = k
    priceYes = reserveNo / (reserveYes + reserveNo)

Fee tiers follow the same 0.30% / 0.10% schedule used on-chain,
with an optional evidence-discount flag passed per trade.

All USDC amounts are expressed as floats for simulation
convenience; the on-chain implementation uses 6-decimal integers,
but the arithmetic is identical.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FeeSchedule:
    """Proportional fee schedule in basis-points of 10_000."""

    normal_bps: int = 30      # 0.30% matches FEE_NORMAL
    evidence_bps: int = 10    # 0.10% matches FEE_WITH_EVIDENCE

    def rate(self, has_evidence: bool) -> float:
        bps = self.evidence_bps if has_evidence else self.normal_bps
        return bps / 10_000.0


class CPMM:
    """Binary prediction-market AMM.

    Initial pool is seeded 50/50 — identical to PDXMarket's
    ``createMarket`` behaviour where each side mints
    ``initialLiquidity / 2`` tokens.
    """

    def __init__(self, initial_liquidity: float, fees: FeeSchedule | None = None) -> None:
        if initial_liquidity <= 0:
            raise ValueError("initial_liquidity must be positive")
        half = initial_liquidity / 2.0
        self.reserve_yes: float = half
        self.reserve_no: float = half
        self.k: float = half * half
        self.fees: FeeSchedule = fees or FeeSchedule()
        self.fees_accrued: float = 0.0
        self.total_deposited: float = initial_liquidity

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------
    @property
    def price_yes(self) -> float:
        return self.reserve_no / (self.reserve_yes + self.reserve_no)

    @property
    def price_no(self) -> float:
        return self.reserve_yes / (self.reserve_yes + self.reserve_no)

    # ------------------------------------------------------------------
    # Trading
    # ------------------------------------------------------------------
    def buy(self, usdc_amount: float, is_yes: bool, has_evidence: bool = False) -> float:
        """Buy YES or NO and return tokens minted to the caller."""
        if usdc_amount <= 0:
            raise ValueError("usdc_amount must be positive")
        fee = usdc_amount * self.fees.rate(has_evidence)
        net = usdc_amount - fee
        self.fees_accrued += fee
        self.total_deposited += net

        if is_yes:
            new_reserve_yes = self.k / (self.reserve_no + net)
            tokens_out = self.reserve_yes - new_reserve_yes
            self.reserve_yes = new_reserve_yes
            self.reserve_no += net
        else:
            new_reserve_no = self.k / (self.reserve_yes + net)
            tokens_out = self.reserve_no - new_reserve_no
            self.reserve_no = new_reserve_no
            self.reserve_yes += net
        # Note: k is intentionally NOT updated post-trade — matches the
        # on-chain contract, which keeps k constant after seeding.
        return tokens_out

    def sell(self, token_amount: float, is_yes: bool) -> float:
        """Sell YES or NO tokens back to the pool and return USDC out."""
        if token_amount <= 0:
            raise ValueError("token_amount must be positive")
        if is_yes:
            new_reserve_no = self.k / (self.reserve_yes + token_amount)
            usdc_out = self.reserve_no - new_reserve_no
            self.reserve_yes += token_amount
            self.reserve_no = new_reserve_no
        else:
            new_reserve_yes = self.k / (self.reserve_no + token_amount)
            usdc_out = self.reserve_yes - new_reserve_yes
            self.reserve_no += token_amount
            self.reserve_yes = new_reserve_yes
        if usdc_out <= 0:
            raise ValueError("insufficient liquidity")
        self.total_deposited -= usdc_out
        return usdc_out

    # ------------------------------------------------------------------
    # Quote helpers (no state change)
    # ------------------------------------------------------------------
    def quote_buy(self, usdc_amount: float, is_yes: bool, has_evidence: bool = False) -> float:
        net = usdc_amount * (1.0 - self.fees.rate(has_evidence))
        if is_yes:
            return self.reserve_yes - self.k / (self.reserve_no + net)
        return self.reserve_no - self.k / (self.reserve_yes + net)

    def quote_sell(self, token_amount: float, is_yes: bool) -> float:
        if is_yes:
            return self.reserve_no - self.k / (self.reserve_yes + token_amount)
        return self.reserve_yes - self.k / (self.reserve_no + token_amount)
