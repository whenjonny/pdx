from web3 import Web3
from app.config import settings
from app.utils.abi_loader import load_abi
from app.models.schemas import MarketResponse, EvidenceResponse


class BlockchainService:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        self._market_contract = None
        self._usdc_contract = None

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
