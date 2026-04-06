export interface Market {
  id: number;
  question: string;
  conditionId: string;
  reserveYes: bigint;
  reserveNo: bigint;
  k: bigint;
  deadline: number;
  lockTime: number;
  totalDeposited: bigint;
  feesAccrued: bigint;
  resolved: boolean;
  outcome: boolean;
  creator: string;
  yesToken: string;
  noToken: string;
  priceYes: number;
  priceNo: number;
  evidenceCount: number;
}

export interface MarketFromAPI {
  id: number;
  question: string;
  condition_id: string;
  reserve_yes: string;
  reserve_no: string;
  k: string;
  deadline: number;
  lock_time: number;
  total_deposited: string;
  fees_accrued: string;
  resolved: boolean;
  outcome: boolean;
  creator: string;
  yes_token: string;
  no_token: string;
  price_yes: number;
  price_no: number;
  evidence_count: number;
}

export interface Evidence {
  submitter: string;
  ipfs_hash: string;
  summary: string;
  timestamp: number;
}

export interface Prediction {
  market_id: number;
  probability_yes: number;
  probability_no: number;
  confidence: number;
  reasoning: string;
  source: string;
}

export interface TradeEstimate {
  tokensOut: bigint;
  fee: bigint;
  feeRate: number;
  priceImpact: number;
}
