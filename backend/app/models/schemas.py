from pydantic import BaseModel


class MarketResponse(BaseModel):
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
    priceYes: float  # 0.0 to 1.0
    priceNo: float
    evidenceCount: int = 0
    category: str = "general"


class MarketTrade(BaseModel):
    type: str  # "buy_yes", "buy_no", "sell_yes", "sell_no"
    trader: str  # address
    usdc_amount: str
    token_amount: str
    fee: str  # only for buys, "0" for sells
    timestamp: int
    tx_hash: str
    block_number: int


class PlatformStats(BaseModel):
    total_markets: int
    active_markets: int
    total_volume: str  # sum of all totalDeposited
    total_evidence: int  # sum of all evidenceCount


class EvidenceResponse(BaseModel):
    submitter: str
    ipfsHash: str
    summary: str
    timestamp: int


class EvidenceUploadRequest(BaseModel):
    market_id: int
    title: str
    content: str
    source_url: str = ""
    direction: str = "YES"  # "YES" or "NO"


class EvidenceUploadResponse(BaseModel):
    cid: str
    evidenceHash: str  # bytes32 hex


class PredictionResponse(BaseModel):
    market_id: int = 0
    probability_yes: float
    probability_no: float
    confidence: float  # 0.0 - 1.0
    reasoning: str
    source: str
    amm_price_yes: float = 0.0
    updated_at: int = 0


class CreateMarketRequest(BaseModel):
    question: str
    initial_liquidity: float = 10000.0  # USDC amount
    deadline_days: int = 30  # days from now
    category: str = "general"
    resolution_source: str = ""


class CreateMarketResponse(BaseModel):
    market_id: int
    question: str
    deadline: int
    initial_liquidity: str
    tx_hash: str


class SetMarketMetadataRequest(BaseModel):
    category: str = "general"
    resolution_source: str = ""


class MintUSDCRequest(BaseModel):
    to: str  # address
    amount: float = 10000.0  # USDC


class MintUSDCResponse(BaseModel):
    to: str
    amount: str
    tx_hash: str


class SettleMarketRequest(BaseModel):
    market_id: int
    outcome: bool  # true = YES wins, false = NO wins


class SettleMarketResponse(BaseModel):
    market_id: int
    outcome: bool
    tx_hash: str


class HealthResponse(BaseModel):
    status: str
    chain_connected: bool
    market_address: str


class UserPosition(BaseModel):
    market_id: int
    question: str
    yes_balance: str  # raw token amount as string
    no_balance: str
    current_price_yes: float
    current_price_no: float
    market_resolved: bool
    market_outcome: bool
    current_value_usdc: str  # estimated USDC value


class UserTransaction(BaseModel):
    type: str  # "buy_yes", "buy_no", "sell", "redeem", "create_market", "submit_evidence"
    market_id: int
    timestamp: int  # block timestamp
    block_number: int
    tx_hash: str
    details: dict  # type-specific details (amount, tokens, fee, etc.)


class UserSummary(BaseModel):
    address: str
    active_positions: int
    markets_created: int
    evidence_submitted: int
    total_value_usdc: str  # sum of all position values
