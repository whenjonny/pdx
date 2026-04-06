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


class CreateMarketRequest(BaseModel):
    question: str
    initial_liquidity: float = 10000.0  # USDC amount
    deadline_days: int = 30  # days from now


class CreateMarketResponse(BaseModel):
    market_id: int
    question: str
    deadline: int
    initial_liquidity: str
    tx_hash: str


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
