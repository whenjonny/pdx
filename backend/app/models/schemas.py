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


class EvidenceResponse(BaseModel):
    submitter: str
    ipfsHash: str
    summary: str
    timestamp: int


class EvidenceUploadRequest(BaseModel):
    marketId: int
    direction: str  # "YES" or "NO"
    confidence: float
    sources: list[dict] = []
    analysis: str = ""


class EvidenceUploadResponse(BaseModel):
    cid: str
    evidenceHash: str  # bytes32 hex


class PredictionResponse(BaseModel):
    probability: float
    confidence: str  # "HIGH", "MEDIUM", "LOW"
    reasoning: str
    lastUpdated: str


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
