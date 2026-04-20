"""PDXClient -- main entry-point for the PDX Agent SDK."""

from __future__ import annotations

import logging
from typing import Optional

import requests
from web3 import Web3

from pdx_sdk.compute import compute_embedding, run_monte_carlo
from pdx_sdk.config import DEFAULT_ABI_DIR, DEFAULT_BACKEND_URL, MAX_UINT256
from pdx_sdk.contracts import ContractManager
from pdx_sdk.types import Evidence, Market, MonteCarloResult, Prediction, TradeResult

logger = logging.getLogger(__name__)


class PDXClient:
    """High-level client that composes contract interaction, evidence
    helpers, and local compute into a single convenient interface.

    Parameters
    ----------
    rpc_url : str
        JSON-RPC endpoint (e.g. ``http://localhost:8545``).
    private_key : str
        Hex-encoded private key used for signing transactions.
    market_address : str
        Deployed ``PDXMarket`` contract address.
    usdc_address : str
        Deployed ``MockUSDC`` contract address.
    backend_url : str
        PDX backend API base URL (used for predictions & evidence upload).
    abi_dir : str | None
        Path to directory containing ABI JSON files.  Defaults to
        ``<sdk>/../contracts/abi/``.
    """

    def __init__(
        self,
        rpc_url: str,
        private_key: str,
        market_address: str,
        usdc_address: str,
        backend_url: str = DEFAULT_BACKEND_URL,
        abi_dir: Optional[str] = None,
    ) -> None:
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            logger.warning("Web3 provider at %s is not connected", rpc_url)

        self.backend_url = backend_url
        self._contracts = ContractManager(
            w3=self.w3,
            market_address=market_address,
            usdc_address=usdc_address,
            private_key=private_key,
            abi_dir=abi_dir or DEFAULT_ABI_DIR,
        )

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def address(self) -> str:
        """The agent's Ethereum address derived from the private key."""
        return self._contracts.address

    @property
    def market_address(self) -> str:
        return self._contracts.market_contract.address

    # ------------------------------------------------------------------
    # Market reading
    # ------------------------------------------------------------------

    def get_market(self, market_id: int) -> Market:
        """Fetch the full on-chain state of a market."""
        return self._contracts.get_market(market_id)

    def list_markets(self) -> list[Market]:
        """Return all markets by iterating from 0 to ``nextMarketId``."""
        count = self._contracts.get_next_market_id()
        markets: list[Market] = []
        for i in range(count):
            try:
                markets.append(self._contracts.get_market(i))
            except Exception as exc:
                logger.warning("Failed to load market %d: %s", i, exc)
        return markets

    # ------------------------------------------------------------------
    # Trading
    # ------------------------------------------------------------------

    def buy_yes(self, market_id: int, usdc_amount: int) -> TradeResult:
        """Buy YES tokens on *market_id* spending *usdc_amount* (6 decimals)."""
        return self._contracts.buy_yes(market_id, usdc_amount)

    def buy_no(self, market_id: int, usdc_amount: int) -> TradeResult:
        """Buy NO tokens on *market_id* spending *usdc_amount* (6 decimals)."""
        return self._contracts.buy_no(market_id, usdc_amount)

    def sell(self, market_id: int, is_yes: bool, token_amount: int) -> TradeResult:
        """Sell *token_amount* outcome tokens back to the AMM."""
        return self._contracts.sell(market_id, is_yes, token_amount)

    def redeem(self, market_id: int) -> TradeResult:
        """Redeem winning tokens after market settlement."""
        return self._contracts.redeem(market_id)

    # ------------------------------------------------------------------
    # USDC helpers
    # ------------------------------------------------------------------

    def mint_usdc(self, amount: int) -> str:
        """Mint *amount* mock USDC to the agent address.  Returns tx hash."""
        return self._contracts.mint_usdc(self.address, amount)

    def approve_usdc(self, amount: Optional[int] = None) -> str:
        """Approve the PDXMarket contract to spend agent USDC.

        Defaults to max uint256 (unlimited) if *amount* is ``None``.
        Returns the tx hash.
        """
        if amount is None:
            amount = MAX_UINT256
        return self._contracts.approve_usdc(self.market_address, amount)

    def get_usdc_balance(self) -> int:
        """Return the agent's USDC balance (6-decimal integer)."""
        return self._contracts.get_usdc_balance()

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    def submit_evidence(self, market_id: int, ipfs_hash: str, summary: str) -> TradeResult:
        """Submit evidence on-chain for a market."""
        return self._contracts.submit_evidence(market_id, ipfs_hash, summary)

    def get_evidence(self, market_id: int) -> list[Evidence]:
        """Fetch all evidence records for a market."""
        count = self._contracts.get_evidence_count(market_id)
        evidence: list[Evidence] = []
        for i in range(count):
            evidence.append(self._contracts.get_evidence(market_id, i))
        return evidence

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    def compute_embedding(self, text: str) -> list[float]:
        """Compute a 384-dim embedding for *text*."""
        return compute_embedding(text)

    def run_monte_carlo(
        self,
        prior_yes: float,
        evidence_scores: Optional[list[float]] = None,
        weights: Optional[list[float]] = None,
        n_sim: int = 5_000,
    ) -> MonteCarloResult:
        """Run a Monte Carlo simulation to estimate outcome probability."""
        return run_monte_carlo(prior_yes, evidence_scores, weights, n_sim)

    # ------------------------------------------------------------------
    # Prediction (from backend)
    # ------------------------------------------------------------------

    def get_prediction(self, market_id: int) -> Prediction:
        """Fetch the latest agent prediction from the PDX backend API.

        Endpoint: ``GET <backend>/api/predictions/<market_id>``
        """
        url = f"{self.backend_url.rstrip('/')}/api/predictions/{market_id}"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return Prediction(
                probability=data.get("probability", 0.0),
                confidence=data.get("confidence", 0.0),
                reasoning=data.get("reasoning", ""),
                lastUpdated=data.get("lastUpdated"),
            )
        except requests.RequestException as exc:
            logger.error("Failed to fetch prediction for market %d: %s", market_id, exc)
            raise
