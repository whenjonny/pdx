"""Contract interaction layer for PDX smart contracts."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from web3 import Web3
from web3.exceptions import ContractLogicError

from pdx_sdk.config import DEFAULT_ABI_DIR, MAX_UINT256
from pdx_sdk.types import Evidence, Market, TradeResult

logger = logging.getLogger(__name__)


def _load_abi(abi_dir: str, filename: str) -> list:
    """Load an ABI JSON file from *abi_dir*."""
    path = Path(abi_dir) / filename
    if not path.exists():
        raise FileNotFoundError(f"ABI file not found: {path}")
    with open(path) as f:
        return json.load(f)


class ContractManager:
    """Wraps PDXMarket, MockUSDC, and OutcomeToken contracts."""

    def __init__(
        self,
        w3: Web3,
        market_address: str,
        usdc_address: str,
        private_key: str,
        abi_dir: Optional[str] = None,
    ) -> None:
        self.w3 = w3
        self.private_key = private_key
        self.account = w3.eth.account.from_key(private_key)
        self.address = self.account.address

        abi_dir = abi_dir or DEFAULT_ABI_DIR

        market_abi = _load_abi(abi_dir, "PDXMarket.json")
        usdc_abi = _load_abi(abi_dir, "MockUSDC.json")
        self._outcome_abi = _load_abi(abi_dir, "OutcomeToken.json")

        self.market_contract = w3.eth.contract(
            address=Web3.to_checksum_address(market_address),
            abi=market_abi,
        )
        self.usdc_contract = w3.eth.contract(
            address=Web3.to_checksum_address(usdc_address),
            abi=usdc_abi,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_and_send(self, fn) -> dict:
        """Build a transaction from a contract function call, sign, send,
        and wait for the receipt.  Returns the receipt dict."""
        tx = fn.build_transaction(
            {
                "from": self.address,
                "nonce": self.w3.eth.get_transaction_count(self.address),
                "gas": 500_000,
                "gasPrice": self.w3.eth.gas_price,
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def _receipt_to_trade_result(self, receipt, tokens_amount: int = 0, fee: int = 0) -> TradeResult:
        return TradeResult(
            tx_hash=receipt["transactionHash"].hex(),
            tokens_amount=tokens_amount,
            fee=fee,
            gas_used=receipt["gasUsed"],
        )

    def _outcome_contract(self, token_address: str):
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=self._outcome_abi,
        )

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def get_market(self, market_id: int) -> Market:
        """Fetch full on-chain market struct plus computed prices."""
        m = self.market_contract.functions.markets(market_id).call()
        price_yes = self.market_contract.functions.getPriceYes(market_id).call()
        price_no = self.market_contract.functions.getPriceNo(market_id).call()

        # markets() returns tuple in order defined in ABI:
        # question, polymarketConditionId, reserveYes, reserveNo, k,
        # deadline, lockTime, totalDeposited, feesAccrued, resolved,
        # outcome, creator, yesToken, noToken
        return Market(
            id=market_id,
            question=m[0],
            reserveYes=m[2],
            reserveNo=m[3],
            k=m[4],
            deadline=m[5],
            lockTime=m[6],
            totalDeposited=m[7],
            feesAccrued=m[8],
            resolved=m[9],
            outcome=m[10],
            creator=m[11],
            yesToken=m[12],
            noToken=m[13],
            priceYes=price_yes,
            priceNo=price_no,
        )

    def get_price_yes(self, market_id: int) -> int:
        return self.market_contract.functions.getPriceYes(market_id).call()

    def get_price_no(self, market_id: int) -> int:
        return self.market_contract.functions.getPriceNo(market_id).call()

    def get_evidence_count(self, market_id: int) -> int:
        return self.market_contract.functions.getEvidenceCount(market_id).call()

    def get_evidence(self, market_id: int, index: int) -> Evidence:
        result = self.market_contract.functions.getEvidence(market_id, index).call()
        # returns (submitter, ipfsHash_bytes32, summary, timestamp)
        return Evidence(
            submitter=result[0],
            ipfsHash=result[1].hex(),
            summary=result[2],
            timestamp=result[3],
        )

    def get_market_tokens(self, market_id: int) -> tuple[str, str]:
        """Return (yesToken, noToken) addresses."""
        result = self.market_contract.functions.getMarketTokens(market_id).call()
        return (result[0], result[1])

    def get_next_market_id(self) -> int:
        return self.market_contract.functions.nextMarketId().call()

    # ------------------------------------------------------------------
    # Write methods — trading
    # ------------------------------------------------------------------

    def buy_yes(self, market_id: int, usdc_amount: int) -> TradeResult:
        """Buy YES tokens with *usdc_amount* (6-decimal USDC)."""
        fn = self.market_contract.functions.buyYes(market_id, usdc_amount)
        receipt = self._build_and_send(fn)

        # Parse Trade event for tokens_amount and fee
        tokens_amount = 0
        fee = 0
        trade_events = self.market_contract.events.Trade().process_receipt(receipt)
        if trade_events:
            evt = trade_events[0]["args"]
            tokens_amount = evt.get("tokensOut", 0)
            fee = evt.get("fee", 0)

        return self._receipt_to_trade_result(receipt, tokens_amount, fee)

    def buy_no(self, market_id: int, usdc_amount: int) -> TradeResult:
        """Buy NO tokens with *usdc_amount* (6-decimal USDC)."""
        fn = self.market_contract.functions.buyNo(market_id, usdc_amount)
        receipt = self._build_and_send(fn)

        tokens_amount = 0
        fee = 0
        trade_events = self.market_contract.events.Trade().process_receipt(receipt)
        if trade_events:
            evt = trade_events[0]["args"]
            tokens_amount = evt.get("tokensOut", 0)
            fee = evt.get("fee", 0)

        return self._receipt_to_trade_result(receipt, tokens_amount, fee)

    def sell(self, market_id: int, is_yes: bool, token_amount: int) -> TradeResult:
        """Sell outcome tokens back to the AMM."""
        # The agent must first approve the market contract to spend outcome tokens.
        market_data = self.get_market(market_id)
        token_addr = market_data.yesToken if is_yes else market_data.noToken
        outcome = self._outcome_contract(token_addr)
        approve_fn = outcome.functions.approve(
            self.market_contract.address, token_amount
        )
        self._build_and_send(approve_fn)

        fn = self.market_contract.functions.sell(market_id, is_yes, token_amount)
        receipt = self._build_and_send(fn)

        tokens_amount = 0
        sold_events = self.market_contract.events.Sold().process_receipt(receipt)
        if sold_events:
            evt = sold_events[0]["args"]
            tokens_amount = evt.get("usdcOut", 0)

        return self._receipt_to_trade_result(receipt, tokens_amount)

    def submit_evidence(self, market_id: int, ipfs_hash: str, summary: str) -> TradeResult:
        """Submit evidence for a market. *ipfs_hash* should be a hex string
        (64 chars) that will be converted to bytes32."""
        if ipfs_hash.startswith("0x"):
            ipfs_hash = ipfs_hash[2:]
        ipfs_bytes = bytes.fromhex(ipfs_hash.ljust(64, "0"))

        fn = self.market_contract.functions.submitEvidence(
            market_id, ipfs_bytes, summary
        )
        receipt = self._build_and_send(fn)
        return self._receipt_to_trade_result(receipt)

    def redeem(self, market_id: int) -> TradeResult:
        """Redeem winning tokens after market settlement."""
        fn = self.market_contract.functions.redeem(market_id)
        receipt = self._build_and_send(fn)

        tokens_amount = 0
        redeemed_events = self.market_contract.events.Redeemed().process_receipt(receipt)
        if redeemed_events:
            evt = redeemed_events[0]["args"]
            tokens_amount = evt.get("amount", 0)

        return self._receipt_to_trade_result(receipt, tokens_amount)

    # ------------------------------------------------------------------
    # USDC helpers
    # ------------------------------------------------------------------

    def approve_usdc(self, spender: str, amount: int = MAX_UINT256) -> str:
        """Approve *spender* to transfer USDC on behalf of the agent."""
        fn = self.usdc_contract.functions.approve(
            Web3.to_checksum_address(spender), amount
        )
        receipt = self._build_and_send(fn)
        return receipt["transactionHash"].hex()

    def mint_usdc(self, to: str, amount: int) -> str:
        """Mint mock USDC to *to* address (test-only)."""
        fn = self.usdc_contract.functions.mint(
            Web3.to_checksum_address(to), amount
        )
        receipt = self._build_and_send(fn)
        return receipt["transactionHash"].hex()

    def get_usdc_balance(self, address: Optional[str] = None) -> int:
        """Return USDC balance for *address* (defaults to agent address)."""
        addr = Web3.to_checksum_address(address or self.address)
        return self.usdc_contract.functions.balanceOf(addr).call()

    def get_outcome_balance(self, token_address: str, address: Optional[str] = None) -> int:
        """Return outcome token balance."""
        addr = Web3.to_checksum_address(address or self.address)
        contract = self._outcome_contract(token_address)
        return contract.functions.balanceOf(addr).call()
