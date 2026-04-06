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
  reserveYes: string;
  reserveNo: string;
  k: string;
  deadline: number;
  lockTime: number;
  totalDeposited: string;
  feesAccrued: string;
  resolved: boolean;
  outcome: boolean;
  creator: string;
  yesToken: string;
  noToken: string;
  priceYes: number;
  priceNo: number;
  evidenceCount: number;
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

export interface UserPosition {
  market_id: number;
  question: string;
  yes_balance: string;
  no_balance: string;
  current_price_yes: number;
  current_price_no: number;
  market_resolved: boolean;
  market_outcome: boolean;
  current_value_usdc: string;
}

export interface UserTransaction {
  type: 'buy_yes' | 'buy_no' | 'sell' | 'redeem' | 'create_market' | 'submit_evidence';
  market_id: number;
  timestamp: number;
  block_number: number;
  tx_hash: string;
  details: Record<string, string | number | boolean>;
}

export interface UserSummary {
  address: string;
  active_positions: number;
  markets_created: number;
  evidence_submitted: number;
  total_value_usdc: string;
}

export interface MarketTrade {
  type: 'buy_yes' | 'buy_no' | 'sell_yes' | 'sell_no';
  trader: string;
  usdc_amount: string;
  token_amount: string;
  fee: string;
  timestamp: number;
  tx_hash: string;
  block_number: number;
}
