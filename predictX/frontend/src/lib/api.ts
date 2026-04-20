import type { MarketFromAPI, Evidence, Prediction, UserPosition, UserTransaction, UserSummary, MarketTrade } from '../types/market';

const BASE = '/api';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function fetchMarkets(params?: {
  category?: string;
  sort?: string;
  search?: string;
  status?: string;
  page?: number;
  limit?: number;
}): Promise<MarketFromAPI[]> {
  const query = new URLSearchParams();
  if (params?.category) query.set('category', params.category);
  if (params?.sort) query.set('sort', params.sort);
  if (params?.search) query.set('search', params.search);
  if (params?.status) query.set('status', params.status);
  if (params?.page) query.set('page', String(params.page));
  if (params?.limit) query.set('limit', String(params.limit));
  const qs = query.toString();
  return get<MarketFromAPI[]>(`/markets${qs ? '?' + qs : ''}`);
}

export interface PlatformStats {
  total_markets: number;
  active_markets: number;
  total_volume: string;
  total_evidence: number;
}

export async function fetchPlatformStats(): Promise<PlatformStats> {
  return get<PlatformStats>('/stats');
}

export async function fetchMarket(id: number): Promise<MarketFromAPI> {
  return get<MarketFromAPI>(`/markets/${id}`);
}

export async function fetchEvidence(marketId: number): Promise<Evidence[]> {
  return get<Evidence[]>(`/evidence/${marketId}`);
}

export async function fetchPrediction(marketId: number): Promise<Prediction> {
  return get<Prediction>(`/predictions/${marketId}`);
}

export async function createMarket(data: {
  question: string;
  initial_liquidity: number;
  deadline_days: number;
  category: string;
  resolution_source: string;
}): Promise<{ market_id: number; question: string; deadline: number; initial_liquidity: string; tx_hash: string }> {
  return post('/markets', data);
}

export async function setMarketMetadata(marketId: number, category: string, resolutionSource: string = ''): Promise<void> {
  const res = await fetch(`${BASE}/markets/${marketId}/metadata`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, resolution_source: resolutionSource }),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
}

export async function fetchMarketTrades(marketId: number, limit: number = 50): Promise<MarketTrade[]> {
  return get<MarketTrade[]>(`/markets/${marketId}/trades?limit=${limit}`);
}

export async function uploadEvidence(data: {
  market_id: number;
  title: string;
  content: string;
  source_url?: string;
  direction: string;
}): Promise<{ evidenceHash: string; cid: string }> {
  return post('/evidence/upload', data);
}

export async function fetchUserPositions(address: string): Promise<UserPosition[]> {
  return get<UserPosition[]>(`/users/${address}/positions`);
}

export async function fetchUserTransactions(address: string): Promise<UserTransaction[]> {
  return get<UserTransaction[]>(`/users/${address}/transactions`);
}

export async function fetchUserSummary(address: string): Promise<UserSummary> {
  return get<UserSummary>(`/users/${address}/summary`);
}
