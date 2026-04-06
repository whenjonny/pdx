import type { MarketFromAPI, Evidence, Prediction } from '../types/market';

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

export async function fetchMarkets(): Promise<MarketFromAPI[]> {
  return get<MarketFromAPI[]>('/markets');
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

export async function uploadEvidence(data: {
  market_id: number;
  title: string;
  content: string;
  source_url?: string;
}): Promise<{ ipfs_hash: string; cid: string }> {
  return post('/evidence/upload', data);
}
