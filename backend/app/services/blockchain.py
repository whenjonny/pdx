import time
from web3 import Web3
from eth_account import Account
from app.config import settings
from app.utils.abi_loader import load_abi
from app.models.schemas import MarketResponse, EvidenceResponse


class BlockchainService:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        self._market_contract = None
        self._usdc_contract = None
        self._oracle_contract = None
        self._account = None

    @property
    def account(self):
        if self._account is None and settings.deployer_private_key:
            self._account = Account.from_key(settings.deployer_private_key)
        return self._account

    @property
    def is_connected(self) -> bool:
        try:
            return self.w3.is_connected()
        except Exception:
            return False

    @property
    def market_contract(self):
        if self._market_contract is None and settings.pdx_market_address:
            abi = load_abi("PDXMarket")
            self._market_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.pdx_market_address),
                abi=abi,
            )
        return self._market_contract

    @property
    def usdc_contract(self):
        if self._usdc_contract is None and settings.mock_usdc_address:
            abi = load_abi("MockUSDC")
            self._usdc_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.mock_usdc_address),
                abi=abi,
            )
        return self._usdc_contract

    @property
    def oracle_contract(self):
        if self._oracle_contract is None and settings.pdx_oracle_address:
            abi = load_abi("PDXOracle")
            self._oracle_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.pdx_oracle_address),
                abi=abi,
            )
        return self._oracle_contract

    def _send_tx(self, func) -> str:
        """Build, sign, and send a contract transaction. Returns tx hash hex."""
        account = self.account
        tx = func.build_transaction({
            "from": account.address,
            "nonce": self.w3.eth.get_transaction_count(account.address),
            "gas": 3_000_000,
            "gasPrice": self.w3.eth.gas_price,
            "chainId": settings.chain_id,
        })
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        return tx_hash.hex()

    def create_market(self, question: str, deadline_days: int, initial_liquidity_usdc: float) -> dict:
        """Approve USDC, then create a new prediction market."""
        liquidity_raw = int(initial_liquidity_usdc * 1e6)
        deadline = int(time.time()) + deadline_days * 86400

        # Mint USDC to deployer if needed
        balance = self.usdc_contract.functions.balanceOf(self.account.address).call()
        if balance < liquidity_raw:
            mint_amount = liquidity_raw - balance + int(1000 * 1e6)  # extra buffer
            self._send_tx(
                self.usdc_contract.functions.mint(self.account.address, mint_amount)
            )

        # Approve market contract to spend USDC
        self._send_tx(
            self.usdc_contract.functions.approve(
                Web3.to_checksum_address(settings.pdx_market_address),
                2**256 - 1,
            )
        )

        # Create market
        func = self.market_contract.functions.createMarket(
            question,
            b"\x00" * 32,  # no polymarket link
            deadline,
            liquidity_raw,
        )
        tx = func.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 5_000_000,
            "gasPrice": self.w3.eth.gas_price,
            "chainId": settings.chain_id,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)

        # Parse MarketCreated event to get market ID
        logs = self.market_contract.events.MarketCreated().process_receipt(receipt)
        market_id = logs[0]["args"]["marketId"] if logs else self.get_market_count() - 1

        return {
            "market_id": market_id,
            "question": question,
            "deadline": deadline,
            "initial_liquidity": str(liquidity_raw),
            "tx_hash": tx_hash.hex(),
        }

    def mint_usdc(self, to: str, amount_usdc: float) -> dict:
        """Mint MockUSDC to an address."""
        raw = int(amount_usdc * 1e6)
        tx_hash = self._send_tx(
            self.usdc_contract.functions.mint(
                Web3.to_checksum_address(to), raw
            )
        )
        return {"to": to, "amount": str(raw), "tx_hash": tx_hash}

    def settle_market(self, market_id: int, outcome: bool) -> dict:
        """Settle a market via the Oracle contract."""
        if self.oracle_contract:
            tx_hash = self._send_tx(
                self.oracle_contract.functions.settleMarket(market_id, outcome)
            )
        else:
            # Fallback: call settle directly on market (if deployer is oracle)
            tx_hash = self._send_tx(
                self.market_contract.functions.settle(market_id, outcome)
            )
        return {"market_id": market_id, "outcome": outcome, "tx_hash": tx_hash}

    def get_market_count(self) -> int:
        if not self.market_contract:
            return 0
        return self.market_contract.functions.nextMarketId().call()

    def get_market(self, market_id: int) -> MarketResponse | None:
        if not self.market_contract:
            return None
        try:
            m = self.market_contract.functions.markets(market_id).call()
            price_yes = self.market_contract.functions.getPriceYes(market_id).call()
            price_no = self.market_contract.functions.getPriceNo(market_id).call()
            tokens = self.market_contract.functions.getMarketTokens(market_id).call()

            return MarketResponse(
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
                yesToken=tokens[0],
                noToken=tokens[1],
                priceYes=price_yes / 1e6,
                priceNo=price_no / 1e6,
            )
        except Exception:
            return None

    def list_markets(self) -> list[MarketResponse]:
        count = self.get_market_count()
        markets = []
        for i in range(count):
            m = self.get_market(i)
            if m:
                markets.append(m)
        return markets

    def get_evidence_list(self, market_id: int) -> list[EvidenceResponse]:
        if not self.market_contract:
            return []
        try:
            count = self.market_contract.functions.getEvidenceCount(market_id).call()
            evidence = []
            for i in range(count):
                e = self.market_contract.functions.getEvidence(market_id, i).call()
                evidence.append(
                    EvidenceResponse(
                        submitter=e[0],
                        ipfsHash="0x" + e[1].hex(),
                        summary=e[2],
                        timestamp=e[3],
                    )
                )
            return evidence
        except Exception:
            return []


blockchain_service = BlockchainService()
