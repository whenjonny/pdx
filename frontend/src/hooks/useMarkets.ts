import { useQuery } from '@tanstack/react-query';
import { fetchMarkets, fetchMarket, fetchPlatformStats } from '../lib/api';

export function useMarkets(params?: {
  category?: string;
  sort?: string;
  search?: string;
  status?: string;
}) {
  return useQuery({
    queryKey: ['markets', params],
    queryFn: () => fetchMarkets(params),
    refetchInterval: 10_000,
  });
}

export function useMarket(id: number) {
  return useQuery({
    queryKey: ['market', id],
    queryFn: () => fetchMarket(id),
    refetchInterval: 5_000,
    enabled: id >= 0,
  });
}

export function usePlatformStats() {
  return useQuery({
    queryKey: ['platform-stats'],
    queryFn: fetchPlatformStats,
    refetchInterval: 30_000,
  });
}
